# menu.py
import streamlit as st

def authenticated_menu():
    role = st.session_state.get("role")

    # Ícones por tipo de utilizador
    icones = {
        "admin": "👑",
        "tesoureiro": "💰",
        "pais": "🏡"
    }

    # Menu comum (todos os utilizadores autenticados)
    st.sidebar.page_link("pages/home.py", label="🏠 Início")
    st.sidebar.page_link("pages/2_📅_Calendario.py", label="📅 Calendário")
    st.sidebar.page_link("pages/1_📦_Pedidos.py", label="📦 Pedidos")
    st.sidebar.page_link("pages/3_👨‍👩‍👧‍👦_Voluntariado.py", label="🙋 Voluntariado")
    st.sidebar.page_link("pages/4_👦_Escuteiros.py", label="👦 Escuteiros")

    # Menu específico por role
    if role == "tesoureiro":
        st.sidebar.page_link("pages/5_💰_ContaCorrente.py", label="💰 Conta Corrente")

    if role == "admin":
        st.sidebar.page_link("pages/5_💰_ContaCorrente.py", label="💰 Conta Corrente (Admin)")

    # 👉 Dashboard dinâmico
    if role in icones:
        st.sidebar.page_link("pages/home.py", label=f"{icones[role]} {role.capitalize()} (Dashboard)")

    # 👉 Botão de logoff
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Terminar sessão"):
        st.session_state.clear()
        st.switch_page("app.py")

def unauthenticated_menu():
    # Para quem não fez login
    st.sidebar.page_link("app.py", label="🔑 Login")

def menu():
    if "role" not in st.session_state or st.session_state.get("role") is None:
        unauthenticated_menu()
    else:
        authenticated_menu()

def menu_with_redirect():
    if "role" not in st.session_state or st.session_state.get("role") is None:
        st.switch_page("app.py")
    menu()
