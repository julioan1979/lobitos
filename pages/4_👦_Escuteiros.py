import streamlit as st
import pandas as pd
from menu import menu_with_redirect

menu_with_redirect()

st.title("👦 Escuteiros")

dados = st.session_state.get("dados_cache", {})
df = dados.get("Escuteiros")

if df is None or df.empty:
    st.info("ℹ️ Não há escuteiros registados.")
else:
    colunas_uteis = [
        "Nome do Escuteiro", "ID_Escuteiro", "Nome do Encarregado", "Email",
        "Email Alternativo", "Tel_Automation", "Data de Aniversário Lobito",
        "Status Inativo", "inativo/desligado", "RGPD"
    ]
    colunas_existentes = [c for c in colunas_uteis if c in df.columns]
    df_limpo = df[colunas_existentes].copy()

    if "Status Inativo" in df.columns or "inativo/desligado" in df.columns:
        df_limpo["Estado"] = df.apply(
            lambda x: "❌ Inativo" if (str(x.get("Status Inativo")) == "True") or (str(x.get("inativo/desligado")) == "True") else "✅ Ativo",
            axis=1
        )

    st.dataframe(df_limpo, use_container_width=True)
