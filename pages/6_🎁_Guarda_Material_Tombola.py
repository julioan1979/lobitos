from __future__ import annotations

import io

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
    processar_movimentos_lote,
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


def _caixa_display_label(registo: dict) -> str:
    codigo = str(registo.get("CodigoCaixa") or "").strip()
    descricao = str(registo.get("Descricao") or "").strip()
    if descricao and codigo:
        return f"{descricao} ({codigo})"
    return descricao or codigo or "Sem identificação"


def _safe_int(valor) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return 0


COLUNAS_LOTE_OBRIGATORIAS = ["NomeItem", "Tipo", "Quantidade", "Notas", "Categoria"]
COLUNAS_LOTE_OPCIONAIS = ["Evento"]
COLUNAS_LOTE = COLUNAS_LOTE_OBRIGATORIAS + COLUNAS_LOTE_OPCIONAIS


def _template_lote_bytes() -> bytes:
    df_template = pd.DataFrame(
        [
            {
                "NomeItem": "Exemplo Brinquedo",
                "Tipo": "Entrada",
                "Quantidade": 10,
                "Notas": "Doação inicial",
                "Categoria": "Brindes",
                "Evento": "",
            }
        ]
    )
    buffer = io.BytesIO()
    for engine in ("openpyxl", "xlsxwriter"):
        try:
            with pd.ExcelWriter(buffer, engine=engine) as writer:
                df_template.to_excel(writer, index=False, sheet_name="Lote")
            buffer.seek(0)
            return buffer.getvalue()
        except ModuleNotFoundError:
            buffer = io.BytesIO()

    return df_template.to_csv(index=False).encode("utf-8")


def _template_lote_download_config() -> tuple[bytes, str, str, str]:
    template = _template_lote_bytes()
    try:
        pd.read_excel(io.BytesIO(template), nrows=0)
        return (
            template,
            "template_lote_tombola.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "Descarregar template Excel",
        )
    except Exception:
        return (
            template,
            "template_lote_tombola.csv",
            "text/csv",
            "Descarregar template CSV",
        )


def _ler_arquivo_lote(uploaded_file) -> pd.DataFrame:
    nome = (uploaded_file.name or "").lower()
    if nome.endswith(".csv"):
        return pd.read_csv(uploaded_file)
    if nome.endswith(".xlsx") or nome.endswith(".xls"):
        return pd.read_excel(uploaded_file)
    raise ValueError("Formato inválido. Use CSV, XLSX ou XLS.")


def _validar_e_preparar_lote(df_lote: pd.DataFrame, inventario_registos: list[dict], evento_por_nome: dict[str, str]) -> tuple[pd.DataFrame, list[dict]]:
    colunas_em_falta = [col for col in COLUNAS_LOTE_OBRIGATORIAS if col not in df_lote.columns]
    if colunas_em_falta:
        raise ValueError(f"Colunas obrigatórias em falta: {', '.join(colunas_em_falta)}")

    lote = df_lote.copy()
    for coluna in COLUNAS_LOTE:
        if coluna not in lote.columns:
            lote[coluna] = ""

    preview_rows: list[dict] = []
    movimentos: list[dict] = []
    tipos_validos = {"Entrada", "Saída", "Ajuste"}

    for index, row in lote.iterrows():
        numero_linha = int(index) + 2
        nome_item = str(row.get("NomeItem") or "").strip()
        tipo = str(row.get("Tipo") or "").strip()
        notas = str(row.get("Notas") or "").strip()
        categoria = str(row.get("Categoria") or "").strip()
        evento_nome = str(row.get("Evento") or "").strip()
        quantidade_raw = row.get("Quantidade")

        erros: list[str] = []
        quantidade = None

        if not nome_item:
            erros.append("NomeItem em falta")
        if tipo not in tipos_validos:
            erros.append("Tipo inválido (Entrada/Saída/Ajuste)")

        try:
            quantidade = int(float(quantidade_raw))
            if quantidade <= 0 or float(quantidade_raw) != float(quantidade):
                raise ValueError
        except (TypeError, ValueError):
            erros.append("Quantidade inválida (inteiro > 0)")

        if tipo in {"Saída", "Ajuste"} and not notas:
            erros.append("Notas obrigatórias para Saída/Ajuste")

        item_registo = encontrar_item_por_nome(inventario_registos, nome_item)
        item_id = item_registo.get("id") if item_registo else None
        nome_normalizado = normalizar_nome_item(nome_item)
        existe_item = bool(item_id)

        sugestao_erro_item = ""
        if tipo in {"Saída", "Ajuste"} and not existe_item:
            mensagem_item_inexistente = (
                "Item não encontrado no inventário. "
                "Para novo item, use Entrada antes de Saída/Ajuste."
            )
            erros.append(mensagem_item_inexistente)
            sugestao_erro_item = "Registe primeiro uma Entrada para criar o item no inventário."

        evento_id = None
        if evento_nome:
            evento_id = evento_por_nome.get(normalizar_nome_item(evento_nome))
            if not evento_id:
                erros.append("Evento não encontrado")

        preview_row = {
            "Linha": numero_linha,
            "NomeItem": nome_item,
            "NomeNormalizado": nome_normalizado,
            "Tipo": tipo,
            "Quantidade": quantidade_raw,
            "Categoria": categoria,
            "Evento": evento_nome,
            "ItemExistente": "Sim" if existe_item else "Não",
            "Estado": "Erro" if erros else "OK",
            "Erros": " | ".join(erros),
        }
        if sugestao_erro_item:
            preview_row["Sugestão"] = sugestao_erro_item
        preview_rows.append(preview_row)

        if not erros:
            movimentos.append(
                {
                    "indice": numero_linha,
                    "nome_item": nome_item,
                    "tipo": tipo,
                    "quantidade": quantidade,
                    "notas": notas,
                    "categoria": categoria,
                    "evento_id": evento_id,
                }
            )

    preview_df = pd.DataFrame(preview_rows)
    if "Sugestão" in preview_df.columns:
        preview_df["Sugestão"] = preview_df["Sugestão"].fillna("")

    return preview_df, movimentos


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
    patrocinador = campos.get("Patrocinador")
    patrocinador_id = patrocinador[0] if isinstance(patrocinador, list) and patrocinador else None
    if not patrocinador_id:
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

