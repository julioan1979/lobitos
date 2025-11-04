#pages/home.py
#-*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import altair as alt
from pyairtable import Api
from menu import menu_with_redirect
import locale
import time
from datetime import date, datetime, timedelta
from urllib.parse import urlparse, urlunparse
import streamlit.components.v1 as components
from airtable_config import context_labels, current_context, get_airtable_credentials, resolve_form_url

import locale

try:
    locale.setlocale(locale.LC_ALL, "pt_PT.UTF-8")
except locale.Error:
    # fallback para não dar erro no Streamlit Cloud
    locale.setlocale(locale.LC_ALL, "")



st.set_page_config(page_title="Portal Escutista", page_icon="🐾", layout="wide")

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
            "Permissoes",
            "Publicar Menu do Scouts",
        ],
        "admin": [
            "Pedidos",
            "Calendario",
            "Voluntariado Pais",
            "Escuteiros",
            "Recipes",
            "Recebimento",
            "Estorno de Recebimento",
            "Permissoes",
            "Publicar Menu do Scouts",
        ],
    }

    lista_tabelas = tabelas_por_role.get(role, [])
    tabelas_opcionais = set()

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




def mapear_lista(valor, mapping):
    if isinstance(valor, list):
        return ", ".join(mapping.get(v, v) for v in valor)
    if pd.isna(valor):
        return ""
    return mapping.get(valor, valor)


def formatar_moeda_euro(valor) -> str:
    if pd.isna(valor):
        return ""

    numero = valor
    if isinstance(valor, str):
        limpo = valor.replace("€", "").replace(" ", "")
        if "," in limpo and "." in limpo:
            limpo = limpo.replace(".", "").replace(",", ".")
        elif "," in limpo:
            limpo = limpo.replace(",", ".")
        try:
            numero = float(limpo)
        except ValueError:
            return valor
    try:
        numero = float(numero)
    except (TypeError, ValueError):
        return str(valor)

    texto = f"{numero:,.2f}"
    texto = texto.replace(",", "x").replace(".", ",").replace("x", ".")
    return f"{texto}€"


def construir_mapa_nomes_por_id(dataset: dict) -> dict[str, str]:
    """Cria um dicionário id -> nome usando quaisquer tabelas já carregadas."""

    def _score_coluna(coluna: str) -> tuple[int, str]:
        nome_lower = coluna.lower()
        if nome_lower in {"nome", "name"}:
            return (0, nome_lower)
        if "nome" in nome_lower:
            return (1, nome_lower)
        if "name" in nome_lower:
            return (2, nome_lower)
        if "email" in nome_lower:
            return (3, nome_lower)
        return (4, nome_lower)

    mapa: dict[str, str] = {}
    for df in dataset.values():
        if df is None or df.empty or "id" not in df.columns:
            continue

        colunas_texto: list[str] = []
        for coluna in df.columns:
            if coluna == "id":
                continue
            serie = df[coluna]
            if serie.dtype == object or serie.apply(lambda v: isinstance(v, list)).any():
                colunas_texto.append(coluna)

        if not colunas_texto:
            continue

        colunas_texto.sort(key=_score_coluna)

        for coluna in colunas_texto:
            serie = df.set_index("id")[coluna].dropna()
            if serie.empty:
                continue

            serie = serie.apply(lambda v: ", ".join(v) if isinstance(v, list) else v)
            algum_mapeado = False
            for idx, valor in serie.items():
                if not isinstance(valor, str):
                    valor = str(valor)
                valor_limpo = valor.strip()
                if not valor_limpo:
                    continue
                if idx not in mapa:
                    mapa[idx] = valor_limpo
                    algum_mapeado = True
            if algum_mapeado:
                break

    return mapa


def escolher_coluna(df: pd.DataFrame, candidatos: list[str]) -> str | None:
    if df is None or df.empty:
        return None

    colunas = list(df.columns)
    normalizados = {col.lower().strip(): col for col in colunas}
    for candidato in candidatos:
        chave = candidato.lower().strip()
        if chave in normalizados:
            return normalizados[chave]

    for candidato in candidatos:
        chave = candidato.lower().strip()
        for coluna in colunas:
            if chave in coluna.lower().strip():
                return coluna
    return None


