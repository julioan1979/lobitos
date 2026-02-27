from __future__ import annotations

import pandas as pd
import streamlit as st
from pyairtable import Api

from airtable_config import context_labels, get_tombola_credentials, get_tombola_table_ref
from menu import menu_with_redirect
from tombola_schema import ensure_tombola_schema
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
    st.info("Defina TOMBOLA_AIRTABLE_BASE_ID e TOMBOLA_AIRTABLE_TOKEN nos secrets da secção.")
    st.stop()

api = Api(AIRTABLE_TOKEN)
executado_por = (st.session_state.get("user", {}).get("email") or "").strip()
if not executado_por:
    st.error("Não foi possível identificar o utilizador autenticado (email).")
    st.stop()


TABLES = {
    "INVENTARIO": get_tombola_table_ref("INVENTARIO", "Inventario"),
    "CAIXAS": get_tombola_table_ref("CAIXAS", "Caixas"),
    "PATROCINADORES": get_tombola_table_ref("PATROCINADORES", "Patrocinadores"),
    "REGISTO_PATROCINIOS": get_tombola_table_ref("REGISTO_PATROCINIOS", "RegistoPatrocinios"),
    "EVENTOS": get_tombola_table_ref("EVENTOS", "Eventos"),
    "MOVIMENTOS": get_tombola_table_ref("MOVIMENTOS", "Movimentos"),
}


def _table_ref(chave: str) -> str:
    return TABLES[chave]




def _tabelas_em_falta() -> list[str]:
    base = api.base(BASE_ID)
    tabelas = base.tables()
    disponiveis = {tbl.name for tbl in tabelas} | {tbl.id for tbl in tabelas}
    return [ref for ref in TABLES.values() if ref not in disponiveis]


def _is_schema_related_error(exc: Exception) -> bool:
    mensagem = str(exc).upper()
    marcadores = [
        "INVALID_PERMISSIONS_OR_MODEL_NOT_FOUND",
        "MODEL_NOT_FOUND",
        "UNKNOWN_TABLE",
        "TABLE NOT FOUND",
    ]
    return any(marcador in mensagem for marcador in marcadores)


def _auto_bootstrap_schema(trigger: str = "startup") -> bool:
    """Auto-corrige schema só quando detetado erro de schema/modelo."""
    chave_execucao = f"tombola_schema_bootstrap_done::{BASE_ID}::{trigger}"
    if st.session_state.get(chave_execucao):
        return False

    st.session_state[chave_execucao] = True

    try:
        resultado = ensure_tombola_schema(api, BASE_ID, TABLES)
    except Exception as exc:
        st.warning(f"Não foi possível auto-inicializar o schema da Tômbola: {exc}")
        return False

    total_criados = len(resultado["created_tables"]) + len(resultado["created_fields"])
    if total_criados > 0:
        st.info(
            "Schema da Tômbola atualizado automaticamente após erro de schema "
            f"({len(resultado['created_tables'])} tabelas e {len(resultado['created_fields'])} campos criados)."
        )

    if resultado["errors"]:
        st.warning(
            "Foram detetados problemas ao atualizar o schema automaticamente. "
            "Valide permissões do token (scope schema.bases:write) e referências TOMBOLA_TABLE_*."
        )
        for erro in resultado["errors"]:
            st.error(erro)

    try:
        faltam = _tabelas_em_falta()
    except Exception:
        return True
    if faltam:
        st.warning(
            "A base da Tômbola ainda não tem o schema mínimo completo. "
            f"Tabelas em falta: {', '.join(faltam)}."
        )
    return True


def _table_df(nome_tabela: str) -> pd.DataFrame:
    """Stock real vive no Inventário; Movimentos é auditoria e tabelas suportam contexto."""
    try:
        registos = api.table(BASE_ID, nome_tabela).all()
    except Exception as exc:
        if _is_schema_related_error(exc):
            _auto_bootstrap_schema(trigger=nome_tabela)
            try:
                registos = api.table(BASE_ID, nome_tabela).all()
            except Exception as retry_exc:
                st.warning(f"Não foi possível carregar a tabela '{nome_tabela}' após auto-correção de schema: {retry_exc}")
                return pd.DataFrame()
        else:
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
    tabela = api.table(BASE_ID, _table_ref("PATROCINADORES"))
    try:
        registos = tabela.all()
    except Exception:
        return None
    for reg in registos:
        if normalizar_nome_item(reg.get("fields", {}).get("Nome")) == normalizar_nome_item(nome):
            return reg["id"]
    novo = tabela.create({"Nome": nome})
    return novo.get("id")


