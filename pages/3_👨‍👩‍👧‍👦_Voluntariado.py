import pandas as pd
import streamlit as st
from menu import menu_with_redirect

menu_with_redirect()

st.title("🙋 Voluntariado dos Pais")

st.markdown(
    """
    ### ✋ Registar disponibilidade
    Utilize o formulário abaixo para indicar quando pode ajudar na preparação dos lanches.
    """
)

st.components.v1.html(
    """
    <iframe class="airtable-embed"
        src="https://airtable.com/embed/appDSu6pj0DJmZSn8/shrFWG14Gyx9kLSP1"
        frameborder="0" onmousewheel="" width="100%" height="720"
        style="background: transparent; border: 1px solid #ccc;">
    </iframe>
    """,
    height=770,
    scrolling=True,
)

st.markdown("---")

st.markdown("### 📋 Registos recentes")

dados = st.session_state.get("dados_cache", {})
df = dados.get("Voluntariado Pais", pd.DataFrame())
df_cal = dados.get("Calendario", pd.DataFrame())

def _normalizar_lista(valor):
    if isinstance(valor, list):
        return ", ".join(str(item) for item in valor if pd.notna(item))
    if pd.isna(valor):
        return ""
    return str(valor)

if df is None or df.empty:
    st.info("Ainda não existem voluntários registados.")
else:
    df_vis = df.copy()

    if "Date (calendário)" in df_vis.columns and not df_cal.empty and "id" in df_cal.columns:
        cal_map = df_cal.set_index("id").get("Data", pd.Series(dtype=str)).to_dict()

        def _mapear_datas(valor):
            if isinstance(valor, list):
                datas = [pd.to_datetime(cal_map.get(v), errors="coerce") for v in valor]
            else:
                datas = [pd.to_datetime(cal_map.get(valor), errors="coerce")]
            datas = [d.strftime("%d/%m/%Y") for d in datas if not pd.isna(d)]
            return ", ".join(datas)

        df_vis["Datas"] = df_vis["Date (calendário)"].apply(_mapear_datas)

    for coluna in ["Pais", "Telefone", "email", "Comentários Questões"]:
        if coluna in df_vis.columns:
            df_vis[coluna] = df_vis[coluna].apply(_normalizar_lista)

    colunas = [
        col
        for col in ["Datas", "Escuteiro", "Pais", "Telefone", "email", "Comentários Questões"]
        if col in df_vis.columns
    ]

    st.dataframe(
        df_vis[colunas].head(20),
        use_container_width=True,
        hide_index=True,
    )