st.markdown("### 🧭 Menu da Tômbola (guia rápido)")
st.info(
    "Use as abas da esquerda para a direita: 1) visão geral, 2) gestão de stock, "
    "3) processamento de patrocínios, 4) saídas para eventos, 5) gestão de caixas."
)

with st.expander("Como usar este menu (passo a passo)", expanded=True):
    st.markdown(
        """
1. **Dashboard** → confirme métricas gerais e alertas de inconsistência.
2. **Inventário** → crie itens, ajuste stock (entrada/saída/ajuste) e faça transferências entre caixas.
3. **Patrocínios** → processe registos pendentes para converter doações em stock.
4. **Eventos** → crie eventos e registe saídas de material com notas obrigatórias.
5. **Caixas** → crie e mantenha as caixas físicas onde o material é guardado.

**Dica prática:** comece sempre no **Dashboard** para validar o estado atual antes de registar movimentos.
        """
    )

aba_dashboard, aba_inventario, aba_patrocinios, aba_eventos, aba_caixas = st.tabs(
    [
        "📊 Dashboard (Visão geral)",
        "📦 Inventário (Stock)",
        "🤝 Patrocínios (Pendentes)",
        "📅 Eventos (Saídas)",
        "🗃️ Caixas (Armazenamento)",
    ]
)

with aba_dashboard:
    df_inv = _table_df(_table_ref("INVENTARIO"))
    df_caixas = _table_df(_table_ref("CAIXAS"))
    caixa_label = {
        str(row.get("id") or "").strip(): _caixa_display_label(row)
        for _, row in df_caixas.iterrows()
        if str(row.get("id") or "").strip()
    } if not df_caixas.empty else {}
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
        df_vis = df_inv[vis].copy()
        if "CaixaAtual" in df_vis.columns:
            def _formatar_caixa(v: object) -> str:
                if isinstance(v, list) and v:
                    caixa_id = str(v[0]).strip()
                    return caixa_label.get(caixa_id, caixa_id)
                return "Sem caixa"

            df_vis["CaixaAtual"] = df_vis["CaixaAtual"].apply(_formatar_caixa)
        st.dataframe(df_vis, use_container_width=True, hide_index=True)
    st.caption(f"Caixas registadas: {len(df_caixas.index)}")