def _processar_patrocinio(registo: dict) -> None:
    campos = registo.get("fields", {})
    if campos.get("Processado"):
        raise ValueError("Este patrocínio já foi processado.")

    descricao = str(campos.get("DescricaoItem") or "").strip()
    quantidade = _safe_int(campos.get("Quantidade"))
    if not descricao or quantidade <= 0:
        raise ValueError("Registo inválido: DescricaoItem e Quantidade > 0 são obrigatórios.")

    tabela_inventario = api.table(BASE_ID, _table_ref("INVENTARIO"))
    inventario_registos = tabela_inventario.all()
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

    api.table(BASE_ID, _table_ref("REGISTO_PATROCINIOS")).update(registo["id"], {"Processado": True, "Estado": "Recebido"})


st.title("🎁 Guarda Material - Tômbola")
_auto_bootstrap_schema()
aba_dashboard, aba_inventario, aba_patrocinios, aba_eventos, aba_caixas = st.tabs(
    ["Dashboard", "Inventário", "Patrocínios", "Eventos", "Caixas"]
)

with aba_dashboard:
    df_inv = _table_df(_table_ref("INVENTARIO"))
    df_caixas = _table_df(_table_ref("CAIXAS"))
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
        if "CaixaAtual" in df_inv.columns:
            sem_caixa = int(df_inv["CaixaAtual"].apply(lambda v: not (isinstance(v, list) and len(v) > 0)).sum())
            if sem_caixa > 0:
                st.warning(f"Inconsistência: existem {sem_caixa} itens sem caixa atribuída.")

        if "QuantidadeAtual" in df_inv.columns:
            qtd_numerica = pd.to_numeric(df_inv["QuantidadeAtual"], errors="coerce")
            invalidas = int((qtd_numerica.isna() | (qtd_numerica < 0)).sum())
            if invalidas > 0:
                st.warning(f"Inconsistência: existem {invalidas} itens com quantidade inválida.")

        vis = [c for c in ["NomeItem", "Categoria", "QuantidadeAtual", "Estado", "CaixaAtual"] if c in df_inv.columns]
        st.dataframe(df_inv[vis], use_container_width=True, hide_index=True)
    st.caption(f"Caixas registadas: {len(df_caixas.index)}")

with aba_inventario:
    df_inv = _table_df(_table_ref("INVENTARIO"))
    df_caixas = _table_df(_table_ref("CAIXAS"))
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
            novo = api.table(BASE_ID, _table_ref("INVENTARIO")).create(campos)
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
            if tipo in {"Saída", "Ajuste"} and not notas.strip():
                st.error("Notas são obrigatórias para Saída e Ajuste.")
            else:
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
            elif not notas_transfer.strip():
                st.error("Notas são obrigatórias para transferências.")
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
    df_pat = _table_df(_table_ref("REGISTO_PATROCINIOS"))
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
            for _, row in pendentes.iterrows():
                reg_id = row["id"]
                label = f"Processar {row.get('DescricaoItem', reg_id)}"
                if st.button(label, key=f"proc_pat_{reg_id}"):
                    try:
                        registo = api.table(BASE_ID, _table_ref("REGISTO_PATROCINIOS")).get(reg_id)
                        if registo.get("fields", {}).get("Processado"):
                            st.warning("Este patrocínio já tinha sido processado.")
                        else:
                            _processar_patrocinio(registo)
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
            api.table(BASE_ID, _table_ref("EVENTOS")).create(
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
    df_eventos = _table_df(_table_ref("EVENTOS"))
    df_inv = _table_df(_table_ref("INVENTARIO"))
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
            if not notas.strip():
                st.error("Notas são obrigatórias para registar saídas.")
            else:
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
            api.table(BASE_ID, _table_ref("CAIXAS")).create(
                {
                    "CodigoCaixa": codigo.strip(),
                    "Descricao": descricao.strip(),
                    "Local": local.strip(),
                    "Estado": estado,
                }
            )
            st.success("Caixa criada.")
            st.rerun()

    df_caixas = _table_df(_table_ref("CAIXAS"))
    if not df_caixas.empty:
        cols = [c for c in ["CodigoCaixa", "Descricao", "Local", "Estado"] if c in df_caixas.columns]
        st.dataframe(df_caixas[cols], use_container_width=True, hide_index=True)