def preparar_dataframe_estornos(
    dados: dict,
    escuteiros_map: dict[str, str],
    permissoes_map: dict[str, str],
    mapa_nomes_ids: dict[str, str],
) -> pd.DataFrame:
    possiveis_tabelas = [
        "Estorno de Recebimento",
        "Estornos de Recebimento",
        "Estorno Recebimento",
        "Estorno",
        "Estornos",
    ]
    df_origem = pd.DataFrame()
    origem_utilizada = None
    for nome in possiveis_tabelas:
        df_candidato = dados.get(nome)
        if isinstance(df_candidato, pd.DataFrame) and not df_candidato.empty:
            df_origem = df_candidato.copy()
            origem_utilizada = nome
            break

    if df_origem.empty:
        df_receb = dados.get("Recebimento", pd.DataFrame())
        if isinstance(df_receb, pd.DataFrame) and not df_receb.empty:
            df_origem = df_receb.copy()
            origem_utilizada = "Recebimento"
        else:
            return pd.DataFrame()

    df_trabalho = df_origem.copy()
    if origem_utilizada == "Recebimento":
        mask_estorno = pd.Series(False, index=df_trabalho.index)

        for coluna in ["Tipo de Movimento", "Tipo", "Categoria", "Movimento", "Motivo"]:
            if coluna in df_trabalho.columns:
                serie = df_trabalho[coluna].astype(str).str.lower()
                mask_estorno = mask_estorno | serie.str.contains("estorno", na=False)

        for coluna in ["É Estorno", "E Estorno", "Estorno?", "Estorno", "é Estorno", "é_estorno"]:
            if coluna in df_trabalho.columns:
                serie = df_trabalho[coluna]
                if serie.dtype == bool:
                    mask_estorno = mask_estorno | serie
                else:
                    serie_str = serie.astype(str).str.strip().str.lower()
                    mask_estorno = mask_estorno | serie_str.isin({"1", "true", "verdadeiro", "sim", "yes"})

        if "Valor Estornado" in df_trabalho.columns:
            valores = pd.to_numeric(df_trabalho["Valor Estornado"], errors="coerce").fillna(0).abs()
            mask_estorno = mask_estorno | (valores > 0)

        if "Valor Recebido" in df_trabalho.columns:
            valores = pd.to_numeric(df_trabalho["Valor Recebido"], errors="coerce")
            mask_estorno = mask_estorno | (valores < 0)

        df_trabalho = df_trabalho.loc[mask_estorno].copy()
        if df_trabalho.empty:
            return pd.DataFrame()

    coluna_escuteiro = escolher_coluna(df_trabalho, ["Escuteiros", "Escuteiro", "Escuteiro(s)", "Escuteiros Relacionados"])
    coluna_valor = escolher_coluna(
        df_trabalho,
        [
            "Valor Estornado",
            "Valor Estorno",
            "Valor do Estorno",
            "Valor",
            "Valor (€)",
            "Valor Recebido",
        ],
    )
    coluna_data = escolher_coluna(df_trabalho, ["Data do Estorno", "Date", "Data"])
    coluna_meio = escolher_coluna(
        df_trabalho,
        ["Meio de Pagamento", "Método de Pagamento", "Metodo de Pagamento", "Método", "Metodo"],
    )
    coluna_responsavel = escolher_coluna(
        df_trabalho,
        [
            "Quem Estornou?",
            "Quem Estornou",
            "Quem Recebeu?",
            "Registado Por",
            "Responsável",
            "Criado Por",
        ],
    )

    resultado = pd.DataFrame(index=df_trabalho.index)

    if coluna_escuteiro:
        resultado["Escuteiro"] = df_trabalho[coluna_escuteiro].apply(lambda valor: mapear_lista(valor, escuteiros_map))

    if coluna_valor:
        resultado["Valor (€)"] = pd.to_numeric(df_trabalho[coluna_valor], errors="coerce").abs()

    if coluna_meio:
        resultado["Meio de Pagamento"] = df_trabalho[coluna_meio]

    if coluna_data:
        resultado["Data"] = pd.to_datetime(df_trabalho[coluna_data], errors="coerce").dt.normalize()

    if coluna_responsavel:
        def _mapear_responsavel(valor):
            if permissoes_map:
                texto = mapear_lista(valor, permissoes_map)
                if texto:
                    return texto
            if mapa_nomes_ids:
                texto = mapear_lista(valor, mapa_nomes_ids)
                if texto:
                    return texto
            if escuteiros_map:
                texto = mapear_lista(valor, escuteiros_map)
                if texto:
                    return texto
            return mapear_lista(valor, {})

        resultado["Quem Estornou"] = df_trabalho[coluna_responsavel].apply(_mapear_responsavel)

    resultado = resultado.dropna(how="all")
    if "Valor (€)" in resultado.columns:
        resultado = resultado[resultado["Valor (€)"].notna()]

    return resultado

def mostrar_formulario(session_key: str, titulo: str, iframe_url: str, iframe_height: int = 600, container_height=None) -> None:
    if not st.session_state.get(session_key, False):
        return
    with st.container(border=True):
        col1, col2 = st.columns([8, 1])
        with col1:
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
    st.session_state["dados_cache"] = carregar_todas_as_tabelas(BASE_ID, role)
    st.session_state["last_update"] = datetime.now()

if st.button("🔄 Atualizar dados do Airtable"):
    st.session_state["dados_cache"] = carregar_todas_as_tabelas(BASE_ID, role)
    st.session_state["last_update"] = datetime.now()
    st.success("✅ Dados atualizados com sucesso!")

# Mostrar data/hora da última atualização
if "last_update" in st.session_state:
    st.caption(f"🕒 Última atualização: {st.session_state['last_update'].strftime('%d/%m/%Y %H:%M:%S')}")

dados = st.session_state["dados_cache"]

# ======================
# 4) Dashboards
# ======================

def dashboard_pais():
    st.markdown("## 🏡 Bem-vindo, Família Escutista!")
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
