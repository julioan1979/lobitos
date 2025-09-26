import streamlit as st
import pandas as pd
from menu import menu_with_redirect

menu_with_redirect()

st.title("📅 Calendário de Atividades")

dados = st.session_state.get("dados_cache", {})
df = dados.get("Calendario")

if df is None or df.empty:
    st.info("ℹ️ Não há eventos registados.")
else:
    colunas_uteis = ["Data", "Dia da Semana", "Agenda", "Haverá preparação de Lanches?", "Voluntariado Pais"]
    colunas_existentes = [c for c in colunas_uteis if c in df.columns]
    df_limpo = df[colunas_existentes].copy()

    if "Data" in df_limpo.columns:
        df_limpo["Data"] = pd.to_datetime(df_limpo["Data"], errors="coerce").dt.strftime("%d/%m/%Y")

    if "Haverá preparação de Lanches?" in df_limpo.columns:
        df_limpo["Haverá preparação de Lanches?"] = df_limpo["Haverá preparação de Lanches?"].apply(lambda x: "✅ Sim" if x else "❌ Não")

    st.dataframe(df_limpo, use_container_width=True)
