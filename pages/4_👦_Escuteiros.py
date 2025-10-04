import pandas as pd
import streamlit as st
from menu import menu_with_redirect

menu_with_redirect()

st.title("🧒 Escuteiros")

dados = st.session_state.get("dados_cache", {})
df_cal = dados.get("Calendario", pd.DataFrame())
df_vol = dados.get("Voluntariado Pais", pd.DataFrame())

st.markdown(
    """
    ### 📄 Formulário de Marcação de Lanche
    Preencha o formulário abaixo para marcar o lanche do seu escuteiro.
    """
)

st.components.v1.html(
    """
    <iframe class="airtable-embed"
        src="https://airtable.com/embed/appzwzHD5YUCyIx63/pagYSCRWOlZSk5hW8/form"
        frameborder="0" onmousewheel="" width="100%" height="650"
        style="background: transparent; border: 1px solid #ccc;">
    </iframe>
    """,
    height=700,
    scrolling=True,
)

if st.button("🔄 Recarregar formulário"):
    st.experimental_rerun()

st.markdown("---")

hoje = pd.Timestamp.today().normalize()
if df_cal is None or df_cal.empty or "id" not in df_cal.columns:
    st.info("Ainda não há eventos do calendário disponíveis.")
else:
    df_cal = df_cal.copy()
    df_cal["__data"] = pd.to_datetime(df_cal.get("Data"), errors="coerce")

    if "Haverá preparação de Lanches?" in df_cal.columns:
        df_cal = df_cal[df_cal["Haverá preparação de Lanches?"].fillna(False).astype(bool)]

    agenda = df_cal[df_cal["__data"].notna() & (df_cal["__data"] >= hoje)].sort_values("__data")

    if agenda.empty:
        st.info("Nenhum lanche marcado para as próximas datas.")
    else:
        voluntarios_por_evento: dict[str, list[str]] = {}
        if df_vol is not None and not df_vol.empty:
            df_vol = df_vol.copy()
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
                    nomes_fmt = ", ".join(str(nome) for nome in nomes if pd.notna(nome))
                elif pd.notna(nomes):
                    nomes_fmt = str(nomes)
                else:
                    nomes_fmt = ""

                for evento_id in evento_ids:
                    voluntarios_por_evento.setdefault(evento_id, [])
                    if nomes_fmt:
                        voluntarios_por_evento[evento_id].append(nomes_fmt)

        agenda_display = agenda.copy()
        agenda_display["Data"] = agenda_display["__data"].dt.strftime("%d/%m/%Y")
        agenda_display["Voluntários"] = agenda_display["id"].apply(
            lambda eid: ", ".join(voluntarios_por_evento.get(eid, []))
        )
        agenda_display["Status Voluntário"] = agenda_display["id"].apply(
            lambda eid: "✅ Com voluntário" if voluntarios_por_evento.get(eid) else "❌ Em aberto"
        )

        colunas = [
            col for col in ["Data", "Agenda", "Local", "Status Voluntário", "Voluntários"]
            if col in agenda_display.columns
        ]
        st.markdown("### 📆 Próximos lanches")
        st.dataframe(
            agenda_display[colunas],
            use_container_width=True,
            hide_index=True,
        )

st.markdown("---")
st.info(
    "Precisa cancelar uma marcação? Utilize a opção **Cancelar Lanche** no dashboard principal."
)