with aba_inventario:
    df_inv = _table_df(_table_ref("INVENTARIO"))
    df_caixas = _table_df(_table_ref("CAIXAS"))
    caixa_options = df_caixas["id"].tolist() if not df_caixas.empty and "id" in df_caixas.columns else []
    caixa_label = {
        str(row.get("id") or "").strip(): _caixa_display_label(row)
        for _, row in df_caixas.iterrows()
        if str(row.get("id") or "").strip()
    } if not df_caixas.empty else {}

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

    with st.expander("Importar lote (CSV/Excel)", expanded=False):
        st.caption(
            "Importe movimentos em lote para Entrada/Saída/Ajuste. "
            "Colunas obrigatórias: NomeItem, Tipo, Quantidade, Notas, Categoria. "
            "Evento é opcional."
        )
        template_data, template_nome, template_mime, template_label = _template_lote_download_config()
        st.download_button(
            template_label,
            data=template_data,
            file_name=template_nome,
            mime=template_mime,
            key="download_template_lote_tombola",
        )

        ficheiro_lote = st.file_uploader(
            "Ficheiro de lote",
            type=["csv", "xlsx", "xls"],
            key="upload_lote_tombola",
            help="Use o template para garantir a estrutura esperada.",
        )

        if ficheiro_lote is not None:
            try:
                df_lote = _ler_arquivo_lote(ficheiro_lote)
                registos_inventario = api.table(BASE_ID, _table_ref("INVENTARIO")).all()
                df_eventos_lote = _table_df(_table_ref("EVENTOS"))
                evento_por_nome = {}
                if not df_eventos_lote.empty and "NomeEvento" in df_eventos_lote.columns:
                    for _, evento_row in df_eventos_lote.iterrows():
                        nome_evento = str(evento_row.get("NomeEvento") or "").strip()
                        if nome_evento:
                            evento_por_nome[normalizar_nome_item(nome_evento)] = evento_row["id"]

                preview_lote, movimentos_lote = _validar_e_preparar_lote(
                    df_lote,
                    inventario_registos=registos_inventario,
                    evento_por_nome=evento_por_nome,
                )

                st.write("Pré-visualização do lote")
                st.dataframe(preview_lote, use_container_width=True, hide_index=True)

                total_erros = int((preview_lote["Estado"] == "Erro").sum()) if not preview_lote.empty else 0
                if total_erros > 0:
                    st.error(f"Foram encontrados {total_erros} erro(s). Corrija o ficheiro antes de gravar.")
                elif not movimentos_lote:
                    st.warning("Nenhuma linha válida para processar.")
                elif st.button("Processar lote", key="btn_processar_lote"):
                    relatorio = processar_movimentos_lote(
                        api,
                        BASE_ID,
                        movimentos=movimentos_lote,
                        executado_por=executado_por,
                    )
                    st.success(
                        "Lote processado. "
                        f"Total: {relatorio['total']} | Sucesso: {relatorio['processados']} | Erros: {relatorio['erros']}"
                    )
                    df_relatorio = pd.DataFrame(relatorio["resultados"])
                    st.dataframe(df_relatorio, use_container_width=True, hide_index=True)
                    st.download_button(
                        "Exportar relatório (CSV)",
                        data=df_relatorio.to_csv(index=False).encode("utf-8"),
                        file_name="relatorio_lote_tombola.csv",
                        mime="text/csv",
                        key="download_relatorio_lote_tombola",
                    )
            except Exception as exc:
                st.error(f"Erro ao validar ficheiro de lote: {exc}")

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

        st.subheader("Registo em lote")
        st.caption(
            "Permite registar múltiplos movimentos de stock de uma só vez. "
            "Linhas vazias são ignoradas automaticamente."
        )

        lote_inicial = pd.DataFrame(
            [
                {
                    "NomeItem": "",
                    "ItemId": "",
                    "Tipo": "Entrada",
                    "Quantidade": 1,
                    "Notas": "",
                    "CaixaDestino": "",
                }
            ]
        )
        lote_editor = st.data_editor(
            lote_inicial,
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key="inv_registo_lote_editor",
            column_config={
                "NomeItem": st.column_config.TextColumn("NomeItem"),
                "ItemId": st.column_config.TextColumn("ItemId"),
                "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Entrada", "Saída", "Ajuste"]),
                "Quantidade": st.column_config.NumberColumn("Quantidade", min_value=1, step=1),
                "Notas": st.column_config.TextColumn("Notas"),
                "CaixaDestino": st.column_config.TextColumn("CaixaDestino"),
            },
        )

        if st.button("Processar lote", key="btn_processar_lote"):
            processadas = 0
            falhadas = 0
            ignoradas = 0

            item_ids_set = set(item_ids)
            nome_para_id = {
                normalizar_nome_item(str(nome)): iid
                for iid, nome in zip(df_inv["id"], df_inv.get("NomeItem", df_inv["id"]))
            }

            linhas_validas = []
            erros_validacao = []

            for idx, row in lote_editor.iterrows():
                numero_linha = idx + 1
                nome_item_linha = str(row.get("NomeItem") or "").strip()
                item_id_linha = str(row.get("ItemId") or "").strip()
                tipo_linha = str(row.get("Tipo") or "").strip()
                quantidade_linha = row.get("Quantidade")
                notas_linha = str(row.get("Notas") or "").strip()
                caixa_destino_linha = str(row.get("CaixaDestino") or "").strip()

                linha_vazia = not any(
                    [nome_item_linha, item_id_linha, tipo_linha, str(quantidade_linha or "").strip(), notas_linha, caixa_destino_linha]
                )
                if linha_vazia:
                    ignoradas += 1
                    continue

                item_id_resolvido = item_id_linha if item_id_linha else nome_para_id.get(normalizar_nome_item(nome_item_linha))
                if not item_id_resolvido or item_id_resolvido not in item_ids_set:
                    erros_validacao.append(
                        f"Linha {numero_linha}: indique NomeItem ou ItemId válido existente no inventário."
                    )
                    continue

                if tipo_linha not in {"Entrada", "Saída", "Ajuste"}:
                    erros_validacao.append(f"Linha {numero_linha}: Tipo inválido.")
                    continue

                try:
                    quantidade_int = int(quantidade_linha)
                except (TypeError, ValueError):
                    erros_validacao.append(f"Linha {numero_linha}: Quantidade inválida.")
                    continue

                if quantidade_int <= 0:
                    erros_validacao.append(f"Linha {numero_linha}: Quantidade deve ser maior que zero.")
                    continue

                if tipo_linha in {"Saída", "Ajuste"} and not notas_linha:
                    erros_validacao.append(f"Linha {numero_linha}: Notas são obrigatórias para {tipo_linha}.")
                    continue

                linhas_validas.append(
                    {
                        "item_id": item_id_resolvido,
                        "tipo": tipo_linha,
                        "quantidade": quantidade_int,
                        "notas": notas_linha,
                    }
                )

            if erros_validacao:
                falhadas += len(erros_validacao)
                st.error("Foram encontradas linhas inválidas. Corrija antes de gravar.")
                for erro in erros_validacao:
                    st.warning(erro)

            for linha in linhas_validas:
                delta = linha["quantidade"]
                if linha["tipo"] == "Saída":
                    delta = -delta
                try:
                    ajustar_stock_item(
                        api,
                        BASE_ID,
                        item_id=linha["item_id"],
                        delta=delta,
                        executado_por=executado_por,
                        tipo_movimento=linha["tipo"],
                        notas=linha["notas"],
                    )
                    processadas += 1
                except Exception as exc:
                    falhadas += 1
                    st.warning(f"Falha ao processar item {linha['item_id']}: {exc}")

            st.info(
                "Resumo do lote — "
                f"processadas: {processadas}, falhadas: {falhadas}, ignoradas: {ignoradas}."
            )
            if processadas > 0:
                st.success("Lote processado. O inventário será atualizado.")
                st.rerun()

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
    st.subheader("Adicionar patrocinador")
    with st.form("form_add_patrocinador_tombola"):
        nome_patrocinador = st.text_input("Nome do patrocinador")
        adicionar_patrocinador = st.form_submit_button("Adicionar")

    if adicionar_patrocinador:
        nome_patrocinador = (nome_patrocinador or "").strip()
        if not nome_patrocinador:
            st.error("Nome do patrocinador é obrigatório.")
        else:
            try:
                patrocinador_id = _ensure_patrocinador_id(nome_patrocinador)
                if patrocinador_id:
                    st.success("Patrocinador confirmado com sucesso.")
                    st.rerun()
                else:
                    st.error("Não foi possível criar ou localizar o patrocinador.")
            except Exception as exc:
                st.error(f"Erro ao adicionar patrocinador: {exc}")

    df_patrocinadores = _table_df(_table_ref("PATROCINADORES"))
    patrocinador_opcoes = {}
    if not df_patrocinadores.empty and "Nome" in df_patrocinadores.columns:
        for _, row in df_patrocinadores.iterrows():
            patrocinador_nome = str(row.get("Nome") or "").strip()
            patrocinador_id = str(row.get("id") or "").strip()
            if patrocinador_nome and patrocinador_id:
                patrocinador_opcoes[patrocinador_nome] = patrocinador_id

    df_caixas_pat = _table_df(_table_ref("CAIXAS"))
    caixa_options_pat = df_caixas_pat["id"].tolist() if not df_caixas_pat.empty and "id" in df_caixas_pat.columns else []
    caixa_label_pat = {
        str(row.get("id") or "").strip(): _caixa_display_label(row)
        for _, row in df_caixas_pat.iterrows()
        if str(row.get("id") or "").strip()
    } if not df_caixas_pat.empty else {}

    df_eventos_pat = _table_df(_table_ref("EVENTOS"))
    evento_options_pat = df_eventos_pat["id"].tolist() if not df_eventos_pat.empty and "id" in df_eventos_pat.columns else []
    evento_label_pat = {
        str(row.get("id") or "").strip(): str(row.get("NomeEvento") or "").strip() or str(row.get("id") or "").strip()
        for _, row in df_eventos_pat.iterrows()
        if str(row.get("id") or "").strip()
    } if not df_eventos_pat.empty else {}

    st.subheader("Criar patrocínio pendente")
    with st.form("form_add_patrocinio_pendente_tombola"):
        col_pat1, col_pat2 = st.columns(2)
        patrocinador_existente = col_pat1.selectbox(
            "Patrocinador existente (opcional)",
            options=[""] + sorted(patrocinador_opcoes.keys()),
            format_func=lambda v: v or "Selecionar...",
        )
        patrocinador_nome = col_pat2.text_input("PatrocinadorNome")
        descricao_item_pat = st.text_input("DescricaoItem")
        quantidade_pat = st.number_input("Quantidade", min_value=1, step=1, value=1)
        categoria_pat = st.text_input("Categoria")
        observacoes_pat = st.text_area("Observacoes")
        col_pat3, col_pat4 = st.columns(2)
        caixa_sugerida_pat = col_pat3.selectbox(
            "CaixaSugerida (opcional)",
            options=[None] + caixa_options_pat,
            format_func=lambda v: caixa_label_pat.get(v, "Sem caixa") if v else "Sem caixa",
        )
        evento_pat = col_pat4.selectbox(
            "Evento (opcional)",
            options=[None] + evento_options_pat,
            format_func=lambda v: evento_label_pat.get(v, "Sem evento") if v else "Sem evento",
        )
        criar_patrocinio_pendente = st.form_submit_button("Criar pendente")

    if criar_patrocinio_pendente:
        patrocinador_nome_resolvido = (patrocinador_nome or "").strip() or (patrocinador_existente or "").strip()
        descricao_item_pat = (descricao_item_pat or "").strip()
        if not patrocinador_nome_resolvido:
            st.error("PatrocinadorNome é obrigatório.")
        elif not descricao_item_pat:
            st.error("DescricaoItem é obrigatório.")
        else:
            try:
                patrocinador_id_resolvido = patrocinador_opcoes.get((patrocinador_existente or "").strip())
                if not patrocinador_id_resolvido:
                    patrocinador_id_resolvido = _ensure_patrocinador_id(patrocinador_nome_resolvido)
                if not patrocinador_id_resolvido:
                    raise ValueError("Não foi possível resolver o patrocinador.")

                campos_patrocinio = {
                    "Patrocinador": [patrocinador_id_resolvido],
                    "PatrocinadorNome": patrocinador_nome_resolvido,
                    "DescricaoItem": descricao_item_pat,
                    "Quantidade": int(quantidade_pat),
                    "Estado": "Pendente",
                    "Processado": False,
                }
                if categoria_pat.strip():
                    campos_patrocinio["Categoria"] = categoria_pat.strip()
                if observacoes_pat.strip():
                    campos_patrocinio["Observacoes"] = observacoes_pat.strip()
                if caixa_sugerida_pat:
                    campos_patrocinio["CaixaSugerida"] = [caixa_sugerida_pat]
                if evento_pat:
                    campos_patrocinio["Evento"] = [evento_pat]

                api.table(BASE_ID, _table_ref("REGISTO_PATROCINIOS")).create(campos_patrocinio)
                st.success("Patrocínio pendente criado com sucesso.")
                st.rerun()
            except Exception as exc:
                st.error(f"Erro ao criar patrocínio pendente: {exc}")

    if not df_patrocinadores.empty:
        st.caption("Patrocinadores atuais")
        cols_patrocinadores = [c for c in ["Nome"] if c in df_patrocinadores.columns]
        st.dataframe(
            df_patrocinadores[cols_patrocinadores] if cols_patrocinadores else df_patrocinadores,
            use_container_width=True,
            hide_index=True,
        )

    df_pat = _table_df(_table_ref("REGISTO_PATROCINIOS"))
    relatorio_batch = st.session_state.pop("patrocinios_batch_relatorio", None)
    if relatorio_batch:
        total_sucesso = sum(1 for item in relatorio_batch if item["Resultado"] == "Sucesso")
        total_erro = len(relatorio_batch) - total_sucesso
        if total_erro == 0:
            st.success(f"Processamento concluído: {total_sucesso} registos com sucesso.")
        else:
            st.warning(
                "Processamento concluído com erros: "
                f"{total_sucesso} sucesso(s) e {total_erro} erro(s)."
            )
        st.dataframe(pd.DataFrame(relatorio_batch), use_container_width=True, hide_index=True)

    if df_pat.empty:
        st.info("Sem registos em RegistoPatrocinios.")
    else:
        pendentes = df_pat[~df_pat.get("Processado", False).fillna(False)] if "Processado" in df_pat.columns else df_pat
        if pendentes.empty:
            st.success("Não existem patrocínios pendentes.")
        else:
            st.write("Patrocínios pendentes")
            mostrar_cols = [c for c in ["PatrocinadorNome", "DescricaoItem", "Quantidade", "Estado", "Processado"] if c in pendentes.columns]
            tabela_pendentes = pendentes[["id", *mostrar_cols]].copy() if mostrar_cols else pendentes[["id"]].copy()
            tabela_pendentes.insert(0, "Selecionar", False)
            tabela_editada = st.data_editor(
                tabela_pendentes,
                use_container_width=True,
                hide_index=True,
                column_config={"Selecionar": st.column_config.CheckboxColumn("Selecionar")},
                disabled=[c for c in tabela_pendentes.columns if c != "Selecionar"],
                key="patrocinios_pendentes_editor",
            )

            if st.button("Processar selecionados", key="proc_pat_lote"):
                selecionados = tabela_editada[tabela_editada["Selecionar"] == True]
                if selecionados.empty:
                    st.warning("Selecione pelo menos um registo para processar.")
                else:
                    relatorio = []
                    tabela_patrocinios = api.table(BASE_ID, _table_ref("REGISTO_PATROCINIOS"))
                    for _, row in selecionados.iterrows():
                        reg_id = row["id"]
                        descricao = row.get("DescricaoItem") or reg_id
                        try:
                            registo = tabela_patrocinios.get(reg_id)
                            if registo.get("fields", {}).get("Processado"):
                                raise ValueError("Este patrocínio já tinha sido processado.")
                            _processar_patrocinio(registo)
                            relatorio.append(
                                {
                                    "Registo": reg_id,
                                    "DescricaoItem": descricao,
                                    "Resultado": "Sucesso",
                                    "Mensagem": "Patrocínio processado com sucesso.",
                                }
                            )
                        except Exception as exc:
                            relatorio.append(
                                {
                                    "Registo": reg_id,
                                    "DescricaoItem": descricao,
                                    "Resultado": "Erro",
                                    "Mensagem": str(exc),
                                }
                            )

                    st.session_state["patrocinios_batch_relatorio"] = relatorio
                    st.rerun()

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

    df_eventos = _table_df(_table_ref("EVENTOS"))
    st.subheader("Eventos registados")
    if df_eventos.empty:
        st.info("Ainda não existem eventos registados.")
    else:
        cols_eventos = [
            c for c in ["NomeEvento", "Tipo", "Data", "Local", "Estado"] if c in df_eventos.columns
        ]
        st.dataframe(df_eventos[cols_eventos] if cols_eventos else df_eventos, use_container_width=True, hide_index=True)

    st.subheader("Registar saída para evento")
    df_inv = _table_df(_table_ref("INVENTARIO"))

    missing_parts = []
    if df_eventos.empty:
        missing_parts.append("1 evento")
    if df_inv.empty:
        missing_parts.append("1 item")

    if missing_parts:
        st.info(
            "Para registar saídas precisa de "
            + " e ".join(missing_parts)
            + f". Atualmente: {len(df_eventos.index)} eventos e {len(df_inv.index)} itens."
        )
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
