import unicodedata
import pandas as pd
import streamlit as st
from urllib.parse import urlparse, urlunparse
from menu import menu_with_redirect
from airtable_config import context_labels, resolve_form_url

DEFAULT_LANCHE_FORM_URL = resolve_form_url("DEFAULT_LANCHE_FORM_URL", "Formulário de Escolha dos Lanches")

menu_with_redirect()

secao_info = context_labels()
if secao_info:
    st.caption(secao_info)

role = st.session_state.get("role")
user_info = st.session_state.get("user", {})
allowed_escuteiros = set(user_info.get("escuteiros_ids", [])) if user_info else set()

if role is None:
    st.stop()

st.title("Escuteiros")

dados = st.session_state.get("dados_cache", {})
df_recipes = dados.get("Recipes", pd.DataFrame())


def normalizar_url_airtable(valor_url, fallback: str) -> str:
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


def _first_existing(frame: pd.DataFrame, columns: list[str]) -> str | None:
    if frame is None or frame.empty:
        return None
    for col in columns:
        if col in frame.columns:
            return col
    return None

df_menu = dados.get("Publicar Menu do Scouts", pd.DataFrame())
recipes_name_col = _first_existing(df_recipes, ['Menu', 'Nome', 'Nome do Item']) if df_recipes is not None else None
recipes_map = {}
if recipes_name_col:
    recipes_map = df_recipes.set_index('id')[recipes_name_col].dropna().astype(str).to_dict()


possible_date_columns = [
    "Date (from Publicação Filtro)",
    "Date (from Marcação dos Pais na preparação do Lanche)",
    "Date ( calendário )",
    "Date (calendário)",
    "Date",
    "Data (from Publicação Filtro)",
    "Data (from Marcação dos Pais na preparação do Lanche)",
    "Data ( calendário )",
    "Data (calendário)",
    "Data",
]

normalized_date_columns = [
    unicodedata.normalize("NFKD", coluna)
    .encode("ASCII", "ignore")
    .decode("ASCII")
    .lower()
    .strip()
    for coluna in possible_date_columns
]


def _normalize_key(valor: str) -> str:
    if valor is None:
        return ""
    texto = unicodedata.normalize("NFKD", str(valor))
    return "".join(car for car in texto if not unicodedata.combining(car)).lower().strip()


def _normalizar_data_menu(frame: pd.DataFrame) -> pd.DataFrame | None:
    if frame is None or frame.empty:
        return None
    frame_local = frame.copy()
    coluna_map = {_normalize_key(coluna): coluna for coluna in frame_local.columns}
    for coluna_normalizada in normalized_date_columns:
        coluna = coluna_map.get(coluna_normalizada)
        if not coluna:
            continue
        serie = frame_local[coluna].apply(
            lambda valor: valor[0] if isinstance(valor, list) and valor else valor
        )
        serie = pd.to_datetime(serie, errors="coerce")
        if serie.notna().any():
            frame_local["__data_menu"] = serie
            return frame_local
    return None

item_columns = [
    ("Entrada", ["Entrada", "Entradas"]),
    ("Lanches", ["Lanches", "Lanche"]),
    ("Bebidas", ["Bebidas", "Bebida"]),
    ("Sobremesa", ["Sobremesa", "Sobremesas"]),
    ("Fruta", ["Fruta", "Frutas"]),
]

