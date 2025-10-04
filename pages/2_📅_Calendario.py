import pandas as pd
import streamlit as st
from menu import menu_with_redirect

menu_with_redirect()

st.title("📅 Calendário de Atividades")

dados = st.session_state.get("dados_cache", {})
df_cal = dados.get("Calendario", pd.DataFrame())
df_vol = dados.get("Voluntariado Pais", pd.DataFrame())

if df_cal is None or df_cal.empty:
    st.info("ℹ️ Não há eventos registados.")
else:
    df_cal = df_cal.copy()
    df_cal["__data"] = pd.to_datetime(df_cal.get("Data"), errors="coerce")

    hoje = pd.Timestamp.today().normalize()
    futuros = df_cal[df_cal["__data"].notna() & (df_cal["__data"] >= hoje)].sort_values("__data")

    if "Haverá preparação de Lanches?" in futuros.columns:
        futuros = futuros[futuros["Haverá preparação de Lanches?"].fillna(False).astype(bool)]

    voluntarios_por_evento: dict[str, list[str]] = {}
    if df_vol is not None and not df_vol.empty:
        for _, row in df_vol.iterrows():
            eventos = row.get("Date (calendário)")
            if isinstance(eventos, list):
                evento_ids = eventos
            elif pd.notna(eventos):
                evento_ids = [eventos]
            else:
                continue

            nomes = row.get("Pais")
            if isinstance(nomes, list):
                nomes_fmt = [str(nome) for nome in nomes if pd.notna(nome)]
            elif pd.notna(nomes):
                nomes_fmt = [str(nomes)]
            else:
                nomes_fmt = []

            for evento_id in evento_ids:
                if not nomes_fmt:
                    continue
                voluntarios_por_evento.setdefault(evento_id, [])
                voluntarios_por_evento[evento_id].extend(nomes_fmt)

    if futuros.empty:
        st.info("Não existem lanches marcados nas próximas datas.")
    else:
        tabela = futuros.copy()
        tabela["Data"] = tabela["__data"].dt.strftime("%d/%m/%Y")
        tabela["Voluntários"] = tabela["id"].apply(
            lambda eid: ", ".join(dict.fromkeys(voluntarios_por_evento.get(eid, [])))
        )
        tabela["Status Voluntário"] = tabela["id"].apply(
            lambda eid: "✅ Com voluntário" if voluntarios_por_evento.get(eid) else "❌ Em aberto"
        )

        colunas = [
            col
            for col in ["Data", "Dia da Semana", "Agenda", "Local", "Status Voluntário", "Voluntários"]
            if col in tabela.columns
        ]

        st.dataframe(
            tabela[colunas],
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("---")

    st.markdown("### 🗂️ Calendário completo")
    colunas_uteis = [
        "Data",
        "Dia da Semana",
        "Agenda",
        "Haverá preparação de Lanches?",
        "Voluntariado Pais",
    ]
    colunas_existentes = [c for c in colunas_uteis if c in df_cal.columns]
    if colunas_existentes:
        df_limpo = df_cal[colunas_existentes].copy()
        if "Data" in df_limpo.columns:
            df_limpo["Data"] = pd.to_datetime(df_limpo["Data"], errors="coerce").dt.strftime("%d/%m/%Y")
        if "Haverá preparação de Lanches?" in df_limpo.columns:
            df_limpo["Haverá preparação de Lanches?"] = df_limpo["Haverá preparação de Lanches?"].apply(
                lambda x: "Sim" if bool(x) else ""
            )
        if "Voluntariado Pais" in df_limpo.columns and "id" in df_cal.columns:
            ids_series = df_cal.loc[df_limpo.index, "id"]
            df_limpo["Voluntariado Pais"] = ids_series.apply(
                lambda eid: ", ".join(dict.fromkeys(voluntarios_por_evento.get(eid, [])))
            )
        st.dataframe(df_limpo, use_container_width=True, hide_index=True)
