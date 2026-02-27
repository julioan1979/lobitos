from __future__ import annotations

import pandas as pd
import streamlit as st
from pyairtable import Api

from airtable_config import context_labels, get_tombola_credentials
from menu import menu_with_redirect
from tombola_utils import (
    ajustar_stock_item,
    criar_movimento,
    encontrar_item_por_nome,
    normalizar_nome_item,
    registrar_entrada,
    transferir_item_caixa,
)


st.set_page_config(page_title="Guarda Material - Tômbola", page_icon="🎁", layout="wide")
menu_with_redirect()

secao_info = context_labels()
if secao_info:
    st.caption(secao_info)

role = st.session_state.get("role")
if role == "pais":
    st.error("Esta área não está disponível para perfis de Pais.")
    st.stop()

if role not in {"admin", "tesoureiro"}:
    st.error("Esta área está disponível apenas para Admin e Tesoureiro.")
    st.stop()

try:
    AIRTABLE_TOKEN, BASE_ID = get_tombola_credentials()
except RuntimeError as exc:
    st.error(str(exc))
    st.info("Defina TOMBOLA_AIRTABLE_BASE_ID (e opcionalmente TOMBOLA_AIRTABLE_TOKEN) nos secrets da secção.")
    st.stop()

api = Api(AIRTABLE_TOKEN)
executado_por = st.session_state.get("user", {}).get("email", "utilizador")


def _table_df(nome_tabela: str) -> pd.DataFrame:
    try:
        registos = api.table(BASE_ID, nome_tabela).all()
    except Exception as exc:
        st.warning(f"Não foi possível carregar a tabela '{nome_tabela}': {exc}")
        return pd.DataFrame()
    return pd.DataFrame([{"id": r["id"], **r.get("fields", {})} for r in registos])


def _safe_int(valor) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return 0


def _ensure_patrocinador_id(nome: str) -> str | None:
    nome = (nome or "").strip()
    if not nome:
        return None
    tabela = api.table(BASE_ID, "Patrocinadores")
    try:
        registos = tabela.all()
    except Exception:
        return None
    for reg in registos:
        if normalizar_nome_item(reg.get("fields", {}).get("Nome")) == normalizar_nome_item(nome):
            return reg["id"]
    novo = tabela.create({"Nome": nome})
    return novo.get("id")


def _processar_patrocinio(registo: dict, inventario_registos: list[dict]) -> None:
    campos = registo.get("fields", {})
    descricao = str(campos.get("DescricaoItem") or "").strip()
    quantidade = _safe_int(campos.get("Quantidade"))
    if not descricao or quantidade <= 0:
        raise ValueError("Registo inválido: DescricaoItem e Quantidade > 0 são obrigatórios.")

    tabela_inventario = api.table(BASE_ID, "Inventario")
    item_existente = encontrar_item_por_nome(inventario_registos, descricao)

    caixa_sugerida = campos.get("CaixaSugerida")
    caixa_sugerida_id = caixa_sugerida[0] if isinstance(caixa_sugerida, list) and caixa_sugerida else None
    categoria = campos.get("Categoria")
    patrocinador_id = _ensure_patrocinador_id(str(campos.get("PatrocinadorNome") or ""))
    evento = campos.get("Evento")
    evento_id = evento[0] if isinstance(evento, list) and evento else None

    if item_existente:
        item_id = item_existente["id"]
        registrar_entrada(
            api,
            BASE_ID,
            item_id=item_id,
            quantidade=quantidade,
            executado_por=executado_por,
            evento_id=evento_id,
            caixa_destino_id=caixa_sugerida_id,
            patrocinador_id=patrocinador_id,
            origem_entrada="Patrocínio",
            notas=str(campos.get("Observacoes") or "").strip(),
        )
    else:
        campos_novo = {
            "NomeItem": descricao,
            "QuantidadeAtual": quantidade,
            "Estado": "Disponível",
            "Ativo": True,
        }
        if categoria:
            campos_novo["Categoria"] = categoria
        if caixa_sugerida_id:
            campos_novo["CaixaAtual"] = [caixa_sugerida_id]
        novo = tabela_inventario.create(campos_novo)
        item_id = novo["id"]
        criar_movimento(
            api,
            BASE_ID,
            tipo="Entrada",
            item_id=item_id,
            quantidade=quantidade,
            executado_por=executado_por,
            evento_id=evento_id,
            caixa_destino_id=caixa_sugerida_id,
            origem_entrada="Patrocínio",
            patrocinador_id=patrocinador_id,
            notas=str(campos.get("Observacoes") or "").strip(),
        )

    api.table(BASE_ID, "RegistoPatrocinios").update(registo["id"], {"Processado": True, "Estado": "Recebido"})


st.title("🎁 Guarda Material - Tômbola")
aba_dashboard, aba_inventario, aba_patrocinios, aba_eventos, aba_caixas = st.tabs(
    ["Dashboard", "Inventário", "Patrocínios", "Eventos", "Caixas"]
)

