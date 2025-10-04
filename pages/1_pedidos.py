import streamlit as st
import pandas as pd
from menu import menu_with_redirect

menu_with_redirect()

st.title("📦 Pedidos")

dados = st.session_state.get("dados_cache", {})
df = dados.get("Pedidos")
df_escuteiros = dados.get("Escuteiros")
df_recipes = dados.get("Recipes")

if df is None or df.empty:
    st.info("ℹ️ Não há pedidos registados.")
else:
    escuteiros_map = {row["id"]: row.get("Nome do Escuteiro", "") for _, row in df_escuteiros.iterrows()} if df_escuteiros is not None else {}
    recipes_map = {row["id"]: row.get("Menu", "") for _, row in df_recipes.iterrows()} if df_recipes is not None else {}

    colunas_uteis = ["Date", "Escuteiros", "Bebida", "Lanche", "Fruta", "Restrição alimentar"]
    colunas_existentes = [c for c in colunas_uteis if c in df.columns]
    df_limpo = df[colunas_existentes].copy()

    if "Date" in df_limpo.columns:
        df_limpo["Date"] = pd.to_datetime(df_limpo["Date"], errors="coerce").dt.strftime("%d/%m/%Y")

    if "Escuteiros" in df_limpo.columns:
        df_limpo["Escuteiros"] = df_limpo["Escuteiros"].apply(
            lambda x: ", ".join(escuteiros_map.get(i, i) for i in (x if isinstance(x, list) else [x])) if pd.notna(x) else ""
        )

    for col in ["Bebida", "Lanche", "Fruta"]:
        if col in df_limpo.columns:
            df_limpo[col] = df_limpo[col].apply(
                lambda x: ", ".join(recipes_map.get(i, i) for i in (x if isinstance(x, list) else [x])) if pd.notna(x) else ""
            )

    st.dataframe(df_limpo, use_container_width=True)
