import pandas as pd
import streamlit as st
from menu import menu_with_redirect

menu_with_redirect()

st.title("🧒 Escuteiros")

dados = st.session_state.get("dados_cache", {})
df_menu = dados.get("Publicar Menu do Scouts", pd.DataFrame())

col_data = "Date"
colunas_lanche = [
    ("Entrada", "Entrada"),
    ("Lanche", "Lanche"),
    ("Bebida", "Bebida"),
    ("Sobremesa", "Sobremesa"),
]

if df_menu is not None and not df_menu.empty and col_data in df_menu.columns:
    df_menu = df_menu.copy()
    df_menu[col_data] = pd.to_datetime(df_menu[col_data], errors="coerce")
    df_menu = df_menu[df_menu[col_data].notna()].sort_values(col_data)
    hoje = pd.Timestamp.today().normalize()
    proximo = df_menu[df_menu[col_data] >= hoje]
    destaque = proximo.iloc[0] if not proximo.empty else (df_menu.iloc[-1] if not df_menu.empty else None)
else:
    destaque = None

if destaque is not None:
    data_txt = destaque[col_data].strftime("%d/%m/%Y")
    itens = []
    for rotulo, campo in colunas_lanche:
        valor = destaque.get(campo)
        if isinstance(valor, list):
            texto = ", ".join(str(v) for v in valor if pd.notna(v))
        elif pd.isna(valor):
            texto = "—"
        else:
            texto = str(valor)
        itens.append(f"- **{rotulo}:** {texto}")
    with st.container(border=True):
        st.markdown(f"### 🍽️ Próximo lanche ({data_txt})")
        st.markdown("\n".join(itens))
else:
    st.info("Sem menu publicado para os próximos lanches.")

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
