#pages/home.py
#-*- coding: utf-8 -*-
from typing import Any

import json

import streamlit as st
import pandas as pd
import altair as alt
from pyairtable import Api
from menu import menu_with_redirect
import locale
import unicodedata
import time
from datetime import date, datetime, timedelta
from urllib.parse import urlparse, urlunparse
import streamlit.components.v1 as components
from st_aggrid import AgGrid, DataReturnMode, GridOptionsBuilder, GridUpdateMode, JsCode
from airtable_config import context_labels, current_context, get_airtable_credentials, resolve_form_url
from components.banner_convites import mostrar_convites
from data_utils import (
    construir_mapa_nomes_por_id,
    escolher_coluna,
    formatar_moeda_euro,
    mapear_lista,
    normalizar_valor_selecao,
    preparar_dataframe_estornos,
)
try:
    locale.setlocale(locale.LC_ALL, "pt_PT.UTF-8")
except locale.Error:
    # fallback para não dar erro no Streamlit Cloud
    locale.setlocale(locale.LC_ALL, "")



st.set_page_config(page_title="Portal Escutista", page_icon="🐾", layout="wide")

AIRTABLE_SINGLE_SELECT_COLORS: dict[str, tuple[str, str]] = {
    "gray": ("#adb5bd", "#212529"),
    "grayDark": ("#6c757d", "#f8f9fa"),
    "grayLight": ("#ced4da", "#212529"),
    "brown": ("#795548", "#ffffff"),
    "orange": ("#ff9800", "#212529"),
    "yellow": ("#ffeb3b", "#212529"),
    "lime": ("#cddc39", "#212529"),
    "green": ("#4caf50", "#ffffff"),
    "teal": ("#009688", "#ffffff"),
    "cyan": ("#00bcd4", "#ffffff"),
    "blue": ("#2196f3", "#ffffff"),
    "darkBlue": ("#0d47a1", "#ffffff"),
    "purple": ("#9c27b0", "#ffffff"),
    "pink": ("#e91e63", "#ffffff"),
    "magenta": ("#d81b60", "#ffffff"),
    "red": ("#f44336", "#ffffff"),
    "darkRed": ("#b71c1c", "#ffffff"),
}


def _map_airtable_color(nome_cor: str | None) -> tuple[str, str]:
    if not nome_cor:
        return "#f8f9fa", "#212529"
    return AIRTABLE_SINGLE_SELECT_COLORS.get(nome_cor, ("#f8f9fa", "#212529"))

# ======================
# 1) Verificar login
# ======================
menu_with_redirect()
role = st.session_state.get("role")
user_info = st.session_state.get("user", {})
allowed_escuteiros = set(user_info.get("escuteiros_ids", [])) if user_info else set()
permissions = st.session_state.get("permissions", {})
is_admin = bool(permissions.get("admin"))
is_tesoureiro = bool(permissions.get("tesoureiro"))
if not permissions:
    is_admin = role == "admin"
    is_tesoureiro = role == "tesoureiro"

if role is None:
    st.stop()

#role = st.selectbox(
#    "Escolha o tipo de utilizador",
#    options=["admin", "tesoureiro", "pais"],
#    index=1  # por defeito tesoureiro
#)

# ======================
# 2) Função para carregar dados do Airtable
# ======================
contexto_atual = current_context()
if contexto_atual is None:
    st.switch_page("app.py")
    st.stop()

DEFAULT_LANCHE_FORM_URL = resolve_form_url("DEFAULT_LANCHE_FORM_URL", "Formulário de Escolha dos Lanches")
secao_legenda = context_labels()
if secao_legenda:
    st.caption(secao_legenda)
mostrar_convites("principal")
AIRTABLE_TOKEN, BASE_ID = get_airtable_credentials()
api = Api(AIRTABLE_TOKEN)

def carregar_todas_as_tabelas(base_id: str, role: str) -> dict:
    dados = {}

    # Mapear tabelas necessárias por role
    tabelas_por_role = {
        "pais": [
            "Pedidos",
            "Calendario",
            "Voluntariado Pais",
            "Escuteiros",
            "Recipes",
            "Publicar Menu do Scouts",
        ],
        "tesoureiro": [
            "Escuteiros",
            "Recebimento",
            "Estorno de Recebimento",
            "Estornos de Recebimento",
            "Permissoes",
            "Publicar Menu do Scouts",
            "Quotas",
            "Tipo de Cotas",
        ],
        "admin": [
            "Pedidos",
            "Calendario",
            "Voluntariado Pais",
            "Escuteiros",
            "Recipes",
            "Recebimento",
            "Estorno de Recebimento",
            "Estornos de Recebimento",
            "Permissoes",
            "Publicar Menu do Scouts",
            "Quotas",
            "Tipo de Cotas",
        ],
    }

    lista_tabelas = tabelas_por_role.get(role, [])
    tabelas_opcionais = {"Quotas", "Tipo de Cotas", "Estornos de Recebimento"}

    for nome in lista_tabelas:
        try:
            tbl = api.table(base_id, nome)
            records = tbl.all()
            rows = [{"id": r["id"], **r["fields"]} for r in records]
            dados[nome] = pd.DataFrame(rows)
            time.sleep(0.25)  # evitar limite 5 requests/s
        except Exception as e:
            mensagem = str(e)
            if nome in tabelas_opcionais and "INVALID_PERMISSIONS_OR_MODEL_NOT_FOUND" in mensagem:
                dados[nome] = pd.DataFrame()
                continue
            st.warning(f"⚠️ Não consegui carregar a tabela {nome}: {e}")
            dados[nome] = pd.DataFrame()
    return dados

def mostrar_barra_acoes(botoes: list[tuple[str, str]], espacador: int = 6) -> dict[str, bool]:
    """Renderiza uma barra de ações consistente e devolve o estado dos botões."""
    if not botoes:
        return {}

    colunas_config = [1] * len(botoes)
    if espacador > 0:
        colunas_config.append(espacador)

    colunas = st.columns(colunas_config)
    resultados = {}

    for coluna, (label, key) in zip(colunas, botoes):
        with coluna:
            resultados[key] = st.button(label, key=key, use_container_width=True)

    return resultados




REFRESH_BUTTON_LABEL = "🔄 Atualizar dados do Airtable"


def atualizar_dados_cache() -> None:
    st.session_state["dados_cache"] = carregar_todas_as_tabelas(BASE_ID, role)
    st.session_state["last_update"] = datetime.now()


def render_refresh_button(key_suffix: str, *, show_timestamp: bool = False) -> None:
    """Mostra o botão de atualização em múltiplos locais com feedback único."""
    button_key = f"refresh_{key_suffix}"
    success_flag = f"refresh_success_{key_suffix}"

    if st.button(REFRESH_BUTTON_LABEL, key=button_key):
        atualizar_dados_cache()
        st.session_state[success_flag] = datetime.now()

    if st.session_state.get(success_flag):
        st.success("✅ Dados atualizados com sucesso!")
        st.session_state.pop(success_flag, None)

    if show_timestamp and "last_update" in st.session_state:
        st.caption(f"🕒 Última atualização: {st.session_state['last_update'].strftime('%d/%m/%Y %H:%M:%S')}")


def _normalizar_texto(valor: str) -> str:
    if not isinstance(valor, str):
        return ""
    texto = unicodedata.normalize("NFKD", str(valor))
    return "".join(ch for ch in texto.lower() if not unicodedata.combining(ch))


def mostrar_formulario(
    session_key: str,
    titulo: str,
    iframe_url: str,
    iframe_height: int = 600,
    container_height=None,
    *,
    wrapper: str = "container",
    expander_label: str | None = None,
    expander_expanded: bool = True,
) -> None:
    if not st.session_state.get(session_key, False):
        return

    if wrapper == "expander":
        label = expander_label or titulo.lstrip("#").strip()
        container = st.expander(label, expanded=expander_expanded)
        mostrar_titulo = False
    else:
        container = st.container(border=True)
        mostrar_titulo = True

    with container:
        col1, col2 = st.columns([8, 1])
        with col1:
            if mostrar_titulo:
                st.markdown(titulo)
        with col2:
            if st.button("❌", key=f"fechar_{session_key}"):
                st.session_state[session_key] = False
                st.rerun()

        altura_render = container_height if container_height is not None else iframe_height + 50

        components.html(
            f"""
            <iframe class="airtable-embed"
                src="{iframe_url}"
                frameborder="0" onmousewheel="" width="100%" height="{iframe_height}"
                style="background: transparent; border: 1px solid #ccc;">
            </iframe>
            """,
            height=altura_render,
            scrolling=True,
        )

def normalizar_url_airtable(valor_url, fallback: str) -> str:
    """Garante que o URL do Airtable está no formato embed e devolve um fallback se estiver vazio."""
    bruto = valor_url
    if isinstance(bruto, list):
        bruto = bruto[0] if bruto else ""
    if pd.isna(bruto) or not str(bruto).strip():
        return fallback

    candidato = str(bruto).strip()
    try:
        parsed = urlparse(candidato)
    except ValueError:
        return fallback

    if not parsed.netloc:
        parsed = urlparse(f"https://{candidato.lstrip('/')}")
    if "airtable.com" not in parsed.netloc:
        return urlunparse(parsed._replace(scheme=parsed.scheme or "https"))

    path = parsed.path or ""
    if not path.startswith("/embed/"):
        path = "/embed/" + path.lstrip("/")

    normalizado = parsed._replace(
        scheme="https",
        path=path,
    )
    return urlunparse(normalizado)


def obter_form_url(extra_key: str, label: str) -> str:
    """Obtém URL de formulário a partir dos extras da secção, validando obrigatoriedade."""
    return resolve_form_url(extra_key, label)


# ======================
# 3) Cache e botão de refresh
# ======================
if "dados_cache" not in st.session_state:
    atualizar_dados_cache()

with st.sidebar:
    render_refresh_button("sidebar")

render_refresh_button("main", show_timestamp=True)

dados = st.session_state["dados_cache"]

# ======================
# 4) Dashboards
# ======================