def _render_menu_info(frame: pd.DataFrame) -> None:
    if frame is None or frame.empty:
        st.info('Sem menu publicado para os próximos lanches.')
        return
    frame = frame.copy()
    coluna_map = {_normalize_key(coluna): coluna for coluna in frame.columns}
    col_data = None
    for coluna_normalizada in normalized_date_columns:
        coluna = coluna_map.get(coluna_normalizada)
        if coluna:
            col_data = coluna
            break
    if col_data is None:
        st.info('Sem menu publicado para os próximos lanches.')
        return
    frame["__data_menu"] = frame[col_data].apply(
        lambda valor: valor[0] if isinstance(valor, list) and valor else valor
    )
    frame["__data_menu"] = pd.to_datetime(frame["__data_menu"], errors="coerce")
    frame = frame[frame["__data_menu"].notna()].sort_values("__data_menu")
    if frame.empty:
        st.info('Sem menu publicado para os próximos lanches.')
        return

    iso = frame["__data_menu"].dt.isocalendar()
    frame["__iso_year"] = iso["year"]
    frame["__iso_week"] = iso["week"]

    hoje = pd.Timestamp.today().normalize()
    hoje_iso = hoje.isocalendar()

    desta_semana = frame[
        (frame["__iso_year"] == hoje_iso.year) & (frame["__iso_week"] == hoje_iso.week)
    ]
    if not desta_semana.empty:
        destaque = desta_semana.iloc[0]
        titulo = 'Menu desta semana'
    else:
        proximo = frame[frame["__data_menu"] >= hoje]
        if not proximo.empty:
            destaque = proximo.iloc[0]
            titulo = 'Menu do próximo lanche'
        else:
            destaque = frame.iloc[-1]
            titulo = 'Último menu publicado'

    data_txt = destaque["__data_menu"].strftime("%d/%m/%Y")

    def _format_valor(valor):
        if isinstance(valor, list):
            valores = []
            for item in valor:
                item_str = str(item).strip() if not isinstance(item, list) else ""
                if item_str in recipes_map:
                    valores.append(recipes_map[item_str])
                elif item_str:
                    valores.append(item_str)
            return ", ".join(v for v in valores if v)
        valor_str = str(valor).strip()
        if not valor_str:
            return ""
        return recipes_map.get(valor_str, valor_str)

    itens = []
    for rotulo, campos in item_columns:
        valor_campo = None
        for campo in campos:
            if campo in destaque and pd.notna(destaque.get(campo)):
                valor_campo = destaque.get(campo)
                break
        if valor_campo is None:
            continue
        texto = _format_valor(valor_campo)
        if not texto:
            texto = "-"
        itens.append(f"- **{rotulo}:** {texto}")

    with st.container(border=True):
        st.markdown(f"### {titulo} ({data_txt})")
        if itens:
            st.markdown("\n".join(itens))
        else:
            st.markdown("Menu ainda não publicado.")


_render_menu_info(_normalizar_data_menu(df_menu))

st.markdown(
    """
    ### Formulário de Marcação de Lanche
    Preencha o formulário abaixo para marcar o lanche do seu escuteiro.
    """
)

df_escuteiros = dados.get("Escuteiros", pd.DataFrame())

if df_escuteiros is None or df_escuteiros.empty or "id" not in df_escuteiros.columns:
    st.warning("Ainda não existem escuteiros registados ou a tabela está incompleta.")
else:
    df_escuteiros = df_escuteiros.copy()

    if allowed_escuteiros:
        df_escuteiros = df_escuteiros[df_escuteiros["id"].isin(allowed_escuteiros)]
        if df_escuteiros.empty:
            st.warning("Não existem dados para os escuteiros associados a esta conta.")
    elif role == "pais":
        st.warning("A sua conta ainda não tem escuteiros associados. Contacte a equipa de administração.")
        df_escuteiros = pd.DataFrame()

    if not df_escuteiros.empty:
        def _formatar_label(row: pd.Series) -> str:
            nome = row.get("Nome do Escuteiro")
            codigo = row.get("ID_Escuteiro")
            if pd.isna(nome) or not str(nome).strip():
                nome = "Lobito sem nome"
            if pd.notna(codigo) and str(codigo).strip():
                return f"{nome} ({codigo})"
            return str(nome)

        df_escuteiros["__label"] = df_escuteiros.apply(_formatar_label, axis=1)
        df_escuteiros = df_escuteiros.sort_values("__label")

        ids = df_escuteiros["id"].tolist()
        label_por_id = dict(zip(df_escuteiros["id"], df_escuteiros["__label"]))

        sess_key = "escuteiro_form_lanche"
        if sess_key not in st.session_state or st.session_state[sess_key] not in ids:
            st.session_state[sess_key] = ids[0]

        escuteiro_id = st.selectbox(
            "Escolha o Lobito",
            options=ids,
            format_func=lambda value: label_por_id.get(value, value),
            key=sess_key,
        )
        escuteiro_row = df_escuteiros[df_escuteiros["id"] == escuteiro_id].iloc[0]

        iframe_src = normalizar_url_airtable(
            escuteiro_row.get("Pre_Field escolha semanal lanches", ""),
            DEFAULT_LANCHE_FORM_URL,
        )

        st.components.v1.html(
            f"""
            <iframe class="airtable-embed"
                src="{iframe_src}"
                frameborder="0" onmousewheel="" width="100%" height="650"
                style="background: transparent; border: 1px solid #ccc;">
            </iframe>
            """,
            height=700,
            scrolling=True,
        )

st.markdown("---")
st.info(
    "Precisa cancelar uma marcação? Utilize a opção **Cancelar Lanche** no dashboard principal."
)
