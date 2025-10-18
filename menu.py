import streamlit as st

PAGE_PATHS = {
    "home": "pages/home.py",
    "calendario": "pages/2_\U0001F4C5_Calendario.py",
    "voluntariado": "pages/3_\U0001F468\u200d\U0001F469\u200d\U0001F467\u200d\U0001F466_Voluntariado.py",
    "escuteiros": "pages/4_\U0001F466_Escuteiros.py",
}


def _hide_streamlit_sidebar_nav() -> None:
    st.markdown(
        """
        <style>
            [data-testid="stSidebarNav"],
            section[data-testid="stSidebarNav"],
            section[data-testid="stSidebarNavItems"] {
                display: none !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def authenticated_menu() -> None:
    role = st.session_state.get("role")
    _hide_streamlit_sidebar_nav()

    st.sidebar.header("Navegação")
    st.sidebar.page_link(PAGE_PATHS["escuteiros"], label="\U0001F466 Escuteiros")
    st.sidebar.page_link(PAGE_PATHS["calendario"], label="\U0001F4C5 Calendário")
    st.sidebar.page_link(
        PAGE_PATHS["voluntariado"],
        label="\U0001F468\u200d\U0001F469\u200d\U0001F467\u200d\U0001F466 Voluntariado",
    )
    st.sidebar.page_link(PAGE_PATHS["home"], label="\U0001F3E0 Dashboard")

    st.sidebar.markdown("---")
    if st.sidebar.button("\U0001F6AA Terminar sessão"):
        st.session_state.clear()
        st.switch_page("app.py")


def unauthenticated_menu() -> None:
    _hide_streamlit_sidebar_nav()
    st.sidebar.header("Acesso")
    st.sidebar.page_link("app.py", label="\U0001F511 Login")


def menu() -> None:
    if st.session_state.get("role") is None:
        unauthenticated_menu()
    else:
        authenticated_menu()


def menu_with_redirect() -> None:
    if st.session_state.get("role") is None:
        st.switch_page("app.py")
    menu()