def dashboard_pais():
    col_titulo, col_refresh = st.columns([4, 1])
    with col_titulo:
        st.markdown("## 🏡 Bem-vindo, Família Escutista!")
    with col_refresh:
        render_refresh_button("pais")
    st.info("Aqui podem gerir lanches, voluntariado e acompanhar as atividades.")

    df_pedidos = dados.get("Pedidos", pd.DataFrame())
    df_calendario = dados.get("Calendario", pd.DataFrame())
    df_volunt = dados.get("Voluntariado Pais", pd.DataFrame())
    df_escuteiros = dados.get("Escuteiros", pd.DataFrame())
    df_recipes = dados.get("Recipes", pd.DataFrame())

    if df_escuteiros is None or df_escuteiros.empty or "id" not in df_escuteiros.columns:
        st.warning("ℹ️ Ainda não há escuteiros registados ou a tabela não está completa.")
        return

    df_escuteiros = df_escuteiros.copy()

    if allowed_escuteiros:
        df_escuteiros = df_escuteiros[df_escuteiros["id"].isin(allowed_escuteiros)]
        if df_escuteiros.empty:
            st.warning("⚠️ Não existem dados para os escuteiros associados a esta conta.")
            return
    elif role == "pais":
        st.warning("ℹ️ A sua conta ainda não tem escuteiros associados. Contacte a equipa de administração.")
        return

    def _formatar_label(row: pd.Series) -> str:
        nome = row.get("Nome do Escuteiro")
        codigo = row.get("ID_Escuteiro")
        if pd.isna(nome) or not str(nome).strip():
            nome = "Escuteiro sem nome"
        if pd.notna(codigo) and str(codigo).strip():
            return f"{nome} ({codigo})"
        return str(nome)

    df_escuteiros["__label"] = df_escuteiros.apply(_formatar_label, axis=1)
    df_escuteiros = df_escuteiros.sort_values("__label")

    escuteiros_ids = df_escuteiros["id"].tolist()
    label_por_id = dict(zip(df_escuteiros["id"], df_escuteiros["__label"]))

    sess_key = "escuteiro_selecionado"
    if sess_key not in st.session_state or st.session_state[sess_key] not in escuteiros_ids:
        st.session_state[sess_key] = escuteiros_ids[0]

    escuteiro_id = st.selectbox(
        "Escolha o Escuteiro",
        options=escuteiros_ids,
        format_func=lambda value: label_por_id.get(value, value),
        key=sess_key,
    )
    escuteiro_nome = label_por_id.get(escuteiro_id, "")
    escuteiro_row = df_escuteiros[df_escuteiros["id"] == escuteiro_id].iloc[0]

    def _contem_escuteiro(valor) -> bool:
        if isinstance(valor, list):
            return escuteiro_id in valor
        if pd.isna(valor):
            return False
        return valor == escuteiro_id

    # 🔘 Barra de Ações
    acoes_pais = mostrar_barra_acoes([
        ("🍞 Marcar Lanche", "btn_marcar_lanche"),
        ("❌ Cancelar Lanche", "btn_cancelar_lanche"),
    ])

    if acoes_pais.get("btn_marcar_lanche"):
        st.session_state["mostrar_form_lanche"] = True
    if acoes_pais.get("btn_cancelar_lanche"):
        st.session_state["mostrar_form_cancelar"] = True

    url_escolha_lanche = normalizar_url_airtable(
        escuteiro_row.get("Pre_Field escolha semanal lanches", ""),
        DEFAULT_LANCHE_FORM_URL,
    )

    # Formulário Escolha dos Lanches
    mostrar_formulario(
        session_key="mostrar_form_lanche",
        titulo="### 🍞 Formulário de Escolha dos Lanches",
        iframe_url=url_escolha_lanche,
        iframe_height=600,
        container_height=650,
    )

    # Formulário Cancelar Lanche
    mostrar_formulario(
        session_key="mostrar_form_cancelar",
        titulo="### ❌ Formulário de Cancelamento de Lanche",
        iframe_url=obter_form_url("CANCEL_LANCHE_FORM_URL", "Formulário de Cancelamento de Lanche"),
        iframe_height=533,
        container_height=650,
    )

    st.divider()

    def _formatar_euro(valor) -> str:
        if pd.isna(valor):
            return "—"
        try:
            return locale.currency(valor, grouping=True)
        except Exception:
            return f"{valor:,.2f} €"

    saldo = pd.to_numeric(escuteiro_row.get("Conta Corrente"), errors="coerce")
    valor_lanches = pd.to_numeric(escuteiro_row.get("Lanches"), errors="coerce")
    recebimentos = pd.to_numeric(escuteiro_row.get("Valores recebidos"), errors="coerce")
    doacoes = pd.to_numeric(escuteiro_row.get("Valores doados"), errors="coerce")
    estornos = pd.to_numeric(escuteiro_row.get("Valor Estornado"), errors="coerce")
    n_lanches = pd.to_numeric(escuteiro_row.get("Numero de Lanches"), errors="coerce")

    st.subheader("💰 Situação financeira")

    def _to_float(valor) -> float:
        if isinstance(valor, list):
            return sum(_to_float(item) for item in valor)
        if isinstance(valor, (int, float)):
            return float(valor)
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            return 0.0
        if pd.isna(valor):
            return 0.0
        texto = str(valor).strip().strip('"').replace("€", "")
        if not texto:
            return 0.0
        texto = texto.replace(" ", "")
        if texto.count(",") > 1 and "." not in texto:
            texto = texto.replace(".", "")
        if "," in texto and "." in texto:
            texto = texto.replace(".", "").replace(",", ".")
        elif "," in texto:
            texto = texto.replace(",", ".")
        try:
            return float(texto)
        except ValueError:
            return 0.0

    saldo_lanches = _to_float(escuteiro_row.get("Saldo Lanches"))
    recebido_lanches = _to_float(escuteiro_row.get("Vls recebidos lanches"))
    estornado_lanches = _to_float(escuteiro_row.get("Vls Estornados Lanches"))

    saldo_quota_mensal = _to_float(escuteiro_row.get("Saldo Quota Mensal"))
    recebido_quota_mensal = _to_float(escuteiro_row.get("Vls recebidos quotas mensal"))
    estornado_quota_mensal = _to_float(escuteiro_row.get("Vls Estornados Quotas Mensal"))

    saldo_quota_anual = _to_float(escuteiro_row.get("Saldo Quota Anual"))
    recebido_quota_anual = _to_float(escuteiro_row.get("Vls recebidos quotas anual"))
    estornado_quota_anual = _to_float(escuteiro_row.get("Vls Estornados Quotas Anual"))

    net_lanches = recebido_lanches - estornado_lanches

    net_recebimentos = recebimentos - estornos

    col_lanches_row = st.columns([1, 1, 1, 1])
    with col_lanches_row[0]:
        st.metric("Lanches registados", int(n_lanches) if not pd.isna(n_lanches) else 0)
    with col_lanches_row[1]:
        st.metric("Valor Total dos Lanches", _formatar_euro(valor_lanches))
    with col_lanches_row[2]:
        st.metric("Pagamentos Recebidos Lanches", _formatar_euro(net_lanches))
    with col_lanches_row[3]:
        st.metric("Saldo Lanches", _formatar_euro(saldo_lanches))

    col_restante = st.columns([1, 1, 1, 1, 1, 1])
    with col_restante[0]:
        st.metric("Pagamento Quota Mensal", _formatar_euro(recebido_quota_mensal - estornado_quota_mensal))
    with col_restante[1]:
        st.metric("Posição Quota Mensal", _formatar_euro(saldo_quota_mensal))
    with col_restante[2]:
        st.metric("Pagamento Quota Anual", _formatar_euro(recebido_quota_anual - estornado_quota_anual))
    with col_restante[3]:
        st.metric("Posição Quota Anual", _formatar_euro(saldo_quota_anual))
    with col_restante[4]:
        st.metric("Doações", _formatar_euro(doacoes))
    with col_restante[5]:
        saldo_display = _formatar_euro(saldo)
        saldo_cor = "#16A34A" if saldo >= 0 else "#DC2626"
        saldo_bg = "rgba(22, 163, 74, 0.15)" if saldo >= 0 else "rgba(220, 38, 38, 0.15)"
        st.markdown(
            f"""
            <div style="
                padding: 0.75rem 1rem;
                border-radius: 0.75rem;
                background-color: {saldo_bg};
                border: 1px solid {saldo_cor}33;
                box-shadow: 0 12px 20px -18px {saldo_cor};
            ">
                <div style="
                    font-size: 0.85rem;
                    letter-spacing: 0.05em;
                    text-transform: uppercase;
                    color: #d1d5db;
                    font-weight: 600;
                ">Saldo Geral</div>
                <div style="
                    margin-top: 0.35rem;
                    font-size: 1.7rem;
                    font-weight: 700;
                    color: {saldo_cor};
                ">{saldo_display}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.divider()

    recipes_map = {}
    if df_recipes is not None and not df_recipes.empty and "id" in df_recipes.columns:
        if "Menu" in df_recipes.columns:
            recipes_map = df_recipes.set_index("id")["Menu"].to_dict()

    def _resolver_lista(valor, mapping) -> str:
        if isinstance(valor, list):
            nomes = [mapping.get(item, item) for item in valor]
            return ", ".join(filter(None, nomes))
        if pd.isna(valor):
            return ""
        return mapping.get(valor, valor)

    pedidos_escuteiro = pd.DataFrame()
    if df_pedidos is not None and not df_pedidos.empty:
        if "Escuteiros" in df_pedidos.columns:
            mask_pedidos = df_pedidos["Escuteiros"].apply(_contem_escuteiro)
        elif "Escuteiro" in df_pedidos.columns:
            mask_pedidos = df_pedidos["Escuteiro"].apply(_contem_escuteiro)
        else:
            mask_pedidos = pd.Series(False, index=df_pedidos.index)
        pedidos_escuteiro = df_pedidos[mask_pedidos].copy()
        if not pedidos_escuteiro.empty:
            if "Date" in pedidos_escuteiro.columns:
                pedidos_escuteiro["__data"] = pd.to_datetime(pedidos_escuteiro["Date"], errors="coerce")
            elif "Created" in pedidos_escuteiro.columns:
                pedidos_escuteiro["__data"] = pd.to_datetime(pedidos_escuteiro["Created"], errors="coerce")
            else:
                pedidos_escuteiro["__data"] = pd.NaT
            pedidos_escuteiro = pedidos_escuteiro.sort_values("__data", ascending=False)

    st.subheader("📖 Últimos pedidos")
    if pedidos_escuteiro.empty:
        st.info("ℹ️ Ainda não há pedidos registados para este Escuteiro.")
    else:
        pedidos_mostrar = pedidos_escuteiro.head(5).copy()
        if "__data" in pedidos_mostrar.columns:
            pedidos_mostrar["Data"] = pedidos_mostrar["__data"].dt.strftime('%d/%m/%Y')
        if "Created" in pedidos_mostrar.columns:
            horarios = pd.to_datetime(pedidos_mostrar["Created"], errors="coerce")
            pedidos_mostrar["Hora"] = horarios.dt.strftime("%H:%M").fillna("")
        elif "__data" in pedidos_mostrar.columns:
            pedidos_mostrar["Hora"] = pedidos_mostrar["__data"].dt.strftime("%H:%M").fillna("")
        for coluna in ["Bebida", "Lanche", "Fruta"]:
            if coluna in pedidos_mostrar.columns:
                pedidos_mostrar[coluna] = pedidos_mostrar[coluna].apply(lambda valor: _resolver_lista(valor, recipes_map))
        if "Restrição alimentar" in pedidos_mostrar.columns:
            pedidos_mostrar["Restrição alimentar"] = pedidos_mostrar["Restrição alimentar"].fillna("")
        colunas_exibir = [c for c in ["Data", "Lanche", "Bebida", "Fruta", "Restrição alimentar"] if c in pedidos_mostrar.columns]
        if "Hora" in pedidos_mostrar.columns:
            if "Data" in colunas_exibir:
                colunas_exibir.insert(colunas_exibir.index("Data") + 1, "Hora")
            else:
                colunas_exibir.insert(0, "Hora")
        st.dataframe(pedidos_mostrar[colunas_exibir], use_container_width=True)

    st.divider()

    hoje = pd.Timestamp.today().normalize()
    metricas_pedidos = pedidos_escuteiro.copy()
    if not metricas_pedidos.empty and "__data" in metricas_pedidos.columns:
        ult30 = metricas_pedidos[metricas_pedidos["__data"] >= hoje - pd.Timedelta(days=30)]
        total_30 = len(ult30)
        total_all = len(metricas_pedidos)
        ultimo_registo = metricas_pedidos.iloc[0]["__data"]
        bebidas_freq = None
        if "Bebida" in metricas_pedidos.columns:
            bebidas_expandidas = []
            for valor in metricas_pedidos["Bebida"].dropna():
                if isinstance(valor, list):
                    bebidas_expandidas.extend(valor)
                else:
                    bebidas_expandidas.append(valor)
            if bebidas_expandidas:
                bebidas_freq = pd.Series(bebidas_expandidas).value_counts().idxmax()
                bebidas_freq = recipes_map.get(bebidas_freq, bebidas_freq)
    else:
        total_30 = 0
        total_all = len(pedidos_escuteiro)
        ultimo_registo = None
        bebidas_freq = None

    col7, col8, col9 = st.columns(3)
    with col7:
        st.metric("Pedidos (30 dias)", total_30)

    senha_mais_recente = None
    if not metricas_pedidos.empty and "Senha_marcações" in metricas_pedidos.columns:
        # usa a mesma ordenação descendente em __data para obter a última senha usada
        senha_mais_recente = metricas_pedidos.iloc[0].get("Senha_marcações")

    with col8:
        st.metric("Senhas (última marcação)", senha_mais_recente or "—")

    with col9:
        st.metric("Último pedido", ultimo_registo.strftime('%d/%m/%Y') if isinstance(ultimo_registo, pd.Timestamp) and not pd.isna(ultimo_registo) else "—")

    if bebidas_freq:
        st.caption(f"🍹 Bebida favorita recente: {bebidas_freq}")

    st.divider()

    calendario_por_id = {}
    if df_calendario is not None and not df_calendario.empty and "id" in df_calendario.columns:
        df_calendario = df_calendario.copy()
        df_calendario["__data"] = pd.to_datetime(df_calendario.get("Data"), errors="coerce")
        calendario_por_id = df_calendario.set_index("id").to_dict(orient="index")

    def _info_calendario(valor):
        ids = []
        if isinstance(valor, list):
            ids = valor
        elif pd.notna(valor):
            ids = [valor]
        infos = []
        for id_cal in ids:
            info = calendario_por_id.get(id_cal)
            if info:
                data = pd.to_datetime(info.get("Data"), errors="coerce")
                agenda = info.get("Agenda")
                infos.append((data, agenda))
        infos = [i for i in infos if i[0] is not None]
        if not infos:
            return None
        return sorted(infos, key=lambda item: item[0])[0]

    proximo_volunt = None
    if df_volunt is not None and not df_volunt.empty and "Escuteiro" in df_volunt.columns:
        df_volunt = df_volunt.copy()
        df_volunt = df_volunt[df_volunt["Escuteiro"].apply(_contem_escuteiro)].copy()
        if "Cancelado" in df_volunt.columns:
            df_volunt = df_volunt[~df_volunt["Cancelado"].astype(str).str.lower().eq("true")]
        if not df_volunt.empty:
            if "Date (calendário)" in df_volunt.columns:
                df_volunt["__info"] = df_volunt["Date (calendário)"].apply(_info_calendario)
            else:
                df_volunt["__info"] = None
            df_volunt = df_volunt[df_volunt["__info"].notna()]
            if not df_volunt.empty:
                df_volunt["__data"] = df_volunt["__info"].apply(lambda item: item[0])
                df_volunt["__agenda"] = df_volunt["__info"].apply(lambda item: item[1])
                df_volunt = df_volunt[df_volunt["__data"] >= hoje]
                if not df_volunt.empty:
                    proximo_volunt = df_volunt.sort_values("__data").iloc[0]

    st.subheader("📅 Próximos compromissos")
    if proximo_volunt is not None:
        data_vol = proximo_volunt["__data"].strftime('%d/%m/%Y') if not pd.isna(proximo_volunt["__data"]) else "Data a confirmar"
        agenda_vol = proximo_volunt["__agenda"] or "Voluntariado"
        st.success(f"✅ {escuteiro_nome} está inscrito no voluntariado de {data_vol}: {agenda_vol}")
    else:
        proximo_evento = None
        if calendario_por_id:
            df_cal_future = df_calendario[df_calendario["__data"] >= hoje].sort_values("__data")
            if not df_cal_future.empty:
                proximo_evento = df_cal_future.iloc[0]
        if proximo_evento is not None:
            data_evt = proximo_evento["__data"].strftime('%d/%m/%Y') if not pd.isna(proximo_evento["__data"]) else "Data a definir"
            agenda_evt = proximo_evento.get("Agenda", "Atividade da Tropa")
            st.info(f"📅 Próximo evento da Tropa: {data_evt} – {agenda_evt}")
        else:
            st.info("ℹ️ Não há eventos futuros registados neste momento.")


def dashboard_tesoureiro(dados: dict):
    col_titulo, col_refresh = st.columns([4, 1])
    with col_titulo:
        st.markdown("## 💰 Dashboard Tesoureiro")
    with col_refresh:
        render_refresh_button("tesoureiro")

    # 🔘 Barra de Ações
    acoes_tesoureiro = mostrar_barra_acoes([
        ("➕ Recebimento", "btn_recebimento"),
        ("➖ Estorno", "btn_estorno"),
    ])

    if acoes_tesoureiro.get("btn_recebimento"):
        st.session_state["mostrar_form_receb"] = True
    if acoes_tesoureiro.get("btn_estorno"):
        st.session_state["mostrar_form_estorno"] = True


    # Mostrar formulário Recebimento
    mostrar_formulario(
        session_key="mostrar_form_receb",
        titulo="### 📋 Formulário de Recebimento",
        iframe_url=obter_form_url("RECEBIMENTO_FORM_URL", "Formulário de Recebimento"),
        iframe_height=600,
        container_height=650,
    )


    # Mostrar formulário Estorno
    mostrar_formulario(
        session_key="mostrar_form_estorno",
        titulo="### 📋 Formulário de Estorno",
        iframe_url=obter_form_url("ESTORNO_FORM_URL", "Formulário de Estorno"),
        iframe_height=600,
        container_height=650,
    )




    col1, col2, col3, col4 = st.columns(4)

    # Saldo total
    saldo_total = 0
    df_tes = dados.get("Escuteiros", pd.DataFrame())
    if not df_tes.empty and "Conta Corrente" in df_tes.columns:
        saldo_total = df_tes["Conta Corrente"].fillna(0).sum()

    # Rentabilidade da semana corrente
    rentabilidade_semana = 0
    semana_numero = None
    df_semana = dados.get("Publicar Menu do Scouts", pd.DataFrame())
    if (
        not df_semana.empty
        and "Rentabilidade Semana" in df_semana.columns
        and "Week Num Menu Publicado" in df_semana.columns
    ):
        df_semana["Date (from Marcação dos Pais na preparação do Lanche)"] = pd.to_datetime(
            df_semana["Date (from Marcação dos Pais na preparação do Lanche)"],
            errors="coerce"
        )
        ano_atual = pd.Timestamp.today().year
        df_atual = df_semana[
            df_semana["Date (from Marcação dos Pais na preparação do Lanche)"].dt.year == ano_atual
        ]
        if not df_atual.empty:
            idx = df_atual["Week Num Menu Publicado"].idxmax()
            rentabilidade_semana = df_atual.loc[idx, "Rentabilidade Semana"]
            semana_numero = df_atual.loc[idx, "Week Num Menu Publicado"]

    # Nº escuteiros em débito
    n_escuteiros_debito = 0
    if not df_tes.empty and "Conta Corrente" in df_tes.columns:
        n_escuteiros_debito = (df_tes["Conta Corrente"] < 0).sum()

    # Total dívida
    divida_total = 0
    if not df_tes.empty and "Conta Corrente" in df_tes.columns:
        divida_total = df_tes.loc[df_tes["Conta Corrente"] < 0, "Conta Corrente"].sum()

    # Exibir métricas
    with col1:
        st.metric("💰 Saldo Total", f"{saldo_total:.2f} €")
    with col2:
        if semana_numero:
            st.metric("📅 Valor Semana", f"{rentabilidade_semana:.2f} €", delta=f"Semana {semana_numero}")
        else:
            st.metric("📅 Valor Semana", f"{rentabilidade_semana:.2f} €")
    with col3:
        st.metric("👦 Nº Escuteiros Devedores", n_escuteiros_debito)
    with col4:
        st.metric("❌ Total em Dívida", f"{divida_total:.2f} €")

    st.divider()

    # Ranking de Escuteiros
    st.markdown("### 🏆 Ranking de Escuteiros")
    if not df_tes.empty and "Conta Corrente" in df_tes.columns and "Escuteiro" in df_tes.columns:
        df_ranking = df_tes.copy()
        df_ranking["__saldo"] = pd.to_numeric(df_ranking["Conta Corrente"], errors="coerce").fillna(0)

        top_ricos = (
            df_ranking[df_ranking["__saldo"] > 0]
            .sort_values("__saldo", ascending=False)
            .head(5)
            .copy()
        )
        df_divida = (
            df_ranking[df_ranking["__saldo"] < 0]
            .sort_values("__saldo", ascending=True)
            .head(5)
            .copy()
        )

        # formatar como moeda
        for df_temp in [top_ricos, df_divida]:
            if not df_temp.empty:
                df_temp["Conta Corrente"] = df_temp["__saldo"].map(lambda valor: f"{valor:.2f} €")
                df_temp.drop(columns="__saldo", inplace=True)

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("💎 Top 5 com maior saldo")
            if not top_ricos.empty:
                styler_ricos = top_ricos[["Escuteiro", "Conta Corrente"]].style.set_properties(
                    subset=["Conta Corrente"], **{"text-align": "center"}
                )
                st.table(styler_ricos)
            else:
                st.info("ℹ️ Nenhum escuteiro com saldo positivo.")

        with col2:
            st.subheader("🚨 Top 5 em dívida")
            if not df_divida.empty:
                styler_divida = df_divida[["Escuteiro", "Conta Corrente"]].style.set_properties(
                    subset=["Conta Corrente"], **{"text-align": "center"}
                )
                st.table(styler_divida)
            else:
                st.info("ℹ️ Nenhum escuteiro em dívida.")
    else:
        st.info("ℹ️ Não há dados suficientes para ranking.")

    # Conta Corrente
    st.divider()
    header_cols = st.columns([4, 1])
    with header_cols[0]:
        st.markdown("### 💰 Conta Corrente dos Escuteiros")

    df_cc = dados.get("Escuteiros", pd.DataFrame())
    if df_cc.empty:
        with header_cols[1]:
            st.empty()
        st.info("ℹ️ Não há movimentos financeiros registados.")
    else:
        filtro_padrao = "Todos os escuteiros"
        lista_escuteiros = sorted(
            df_cc.get("Nome do Escuteiro", pd.Series(dtype=str))
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        with header_cols[1]:
            with st.expander("Filtrar escuteiro", expanded=False, icon="🔍"):
                st.session_state.setdefault("cc_filtro_escuteiro", filtro_padrao)
                opcoes_filtro = [filtro_padrao] + lista_escuteiros
                if st.session_state["cc_filtro_escuteiro"] not in opcoes_filtro:
                    st.session_state["cc_filtro_escuteiro"] = filtro_padrao
                filtro_escolhido = st.selectbox(
                    "Escuteiro",
                    options=opcoes_filtro,
                    index=opcoes_filtro.index(st.session_state["cc_filtro_escuteiro"]),
                    key="cc_filtro_escuteiro_select",
                )
                st.session_state["cc_filtro_escuteiro"] = filtro_escolhido

        if st.session_state["cc_filtro_escuteiro"] != filtro_padrao and "Nome do Escuteiro" in df_cc.columns:
            df_cc_filtrado = df_cc[df_cc["Nome do Escuteiro"].astype(str) == st.session_state["cc_filtro_escuteiro"]]
        else:
            df_cc_filtrado = df_cc

        # Selecionar e renomear colunas
        colunas_uteis = [
            "Nome do Escuteiro",
            "Numero de Lanches",
            "Lanches",
            "Conta Corrente",
            "Valores recebidos",
            "Valor Estornado",
            "Valores doados",
            "Quota Mensal",
            "Quota Anual",
        ]
        colunas_existentes = [c for c in colunas_uteis if c in df_cc_filtrado.columns]

        df_limpo = df_cc_filtrado[colunas_existentes].rename(columns={
            "Nome do Escuteiro": "Escuteiro",
            "Numero de Lanches": "Nº de Lanches",
            "Lanches": "Valor dos Lanches",
            "Conta Corrente": "Saldo Conta Corrente",
            "Valores recebidos": "Recebimentos",
            "Valor Estornado": "Estornos",
            "Valores doados": "Doações",
        })

        # Ordenar colunas na ordem correta
        ordem = [
            "Escuteiro",
            "Nº de Lanches",
            "Valor dos Lanches",
            "Recebimentos",
            "Estornos",
            "Quota Mensal",
            "Quota Anual",
            "Doações",
            "Saldo Conta Corrente",
        ]
        df_limpo = df_limpo[[c for c in ordem if c in df_limpo.columns]]

        # Garantir que colunas numéricas mantêm tipo numérico para filtros/ordenar
        colunas_numericas = [
            "Nº de Lanches",
            "Valor dos Lanches",
            "Recebimentos",
            "Doações",
            "Estornos",
            "Quota Mensal",
            "Quota Anual",
            "Saldo Conta Corrente"
        ]
        for coluna in colunas_numericas:
            if coluna in df_limpo.columns:
                df_limpo[coluna] = pd.to_numeric(df_limpo[coluna], errors="coerce")

        if "Nº de Lanches" in df_limpo.columns:
            df_limpo["Nº de Lanches"] = df_limpo["Nº de Lanches"].astype("Int64")

        column_config = {
            "Escuteiro": st.column_config.TextColumn("Escuteiro", width="medium"),
        }
        if "Nº de Lanches" in df_limpo.columns:
            column_config["Nº de Lanches"] = st.column_config.NumberColumn("Nº de Lanches", format="%d", width="small")

        for coluna in ["Valor dos Lanches", "Recebimentos", "Estornos", "Quota Mensal", "Quota Anual", "Doações", "Saldo Conta Corrente"]:
            if coluna in df_limpo.columns:
                column_config[coluna] = st.column_config.NumberColumn(coluna, format="%.2f €", width="small")

        st.dataframe(
            df_limpo,
            use_container_width=True,
            column_config=column_config,
        )

        def _converter_valor_monetario(valor):
            if isinstance(valor, list):
                for item in valor:
                    convertido = _converter_valor_monetario(item)
                    if convertido is not None:
                        return convertido
                return None
            if isinstance(valor, (int, float)):
                return float(valor)
            if pd.isna(valor):
                return None
            texto = str(valor).strip().strip('"')
            texto = texto.replace("€", "").replace(" ", "")
            if texto.count(",") > 1 and "." not in texto:
                texto = texto.replace(".", "")
            if "," in texto and "." in texto:
                texto = texto.replace(".", "").replace(",", ".")
            elif "," in texto:
                texto = texto.replace(",", ".")
            try:
                return float(texto)
            except ValueError:
                return None

        def _criar_tabela_detalhe(mapeamento: list[tuple[str, str]], *, integer_cols: tuple[str, ...] = ()) -> pd.DataFrame:
            colunas_origem: list[str] = []
            renomear: dict[str, str] = {}
            for origem, destino in mapeamento:
                if origem in df_cc_filtrado.columns:
                    colunas_origem.append(origem)
                    renomear[origem] = destino
            if not colunas_origem:
                return pd.DataFrame()
            tabela = df_cc_filtrado[colunas_origem].rename(columns=renomear).copy()
            for coluna in tabela.columns:
                if coluna in integer_cols:
                    tabela[coluna] = pd.to_numeric(tabela[coluna], errors="coerce").astype("Int64")
                elif coluna != "Escuteiro":
                    tabela[coluna] = tabela[coluna].apply(_converter_valor_monetario)
                    tabela[coluna] = pd.to_numeric(tabela[coluna], errors="coerce")
            return tabela

        def _configuracao_detalhe(
            tabela: pd.DataFrame,
            *,
            integer_cols: tuple[str, ...] = (),
            numeric_cols: tuple[str, ...] = (),
        ) -> dict[str, Any]:
            config: dict[str, st.ColumnConfig] = {}
            if "Escuteiro" in tabela.columns:
                config["Escuteiro"] = st.column_config.TextColumn("Escuteiro", width="medium")
            for coluna in integer_cols:
                if coluna in tabela.columns:
                    config[coluna] = st.column_config.NumberColumn(coluna, format="%d", width="small")
            for coluna in numeric_cols:
                if coluna in tabela.columns:
                    config[coluna] = st.column_config.NumberColumn(coluna, format="%.2f €", width="small")
            return config

        mostrar_lanches = st.toggle(
            "Mostrar tabela detalhada de lanches",
            value=False,
            key="admin_toggle_lanches",
        )
        if mostrar_lanches:
            tabela_lanches = _criar_tabela_detalhe(
                [
                    ("Nome do Escuteiro", "Escuteiro"),
                    ("Numero de Lanches", "Nº de Lanches"),
                    ("Lanches", "Valor dos Lanches"),
                    ("Vls recebidos lanches", "Recebido (Lanches)"),
                    ("Vls Estornados Lanches", "Estornado (Lanches)"),
                    ("Saldo Lanches", "Saldo Lanches"),
                ],
                integer_cols=("Nº de Lanches",),
            )
            if tabela_lanches.empty:
                st.info("ℹ️ Não encontrei colunas de lanches na tabela de escuteiros.")
            else:
                st.dataframe(
                    tabela_lanches,
                    use_container_width=True,
                    column_config=_configuracao_detalhe(
                        tabela_lanches,
                        integer_cols=("Nº de Lanches",),
                        numeric_cols=(
                            "Valor dos Lanches",
                            "Recebido (Lanches)",
                            "Estornado (Lanches)",
                            "Saldo Lanches",
                        ),
                    ),
                )

        mostrar_quota_mensal = st.toggle(
            "Mostrar tabela detalhada de quota mensal",
            value=False,
            key="admin_toggle_quota_mensal",
        )
        if mostrar_quota_mensal:
            tabela_quota_mensal = _criar_tabela_detalhe(
                [
                    ("Nome do Escuteiro", "Escuteiro"),
                    ("Quota Mensal", "Quota Mensal Prevista"),
                    ("Vls recebidos quotas mensal", "Recebido (Quota Mensal)"),
                    ("Vls Estornados Quotas Mensal", "Estornado (Quota Mensal)"),
                    ("Saldo Quota Mensal", "Saldo Quota Mensal"),
                ]
            )
            if tabela_quota_mensal.empty:
                st.info("ℹ️ Não encontrei colunas de quota mensal na tabela de escuteiros.")
            else:
                st.dataframe(
                    tabela_quota_mensal,
                    use_container_width=True,
                    column_config=_configuracao_detalhe(
                        tabela_quota_mensal,
                        numeric_cols=(
                            "Quota Mensal Prevista",
                            "Recebido (Quota Mensal)",
                            "Estornado (Quota Mensal)",
                            "Saldo Quota Mensal",
                        ),
                    ),
                )

        mostrar_quota_anual = st.toggle(
            "Mostrar tabela detalhada de quota anual",
            value=False,
            key="admin_toggle_quota_anual",
        )
        if mostrar_quota_anual:
            tabela_quota_anual = _criar_tabela_detalhe(
                [
                    ("Nome do Escuteiro", "Escuteiro"),
                    ("Quota Anual", "Quota Anual Prevista"),
                    ("Vls recebidos quotas anual", "Recebido (Quota Anual)"),
                    ("Vls Estornados Quotas Anual", "Estornado (Quota Anual)"),
                    ("Saldo Quota Anual", "Saldo Quota Anual"),
                ]
            )
            if tabela_quota_anual.empty:
                st.info("ℹ️ Não encontrei colunas de quota anual na tabela de escuteiros.")
            else:
                st.dataframe(
                    tabela_quota_anual,
                    use_container_width=True,
                    column_config=_configuracao_detalhe(
                        tabela_quota_anual,
                        numeric_cols=(
                            "Quota Anual Prevista",
                            "Recebido (Quota Anual)",
                            "Estornado (Quota Anual)",
                            "Saldo Quota Anual",
                        ),
                    ),
                )

    # Recebimentos
    st.divider()
    st.markdown("### 🧾 Recebimentos")

    def _preparar_recebimentos(dados: dict) -> tuple[pd.DataFrame, dict[str, str], dict[str, str], dict[str, str]]:
        df_rec = dados.get("Recebimento", pd.DataFrame())
        expected_columns = ["Escuteiro", "Valor (€)", "Categoria", "Meio de Pagamento", "Data", "Responsável"]
        if df_rec is None or df_rec.empty:
            vazio = pd.DataFrame(columns=expected_columns)
            vazio["Valor (€)"] = pd.Series(dtype="float64")
            vazio["Data"] = pd.Series(dtype="datetime64[ns]")
            return vazio, {}, {}, construir_mapa_nomes_por_id(dados)

        colunas_uteis = ["Escuteiros", "Valor Recebido", "Meio de Pagamento", "Date", "Quem Recebeu?"]
        if "id" in df_rec.columns and "id" not in colunas_uteis:
            colunas_uteis.append("id")
        colunas_existentes = [col for col in colunas_uteis if col in df_rec.columns]
        if not colunas_existentes:
            vazio = pd.DataFrame(columns=expected_columns)
            vazio["Valor (€)"] = pd.Series(dtype="float64")
            vazio["Data"] = pd.Series(dtype="datetime64[ns]")
            return vazio, {}, {}, construir_mapa_nomes_por_id(dados)

        df_limpo = df_rec[colunas_existentes].copy().rename(
            columns={
                "Escuteiros": "Escuteiro",
                "Valor Recebido": "Valor (€)",
                "Meio de Pagamento": "Meio de Pagamento",
                "Date": "Data",
                "Quem Recebeu?": "Quem Recebeu",
            }
        )
        if "Meio de Pagamento" in df_limpo.columns:
            df_limpo["Meio de Pagamento"] = df_limpo["Meio de Pagamento"].apply(normalizar_valor_selecao)
        if "id" in df_limpo.columns:
            df_limpo["__record_id"] = df_limpo["id"]
            df_limpo.drop(columns=["id"], inplace=True)
        else:
            df_limpo["__record_id"] = ""

        coluna_categoria = escolher_coluna(
            df_rec,
            [
                "Tag_Recebimento",
                "Tag Recebimento",
                "Categoria",
                "Motivo",
                "Tag",
            ],
        )

        if coluna_categoria and coluna_categoria in df_rec.columns:
            def _normalizar_categoria(valor):
                if isinstance(valor, list):
                    return ", ".join(str(item) for item in valor if str(item).strip())
                return valor

            df_limpo["Categoria"] = df_rec[coluna_categoria].apply(_normalizar_categoria)

        df_escuteiros = dados.get("Escuteiros", pd.DataFrame())
        escuteiros_map: dict[str, str] = {}
        if isinstance(df_escuteiros, pd.DataFrame) and not df_escuteiros.empty and "id" in df_escuteiros.columns:
            for coluna_nome in ("Nome do Escuteiro", "Escuteiro", "Nome"):
                if coluna_nome in df_escuteiros.columns:
                    escuteiros_map = df_escuteiros.set_index("id")[coluna_nome].dropna().to_dict()
                    break

        if escuteiros_map and "Escuteiro" in df_limpo.columns:
            df_limpo["Escuteiro"] = df_limpo["Escuteiro"].apply(lambda valor: mapear_lista(valor, escuteiros_map))

        df_permissoes = dados.get("Permissoes", pd.DataFrame())
        permissoes_map: dict[str, str] = {}
        if isinstance(df_permissoes, pd.DataFrame) and not df_permissoes.empty:
            permissoes_map = construir_mapa_nomes_por_id({"Permissoes": df_permissoes})

        mapa_nomes_ids = construir_mapa_nomes_por_id(dados)

        if "Quem Recebeu" in df_limpo.columns:
            candidatos_quem_recebeu = [
                coluna
                for coluna in df_rec.columns
                if coluna not in {"Quem Recebeu?", "Quem recebeu?_OLD"} and coluna.lower().startswith("quem recebeu")
            ]

            def _score_coluna(nome_coluna: str) -> tuple[int, str]:
                nome_lower = nome_coluna.lower()
                if "nome" in nome_lower or "name" in nome_lower:
                    return (0, nome_lower)
                if "lookup" in nome_lower:
                    return (1, nome_lower)
                return (2, nome_lower)

            coluna_escolhida = None
            if candidatos_quem_recebeu:
                candidatos_quem_recebeu.sort(key=_score_coluna)
                coluna_escolhida = candidatos_quem_recebeu[0]

            if coluna_escolhida:
                df_limpo["Quem Recebeu"] = df_rec[coluna_escolhida].apply(lambda valor: mapear_lista(valor, {}))
            elif permissoes_map:
                df_limpo["Quem Recebeu"] = df_limpo["Quem Recebeu"].apply(
                    lambda valor: mapear_lista(valor, permissoes_map)
                )
            elif mapa_nomes_ids:
                df_limpo["Quem Recebeu"] = df_limpo["Quem Recebeu"].apply(
                    lambda valor: mapear_lista(valor, mapa_nomes_ids)
                )
            elif escuteiros_map:
                df_limpo["Quem Recebeu"] = df_limpo["Quem Recebeu"].apply(
                    lambda valor: mapear_lista(valor, escuteiros_map)
                )

        if "Valor (€)" in df_limpo.columns:
            df_limpo["Valor (€)"] = pd.to_numeric(df_limpo["Valor (€)"], errors="coerce")
        else:
            df_limpo["Valor (€)"] = pd.Series(dtype="float64")

        if "Data" in df_limpo.columns:
            df_limpo["Data"] = pd.to_datetime(df_limpo["Data"], errors="coerce").dt.normalize()
        else:
            df_limpo["Data"] = pd.Series(dtype="datetime64[ns]")

        if "Categoria" in df_limpo.columns:
            df_limpo["Categoria"] = df_limpo["Categoria"].apply(lambda valor: mapear_lista(valor, {}))
        else:
            df_limpo["Categoria"] = ""

        if "Quem Recebeu" in df_limpo.columns:
            df_limpo.rename(columns={"Quem Recebeu": "Responsável"}, inplace=True)
        else:
            df_limpo["Responsável"] = ""

        for coluna in ("Escuteiro", "Categoria", "Meio de Pagamento", "Responsável"):
            if coluna not in df_limpo.columns:
                df_limpo[coluna] = ""

        df_limpo = df_limpo[expected_columns + ["__record_id"]]
        return df_limpo, escuteiros_map, permissoes_map, mapa_nomes_ids

    def _normalizar_estornos(df_estornos: pd.DataFrame | None) -> pd.DataFrame:
        expected_columns = ["Escuteiro", "Valor (€)", "Categoria", "Meio de Pagamento", "Data", "Responsável"]
        if df_estornos is None or not isinstance(df_estornos, pd.DataFrame) or df_estornos.empty:
            vazio = pd.DataFrame(columns=expected_columns)
            vazio["Valor (€)"] = pd.Series(dtype="float64")
            vazio["Data"] = pd.Series(dtype="datetime64[ns]")
            return vazio

        resultado = df_estornos.copy()
        if "Valor (€)" in resultado.columns:
            resultado["Valor (€)"] = pd.to_numeric(resultado["Valor (€)"], errors="coerce")
        else:
            resultado["Valor (€)"] = pd.Series(dtype="float64")

        if "Data" in resultado.columns:
            resultado["Data"] = pd.to_datetime(resultado["Data"], errors="coerce").dt.normalize()
        else:
            resultado["Data"] = pd.Series(dtype="datetime64[ns]")

        if "Meio de Pagamento" in resultado.columns:
            resultado["Meio de Pagamento"] = resultado["Meio de Pagamento"].apply(normalizar_valor_selecao)

        for coluna in expected_columns:
            if coluna not in resultado.columns:
                if coluna == "Valor (€)":
                    resultado[coluna] = pd.Series(dtype="float64")
                elif coluna == "Data":
                    resultado[coluna] = pd.Series(dtype="datetime64[ns]")
                else:
                    resultado[coluna] = ""

        colunas_ordem = expected_columns + ["__record_id"] if "__record_id" in resultado.columns else expected_columns
        return resultado[colunas_ordem]

    def _aplicar_formatacao_display(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        display_df = df.copy()
        aux_cols = [col for col in display_df.columns if col.startswith("__")]
        if aux_cols:
            display_df = display_df.drop(columns=aux_cols)
        if "Valor (€)" in display_df.columns:
            display_df["Valor (€)"] = display_df["Valor (€)"].apply(
                lambda valor: formatar_moeda_euro(valor) if pd.notna(valor) else ""
            )
        if "Data" in display_df.columns:
            display_df["Data"] = pd.to_datetime(display_df["Data"], errors="coerce").dt.strftime("%d/%m/%Y").fillna("")
        return display_df

    def _renderizar_tabela(df_base: pd.DataFrame, mensagem_vazio: str) -> None:
        if df_base.empty:
            st.info(mensagem_vazio)
            return
        display_df = _aplicar_formatacao_display(df_base)
        column_config = {
            "Escuteiro": st.column_config.TextColumn("Escuteiro", width="medium"),
            "Valor (€)": st.column_config.TextColumn("Valor (€)", width="small"),
            "Categoria": st.column_config.TextColumn("Categoria", width="medium"),
            "Meio de Pagamento": st.column_config.TextColumn("Meio de Pagamento", width="medium"),
            "Data": st.column_config.TextColumn("Data", width="small"),
            "Responsável": st.column_config.TextColumn("Responsável", width="medium"),
        }
        if "Alterado" in display_df.columns:
            column_config["Alterado"] = st.column_config.TextColumn("Alterado", width="small")
        st.dataframe(
            display_df,
            use_container_width=True,
            column_config={col: cfg for col, cfg in column_config.items() if col in display_df.columns},
        )

    df_rec_origem = dados.get("Recebimento", pd.DataFrame())
    df_rec_limpo, escuteiros_map, permissoes_map, mapa_nomes_ids = _preparar_recebimentos(dados)
    df_estornos = _normalizar_estornos(
        preparar_dataframe_estornos(dados, escuteiros_map, permissoes_map, mapa_nomes_ids)
    )

    def _obter_opcoes_meio_pagamento(df_origem: pd.DataFrame) -> list[str]:
        cache_key = f"meios_pagamento_{BASE_ID}"
        cache_color_key = f"meios_pagamento_cores_{BASE_ID}"
        if cache_key in st.session_state:
            opcoes_cache = st.session_state.get(cache_key, [])
            if isinstance(opcoes_cache, list) and opcoes_cache:
                return opcoes_cache

        opcoes: list[str] = []
        cores: dict[str, dict[str, str]] = {}
        try:
            schema = api.meta.base_schema(BASE_ID)
            for tabela in schema.get("tables", []):
                if tabela.get("name") != "Recebimento":
                    continue
                for campo in tabela.get("fields", []):
                    if campo.get("name") == "Meio de Pagamento" and campo.get("type") == "singleSelect":
                        choices = campo.get("options", {}).get("choices", [])
                        opcoes = []
                        for choice in choices:
                            nome = str(choice.get("name", "")).strip()
                            if not nome:
                                continue
                            opcoes.append(nome)
                            bg, fg = _map_airtable_color(choice.get("color"))
                            cores[nome] = {"bg": bg, "fg": fg}
                        break
                if opcoes:
                    break
        except Exception:
            opcoes = []

        if not opcoes and isinstance(df_origem, pd.DataFrame) and not df_origem.empty:
            if "Meio de Pagamento" in df_origem.columns:
                valores = (
                    df_origem["Meio de Pagamento"]
                    .dropna()
                    .apply(lambda valor: valor[0] if isinstance(valor, list) and valor else valor)
                )
                opcoes = sorted({str(valor).strip() for valor in valores if str(valor).strip()})
                for nome in opcoes:
                    if nome not in cores:
                        bg, fg = _map_airtable_color(None)
                        cores[nome] = {"bg": bg, "fg": fg}

        st.session_state[cache_key] = opcoes
        st.session_state[cache_color_key] = cores
        return opcoes

    periodo_key = "tesouraria_periodo_movimentos"
    hoje = pd.Timestamp.today().date()
    periodo_padrao: tuple[date, date] = (hoje, hoje)

    def _converter_para_date(valor):
        if isinstance(valor, date):
            return valor
        if isinstance(valor, datetime):
            return valor.date()
        if isinstance(valor, pd.Timestamp):
            return valor.date()
        return None

    def _normalizar_periodo(valor):
        if isinstance(valor, (tuple, list)):
            valores = [_converter_para_date(item) for item in valor]
            valores = [item for item in valores if item is not None]
        else:
            item = _converter_para_date(valor)
            valores = [item] if item is not None else []

        if len(valores) >= 2:
            inicio, fim = valores[0], valores[1]
        elif len(valores) == 1:
            inicio = fim = valores[0]
        else:
            inicio, fim = periodo_padrao

        if inicio > fim:
            inicio, fim = fim, inicio
        return inicio, fim

    def _periodo_mes_atual(referencia: date) -> tuple[date, date]:
        primeiro_dia = date(referencia.year, referencia.month, 1)
        if referencia.month == 12:
            proximo_mes = date(referencia.year + 1, 1, 1)
        else:
            proximo_mes = date(referencia.year, referencia.month + 1, 1)
        return primeiro_dia, proximo_mes - timedelta(days=1)

    periodo_atual = _normalizar_periodo(st.session_state.get(periodo_key, periodo_padrao))

    st.markdown("### 📊 Posição de Caixa")

    filtro_cols = st.columns([2, 3])
    novo_periodo: tuple[date, date] | None = None

    atalhos_periodo = {
        "Hoje": lambda referencia: (referencia, referencia),
        "Últimos 3 dias": lambda referencia: (referencia - timedelta(days=2), referencia),
        "Esta semana": lambda referencia: (
            referencia - timedelta(days=referencia.weekday()),
            min(referencia - timedelta(days=referencia.weekday()) + timedelta(days=6), referencia),
        ),
        "Este mês": _periodo_mes_atual,
    }

    with filtro_cols[1]:
        botoes = st.columns(len(atalhos_periodo))
        funcao_selecionada = None
        for (rotulo, funcao_periodo), coluna in zip(atalhos_periodo.items(), botoes):
            if coluna.button(rotulo, use_container_width=True):
                funcao_selecionada = funcao_periodo
        if funcao_selecionada is not None:
            novo_periodo = funcao_selecionada(hoje)

    valor_inicial = novo_periodo or periodo_atual
    with filtro_cols[0]:
        periodo_escolhido = st.date_input(
            "Intervalo personalizado",
            value=valor_inicial,
            format="DD/MM/YYYY",
        )

    periodo_atual = _normalizar_periodo(novo_periodo if novo_periodo is not None else periodo_escolhido)
    st.session_state[periodo_key] = periodo_atual

    data_inicio, data_fim = periodo_atual
    data_inicio_ts = pd.Timestamp(data_inicio)
    data_fim_ts = pd.Timestamp(data_fim)

    df_rec_periodo = df_rec_limpo[df_rec_limpo["Data"].between(data_inicio_ts, data_fim_ts, inclusive="both")].copy()
    df_rec_periodo.sort_values("Data", ascending=False, inplace=True)

    df_estornos_periodo = df_estornos[df_estornos["Data"].between(data_inicio_ts, data_fim_ts, inclusive="both")].copy()
    df_estornos_periodo.sort_values("Data", ascending=False, inplace=True)

    total_recebimentos = df_rec_periodo["Valor (€)"].sum()
    total_estornos = df_estornos_periodo["Valor (€)"].sum()
    saldo = total_recebimentos - total_estornos

    st.markdown("#### 🧾 Recebimentos")
    mensagem_sucesso_receb = st.session_state.pop("recebimentos_success_message", None)
    avisos_receb = st.session_state.pop("recebimentos_warning_messages", None)
    if mensagem_sucesso_receb:
        st.success(mensagem_sucesso_receb)
    if avisos_receb:
        for aviso in avisos_receb:
            st.warning(aviso)

    meios_pagamento_opcoes = _obter_opcoes_meio_pagamento(df_rec_origem)
    pode_editar_recebimentos = (is_admin or is_tesoureiro) and not df_rec_periodo.empty
    modo_edicao_receb = False
    if pode_editar_recebimentos:
        modo_edicao_receb = st.toggle(
            "Editar meios de pagamento",
            value=False,
            key="toggle_recebimentos_meio_pagamento",
        )
        if modo_edicao_receb and not meios_pagamento_opcoes:
            st.warning("Não foi possível obter as opções de meio de pagamento. Edite diretamente no Airtable.")
            modo_edicao_receb = False

    mensagem_recebimentos = (
        "ℹ️ Não há recebimentos registados."
        if df_rec_origem is None or df_rec_origem.empty
        else "ℹ️ Nenhum recebimento no período selecionado."
    )

    recentes_ids = set(st.session_state.get("recebimentos_recent_ids", []))
    df_recebimentos_display = df_rec_periodo.copy()
    if recentes_ids and not df_recebimentos_display.empty:
        df_recebimentos_display["Alterado"] = df_recebimentos_display["__record_id"].apply(
            lambda rid: "Alterado" if rid in recentes_ids else ""
        )

    if pode_editar_recebimentos and modo_edicao_receb and not df_rec_periodo.empty:
        base_editor = df_rec_periodo.copy()
        dataset_editor = base_editor.copy()
        if "__record_id" not in dataset_editor.columns:
            st.warning("Não foi possível identificar os registos para edição.")
        else:
            color_cache_key = f"meios_pagamento_cores_{BASE_ID}"
            color_map = st.session_state.get(color_cache_key, {}) or {}
            if meios_pagamento_opcoes and not color_map:
                padrao_bg, padrao_fg = _map_airtable_color(None)
                color_map = {
                    opcao: {"bg": padrao_bg, "fg": padrao_fg}
                    for opcao in meios_pagamento_opcoes
                }

            color_map_js = json.dumps(color_map)
            color_style_js = JsCode(
                """
                function(params) {
                    const mapa = %s;
                    const valor = params.value || '';
                    const meta = mapa[valor];
                    if (!meta) {
                        return {};
                    }
                    return {
                        'backgroundColor': meta.bg,
                        'color': meta.fg,
                        'fontWeight': '600',
                        'borderRadius': '6px'
                    };
                }
                """
                % color_map_js
            ) if color_map else None

            color_renderer_js = JsCode(
                """
                function(params) {
                    const mapa = %s;
                    const valor = params.value || '';
                    const meta = mapa[valor];
                    if (!meta) {
                        return valor;
                    }
                    return `<span style="display:inline-flex;align-items:center;padding:0 6px;border-radius:6px;background-color:${meta.bg};color:${meta.fg};font-weight:600;">${valor}</span>`;
                }
                """
                % color_map_js
            ) if color_map else None

            gob = GridOptionsBuilder.from_dataframe(dataset_editor)
            gob.configure_default_column(editable=False, resizable=True)
            gob.configure_column("__record_id", header_name="Record ID", editable=False, hide=True)

            for coluna in dataset_editor.columns:
                if coluna not in {"Meio de Pagamento", "__record_id"}:
                    gob.configure_column(coluna, editable=False)

            parametros_editor = {"values": meios_pagamento_opcoes}
            if color_renderer_js is not None:
                parametros_editor["cellRenderer"] = color_renderer_js

            gob.configure_column(
                "Meio de Pagamento",
                editable=True,
                cellEditor="agRichSelectCellEditor",
                cellEditorParams=parametros_editor,
                cellRenderer=color_renderer_js,
                cellStyle=color_style_js,
            )
            grid_options = gob.build()

            grid_response = None
            with st.form("form_editar_meio_pagamento"):
                grid_response = AgGrid(
                    dataset_editor,
                    gridOptions=grid_options,
                    height=320,
                    fit_columns_on_grid_load=True,
                    update_mode=GridUpdateMode.VALUE_CHANGED,
                    data_return_mode=DataReturnMode.AS_INPUT,
                    allow_unsafe_jscode=True,
                    theme="balham",
                    key="aggrid_recebimentos",
                )
                gravar = st.form_submit_button("💾 Guardar alterações")

            if gravar:
                dados_grid = grid_response.get("data") if grid_response else None
                df_editado = pd.DataFrame(dados_grid or [])
                if df_editado.empty:
                    st.info("Não foram detetadas alterações.")
                elif "__record_id" not in df_editado.columns:
                    st.error("Os dados devolvidos pelo editor não contêm o identificador do registo.")
                else:
                    mapa_original = df_rec_periodo.set_index("__record_id")["Meio de Pagamento"]
        
                    alteracoes: list[tuple[str, str, str]] = []
                    for _, linha in df_editado.iterrows():
                        record_id = linha.get("__record_id", "")
                        if not record_id:
                            continue
                        valor_novo = linha.get("Meio de Pagamento", "")
                        valor_antigo = mapa_original.get(record_id, "")
                        if pd.isna(valor_antigo):
                            valor_antigo = ""
                        if pd.isna(valor_novo):
                            valor_novo = ""
                        valor_antigo_str = str(valor_antigo).strip()
                        valor_novo_str = str(valor_novo).strip()
                        if valor_antigo_str != valor_novo_str:
                            alteracoes.append((record_id, valor_antigo_str, valor_novo_str))
        
                    if not alteracoes:
                        st.info("Não foram detetadas alterações.")
                    else:
                        tabela_receb = api.table(BASE_ID, "Recebimento")
                        tabela_audit = api.table(BASE_ID, "Audit Log")
                        ids_sucesso: list[str] = []
                        erros: list[str] = []
                        utilizador_atual = st.session_state.get("user", {}).get("email", "")
        
                        for record_id, valor_antigo, valor_novo in alteracoes:
                            try:
                                tabela_receb.update(record_id, {"Meio de Pagamento": valor_novo})
                                ids_sucesso.append(record_id)
                            except Exception as exc:
                                erros.append(f"{record_id}: {exc}")
                                continue
        
                            try:
                                tabela_audit.create(
                                    {
                                        "Tabela Alterada": "Recebimento",
                                        "ID do Registo": record_id,
                                        "Data da Mudança": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                                        "Informação Antes": f"Meio de Pagamento: {valor_antigo or '-'}",
                                        "Informação Depois": f"Meio de Pagamento: {valor_novo or '-'}",
                                        "Mudança Resumida (AI)": f"Alterado de {valor_antigo or '-'} para {valor_novo or '-'}",
                                        "Usuário": utilizador_atual or "desconhecido",
                                        "Origem da Mudança": "Streamlit",
                                    }
                                )
                            except Exception as exc:
                                erros.append(f"{record_id} (Audit Log): {exc}")
        
                            time.sleep(0.2)
        
                        if ids_sucesso:
                            recentes = set(st.session_state.get("recebimentos_recent_ids", []))
                            recentes.update(ids_sucesso)
                            st.session_state["recebimentos_recent_ids"] = list(recentes)
                            st.session_state["recebimentos_success_message"] = "✅ Alterações guardadas com sucesso."
                        if erros:
                            st.session_state.setdefault("recebimentos_warning_messages", []).extend(erros)
                        st.rerun()
    else:
        _renderizar_tabela(df_recebimentos_display, mensagem_recebimentos)

    df_audit_log = dados.get("Audit Log", pd.DataFrame())
    if (
        not df_rec_periodo.empty
        and isinstance(df_audit_log, pd.DataFrame)
        and not df_audit_log.empty
        and "ID do Registo" in df_audit_log.columns
    ):
        df_audit_receb = df_audit_log[df_audit_log.get("Tabela Alterada") == "Recebimento"].copy()
        if not df_audit_receb.empty:
            if "Data da Mudança" in df_audit_receb.columns:
                df_audit_receb["Data da Mudança"] = pd.to_datetime(
                    df_audit_receb["Data da Mudança"], errors="coerce"
                )

            label_por_registo: dict[str, str] = {}
            for _, linha in df_rec_periodo.iterrows():
                rid = linha.get("__record_id", "")
                if not rid or rid in label_por_registo:
                    continue
                escuteiro = str(linha.get("Escuteiro") or "").strip() or "Sem nome"
                data_linha = linha.get("Data")
                if isinstance(data_linha, pd.Timestamp):
                    data_txt = data_linha.strftime("%d/%m/%Y")
                elif isinstance(data_linha, datetime):
                    data_txt = data_linha.strftime("%d/%m/%Y")
                else:
                    data_txt = ""
                sufixo = f" · {data_txt}" if data_txt else ""
                label_por_registo[rid] = f"{escuteiro}{sufixo}"

            opcoes_hist = [rid for rid in df_rec_periodo["__record_id"].dropna().unique().tolist() if rid]
            if opcoes_hist:
                col_hist_select, col_hist_button = st.columns([4, 1])
                with col_hist_select:
                    registo_hist = st.selectbox(
                        "Ver histórico de alterações",
                        options=opcoes_hist,
                        format_func=lambda rid: label_por_registo.get(rid, rid),
                        key="historico_recebimentos_select",
                    )

                with col_hist_button:
                    ver_hist = st.button("ℹ Histórico", key="historico_recebimentos_button", use_container_width=True)

                if registo_hist and ver_hist:
                    historico_registo = (
                        df_audit_receb[df_audit_receb["ID do Registo"] == registo_hist]
                        .sort_values("Data da Mudança", ascending=False)
                        .head(3)
                        .copy()
                    )

                    def _renderizar_historico() -> None:
                        if historico_registo.empty:
                            st.info("Não há registos de histórico para este recebimento.")
                            return
                        if "Data da Mudança" in historico_registo.columns:
                            historico_registo["Data da Mudança"] = historico_registo["Data da Mudança"].dt.strftime(
                                "%d/%m/%Y %H:%M"
                            )
                        colunas_hist = [
                            coluna
                            for coluna in [
                                "Data da Mudança",
                                "Informação Antes",
                                "Informação Depois",
                                "Usuário",
                                "Origem da Mudança",
                            ]
                            if coluna in historico_registo.columns
                        ]
                        st.dataframe(historico_registo[colunas_hist], use_container_width=True)

                    if hasattr(st, "popover"):
                        with st.popover("Histórico de alterações"):
                            _renderizar_historico()
                    else:
                        with st.expander("Histórico de alterações", expanded=True):
                            _renderizar_historico()

    st.markdown("### ↩️ Estornos de Recebimento")
    if df_estornos.empty:
        st.info("ℹ️ Nenhum estorno registado.")
    else:
        _renderizar_tabela(df_estornos_periodo, "ℹ️ Nenhum estorno no período selecionado.")

    st.caption(
        f"Período selecionado: {data_inicio_ts.strftime('%d/%m/%Y')} - {data_fim_ts.strftime('%d/%m/%Y')}"
    )

    col_metricas = st.columns(3)
    col_metricas[0].metric("Recebido no período", formatar_moeda_euro(total_recebimentos))
    col_metricas[1].metric("Estornado no período", formatar_moeda_euro(total_estornos))
    col_metricas[2].metric("Saldo do período", formatar_moeda_euro(saldo))

    def _pertence_categoria(valor, alvo: str) -> bool:
        if pd.isna(valor):
            return False
        alvo_norm = alvo.strip().lower()
        if isinstance(valor, str):
            partes = [parte.strip().lower() for parte in valor.split(",") if parte.strip()]
            return alvo_norm in partes
        if isinstance(valor, (list, tuple, set)):
            return any(_pertence_categoria(item, alvo_norm) for item in valor)
        return str(valor).strip().lower() == alvo_norm

    def _total_por_categoria(df_referencia: pd.DataFrame, categoria: str) -> float:
        if df_referencia.empty or "Categoria" not in df_referencia.columns or "Valor (€)" not in df_referencia.columns:
            return 0.0
        mask = df_referencia["Categoria"].apply(lambda valor: _pertence_categoria(valor, categoria))
        if mask.any():
            return float(df_referencia.loc[mask, "Valor (€)"].sum())
        return 0.0

    categorias_destacadas = [
        ({"lanches"}, "🥪 Lanches"),
        ({"quota mensal", "cota mensal"}, "🗓️ Quota Mensal"),
        ({"quota anual", "cota anual"}, "📅 Quota Anual"),
    ]

    st.markdown("##### Detalhe por categoria")
    cols_categorias = st.columns(len(categorias_destacadas))
    for (chaves_categoria, label_categoria), coluna in zip(categorias_destacadas, cols_categorias):
        recebido_categoria = sum(_total_por_categoria(df_rec_periodo, chave) for chave in chaves_categoria)
        estornado_categoria = sum(_total_por_categoria(df_estornos_periodo, chave) for chave in chaves_categoria)
        saldo_categoria = recebido_categoria - estornado_categoria
        with coluna:
            coluna.metric(
                label_categoria,
                formatar_moeda_euro(saldo_categoria),
                delta=(
                    f"Recebido {formatar_moeda_euro(recebido_categoria)} · "
                    f"Estornado {formatar_moeda_euro(estornado_categoria)}"
                ),
                delta_color="off",
            )

def dashboard_admin(dados: dict):
    st.markdown("## 👑 Dashboard Admin")

    def refrescar_dados():
        st.session_state["dados_cache"] = carregar_todas_as_tabelas(BASE_ID, role)
        st.session_state["last_update"] = datetime.now()

    df_pedidos = dados.get("Pedidos", pd.DataFrame())
    df_calendario = dados.get("Calendario", pd.DataFrame())
    df_volunt = dados.get("Voluntariado Pais", pd.DataFrame())
    df_receb = dados.get("Recebimento", pd.DataFrame())
    df_esc = dados.get("Escuteiros", pd.DataFrame())
    df_recipes = dados.get("Recipes", pd.DataFrame())
    df_quotas = dados.get("Quotas", pd.DataFrame())
    df_tipo_cotas = dados.get("Tipo de Cotas", pd.DataFrame())

    hoje = pd.Timestamp.today().normalize()

    recipes_map = {}
    if df_recipes is not None and not df_recipes.empty and "id" in df_recipes.columns:
        recipes_map = (
            df_recipes.set_index("id")
            .get("Menu", pd.Series(dtype=str))
            .dropna()
            .to_dict()
        )

    escuteiros_map = {}
    if df_esc is not None and not df_esc.empty and "id" in df_esc.columns:
        escuteiros_map = (
            df_esc.set_index("id")
            .get("Nome do Escuteiro", pd.Series(dtype=str))
            .dropna()
            .to_dict()
        )

    def _ensure_checkbox(df_like: pd.DataFrame, coluna: str) -> pd.Series:
        if coluna not in df_like.columns:
            return pd.Series(False, index=df_like.index, dtype=bool)
        serie = df_like[coluna]
        if pd.api.types.is_bool_dtype(serie):
            return serie.fillna(False)
        return serie.fillna(False).astype(str).str.lower().eq("true")

    def _preparar_df_pedidos(df_like: pd.DataFrame) -> pd.DataFrame:
        df_display = df_like.copy()
        if df_display.empty:
            return df_display
        if "Date" in df_display.columns:
            df_display["Date"] = pd.to_datetime(df_display["Date"], errors="coerce").dt.strftime("%d/%m/%Y")
        if "Escuteiros" in df_display.columns:
            df_display["Escuteiros"] = df_display["Escuteiros"].apply(lambda v: mapear_lista(v, escuteiros_map))
        for coluna in ["Lanche", "Bebida", "Fruta"]:
            if coluna in df_display.columns:
                df_display[coluna] = df_display[coluna].apply(lambda v: mapear_lista(v, recipes_map))
        if "Senha_marcações" in df_display.columns:
            df_display["Senha_marcações"] = df_display["Senha_marcações"].fillna("")
        colunas_exibicao = [
            c
            for c in ["Date", "Escuteiros", "Lanche", "Bebida", "Fruta", "Senha_marcações"]
            if c in df_display.columns
        ]
        return df_display[colunas_exibicao]

    def _first_existing_col(df_like, candidates):
        for col_name in candidates:
            if col_name in df_like.columns:
                return col_name
        return None

    tipo_cotas_map: dict[str, str] = {}
    if df_tipo_cotas is not None and not df_tipo_cotas.empty and "id" in df_tipo_cotas.columns:
        col_tipo_nome = _first_existing_col(
            df_tipo_cotas,
            [
                "Tipo de Quotas",
                "Tipo de Cotas",
                "Nome",
                "Name",
                "Tipo",
                "Descrição",
            ],
        )
        if col_tipo_nome:
            serie_map = df_tipo_cotas.set_index("id")[col_tipo_nome].dropna()
            tipo_cotas_map = {str(idx): str(valor) for idx, valor in serie_map.items()}

    def _find_column_keywords(df_like: pd.DataFrame, keyword_groups: list[tuple[str, ...]]):
        if df_like is None or df_like.empty:
            return None
        for keywords in keyword_groups:
            tokens = [_normalizar_texto(token) for token in keywords if token]
            if not tokens:
                continue
            for coluna in df_like.columns:
                nome_norm = _normalizar_texto(coluna)
                if all(token in nome_norm for token in tokens):
                    return coluna
        return None

    def _preparar_df_quotas(df_like: pd.DataFrame) -> pd.DataFrame:
        base_columns = [
            "Data da cobrança",
            "Escuteiro",
            "Valor",
            "__tipo",
            "__tipo_label",
            "__data",
            "__periodo_label",
        ]
        if df_like is None or df_like.empty:
            vazio = pd.DataFrame(columns=base_columns)
            vazio["Valor"] = pd.Series(dtype="float64")
            return vazio

        df_display = df_like.copy()

        tipo_col = _first_existing_col(
            df_display,
            [
                "Tipo",
                "Tipo de Quota",
                "Tipo da Quota",
                "Tipo de Cota",
                "Categoria",
                "Tipo de Pagamento",
            ],
        )
        if not tipo_col:
            tipo_col = _find_column_keywords(
                df_display,
                [
                    ("tipo", "quota"),
                    ("tipo",),
                ],
            )

        periodo_col = _first_existing_col(
            df_display,
            [
                "Quota_periodo",
                "Quota Periodo",
                "Quota Período",
                "Quota período",
                "Quota - Período",
                "Período",
            ],
        )
        if not periodo_col:
            periodo_col = _find_column_keywords(
                df_display,
                [
                    ("quota", "periodo"),
                    ("quota", "período"),
                    ("periodo",),
                ],
            )
        if not periodo_col and tipo_col:
            periodo_col = tipo_col

        def _stringify(valor, *, map_tipo: bool = False) -> str:
            if isinstance(valor, list):
                valores = []
                for item in valor:
                    texto_item = _stringify(item, map_tipo=map_tipo)
                    if texto_item:
                        valores.append(texto_item)
                return ", ".join(valores)
            if pd.isna(valor):
                return ""
            texto = str(valor).strip()
            if map_tipo:
                return tipo_cotas_map.get(texto, texto)
            return texto

        if tipo_col:
            df_display["__tipo_label"] = df_display[tipo_col].apply(lambda v: _stringify(v, map_tipo=True))
        else:
            df_display["__tipo_label"] = ""

        if periodo_col:
            df_display["__periodo_label"] = df_display[periodo_col].apply(
                lambda v: _stringify(v, map_tipo=periodo_col == tipo_col)
            )
        elif tipo_col:
            df_display["__periodo_label"] = df_display["__tipo_label"]
        else:
            df_display["__periodo_label"] = pd.Series("", index=df_display.index, dtype="object")

        def _detectar_tipo(texto: str) -> str:
            texto_norm = _normalizar_texto(texto)
            if "mens" in texto_norm:
                return "mensal"
            if "anu" in texto_norm:
                return "anual"
            return ""

        df_display["__tipo"] = df_display["__tipo_label"].apply(_detectar_tipo)
        if df_display["__tipo"].eq("").any():
            mascara_sem_tipo = df_display["__tipo"].eq("")
            df_display.loc[mascara_sem_tipo, "__tipo"] = df_display.loc[mascara_sem_tipo, "__periodo_label"].apply(
                _detectar_tipo
            )

        data_col = _first_existing_col(
            df_display,
            [
                "Data da Cobrança",
                "Data da cobrança",
                "Data cobrança",
                "Data de Cobrança",
                "Data de cobrança",
                "Data",
            ],
        )
        if not data_col:
            data_col = _find_column_keywords(
                df_display,
                [
                    ("data", "cobranca"),
                    ("data", "cobrança"),
                    ("data",),
                ],
            )
        if data_col:
            df_display["__data"] = pd.to_datetime(df_display[data_col], errors="coerce")
            df_display["Data da cobrança"] = df_display["__data"].dt.strftime("%d/%m/%Y")
        else:
            df_display["__data"] = pd.to_datetime(df_display.get("Data da cobrança"), errors="coerce")
            if "Data da cobrança" in df_display.columns:
                df_display["Data da cobrança"] = df_display["Data da cobrança"].fillna("").astype(str)
            else:
                df_display["Data da cobrança"] = ""

        esc_col = _first_existing_col(
            df_display,
            [
                "Escuteiro",
                "Escuteiros",
                "Nome do Escuteiro",
                "Nome do Escuteiro (from Escuteiros)",
                "Responsável",
            ],
        )
        if not esc_col:
            esc_col = _find_column_keywords(
                df_display,
                [
                    ("escuteiro",),
                    ("nome", "escuteiro"),
                ],
            )
        if esc_col:
            df_display["Escuteiro"] = df_display[esc_col].apply(lambda v: mapear_lista(v, escuteiros_map))
        else:
            df_display["Escuteiro"] = df_display.get("Escuteiro", "").fillna("").astype(str)

        def _parse_valor(valor):
            if isinstance(valor, list):
                for item in valor:
                    resultado = _parse_valor(item)
                    if resultado is not None:
                        return resultado
                return None
            if isinstance(valor, (int, float)):
                return float(valor)
            if pd.isna(valor):
                return None
            texto = str(valor).strip().strip('"')
            texto = texto.replace("€", "").replace(" ", "")
            if texto.count(",") > 1 and "." not in texto:
                texto = texto.replace(".", "")
            if "," in texto and "." in texto:
                texto = texto.replace(".", "").replace(",", ".")
            elif "," in texto:
                texto = texto.replace(",", ".")
            try:
                return float(texto)
            except ValueError:
                return None

        valor_col = _first_existing_col(
            df_display,
            [
                "Valor",
                "Valor (€)",
                "Valor da Quota",
                "Valor da quota",
                "Valor de Cobrança",
                "Valor Recebido",
            ],
        )
        if not valor_col:
            valor_col = _find_column_keywords(
                df_display,
                [
                    ("valor",),
                    ("montante",),
                ],
            )
        if valor_col:
            df_display["Valor"] = df_display[valor_col].apply(_parse_valor)
        else:
            df_display["Valor"] = pd.Series(dtype="float64", index=df_display.index)

        resultado = df_display[
            ["Data da cobrança", "Escuteiro", "Valor", "__tipo", "__tipo_label", "__data", "__periodo_label"]
        ].copy()
        resultado["__tipo"] = resultado["__tipo"].fillna("")
        resultado["__tipo_label"] = resultado["__tipo_label"].fillna("")
        resultado["__periodo_label"] = resultado["__periodo_label"].fillna("")
        return resultado

    aba_resumo, aba_formularios, aba_pedidos, aba_quotas, aba_eventos = st.tabs(
        ["📊 Resumo", "📝 Formulários", "📦 Pedidos", "💶 Quotas", "📅 Eventos"]
    )

    with aba_formularios:
        st.markdown("### 📝 Ações rápidas")
        acoes_admin = mostrar_barra_acoes(
            [
                ("🚫 Cancelar lanche (forçado)", "btn_admin_cancelar"),
                ("📝 Novo pedido (forçado)", "btn_admin_pedido"),
                ("🧒 Gestão de escuteiro", "btn_admin_escuteiro"),
            ]
        )
        st.caption("Use estas ações apenas em casos excecionais; os formulários abrem em modo forçado.")

        if acoes_admin.get("btn_admin_cancelar"):
            st.session_state["mostrar_form_registo"] = True
        if acoes_admin.get("btn_admin_pedido"):
            st.session_state["mostrar_form_pedido"] = True
        if acoes_admin.get("btn_admin_escuteiro"):
            st.session_state["mostrar_form_escuteiro"] = True

        mostrar_formulario(
            session_key="mostrar_form_registo",
            titulo="### 🗂️ Cancelamento de Lanche (Forçado)",
            iframe_url=obter_form_url("FORCED_CANCEL_FORM_URL", "Cancelamento de Lanche (forçado)"),
            iframe_height=533,
            container_height=600,
            wrapper="expander",
            expander_label="🗂️ Cancelamento de Lanche (Forçado)",
            expander_expanded=True,
        )

        mostrar_formulario(
            session_key="mostrar_form_pedido",
            titulo="### 📝 Forçar Novo Pedido",
            iframe_url=obter_form_url("FORCED_ORDER_FORM_URL", "Forçar novo pedido"),
            iframe_height=533,
            container_height=600,
            wrapper="expander",
            expander_label="📝 Forçar Novo Pedido",
            expander_expanded=True,
        )

        mostrar_formulario(
            session_key="mostrar_form_escuteiro",
            titulo="### 🧒 Gestão de Escuteiros",
            iframe_url=obter_form_url("MANAGE_ESCUTEIROS_FORM_URL", "Gestão de Escuteiros"),
            iframe_height=533,
            container_height=600,
            wrapper="expander",
            expander_label="🧒 Gestão de Escuteiros",
            expander_expanded=True,
        )

    with aba_resumo:
        st.markdown("### 📊 Visão rápida")

        pendentes_cancel = 0
        if not df_pedidos.empty:
            pendentes_cancel = int(_ensure_checkbox(df_pedidos, "Pendente de Cancelamento").sum())

        eventos_proximos = 0
        if not df_calendario.empty and "Data" in df_calendario.columns:
            datas = pd.to_datetime(df_calendario["Data"], errors="coerce")
            eventos_proximos = ((datas >= hoje) & (datas <= hoje + pd.Timedelta(days=30))).sum()

        voluntariado_em_falta = 0
        total_turnos_preparacao = 0
        turnos_com_voluntario = 0
        col_preparacao = "Haverá preparação de Lanches?"
        col_voluntarios = "Voluntariado Pais"
        if not df_calendario.empty and col_preparacao in df_calendario.columns:
            df_cal_check = df_calendario.copy()
            if "Data" in df_cal_check.columns:
                df_cal_check["__data"] = pd.to_datetime(df_cal_check["Data"], errors="coerce")
                df_cal_check = df_cal_check[df_cal_check["__data"].isna() | (df_cal_check["__data"] >= hoje)]
            df_cal_check = df_cal_check[df_cal_check[col_preparacao].apply(lambda v: isinstance(v, bool) and v)]
            total_turnos_preparacao = len(df_cal_check)

            def _tem_voluntarios(valor) -> bool:
                if isinstance(valor, list):
                    return any(str(item).strip() for item in valor)
                if pd.isna(valor):
                    return False
                return bool(str(valor).strip())

            if total_turnos_preparacao:
                if col_voluntarios in df_cal_check.columns:
                    faltam_series = df_cal_check[col_voluntarios].apply(lambda v: not _tem_voluntarios(v))
                    voluntariado_em_falta = int(faltam_series.sum())
                    turnos_com_voluntario = int(total_turnos_preparacao - voluntariado_em_falta)
                else:
                    voluntariado_em_falta = len(df_cal_check)
                    turnos_com_voluntario = 0

        with st.container(border=True):
            st.markdown("#### Pedidos e lanches")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Cancelamentos pendentes", int(pendentes_cancel))
            with col2:
                st.metric("Lanches (próx. 30 dias)", int(eventos_proximos))

        if total_turnos_preparacao:
            cobertura_percent = (turnos_com_voluntario / total_turnos_preparacao) * 100
            cobertura_texto = f"{cobertura_percent:.0f}%"
            cobertura_delta = f"{turnos_com_voluntario}/{total_turnos_preparacao} com voluntario"
        else:
            cobertura_texto = "N/A"
            cobertura_delta = None

        with st.container(border=True):
            st.markdown("#### Voluntariado")
            col3, col4 = st.columns(2)
            with col3:
                st.metric("Lanches sem voluntário", int(voluntariado_em_falta))
            with col4:
                st.metric(
                    "Cobertura de voluntariado",
                    cobertura_texto,
                    delta=cobertura_delta,
                    help="Lanches com voluntario / lanches com preparacao agendada nos próximos 30 dias.",
                )

        st.markdown("### 🧾 Registos recentes")
        with st.container(border=True):
            col_a, col_b, col_c = st.columns(3)
            if not df_pedidos.empty and "Created" in df_pedidos.columns:
                df_recent = df_pedidos.sort_values("Created", ascending=False).head(5).copy()
                if "Escuteiros" in df_recent.columns:
                    df_recent["Escuteiros"] = df_recent["Escuteiros"].apply(lambda v: mapear_lista(v, escuteiros_map))
                if "Senha_marcações" in df_recent.columns:
                    df_recent["Senha_marcações"] = df_recent["Senha_marcações"].fillna("")
                for coluna in ["Lanche", "Bebida", "Fruta"]:
                    if coluna in df_recent.columns:
                        df_recent[coluna] = df_recent[coluna].apply(lambda v: mapear_lista(v, recipes_map))
                cols = [
                    c
                    for c in ["Created", "Escuteiros", "Lanche", "Bebida", "Fruta", "Senha_marcações"]
                    if c in df_recent.columns
                ]
                with col_a:
                    st.caption("Pedidos")
                    st.dataframe(df_recent[cols], use_container_width=True, hide_index=True)
            if not df_receb.empty and "Created" in df_receb.columns:
                df_recent_rec = df_receb.sort_values("Created", ascending=False).head(5)
                cols = [
                    c
                    for c in ["Created", "Nome do Escuteiro", "Valor Recebido", "Meio de Pagamento"]
                    if c in df_recent_rec.columns
                ]
                with col_b:
                    st.caption("Recebimentos")
                    st.dataframe(df_recent_rec[cols], use_container_width=True, hide_index=True)
            if not df_esc.empty and "Created" in df_esc.columns:
                df_recent_esc = df_esc.sort_values("Created", ascending=False).head(5)
                cols = [
                    c
                    for c in ["Created", "Nome do Escuteiro", "Email", "Status Inativo"]
                    if c in df_recent_esc.columns
                ]
                with col_c:
                    st.caption("Escuteiros")
                    st.dataframe(df_recent_esc[cols], use_container_width=True, hide_index=True)

    with aba_pedidos:
        st.markdown("### ⚠️ Pedidos com pedidos de cancelamento")
        if df_pedidos.empty:
            st.info("Nenhum pedido pendente.")
        else:
            pendentes_mask = _ensure_checkbox(df_pedidos, "Pendente de Cancelamento")
            cancelados_mask = _ensure_checkbox(df_pedidos, "Cancelado?")

            df_pend = df_pedidos[pendentes_mask & (~cancelados_mask)].copy()
            df_cancelados = df_pedidos[cancelados_mask].copy()
            df_todos = df_pedidos.copy()

            df_pend_display = _preparar_df_pedidos(df_pend)
            if df_pend_display.empty:
                st.info("Nenhum pedido pendente.")
            else:
                st.dataframe(df_pend_display, use_container_width=True, hide_index=True)

            mostrar_cancelados = st.toggle(
                "Mostrar pedidos cancelados",
                value=False,
                key="admin_toggle_pedidos_cancelados",
            )
            if mostrar_cancelados:
                st.markdown("#### ✅ Pedidos cancelados")
                df_cancelados_display = _preparar_df_pedidos(df_cancelados)
                if df_cancelados_display.empty:
                    st.info("Ainda não existem pedidos cancelados.")
                else:
                    st.dataframe(df_cancelados_display, use_container_width=True, hide_index=True)

            mostrar_todos = st.toggle(
                "Mostrar todos os pedidos",
                value=False,
                key="admin_toggle_pedidos_todos",
            )
            if mostrar_todos:
                st.markdown("#### 📋 Todos os pedidos")
                df_todos_display = _preparar_df_pedidos(df_todos)
                if df_todos_display.empty:
                    st.info("Sem registos de pedidos.")
                else:
                    st.dataframe(df_todos_display, use_container_width=True, hide_index=True)

    with aba_quotas:
        st.markdown("### 💶 Quotas")
        df_quotas_preparado = _preparar_df_quotas(df_quotas)

        if df_quotas_preparado.empty:
            if df_quotas is None or df_quotas.empty:
                st.info("ℹ️ Ainda não existem quotas registadas.")
            else:
                st.warning(
                    "⚠️ Não foi possível identificar o tipo (Mensal/Anual) dos registos atuais. "
                    "Verifique se o campo 'Tipo de Quota' está preenchido no Airtable."
                )
        else:
            def _nomes_validos(valor) -> list[str]:
                if pd.isna(valor):
                    return []
                nomes_validos = []
                for item in str(valor).split(","):
                    limpo = item.strip()
                    if limpo and limpo.lower() != "nan":
                        nomes_validos.append(limpo)
                return nomes_validos

            nomes_opcoes = sorted(
                {
                    nome
                    for nomes in df_quotas_preparado["Escuteiro"]
                    for nome in _nomes_validos(nomes)
                }
            )
            periodos_opcoes = sorted(
                {
                    periodo
                    for periodo in df_quotas_preparado["__periodo_label"]
                    if isinstance(periodo, str) and periodo.strip()
                }
            )

            filtro_cols = st.columns([3, 2])
            with filtro_cols[0]:
                selecionados = st.multiselect(
                    "Filtrar por escuteiro",
                    options=nomes_opcoes,
                    key="admin_quotas_filter",
                    help="Selecione um ou mais escuteiros para limitar as tabelas abaixo.",
                )
            with filtro_cols[1]:
                periodos_selecionados = st.multiselect(
                    "Filtrar por período da quota",
                    options=periodos_opcoes,
                    key="admin_quotas_periodo_filter",
                    help="Escolha períodos específicos (ex.: Quota Mensal, Quota Anual).",
                )

            df_filtrado = df_quotas_preparado.copy()
            if selecionados:
                selecionados_normalizados = {nome.strip() for nome in selecionados}
                df_filtrado = df_filtrado[
                    df_filtrado["Escuteiro"].apply(
                        lambda nomes: any(
                            nome in selecionados_normalizados
                            for nome in _nomes_validos(nomes)
                        )
                    )
                ]
            if periodos_selecionados:
                periodos_normalizados = {periodo for periodo in periodos_selecionados if periodo}
                df_filtrado = df_filtrado[
                    df_filtrado["__periodo_label"].isin(periodos_normalizados)
                ]

            sem_tipo = df_filtrado[df_filtrado["__tipo"] == ""]
            if not sem_tipo.empty:
                st.warning(
                    "⚠️ Existem quotas sem o tipo definido. "
                    "Complete com 'Quota Mensal' ou 'Quota Anual' para que apareçam nas tabelas."
                )

            df_filtrado = df_filtrado[df_filtrado["__tipo"].isin({"mensal", "anual"})]

            def _formatar_para_exibicao(df_input: pd.DataFrame) -> pd.DataFrame:
                if df_input.empty:
                    return df_input
                df_temp = df_input.sort_values(
                    by=["__data", "Data da cobrança"],
                    ascending=[False, False],
                    na_position="last",
                ).copy()
                df_temp["Tipo"] = df_temp.get("__tipo_label", "")
                df_temp["Período"] = df_temp.get("__periodo_label", "")
                df_temp.drop(
                    columns=["__tipo", "__tipo_label", "__data", "__periodo_label"],
                    inplace=True,
                    errors="ignore",
                )
                df_temp["Data da cobrança"] = df_temp["Data da cobrança"].fillna("")
                ordem = [
                    coluna
                    for coluna in ["Data da cobrança", "Escuteiro", "Tipo", "Período", "Valor"]
                    if coluna in df_temp.columns
                ]
                if ordem:
                    df_temp = df_temp[ordem]
                return df_temp

            df_mensal_exibir = _formatar_para_exibicao(df_filtrado[df_filtrado["__tipo"] == "mensal"])
            df_anual_exibir = _formatar_para_exibicao(df_filtrado[df_filtrado["__tipo"] == "anual"])

            col_mensal, col_anual = st.columns(2)

            with col_mensal:
                with st.container(border=True):
                    st.subheader("📆 Quotas mensais")
                    if df_mensal_exibir.empty:
                        st.info("ℹ️ Nenhuma quota mensal encontrada para os filtros aplicados.")
                    else:
                                st.dataframe(
                                    df_mensal_exibir,
                                    use_container_width=True,
                                    hide_index=True,
                                    column_config={
                                        "Data da cobrança": st.column_config.TextColumn("Data da cobrança", width="small"),
                                        "Escuteiro": st.column_config.TextColumn("Escuteiro", width="medium"),
                                        "Tipo": st.column_config.TextColumn("Tipo", width="small"),
                                        "Período": st.column_config.TextColumn("Período", width="medium"),
                                        "Valor": st.column_config.NumberColumn("Valor", format="%.2f €", width="small"),
                                    },
                                )

            with col_anual:
                with st.container(border=True):
                    st.subheader("📅 Quotas anuais")
                    if df_anual_exibir.empty:
                        st.info("ℹ️ Nenhuma quota anual encontrada para os filtros aplicados.")
                    else:
                                st.dataframe(
                                    df_anual_exibir,
                                    use_container_width=True,
                                    hide_index=True,
                                    column_config={
                                        "Data da cobrança": st.column_config.TextColumn("Data da cobrança", width="small"),
                                        "Escuteiro": st.column_config.TextColumn("Escuteiro", width="medium"),
                                        "Tipo": st.column_config.TextColumn("Tipo", width="small"),
                                        "Período": st.column_config.TextColumn("Período", width="medium"),
                                        "Valor": st.column_config.NumberColumn("Valor", format="%.2f €", width="small"),
                                    },
                                )

            if (selecionados or periodos_selecionados) and df_filtrado.empty:
                st.caption("Nenhum registo corresponde aos filtros aplicados.")

    with aba_eventos:
        st.markdown("### 📅 Eventos sem voluntários")
        if df_calendario.empty:
            st.info("Sem eventos registados.")
        else:
            df_cal = df_calendario.copy()
            if "Data" in df_cal.columns:
                df_cal["__data"] = pd.to_datetime(df_cal["Data"], errors="coerce")
            else:
                df_cal["__data"] = pd.NaT

            eventos_com_vol = set()
            if not df_volunt.empty:
                df_volunt_valid = df_volunt.copy()
                if "Cancelado" in df_volunt_valid.columns:
                    df_volunt_valid = df_volunt_valid[
                        ~df_volunt_valid["Cancelado"].astype(str).str.lower().eq("true")
                    ]
                coluna_ligacao = _first_existing_col(
                    df_volunt_valid,
                    [
                        "Record_ID Calendário (from Date ( calendário ))",
                        "Record_ID Calendário (from Date (calendário))",
                        "Record_ID Calendario (from Date ( calendario ))",
                        "Date ( calendário )",
                        "Date (calendário)",
                        "Date ( calendario )",
                    ],
                )
                if coluna_ligacao:
                    for val in df_volunt_valid[coluna_ligacao].dropna():
                        if isinstance(val, list):
                            eventos_com_vol.update(val)
                        else:
                            eventos_com_vol.add(val)

            if "id" in df_cal.columns:
                df_cal["__tem_volunt"] = df_cal["id"].apply(lambda x: x in eventos_com_vol)
                sem_vol = df_cal[(df_cal["__data"] >= hoje) & (~df_cal["__tem_volunt"])].copy()
                sem_vol = sem_vol.sort_values("__data")
                if sem_vol.empty:
                    st.success("Todos os eventos futuros têm voluntários associados.")
                else:
                    sem_vol_display = sem_vol.copy()
                    sem_vol_display["Data"] = sem_vol_display["__data"].dt.strftime('%d/%m/%Y')
                    if "Agenda" not in sem_vol_display.columns:
                        sem_vol_display["Agenda"] = ""
                    else:
                        sem_vol_display["Agenda"] = sem_vol_display["Agenda"].fillna("")
                    if "Local" in sem_vol_display.columns:
                        sem_vol_display["Local"] = sem_vol_display["Local"].fillna("")

                    cols = [c for c in ["Data", "Agenda", "Local"] if c in sem_vol_display.columns]
                    col_tabela, col_grafico = st.columns([3, 2])
                    with col_tabela:
                        st.dataframe(
                            sem_vol_display[cols],
                            use_container_width=True,
                            hide_index=True,
                            height=360,
                        )
                        st.caption(f"{len(sem_vol_display)} turnos sem voluntarios.")

                    with col_grafico:
                        with st.expander("Ver gráficos de cobertura", expanded=False):
                            if "__data" not in df_cal.columns:
                                st.info("Sem datas disponiveis para os graficos.")
                            else:
                                tab_faltas, tab_cobertura = st.tabs(["Faltas por mes", "Cobertura por mes"])

                                with tab_faltas:
                                    if not sem_vol.empty and "__data" in sem_vol.columns:
                                        agrupamento = (
                                            sem_vol["__data"].dt.to_period("M").value_counts().sort_index()
                                        )
                                        if not agrupamento.empty:
                                            df_barras = (
                                                agrupamento.rename_axis("Periodo").to_frame("Turnos em falta").reset_index()
                                            )
                                            df_barras["Periodo"] = df_barras["Periodo"].astype(str)
                                            st.bar_chart(
                                                df_barras,
                                                x="Periodo",
                                                y="Turnos em falta",
                                                use_container_width=True,
                                                height=320,
                                            )
                                        else:
                                            st.info("Sem turnos em falta neste periodo.")
                                    else:
                                        st.info("Todos os turnos estao com voluntarios.")

                                with tab_cobertura:
                                    df_cobertura = df_cal.copy()
                                    df_cobertura = df_cobertura[
                                        df_cobertura["__data"].notna()
                                        & (df_cobertura["__data"] >= hoje)
                                    ].copy()
                                    col_pre_evento = "Haverá preparação de Lanches?"
                                    if col_pre_evento in df_cobertura.columns:
                                        df_cobertura = df_cobertura[
                                            df_cobertura[col_pre_evento].apply(lambda v: isinstance(v, bool) and v)
                                        ]

                                    if df_cobertura.empty:
                                        st.info("Sem dados para agrupar por periodo.")
                                    else:
                                        df_cobertura["Periodo"] = df_cobertura["__data"].dt.to_period("M").astype(str)
                                        df_cobertura["status"] = df_cobertura["id"].apply(
                                            lambda eid: "Com voluntario" if eid in eventos_com_vol else "Sem voluntario"
                                        )
                                        contagem = (
                                            df_cobertura.groupby(["Periodo", "status"]).size().reset_index(name="Turnos").sort_values("Periodo")
                                        )
                                        if contagem.empty:
                                            st.info("Sem dados para agrupar por periodo.")
                                        else:
                                            chart = (
                                                alt.Chart(contagem)
                                                .mark_bar()
                                                .encode(
                                                    x=alt.X("Periodo:N", title="Periodo"),
                                                    y=alt.Y("Turnos:Q", title="Turnos"),
                                                    color=alt.Color(
                                                        "status:N",
                                                        title="Situacao",
                                                        scale=alt.Scale(
                                                            domain=["Com voluntario", "Sem voluntario"],
                                                            range=["#4CAF50", "#F44336"],
                                                        ),
                                                    ),
                                                )
                                                .properties(height=320)
                                            )
                                            st.altair_chart(chart, use_container_width=True)
            else:
                st.info("Não foi possível cruzar eventos sem voluntários (sem coluna 'id').")

        st.markdown("#### Gestão de eventos e lanches")
        if "id" not in df_calendario.columns:
            st.info("Gestão indisponível (sem coluna 'id' no calendário).")
        else:
            df_cal_full = df_calendario.copy()
            df_cal_full["__data"] = pd.to_datetime(df_cal_full.get("Data"), errors="coerce")
            futuros = df_cal_full[
                df_cal_full["__data"].notna() & (df_cal_full["__data"] >= hoje)
            ].sort_values("__data")

            def _format_evento(idx):
                row = futuros.loc[idx]
                data = row.get("__data")
                if pd.notna(data):
                    data_str = data.strftime('%d/%m/%Y')
                else:
                    data_raw = row.get("Data")
                    data_str = data_raw if isinstance(data_raw, str) and data_raw else "Sem data"
                agenda = row.get("Agenda") or ""
                return f"{data_str} – {agenda}" if agenda else data_str

            with st.expander("Criar novo evento", expanded=False):
                with st.form("admin_criar_evento"):
                    data_nova = st.date_input("Data do evento", key="admin_novo_data")
                    agenda_nova = st.text_input("Agenda/Descrição", key="admin_novo_agenda")
                    local_novo = (
                        st.text_input("Local", value="", key="admin_novo_local")
                        if "Local" in df_cal_full.columns
                        else None
                    )
                    prepara_novo = st.checkbox("Haverá preparação de Lanches?", value=True, key="admin_novo_prepara")
                    submetido = st.form_submit_button("Criar evento")
                if submetido:
                    campos = {
                        "Data": data_nova.strftime("%Y-%m-%d"),
                        "Agenda": agenda_nova,
                        "Haverá preparação de Lanches?": prepara_novo,
                    }
                    if local_novo is not None:
                        campos["Local"] = local_novo
                    try:
                        api.table(BASE_ID, "Calendario").create(campos)
                    except Exception as exc:
                        st.error(f"Não consegui criar o evento: {exc}")
                    else:
                        st.success("Evento criado com sucesso.")
                        refrescar_dados()
                        st.rerun()

            st.markdown("##### Editar / cancelar eventos futuros")
            if futuros.empty:
                st.info("Sem eventos futuros para editar.")
            else:
                df_manage = futuros.copy()
                df_manage["ID"] = df_manage["id"]
                df_manage["Data"] = df_manage["__data"].dt.date
                try:
                    df_manage["Dia da semana"] = df_manage["__data"].dt.day_name(locale="pt_PT")
                except Exception:
                    df_manage["Dia da semana"] = df_manage["__data"].dt.day_name()
                df_manage["Semana"] = df_manage["__data"].dt.isocalendar().week
                if "Agenda" in df_manage.columns:
                    df_manage["_agenda_raw"] = df_manage["Agenda"].fillna("")
                else:
                    df_manage["_agenda_raw"] = pd.Series("", index=df_manage.index)

                def _limpar_agenda(valor: str) -> str:
                    if isinstance(valor, str) and valor.strip().startswith("[CANCELADO]"):
                        return valor.replace("[CANCELADO]", "", 1).strip()
                    return valor or ""

                df_manage["Agenda"] = df_manage["_agenda_raw"].apply(_limpar_agenda)
                col_local = "Local" if "Local" in df_manage.columns else None
                if "Haverá preparação de Lanches?" in df_manage.columns:
                    df_manage["Preparação"] = df_manage["Haverá preparação de Lanches?"].fillna(False).astype(bool)
                else:
                    df_manage["Preparação"] = False
                df_manage["Estado"] = df_manage["_agenda_raw"].apply(
                    lambda txt: "Cancelado" if isinstance(txt, str) and txt.strip().startswith("[CANCELADO]") else "Ativo"
                )
                df_manage["Apagar"] = False

                display_cols = ["Data", "Dia da semana", "Semana", "Agenda"]
                if col_local:
                    display_cols.append(col_local)
                display_cols += ["Preparação", "Estado", "Apagar", "ID"]
                df_display = df_manage[display_cols].copy()
                rename_map = {
                    "Data": "Data",
                    "Dia da semana": "Dia",
                    "Semana": "Semana",
                    "Agenda": "Agenda",
                    "Preparação": "Preparação",
                    "Estado": "Estado",
                    "Apagar": "Apagar",
                    "ID": "ID",
                }
                if col_local:
                    rename_map[col_local] = "Local"
                df_display = df_display.rename(columns=rename_map)

                df_display["Data"] = pd.to_datetime(df_display["Data"], errors="coerce").dt.strftime("%Y-%m-%d")

                st.caption("Marque 'Apagar' para remover um evento sem voluntários associados e clique em 'Guardar alterações da tabela'.")

                date_formatter = JsCode(
                    """
                    function(params) {
                        if (!params.value) {
                            return '';
                        }
                        const data = new Date(params.value);
                        if (isNaN(data.getTime())) {
                            return params.value;
                        }
                        return data.toISOString().slice(0, 10);
                    }
                    """
                )
                date_parser = JsCode(
                    """
                    function(params) {
                        if (!params.newValue) {
                            return null;
                        }
                        const valor = params.newValue;
                        const data = new Date(valor);
                        if (isNaN(data.getTime())) {
                            return valor;
                        }
                        return data.toISOString().slice(0, 10);
                    }
                    """
                )

                gob_cal = GridOptionsBuilder.from_dataframe(df_display)
                gob_cal.configure_default_column(editable=False, resizable=True)
                gob_cal.configure_column(
                    "Data",
                    editable=True,
                    type=["dateColumn"],
                    cellEditor="agDateCellEditor",
                    cellEditorParams={"useBrowserDatePicker": True},
                    valueFormatter=date_formatter,
                    valueParser=date_parser,
                )
                gob_cal.configure_column("Dia", editable=False)
                gob_cal.configure_column("Semana", editable=False)
                gob_cal.configure_column("Agenda", editable=True)
                if "Local" in df_display.columns:
                    gob_cal.configure_column("Local", editable=True)
                gob_cal.configure_column(
                    "Preparação",
                    editable=True,
                    cellEditor="agCheckboxCellEditor",
                    cellRenderer="agCheckboxRenderer",
                    type=["booleanColumn"],
                )
                gob_cal.configure_column(
                    "Estado",
                    editable=True,
                    cellEditor="agSelectCellEditor",
                    cellEditorParams={"values": ["Ativo", "Cancelado"]},
                )
                gob_cal.configure_column(
                    "Apagar",
                    editable=True,
                    cellEditor="agCheckboxCellEditor",
                    cellRenderer="agCheckboxRenderer",
                    type=["booleanColumn"],
                )
                gob_cal.configure_column("ID", editable=False)
                gob_cal.configure_grid_options(stopEditingWhenCellsLoseFocus=True)
                grid_options_cal = gob_cal.build()

                grid_response_cal = AgGrid(
                    df_display,
                    gridOptions=grid_options_cal,
                    height=380,
                    fit_columns_on_grid_load=True,
                    update_mode=GridUpdateMode.VALUE_CHANGED,
                    data_return_mode=DataReturnMode.AS_INPUT,
                    allow_unsafe_jscode=True,
                    theme="balham",
                    key="aggrid_admin_eventos",
                )

                if st.button("Guardar alterações da tabela", key="admin_event_table_save"):
                    dados_cal = grid_response_cal.get("data") if grid_response_cal else None
                    if not dados_cal:
                        st.info("Nenhuma alteração para guardar.")
                    else:
                        editado = pd.DataFrame(dados_cal)
                        missing_cols = [col for col in df_display.columns if col not in editado.columns]
                        for col in missing_cols:
                            editado[col] = df_display[col]

                        def _to_bool(valor: Any) -> bool:
                            if isinstance(valor, bool):
                                return valor
                            if valor is None:
                                return False
                            if isinstance(valor, str):
                                return valor.strip().lower() in {"true", "1", "sim", "yes", "on"}
                            if isinstance(valor, (int, float)):
                                if pd.isna(valor):
                                    return False
                                return bool(valor)
                            return bool(valor)

                        for coluna_bool in ("Preparação", "Apagar"):
                            if coluna_bool in editado.columns:
                                editado[coluna_bool] = editado[coluna_bool].apply(_to_bool)

                        if "Estado" in editado.columns:
                            editado["Estado"] = editado["Estado"].fillna("Ativo").astype(str)
                        if "Agenda" in editado.columns:
                            editado["Agenda"] = editado["Agenda"].fillna("").astype(str)
                        if "Local" in editado.columns:
                            editado["Local"] = editado["Local"].fillna("").astype(str)

                        edited_records = editado.to_dict("records")
                        original_records = df_display.to_dict("records")

                        def _normalize_id(value):
                            if value is None:
                                return None
                            if isinstance(value, float) and pd.isna(value):
                                return None
                            value = str(value).strip()
                            return value or None
    
                        def _to_iso(value):
                            if isinstance(value, pd.Timestamp):
                                return value.strftime("%Y-%m-%d")
                            if hasattr(value, "isoformat"):
                                return value.isoformat()
                            if isinstance(value, str) and value:
                                try:
                                    return pd.to_datetime(value).strftime("%Y-%m-%d")
                                except Exception:
                                    return None
                            return None
    
                        original_map = {}
                        for rec in original_records:
                            norm_id = _normalize_id(rec.get("ID"))
                            if norm_id:
                                original_map[norm_id] = rec
    
                        atualizados = 0
                        removidos = 0
                        bloqueados = []
                        tbl_cal = api.table(BASE_ID, "Calendario")
    
                        def _tem_voluntarios(evento_id: str) -> bool:
                            if df_volunt.empty or "Date (calendário)" not in df_volunt.columns:
                                return False
                            return df_volunt["Date (calendário)"].apply(
                                lambda v: evento_id in v if isinstance(v, list) else v == evento_id
                            ).any()
    
                        for row in edited_records:
                            event_id = _normalize_id(row.get("ID"))
                            if not event_id:
                                continue
                            original = original_map.get(event_id)
                            if original is None:
                                continue
    
                            if row.get("Apagar"):
                                if _tem_voluntarios(event_id):
                                    bloqueados.append((event_id, "Existe voluntariado associado"))
                                    continue
                                try:
                                    tbl_cal.delete(event_id)
                                except Exception as exc:
                                    st.error(f"Não consegui apagar o evento {event_id}: {exc}")
                                else:
                                    removidos += 1
                                continue
    
                            campos_update = {}
                            iso_novo = _to_iso(row.get("Data"))
                            iso_original = _to_iso(original.get("Data"))
                            if iso_novo and iso_novo != iso_original:
                                campos_update["Data"] = iso_novo
    
                            estado_novo = row.get("Estado", "Ativo") or "Ativo"
                            agenda_nova = (row.get("Agenda") or "").strip()
                            if estado_novo == "Cancelado":
                                if not agenda_nova:
                                    agenda_nova = "CANCELADO"
                                if not agenda_nova.startswith("[CANCELADO]"):
                                    agenda_nova = f"[CANCELADO] {agenda_nova}".strip()
                                campos_update["Haverá preparação de Lanches?"] = False
                            else:
                                if agenda_nova.startswith("[CANCELADO]"):
                                    agenda_nova = agenda_nova.replace("[CANCELADO]", "", 1).strip()
    
                            agenda_original = (
                                df_manage.loc[df_manage["ID"] == event_id, "_agenda_raw"].iloc[0]
                                if event_id in df_manage["ID"].values
                                else ""
                            )
                            if agenda_nova != (agenda_original or ""):
                                campos_update["Agenda"] = agenda_nova
    
                            prep_novo = bool(row.get("Preparação", False))
                            prep_original = (
                                bool(df_manage.loc[df_manage["ID"] == event_id, "Preparação"].iloc[0])
                                if event_id in df_manage["ID"].values
                                else False
                            )
                            if estado_novo != "Cancelado" and prep_novo != prep_original:
                                campos_update["Haverá preparação de Lanches?"] = prep_novo
    
                            if "Local" in row:
                                local_novo = row.get("Local", "")
                                local_original = (
                                    df_manage.loc[df_manage["ID"] == event_id, "Local"].iloc[0]
                                    if (col_local and event_id in df_manage["ID"].values)
                                    else ""
                                )
                                if (local_novo or "") != (local_original or ""):
                                    campos_update["Local"] = local_novo
    
                            if not campos_update:
                                continue
    
                            try:
                                tbl_cal.update(event_id, campos_update)
                            except Exception as exc:
                                st.error(f"Não consegui atualizar o evento {event_id}: {exc}")
                            else:
                                atualizados += 1
    
                        if atualizados or removidos:
                            mensagens = []
                            if atualizados:
                                mensagens.append(f"{atualizados} evento(s) atualizados")
                            if removidos:
                                mensagens.append(f"{removidos} evento(s) apagados")
                            st.success("; ".join(mensagens) + ".")
                            refrescar_dados()
                            st.rerun()
                        else:
                            st.info("Nenhuma alteração para guardar.")
    
                        if bloqueados:
                            detalhes = ", ".join(f"{rid} ({motivo})" for rid, motivo in bloqueados)
                            st.warning(f"Não foi possível eliminar os eventos: {detalhes}.")

# ======================
# 5) Mostrar dashboards consoante role
# ======================
sections_a_mostrar: list[str] = []
if is_admin:
    sections_a_mostrar.append("admin")
if is_tesoureiro:
    sections_a_mostrar.append("tesoureiro")
sections_a_mostrar.append("pais")

for idx, sec in enumerate(sections_a_mostrar):
    if sec == "admin":
        dashboard_admin(dados)
    elif sec == "tesoureiro":
        dashboard_tesoureiro(dados)
    else:
        dashboard_pais()

    if idx < len(sections_a_mostrar) - 1:
        st.divider()
