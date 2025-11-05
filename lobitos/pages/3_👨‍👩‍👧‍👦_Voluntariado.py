import pandas as pd
import streamlit as st
from urllib.parse import urlparse, urlunparse
from menu import menu_with_redirect
from airtable_config import context_labels, resolve_form_url

menu_with_redirect()

secao_info = context_labels()
if secao_info:
    st.caption(secao_info)

role = st.session_state.get("role")
user_info = st.session_state.get("user", {})
allowed_escuteiros = set(user_info.get("escuteiros_ids", [])) if user_info else set()

if role is None:
    st.stop()

DEFAULT_VOLUNT_FORM_URL = resolve_form_url("DEFAULT_VOLUNT_FORM_URL", "Formulário de Voluntariado")

st.title("Voluntariado dos Pais")

dados = st.session_state.get("dados_cache", {})
df = dados.get("Voluntariado Pais", pd.DataFrame())
df_cal = dados.get("Calendario", pd.DataFrame())
df_esc = dados.get("Escuteiros", pd.DataFrame())


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


def _first_existing(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    return None


if df is None or df.empty:
    st.info("Ainda não existem voluntários registados.")
    df_valid = pd.DataFrame()
else:
    df_valid = df.copy()

    cancel_col = _first_existing(df_valid, ["Cancelado"])
    if cancel_col:
        df_valid = df_valid[~df_valid[cancel_col].fillna(False)]

    if "Created" in df_valid.columns:
        df_valid = df_valid.sort_values("Created", ascending=False)

highlight = df_valid.head(3) if not df_valid.empty else pd.DataFrame()
if not highlight.empty:
    st.markdown("### Obrigado aos últimos voluntários!")
    col_link = _first_existing(
        df_valid,
        [
            "Record_ID Calendário (from Date ( calendário ))",
            "Record_ID Calendário (from Date (calendário))",
            "Date ( calendário )",
            "Date (calendário)",
        ],
    )
    if col_link and not df_cal.empty and "id" in df_cal.columns:
        cal_map = df_cal.set_index("id").get("Data", pd.Series(dtype=str)).to_dict()
    else:
        cal_map = {}

    cols = st.columns(len(highlight))
    for col, (_, row) in zip(cols, highlight.iterrows()):
        nome = str(row.get("Pais", "Família solidária")).strip() or "Família solidária"
        datas = []
        if col_link:
            eventos = row.get(col_link)
            if isinstance(eventos, list):
                eventos_ids = eventos
            elif pd.notna(eventos):
                eventos_ids = [eventos]
            else:
                eventos_ids = []
            for eid in eventos_ids:
                data = pd.to_datetime(cal_map.get(eid), errors="coerce")
                if not pd.isna(data):
                    datas.append(data.strftime("%d/%m/%Y"))
        data_txt = ", ".join(datas) if datas else "data a confirmar"
        with col:
            st.markdown(
                f"#### {nome}\n<small>{data_txt}</small>",
                unsafe_allow_html=True,
            )

st.markdown(
    """
    ### Registar disponibilidade
    Utilize o formulário abaixo para indicar quando pode ajudar na preparação dos lanches.
    """
)

iframe_src = DEFAULT_VOLUNT_FORM_URL

df_esc_form = df_esc.copy() if df_esc is not None else pd.DataFrame()
if not df_esc_form.empty and "id" in df_esc_form.columns:
    if allowed_escuteiros:
        df_esc_form = df_esc_form[df_esc_form["id"].isin(allowed_escuteiros)]
        if df_esc_form.empty:
            st.warning("Não existem escuteiros associados a esta conta para registar voluntariado.")
    elif role == "pais":
        st.warning("A sua conta ainda não tem escuteiros associados. Contacte a equipa de administração.")
        df_esc_form = pd.DataFrame()

    if not df_esc_form.empty:
        def _formatar_label(row: pd.Series) -> str:
            nome = row.get("Nome do Escuteiro")
            codigo = row.get("ID_Escuteiro")
            if pd.isna(nome) or not str(nome).strip():
                nome = "Lobito sem nome"
            if pd.notna(codigo) and str(codigo).strip():
                return f"{nome} ({codigo})"
            return str(nome)

        df_esc_form = df_esc_form.copy()
        df_esc_form["__label"] = df_esc_form.apply(_formatar_label, axis=1)
        df_esc_form = df_esc_form.sort_values("__label")

        ids = df_esc_form["id"].tolist()
        label_por_id = dict(zip(df_esc_form["id"], df_esc_form["__label"]))

        sess_key = "voluntariado_escuteiro"
        if sess_key not in st.session_state or st.session_state[sess_key] not in ids:
            st.session_state[sess_key] = ids[0]

        escuteiro_id = st.selectbox(
            "Escolha o Lobito",
            options=ids,
            format_func=lambda value: label_por_id.get(value, value),
            key=sess_key,
        )
        escuteiro_row = df_esc_form[df_esc_form["id"] == escuteiro_id].iloc[0]

        iframe_src = normalizar_url_airtable(
            escuteiro_row.get("Link Forms_Voluntariado Pre_Field", ""),
            DEFAULT_VOLUNT_FORM_URL,
        )

st.components.v1.html(
    f"""
    <iframe class="airtable-embed"
        src="{iframe_src}"
        frameborder="0" onmousewheel="" width="100%" height="720"
        style="background: transparent; border: 1px solid #c;">
    </iframe>
    """
,
    height=770,
    scrolling=True,
)

st.markdown("---")
st.markdown("### Registos recentes")

def _normalizar_lista(valor):
    if isinstance(valor, list):
        return [str(item) for item in valor if pd.notna(item)]
    if pd.isna(valor):
        return []
    return [str(valor)]


if df is None or df.empty:
    st.info("Ainda não existem voluntários registados.")
else:
    df_vis = df.copy()

    if "Date (calendário)" in df_vis.columns and not df_cal.empty and "id" in df_cal.columns:
        cal_map = df_cal.set_index("id").get("Data", pd.Series(dtype=str)).to_dict()

        def _mapear_datas(valor):
            datas_ids = _normalizar_lista(valor)
            datas = [pd.to_datetime(cal_map.get(v), errors="coerce") for v in datas_ids]
            return ", ".join(d.strftime("%d/%m/%Y") for d in datas if not pd.isna(d))

        df_vis["Datas"] = df_vis["Date (calendário)"].apply(_mapear_datas)

    esc_map = {}
    if df_esc is not None and not df_esc.empty and "id" in df_esc.columns:
        if "Nome do Escuteiro" in df_esc.columns:
            esc_map = df_esc.set_index("id")["Nome do Escuteiro"].dropna().to_dict()

    if "Escuteiro" in df_vis.columns:
        def _mapear_esc(valor):
            ids = _normalizar_lista(valor)
            nomes = [esc_map.get(eid, eid) for eid in ids]
            return ", ".join(nomes)
        df_vis["Escuteiro"] = df_vis["Escuteiro"].apply(_mapear_esc)

    if "Pais" in df_vis.columns:
        df_vis["Pais"] = df_vis["Pais"].apply(
            lambda valor: ", ".join(_normalizar_lista(valor))
        )

    colunas = [
        col
        for col in ["Datas", "Escuteiro", "Pais"]
        if col in df_vis.columns
    ]

    st.dataframe(
        df_vis[colunas].head(20),
        use_container_width=True,
        hide_index=True,
    )
