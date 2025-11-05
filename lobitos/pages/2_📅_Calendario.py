import pandas as pd
import streamlit as st
from menu import menu_with_redirect
from airtable_config import context_labels

menu_with_redirect()

secao_info = context_labels()
if secao_info:
    st.caption(secao_info)

st.title("📅 Calendário de Atividades")

dados = st.session_state.get("dados_cache", {})
df_cal = dados.get("Calendario", pd.DataFrame())
df_vol = dados.get("Voluntariado Pais", pd.DataFrame())


def _first_existing(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    return None


def _listar_nomes(valor) -> list[str]:
    if isinstance(valor, list):
        return [str(v).strip() for v in valor if pd.notna(v) and str(v).strip()]
    if pd.isna(valor):
        return []
    texto = str(valor).strip()
    return [texto] if texto else []


if df_cal is None or df_cal.empty:
    st.info("ℹ️ Não há eventos registados.")
else:
    df_cal = df_cal.copy()
    df_cal["__data"] = pd.to_datetime(df_cal.get("Data"), errors="coerce")

    hoje = pd.Timestamp.today().normalize()
    futuros = df_cal[df_cal["__data"].notna() & (df_cal["__data"] >= hoje)].sort_values("__data")

    coluna_prep = "Haverá preparação de Lanches?"
    coluna_vol = "Voluntariado Pais"

    def _tem_preparacao(valor) -> bool:
        return isinstance(valor, bool) and valor

    if coluna_prep in futuros.columns:
        futuros_requer_prep = futuros[futuros[coluna_prep].apply(_tem_preparacao)].copy()
    else:
        futuros_requer_prep = futuros.iloc[0:0].copy()

    voluntarios_por_evento: dict[str, list[str]] = {}
    if df_vol is not None and not df_vol.empty:
        df_vol = df_vol.copy()
        col_link = _first_existing(
            df_vol,
            [
                "Record_ID Calendário (from Date ( calendário ))",
                "Record_ID Calendário (from Date (calendário))",
                "Date ( calendário )",
                "Date (calendário)",
            ],
        )
        cancel_col = _first_existing(df_vol, ["Cancelado"])
        if cancel_col:
            df_vol = df_vol[~df_vol[cancel_col].fillna(False)]
        if col_link:
            for _, row in df_vol.iterrows():
                evento_ids = row.get(col_link)
                if isinstance(evento_ids, str):
                    evento_ids = [evento_ids]
                elif not isinstance(evento_ids, list):
                    evento_ids = []
                nomes = _listar_nomes(row.get("Pais"))
                if not evento_ids or not nomes:
                    continue
                for evento_id in evento_ids:
                    voluntarios_por_evento.setdefault(evento_id, [])
                    voluntarios_por_evento[evento_id].extend(nomes)

    def _list_voluntarios(evento_id: str) -> str:
        nomes = voluntarios_por_evento.get(evento_id, [])
        if not nomes:
            return ""
        vistos = []
        for nome in nomes:
            if nome not in vistos:
                vistos.append(nome)
        return ", ".join(vistos)

    pendentes = futuros_requer_prep[
        futuros_requer_prep["id"].apply(lambda eid: not voluntarios_por_evento.get(eid))
    ].copy()
    if pendentes.empty:
        st.success("Todos os lanches com preparação marcada já têm voluntários.")
    else:
        pendentes["Data"] = pendentes["__data"].dt.strftime("%d/%m/%Y")
        colunas_topo = [
            col for col in ["Data", "Dia da Semana", "Agenda", "Local"] if col in pendentes.columns
        ]
        st.markdown("### 📆 Lanches a aguardar voluntários")
        st.dataframe(pendentes[colunas_topo], use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("### 🗂️ Calendário completo")

    colunas_uteis = ["Data", "Dia da Semana", "Agenda", coluna_prep, coluna_vol]
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
            df_limpo[coluna_prep] = df_limpo[coluna_prep].apply(
                lambda x: "Sim" if isinstance(x, bool) and x else ""
            )
        if coluna_vol in df_limpo.columns and "id" in df_cal.columns:
            ids_series = df_cal.loc[df_limpo.index, "id"]
            df_limpo[coluna_vol] = ids_series.apply(_list_voluntarios)

        st.dataframe(df_limpo, use_container_width=True, hide_index=True)
