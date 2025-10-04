import streamlit as st
import pandas as pd
from menu import menu_with_redirect

menu_with_redirect()

st.title("👨‍👩‍👧‍👦 Voluntariado dos Pais")

dados = st.session_state.get("dados_cache", {})
df = dados.get("Voluntariado Pais")
df_escuteiros = dados.get("Escuteiros")
df_cal = dados.get("Calendario")

if df is None or df.empty:
    st.info("ℹ️ Não há voluntariado registado.")
else:
    colunas_uteis = ["Date (calendário)", "Escuteiro", "Pais", "Telefone", "email", "Comentários Questões"]
    colunas_existentes = [c for c in colunas_uteis if c in df.columns]
    df_limpo = df[colunas_existentes].copy()

    if "Date (calendário)" in df_limpo.columns and df_cal is not None:
        cal_map = {row["id"]: row.get("Data", "") for _, row in df_cal.iterrows()}
        df_limpo["Data"] = df["Date (calendário)"].apply(
            lambda x: cal_map.get(x, x) if isinstance(x, str)
            else ", ".join(cal_map.get(i, i) for i in x) if isinstance(x, list)
            else x
        )
        df_limpo["Data"] = pd.to_datetime(df_limpo["Data"], errors="coerce").dt.strftime("%d/%m/%Y")

    if "Escuteiro" in df_limpo.columns and df_escuteiros is not None:
        esc_map = {row["id"]: row.get("Nome do Escuteiro", "") for _, row in df_escuteiros.iterrows()}
        df_limpo["Escuteiro"] = df_limpo["Escuteiro"].apply(
            lambda x: esc_map.get(x, x) if isinstance(x, str)
            else ", ".join(esc_map.get(i, i) for i in x) if isinstance(x, list)
            else x
        )

    if "Cancelado" in df.columns:
        df_limpo["Status"] = df["Cancelado"].apply(lambda x: "❌ Cancelado" if x else "✅ Ativo")

    st.dataframe(df_limpo, use_container_width=True)
