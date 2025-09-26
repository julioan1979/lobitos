# app.py
import streamlit as st

from menu import menu

st.set_page_config(page_title="Portal Lobitos - Login", page_icon="🐾", layout="centered")

# ==============================
# Carregar senhas de secrets.toml
# ==============================
import streamlit as st
ROLES = st.secrets.get("roles", {})


st.title("🐾 Portal Lobitos")
st.write("Bem-vindo ao Portal dos Lanches Lobitos! Faça login para continuar.")

role = st.selectbox("Perfil", ["pais", "tesoureiro", "admin"])
password = st.text_input("Senha", type="password")

if st.button("Entrar 🚀"):
    if password == ROLES.get(role):
        st.session_state["role"] = role
        st.session_state["logged_in"] = True
        st.success(f"✅ Login como {role.capitalize()}!")
        st.switch_page("pages/home.py")  # vai sempre para o router
    else:
        st.error("❌ Senha incorreta!")
