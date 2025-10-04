# menu.py
import streamlit as st

# Caminhos das páginas no diretório `pages/`
PAGE_PATHS = {
    "home": "pages/home.py",
    "pedidos": "pages/1_\U0001f4e6_Pedidos.py",
    "calendario": "pages/2_\U0001f4c5_Calendario.py",
    "voluntariado": "pages/3_\U0001f468\u200d\U0001f469\u200d\U0001f467\u200d\U0001f466_Voluntariado.py",
    "escuteiros": "pages/4_\U0001f466_Escuteiros.py",
    "conta_corrente": "pages/5_\U0001f4b0_ContaCorrente.py",
}


def _hide_streamlit_sidebar_nav() -> None:
    """Esconde o menu automático do Streamlit para evitar duplicação."""
    if st.session_state.get("_lobitos_nav_hidden"):
        return
    st.markdown(
        """
        <style>
            [data-testid="stSidebarNav"] {display: none;}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.session_state["_lobitos_nav_hidden"] = True


def authenticated_menu() -> None:
    role = st.session_state.get("role")
    _hide_streamlit_sidebar_nav()

    icons = {
        "admin": "👑",
        "tesoureiro": "💰",
        "pais": "🏠",
    }

    st.sidebar.header("Navegação")
    st.sidebar.page_link(PAGE_PATHS["home"], label="🏠 Início")
    st.sidebar.page_link(PAGE_PATHS["calendario"], label="📅 Calendário")
    st.sidebar.page_link(PAGE_PATHS["pedidos"], label="📦 Pedidos")
    st.sidebar.page_link(PAGE_PATHS["voluntariado"], label="🙋 Voluntariado")
    st.sidebar.page_link(PAGE_PATHS["escuteiros"], label="🧒 Escuteiros")

    if role in {"tesoureiro", "admin"}:
        st.sidebar.markdown("### Gestão")
        st.sidebar.page_link(
            PAGE_PATHS["conta_corrente"],
            label="💰 Conta Corrente" if role == "tesoureiro" else "💰 Conta Corrente (Admin)",
        )

    if role in icons:
        st.sidebar.caption(f"Sessão ativa: {icons[role]} {role.capitalize()}")

    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Terminar sessão"):
        st.session_state.clear()
        st.switch_page("app.py")


def unauthenticated_menu() -> None:
    _hide_streamlit_sidebar_nav()
    st.sidebar.header("Acesso")
    st.sidebar.page_link("app.py", label="🔑 Login")


def menu() -> None:
    if st.session_state.get("role") is None:
        unauthenticated_menu()
    else:
        authenticated_menu()


def menu_with_redirect() -> None:
    if st.session_state.get("role") is None:
        st.switch_page("app.py")
    menu()