with aba_dashboard:
    df_inv = _table_df("Inventario")
    df_caixas = _table_df("Caixas")
    total_itens = len(df_inv.index)
    stock_total = pd.to_numeric(df_inv.get("QuantidadeAtual"), errors="coerce").fillna(0).sum() if not df_inv.empty else 0
    baixo_stock = 0
    if not df_inv.empty and "QuantidadeAtual" in df_inv.columns:
        baixo_stock = int((pd.to_numeric(df_inv["QuantidadeAtual"], errors="coerce").fillna(0) <= 2).sum())

    col1, col2, col3 = st.columns(3)
    col1.metric("Itens ativos", int(total_itens))
    col2.metric("Stock total", int(stock_total))
    col3.metric("Itens em baixo stock (<=2)", int(baixo_stock))

    if not df_inv.empty:
        vis = [c for c in ["NomeItem", "Categoria", "QuantidadeAtual", "Estado", "CaixaAtual"] if c in df_inv.columns]
        st.dataframe(df_inv[vis], use_container_width=True, hide_index=True)
    st.caption(f"Caixas registadas: {len(df_caixas.index)}")

with aba_inventario:
    df_inv = _table_df("Inventario")
    df_caixas = _table_df("Caixas")
    caixa_options = df_caixas["id"].tolist() if not df_caixas.empty and "id" in df_caixas.columns else []
    caixa_label = dict(zip(df_caixas.get("id", []), df_caixas.get("CodigoCaixa", []))) if not df_caixas.empty else {}

    st.subheader("Adicionar item")
    with st.form("form_add_item_tombola"):
        nome_item = st.text_input("NomeItem")
        categoria = st.text_input("Categoria")
        quantidade = st.number_input("QuantidadeAtual", min_value=1, step=1)
        caixa_id = st.selectbox("CaixaAtual", options=[None] + caixa_options, format_func=lambda v: caixa_label.get(v, "Sem caixa") if v else "Sem caixa")
        criar = st.form_submit_button("Criar item")

    if criar:
        if not nome_item.strip():
            st.error("NomeItem é obrigatório.")
        else:
            campos = {
                "NomeItem": nome_item.strip(),
                "QuantidadeAtual": int(quantidade),
                "Estado": "Disponível",
                "Ativo": True,
            }
            if categoria.strip():
                campos["Categoria"] = categoria.strip()
            if caixa_id:
                campos["CaixaAtual"] = [caixa_id]
            novo = api.table(BASE_ID, "Inventario").create(campos)
            criar_movimento(
                api,
                BASE_ID,
                tipo="Ajuste",
                item_id=novo["id"],
                quantidade=int(quantidade),
                executado_por=executado_por,
                notas="Inventário inicial",
            )
            st.success("Item criado e movimento de ajuste inicial registado.")
            st.rerun()

    if not df_inv.empty:
        item_ids = df_inv["id"].tolist()
        item_label = dict(zip(df_inv["id"], df_inv.get("NomeItem", df_inv["id"])))

        st.subheader("Ajustar stock")
        col_a, col_b, col_c = st.columns([2, 1, 2])
        item_id = col_a.selectbox("Item", options=item_ids, format_func=lambda v: item_label.get(v, v), key="inv_item_ajuste")
        delta = col_b.number_input("Delta (+/-)", value=1, step=1)
        tipo = col_c.selectbox("Tipo", options=["Entrada", "Saída", "Ajuste"])
        notas = st.text_input("Notas do movimento", key="inv_ajuste_notas")
        if st.button("Aplicar ajuste", key="btn_ajustar_stock"):
            sinal = int(delta)
            if tipo == "Saída" and sinal > 0:
                sinal = -sinal
            try:
                ajustar_stock_item(
                    api,
                    BASE_ID,
                    item_id=item_id,
                    delta=sinal,
                    executado_por=executado_por,
                    tipo_movimento=tipo,
                    notas=notas,
                )
                st.success("Stock atualizado com sucesso.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

        st.subheader("Transferir item de caixa")
        col_t1, col_t2, col_t3 = st.columns([2, 2, 1])
        item_transfer = col_t1.selectbox("Item para transferir", options=item_ids, format_func=lambda v: item_label.get(v, v), key="inv_item_transfer")
        caixa_dest = col_t2.selectbox("Caixa destino", options=caixa_options, format_func=lambda v: caixa_label.get(v, v)) if caixa_options else None
        qty_transfer = col_t3.number_input("Quantidade", min_value=1, step=1, value=1)
        notas_transfer = st.text_input("Notas da transferência", key="transfer_notas")
        if st.button("Transferir", key="btn_transferir_item"):
            if not caixa_dest:
                st.error("Crie primeiro uma caixa de destino.")
            else:
                try:
                    transferir_item_caixa(
                        api,
                        BASE_ID,
                        item_id=item_transfer,
                        caixa_destino_id=caixa_dest,
                        quantidade=int(qty_transfer),
                        executado_por=executado_por,
                        notas=notas_transfer,
                    )
                    st.success("Transferência registada.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

with aba_patrocinios:
    df_pat = _table_df("RegistoPatrocinios")
    if df_pat.empty:
        st.info("Sem registos em RegistoPatrocinios.")
    else:
        pendentes = df_pat[~df_pat.get("Processado", False).fillna(False)] if "Processado" in df_pat.columns else df_pat
        if pendentes.empty:
            st.success("Não existem patrocínios pendentes.")
        else:
            st.write("Patrocínios pendentes")
            mostrar_cols = [c for c in ["PatrocinadorNome", "DescricaoItem", "Quantidade", "Estado", "Processado"] if c in pendentes.columns]
            st.dataframe(pendentes[mostrar_cols], use_container_width=True, hide_index=True)
            registos_inv = api.table(BASE_ID, "Inventario").all()
            for _, row in pendentes.iterrows():
                reg_id = row["id"]
                label = f"Processar {row.get('DescricaoItem', reg_id)}"
                if st.button(label, key=f"proc_pat_{reg_id}"):
                    try:
                        registo = api.table(BASE_ID, "RegistoPatrocinios").get(reg_id)
                        _processar_patrocinio(registo, registos_inv)
                        st.success("Patrocínio processado com sucesso.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Erro ao processar patrocínio: {exc}")

with aba_eventos:
    st.subheader("Criar evento")
    with st.form("form_criar_evento_tombola"):
        nome = st.text_input("NomeEvento")
        tipo = st.selectbox("Tipo", ["Tômbola", "Angariação", "Feira"])
        data = st.date_input("Data")
        local = st.text_input("Local")
        estado = st.selectbox("Estado", ["Planeamento", "A decorrer", "Concluído"])
        sub = st.form_submit_button("Criar evento")
    if sub:
        if not nome.strip() or not local.strip():
            st.error("NomeEvento e Local são obrigatórios.")
        else:
            api.table(BASE_ID, "Eventos").create(
                {
                    "NomeEvento": nome.strip(),
                    "Tipo": tipo,
                    "Data": str(data),
                    "Local": local.strip(),
                    "Estado": estado,
                }
            )
            st.success("Evento criado.")
            st.rerun()

    st.subheader("Registar saída para evento")
    df_eventos = _table_df("Eventos")
    df_inv = _table_df("Inventario")
    if df_eventos.empty or df_inv.empty:
        st.info("Precisa de pelo menos 1 evento e 1 item para registar saídas.")
    else:
        evento_opts = df_eventos["id"].tolist()
        evento_label = dict(zip(df_eventos["id"], df_eventos.get("NomeEvento", df_eventos["id"])))
        item_opts = df_inv["id"].tolist()
        item_label = dict(zip(df_inv["id"], df_inv.get("NomeItem", df_inv["id"])))
        col1, col2, col3 = st.columns([2, 2, 1])
        evento_id = col1.selectbox("Evento", options=evento_opts, format_func=lambda v: evento_label.get(v, v))
        item_id = col2.selectbox("Item", options=item_opts, format_func=lambda v: item_label.get(v, v))
        qtd = col3.number_input("Quantidade", min_value=1, step=1)
        notas = st.text_input("Notas", key="saida_evento_notas")
        if st.button("Registar saída", key="btn_saida_evento"):
            try:
                ajustar_stock_item(
                    api,
                    BASE_ID,
                    item_id=item_id,
                    delta=-int(qtd),
                    executado_por=executado_por,
                    tipo_movimento="Saída",
                    evento_id=evento_id,
                    notas=notas,
                )
                st.success("Saída registada.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

with aba_caixas:
    st.subheader("Criar caixa")
    with st.form("form_criar_caixa"):
        codigo = st.text_input("CodigoCaixa")
        descricao = st.text_input("Descricao")
        local = st.text_input("Local")
        estado = st.selectbox("Estado", ["Ativa", "Arquivada"])
        criar_caixa = st.form_submit_button("Criar caixa")
    if criar_caixa:
        if not codigo.strip() or not local.strip():
            st.error("CodigoCaixa e Local são obrigatórios.")
        else:
            api.table(BASE_ID, "Caixas").create(
                {
                    "CodigoCaixa": codigo.strip(),
                    "Descricao": descricao.strip(),
                    "Local": local.strip(),
                    "Estado": estado,
                }
            )
            st.success("Caixa criada.")
            st.rerun()

    df_caixas = _table_df("Caixas")
    if not df_caixas.empty:
        cols = [c for c in ["CodigoCaixa", "Descricao", "Local", "Estado"] if c in df_caixas.columns]
        st.dataframe(df_caixas[cols], use_container_width=True, hide_index=True)
