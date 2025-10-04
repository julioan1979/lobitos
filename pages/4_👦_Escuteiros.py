import pandas as pd
import streamlit as st
from menu import menu_with_redirect

menu_with_redirect()

st.title("🧒 Escuteiros")

dados = st.session_state.get("dados_cache", {})
df_menu = dados.get("Publicar Menu do Scouts", pd.DataFrame())

possible_date_columns = [
    "Date (from Publicação Filtro)",
    "Date (from Marcação dos Pais na preparação do Lanche)",
    "Date ( calendário )",
    "Date (calendário)",
    "Date",
]

def _normalizar_data_menu(frame: pd.DataFrame) -> pd.DataFrame | None:
    if frame is None or frame.empty:
        return None
    frame_local = frame.copy()
    for coluna in possible_date_columns:
        if coluna not in frame_local.columns:
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
    if frame is None or frame.empty or "__data_menu" not in frame.columns:
        st.info("Sem menu publicado para os próximos lanches.")
        return
    frame = frame[frame["__data_menu"].notna()].sort_values("__data_menu")
    if frame.empty:
        st.info("Sem menu publicado para os próximos lanches.")
        return
    hoje = pd.Timestamp.today().normalize()
    proximo = frame[frame["__data_menu"] >= hoje]
    destaque = proximo.iloc[0] if not proximo.empty else frame.iloc[-1]
    data_txt = destaque["__data_menu"].strftime("%d/%m/%Y")

    itens = []
    for rotulo, campos in item_columns:
        valor_campo = None
        for campo in campos:
            if campo in destaque and pd.notna(destaque.get(campo)):
                valor_campo = destaque.get(campo)
                break
        if valor_campo is None:
            continue
        if isinstance(valor_campo, list):
            texto = ", ".join(str(v) for v in valor_campo if pd.notna(v) and str(v).strip())
        else:
            texto = str(valor_campo).strip()
        if not texto:
            texto = "—"
        itens.append(f"- **{rotulo}:** {texto}")

    with st.container(border=True):
        st.markdown(f"### 🍱 Menu do próximo lanche ({data_txt})")
        if itens:
            st.markdown("\n".join(itens))
        else:
            st.markdown("Menu ainda não publicado.")


_render_menu_info(_normalizar_data_menu(df_menu))

st.markdown(
    """
    ### 📄 Formulário de Marcação de Lanche
    Preencha o formulário abaixo para marcar o lanche do seu escuteiro.
    """
)

st.components.v1.html(
    """
    <iframe class="airtable-embed"
        src="https://airtable.com/embed/appzwzHD5YUCyIx63/pagYSCRWOlZSk5hW8/form"
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
