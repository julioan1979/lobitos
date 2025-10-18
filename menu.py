import streamlit as st

#PAGE_PATHS = {
#    "home": "pages/home.py",
#    "calendario": "pages/2_📅_Calendario.py",
#    "voluntariado": "pages/3_👨‍👩‍👧‍👦_Voluntariado.py",
#    "escuteiros": "pages/4_👦_Escuteiros.py",
#}


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
    st.sidebar.page_link(PAGE_PATHS["escuteiros"], label="🧒 Escuteiros")
    st.sidebar.page_link(PAGE_PATHS["calendario"], label="📅 Calendário")
    st.sidebar.page_link(PAGE_PATHS["voluntariado"], label="🙋 Voluntariado")
    st.sidebar.page_link(PAGE_PATHS["home"], label="🏠 Dashboard")

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
