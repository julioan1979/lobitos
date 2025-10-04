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

    coluna_prep = "Haverá preparação de Lanches?"
    coluna_vol = "Voluntariado Pais"

    if coluna_prep in futuros.columns:
        futuros_requer_prep = futuros[futuros[coluna_prep].fillna(False).astype(bool)].copy()
    else:
        futuros_requer_prep = futuros.iloc[0:0].copy()

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

            nomes_raw = row.get("Pais")
            if isinstance(nomes_raw, list):
                nomes = [str(nome) for nome in nomes_raw if pd.notna(nome)]
            elif pd.notna(nomes_raw):
                nomes = [str(nomes_raw)]
            else:
                nomes = []

            for evento_id in evento_ids:
                if not nomes:
                    continue
                voluntarios_por_evento.setdefault(evento_id, [])
                voluntarios_por_evento[evento_id].extend(nomes)

    def _list_voluntarios(evento_id: str) -> str:
        nomes = voluntarios_por_evento.get(evento_id, [])
        if not nomes:
            return ""
        return ", ".join(dict.fromkeys(nomes))

    if futuros_requer_prep.empty:
        st.info("Não existem lanches em preparação nas próximas datas.")
    else:
        pendentes = futuros_requer_prep[
            futuros_requer_prep[coluna_prep].fillna(False).astype(bool)
            & futuros_requer_prep["id"].apply(lambda eid: not voluntarios_por_evento.get(eid))
        ].copy()
        pendentes["Data"] = pendentes["__data"].dt.strftime("%d/%m/%Y")
        pendentes["Voluntários"] = pendentes["id"].apply(_list_voluntarios)

        colunas_topo = [
            col for col in ["Data", "Dia da Semana", "Agenda", "Local", "Voluntários"]
            if col in pendentes.columns or col == "Voluntários"
        ]
        if pendentes.empty:
            st.success("Todos os lanches com preparação marcada já têm voluntários.")
        else:
            st.markdown("### 📆 Lanches a aguardar voluntários")
            st.dataframe(
                pendentes[colunas_topo],
                use_container_width=True,
                hide_index=True,
            )

    st.markdown("---")
    st.markdown("### 🗂️ Calendário completo")

    colunas_uteis = [
        "Data",
        "Dia da Semana",
        "Agenda",
        coluna_prep,
        coluna_vol,
    ]
    colunas_existentes = [c for c in colunas_uteis if c in df_cal.columns]
    if colunas_existentes:
        df_limpo = df_cal[colunas_existentes].copy()
        if "Data" in df_limpo.columns:
            df_limpo["Data"] = pd.to_datetime(df_limpo["Data"], errors="coerce").dt.strftime("%d/%m/%Y")
        if "Dia da Semana" in df_limpo.columns:
            df_limpo["Dia da Semana"] = df_limpo["Dia da Semana"].apply(
                lambda valor: valor if isinstance(valor, str) else ""
            )
        if coluna_prep in df_limpo.columns:
            df_limpo[coluna_prep] = df_limpo[coluna_prep].apply(lambda x: "Sim" if bool(x) else "")
        if coluna_vol in df_limpo.columns and "id" in df_cal.columns:
            ids_series = df_cal.loc[df_limpo.index, "id"]
            df_limpo[coluna_vol] = ids_series.apply(_list_voluntarios)

        st.dataframe(df_limpo, use_container_width=True, hide_index=True)
