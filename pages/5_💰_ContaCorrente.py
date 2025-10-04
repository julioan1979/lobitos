import streamlit as st
import pandas as pd
from menu import menu_with_redirect

menu_with_redirect()

st.title("💰 Conta Corrente")

dados = st.session_state.get("dados_cache", {})
df = dados.get("Escuteiros")

if df is None or df.empty:
    st.info("ℹ️ Não há movimentos financeiros registados.")
else:
    colunas_uteis = [
        "Nome do Escuteiro", "Numero de Lanches", "Lanches", "Conta Corrente",
        "Valores recebidos", "Valor Estornado", "Valores doados"
    ]
    colunas_existentes = [c for c in colunas_uteis if c in df.columns]
    df_limpo = df[colunas_existentes].copy()

    df_limpo = df_limpo.rename(columns={
        "Nome do Escuteiro": "Escuteiro",
        "Numero de Lanches": "Nº de Lanches",
        "Lanches": "Valor dos Lanches",
        "Conta Corrente": "Saldo Conta Corrente",
        "Valores recebidos": "Recebimentos",
        "Valor Estornado": "Estornos",
        "Valores doados": "Doações",
    })

    ordem = [
        "Escuteiro",
        "Nº de Lanches", "Valor dos Lanches",
        "Recebimentos", "Doações", "Estornos",
        "Saldo Conta Corrente"
    ]
    df_limpo = df_limpo[[c for c in ordem if c in df_limpo.columns]]

    st.dataframe(df_limpo, use_container_width=True)
