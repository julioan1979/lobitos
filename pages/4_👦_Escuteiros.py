import streamlit as st
from menu import menu_with_redirect

menu_with_redirect()

st.title("🧒 Escuteiros")

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

if st.button("🔄 Recarregar formulário"):
    st.experimental_rerun()

st.markdown("---")
st.info(
    "Precisa cancelar uma marcação? Utilize a opção **Cancelar Lanche** no dashboard principal."
)
