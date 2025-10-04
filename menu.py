# menu.py
import streamlit as st


def authenticated_menu() -> None:
    role = st.session_state.get("role")

    icons = {
        "admin": "👑",
        "tesoureiro": "💰",
        "pais": "🏠",
    }

    st.sidebar.page_link("pages/home.py", label="🏡 Início")
    st.sidebar.page_link("pages/2_calendario.py", label="📅 Calendário")
    st.sidebar.page_link("pages/1_pedidos.py", label="📦 Pedidos")
    st.sidebar.page_link("pages/3_voluntariado.py", label="🙋 Voluntariado")
    st.sidebar.page_link("pages/4_escuteiros.py", label="👦 Escuteiros")

    if role == "tesoureiro":
        st.sidebar.page_link("pages/5_conta_corrente.py", label="💰 Conta Corrente")

    if role == "admin":
        st.sidebar.page_link(
            "pages/5_conta_corrente.py",
            label="💰 Conta Corrente (Admin)",
        )

    if role in icons:
        st.sidebar.page_link(
            "pages/home.py",
            label=f"{icons[role]} {role.capitalize()} (Dashboard)",
        )

    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Terminar sessão"):
        st.session_state.clear()
        st.switch_page("app.py")


def unauthenticated_menu() -> None:
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
