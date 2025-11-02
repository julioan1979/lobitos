import math
from datetime import date, datetime, timedelta

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from pyairtable import Api

from airtable_config import context_labels, current_context, get_airtable_credentials
from data_utils import (
    formatar_moeda_euro,
    preparar_dataframe_estornos,
    preparar_dataframe_recebimentos,
)
from menu import menu_with_redirect


@st.cache_data(ttl=300)
def carregar_todas_as_tabelas(base_id: str, role: str, token: str) -> dict[str, pd.DataFrame]:
    api = Api(token)
    dados: dict[str, pd.DataFrame] = {}

    tabelas_por_role = {
        "pais": [
            "Pedidos",
            "Calendario",
            "Voluntariado Pais",
            "Escuteiros",
            "Recipes",
            "Publicar Menu do Scouts",
        ],
        "tesoureiro": [
            "Escuteiros",
            "Recebimento",
            "Estorno de Recebimento",
            "Permissoes",
            "Publicar Menu do Scouts",
            "Voluntariado Pais",
        ],
        "admin": [
            "Pedidos",
            "Calendario",
            "Voluntariado Pais",
            "Escuteiros",
            "Recipes",
            "Recebimento",
            "Estorno de Recebimento",
            "Permissoes",
            "Publicar Menu do Scouts",
        ],
    }

    for nome in tabelas_por_role.get(role, []):
        try:
            registros = api.table(base_id, nome).all()
            linhas = [{"id": reg["id"], **reg["fields"]} for reg in registros]
            dados[nome] = pd.DataFrame(linhas)
        except Exception:
            dados[nome] = pd.DataFrame()

    return dados


def normalizar_periodo(valor, fallback: tuple[date, date]) -> tuple[date, date]:
    def _to_date(v):
        if isinstance(v, date):
            return v
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, pd.Timestamp):
            return v.date()
        return None

    if isinstance(valor, (tuple, list)):
        itens = [_to_date(v) for v in valor if _to_date(v) is not None]
    else:
        item = _to_date(valor)
        itens = [item] if item else []

    if len(itens) >= 2:
        inicio, fim = itens[0], itens[1]
    elif len(itens) == 1:
        inicio = fim = itens[0]
    else:
        inicio, fim = fallback

    if inicio > fim:
        inicio, fim = fim, inicio
    return (inicio, fim)


def calcular_delta(atual: float, anterior: float) -> str:
    if anterior in (0, None) or math.isclose(anterior, 0.0):
        return "–"
    variacao = ((atual - anterior) / anterior) * 100
    return f"{variacao:+.1f}%"


def agrupar_movimentos_por_data(df: pd.DataFrame, etiqueta: str) -> pd.DataFrame:
    if df.empty or "Data" not in df.columns:
        return pd.DataFrame(columns=["Data", "Total", "Tipo"])
    agrupado = (
        df.groupby("Data", as_index=False)["Valor (€)"]
        .sum()
        .rename(columns={"Valor (€)": "Total"})
    )
    agrupado["Tipo"] = etiqueta
    return agrupado


def preparar_heatmap(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "Data" not in df.columns:
        return pd.DataFrame(columns=["Semana", "Dia", "Total"])

    trabalho = df.copy()
    trabalho["Semana"] = trabalho["Data"].dt.isocalendar().week.astype(int)
    trabalho["Ano"] = trabalho["Data"].dt.isocalendar().year.astype(int)
    trabalho["Dia"] = trabalho["Data"].dt.day_name(locale="pt_PT")
    trabalho["Dia"] = pd.Categorical(
        trabalho["Dia"],
        categories=["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"],
        ordered=True,
    )
    return (
        trabalho.groupby(["Ano", "Semana", "Dia"], as_index=False)["Valor (€)"]
        .sum()
        .rename(columns={"Valor (€)": "Total"})
    )


def contar_ocorrencias(df: pd.DataFrame, coluna: str) -> pd.DataFrame:
    if df.empty or coluna not in df.columns:
        return pd.DataFrame(columns=["Item", "Total"])
    valores: list[str] = []
    for item in df[coluna].dropna():
        if isinstance(item, list):
            valores.extend([str(v).strip() for v in item if str(v).strip()])
        elif isinstance(item, str):
            valores.append(item.strip())
    serie = pd.Series(valores)
    if serie.empty:
        return pd.DataFrame(columns=["Item", "Total"])
    contagem = serie.value_counts().reset_index()
    contagem.columns = ["Item", "Total"]
    return contagem


def calcular_aging_contas(df_cotas: pd.DataFrame) -> pd.DataFrame:
    if df_cotas.empty or "Conta Corrente" not in df_cotas.columns:
        return pd.DataFrame(columns=["Faixa", "Total"])

    contas = pd.to_numeric(df_cotas["Conta Corrente"], errors="coerce").fillna(0)
    bins = [-float("inf"), -20, -10, 0, float("inf")]
    labels = ["≤ -20€", "-20€ a -10€", "-10€ a 0€", "≥ 0€"]
    categorias = pd.cut(contas, bins=bins, labels=labels)
    return (
        categorias.value_counts()
        .rename_axis("Faixa")
        .reset_index(name="Total")
        .sort_values("Faixa", ascending=False)
    )


def main():
    st.set_page_config(page_title="Estatísticas Gerais", page_icon="📊", layout="wide")
    menu_with_redirect()

    if current_context() is None or st.session_state.get("role") is None:
        st.switch_page("app.py")
        st.stop()

    role = st.session_state.get("role", "tesoureiro")
    AIRTABLE_TOKEN, BASE_ID = get_airtable_credentials()
    dados = carregar_todas_as_tabelas(BASE_ID, role, AIRTABLE_TOKEN)

    df_rec_limpo, escuteiros_map, permissoes_map, mapa_nomes_ids = preparar_dataframe_recebimentos(dados)
    df_estornos = preparar_dataframe_estornos(dados, escuteiros_map, permissoes_map, mapa_nomes_ids)
    df_cotas = dados.get("Escuteiros", pd.DataFrame())
    df_menu = dados.get("Publicar Menu do Scouts", pd.DataFrame())
    df_volunt = dados.get("Voluntariado Pais", pd.DataFrame())

    hoje = pd.Timestamp.today().date()
    periodo_key = "estatisticas_periodo"
    widget_key = "estatisticas_periodo_widget"

    periodo_default = (hoje - timedelta(days=27), hoje)
    st.session_state.setdefault(periodo_key, periodo_default)
    st.session_state.setdefault(widget_key, periodo_default)

    st.title("📊 Estatísticas Gerais")
    legenda = context_labels()
    if legenda:
        st.caption(legenda)

    with st.container():
        filtro_cols = st.columns([2, 3])
        with filtro_cols[1]:
            botoes = st.columns(4)

            def _definir_periodo(novo_inicio: date, novo_fim: date) -> None:
                periodo = normalizar_periodo((novo_inicio, novo_fim), periodo_default)
                st.session_state[periodo_key] = periodo
                st.session_state[widget_key] = periodo

            if botoes[0].button("Hoje", use_container_width=True):
                _definir_periodo(hoje, hoje)
            if botoes[1].button("Últimos 3 dias", use_container_width=True):
                _definir_periodo(hoje - timedelta(days=2), hoje)
            if botoes[2].button("Esta semana", use_container_width=True):
                inicio_semana = hoje - timedelta(days=hoje.weekday())
                fim_semana = inicio_semana + timedelta(days=6)
                _definir_periodo(inicio_semana, min(fim_semana, hoje))
            if botoes[3].button("Este mês", use_container_width=True):
                inicio_mes = hoje.replace(day=1)
                if hoje.month == 12:
                    fim_mes = date(hoje.year, 12, 31)
                else:
                    prox = hoje.replace(month=hoje.month + 1, day=1)
                    fim_mes = prox - timedelta(days=1)
                _definir_periodo(inicio_mes, fim_mes)

        with filtro_cols[0]:
            periodo_input = st.date_input(
                "Intervalo personalizado",
                value=st.session_state[widget_key],
                key=widget_key,
                format="DD/MM/YYYY",
            )
            periodo_normalizado = normalizar_periodo(periodo_input, periodo_default)
            st.session_state[periodo_key] = periodo_normalizado

    data_inicio, data_fim = st.session_state[periodo_key]
    dias_intervalo = (data_fim - data_inicio).days + 1
    prev_fim = data_inicio - timedelta(days=1)
    prev_inicio = prev_fim - timedelta(days=dias_intervalo - 1)

    def _filtrar_periodo(df: pd.DataFrame, inicio: date, fim: date) -> pd.DataFrame:
        if df.empty or "Data" not in df.columns:
            return pd.DataFrame(columns=df.columns)
        mask = df["Data"].between(pd.Timestamp(inicio), pd.Timestamp(fim), inclusive="both")
        return df.loc[mask].copy()

    df_rec_periodo = _filtrar_periodo(df_rec_limpo, data_inicio, data_fim)
    df_estornos_periodo = _filtrar_periodo(df_estornos, data_inicio, data_fim)
    df_rec_prev = _filtrar_periodo(df_rec_limpo, prev_inicio, prev_fim)
    df_estornos_prev = _filtrar_periodo(df_estornos, prev_inicio, prev_fim)

    total_recebimentos = df_rec_periodo["Valor (€)"].sum()
    total_estornos = df_estornos_periodo["Valor (€)"].sum()
    saldo_liquido = total_recebimentos - total_estornos
    movimentos = len(df_rec_periodo) + len(df_estornos_periodo)
    ticket_medio = total_recebimentos / len(df_rec_periodo) if len(df_rec_periodo) else 0.0
    saldo_total = pd.to_numeric(df_cotas.get("Conta Corrente", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()

    total_receb_prev = df_rec_prev["Valor (€)"].sum()
    total_est_prev = df_estornos_prev["Valor (€)"].sum()
    saldo_prev = total_receb_prev - total_est_prev

    st.caption(f"Período selecionado: {data_inicio.strftime('%d/%m/%Y')} — {data_fim.strftime('%d/%m/%Y')}")

    kpi_cols = st.columns(5)
    kpi_cols[0].metric("Recebimentos", formatar_moeda_euro(total_recebimentos), calcular_delta(total_recebimentos, total_receb_prev))
    kpi_cols[1].metric("Estornos", formatar_moeda_euro(total_estornos), calcular_delta(total_estornos, total_est_prev))
    kpi_cols[2].metric("Saldo líquido", formatar_moeda_euro(saldo_liquido), calcular_delta(saldo_liquido, saldo_prev))
    kpi_cols[3].metric("Movimentos", f"{movimentos}", f"{len(df_rec_prev) + len(df_estornos_prev)} prev.")
    kpi_cols[4].metric("Ticket médio", formatar_moeda_euro(ticket_medio), calcular_delta(ticket_medio, total_receb_prev / len(df_rec_prev) if len(df_rec_prev) else 0))

    st.subheader("💶 Evolução financeira")
    serie_receb = agrupar_movimentos_por_data(df_rec_periodo, "Recebimentos")
    serie_estornos = agrupar_movimentos_por_data(df_estornos_periodo, "Estornos")
    grafico_dados = pd.concat([serie_receb, serie_estornos], ignore_index=True)

    if not grafico_dados.empty:
        linha = (
            alt.Chart(grafico_dados)
            .mark_line(point=True)
            .encode(
                x=alt.X("Data:T", title="Data"),
                y=alt.Y("Total:Q", title="Valor (€)", stack=None),
                color=alt.Color("Tipo:N", title="Movimento"),
                tooltip=["Tipo", alt.Tooltip("Data:T", title="Data"), alt.Tooltip("Total:Q", title="Valor (€)", format=".2f")],
            )
            .properties(height=280)
        )
        st.altair_chart(linha, use_container_width=True)
    else:
        st.info("Sem movimentos financeiros no período selecionado.")

    heatmap_df = preparar_heatmap(df_rec_periodo)
    if not heatmap_df.empty:
        heatmap = (
            alt.Chart(heatmap_df)
            .mark_rect()
            .encode(
                x=alt.X("Semana:O", title="Semana"),
                y=alt.Y("Dia:O", title="Dia da semana"),
                color=alt.Color("Total:Q", title="Valor (€)", scale=alt.Scale(scheme="blues")),
                tooltip=[
                    alt.Tooltip("Ano:O", title="Ano"),
                    alt.Tooltip("Semana:O", title="Semana"),
                    alt.Tooltip("Dia:O", title="Dia"),
                    alt.Tooltip("Total:Q", title="Valor (€)", format=".2f"),
                ],
            )
            .properties(height=220)
        )
        st.subheader("🔥 Intensidade de recebimentos por semana")
        st.altair_chart(heatmap, use_container_width=True)

    st.subheader("📦 Cotas e saldo geral")
    if not df_cotas.empty:
        cotas = df_cotas.copy()
        cotas["Quota Mensal"] = pd.to_numeric(cotas.get("Quota Mensal"), errors="coerce").fillna(0)
        cotas["Quota Anual"] = pd.to_numeric(cotas.get("Quota Anual"), errors="coerce").fillna(0)
        cotas["Conta Corrente"] = pd.to_numeric(cotas.get("Conta Corrente"), errors="coerce").fillna(0)

        quota_prevista_mes = cotas["Quota Mensal"].sum()
        quota_prevista_ano = cotas["Quota Anual"].sum()
        contas_negativas = cotas[cotas["Conta Corrente"] < 0]["Conta Corrente"]
        divida_total = -contas_negativas.sum()
        escuteiros_total = len(cotas)
        escuteiros_ok = (cotas["Conta Corrente"] >= 0).sum()
        cobertura = (saldo_liquido / quota_prevista_ano) if quota_prevista_ano else 0

        cotas_cols = st.columns(4)
        cotas_cols[0].metric("Saldo total", formatar_moeda_euro(saldo_total))
        cotas_cols[1].metric("Dívida registada", formatar_moeda_euro(divida_total))
        cotas_cols[2].metric("Escuteiros em dia", f"{escuteiros_ok}/{escuteiros_total}")
        cotas_cols[3].metric("Cobertura anual", f"{cobertura*100:.1f}%" if quota_prevista_ano else "–")

        aging_df = calcular_aging_contas(cotas)
        if not aging_df.empty:
            grafico_aging = (
                alt.Chart(aging_df)
                .mark_bar()
                .encode(
                    x=alt.X("Faixa:N", title="Faixa de saldo"),
                    y=alt.Y("Total:Q", title="Escuteiros"),
                    color=alt.Color("Faixa:N", legend=None, scale=alt.Scale(scheme="redyellowgreen")),
                    tooltip=["Faixa", alt.Tooltip("Total:Q", title="Escuteiros")],
                )
                .properties(height=240)
            )
            st.altair_chart(grafico_aging, use_container_width=True)
    else:
        st.info("Não há dados de escuteiros para calcular as cotas.")

    st.subheader("🥪 Preferências de lanches")
    if not df_menu.empty:
        df_menu_trabalho = df_menu.copy()

        for coluna_data in ["Data (from Publicação Filtro)", "Date (from Marcação dos Pais na preparação do Lanche)"]:
            if coluna_data in df_menu_trabalho.columns:
                df_menu_trabalho[coluna_data] = pd.to_datetime(df_menu_trabalho[coluna_data], errors="coerce")

        total_marcacoes = pd.to_numeric(df_menu_trabalho.get("Count (Pedidos)"), errors="coerce").fillna(0).sum()
        cancelados = df_menu_trabalho.get("Cancelado ?", pd.Series(dtype=str)).astype(str).str.lower().isin({"true", "1", "yes"}).sum()
        preparados = len(df_menu_trabalho) - cancelados

        lanches_cols = st.columns(3)
        lanches_cols[0].metric("Total de marcações", f"{int(total_marcacoes)}")
        lanches_cols[1].metric("Lanches cancelados", str(int(cancelados)))
        lanches_cols[2].metric("Registos ativos", str(int(preparados)))

        for titulo, coluna in [("Lanches", "Lanches"), ("Bebidas", "Bebidas"), ("Frutas", "Fruta")]:
            contagem = contar_ocorrencias(df_menu_trabalho, coluna)
            if contagem.empty:
                continue
            grafico = (
                alt.Chart(contagem)
                .mark_bar()
                .encode(
                    x=alt.X("Total:Q", title="Quantidade"),
                    y=alt.Y("Item:N", sort="-x", title=titulo),
                    color=alt.Color("Item:N", legend=None),
                    tooltip=["Item", alt.Tooltip("Total:Q", title="Quantidade")],
                )
                .properties(height=240)
            )
            st.altair_chart(grafico, use_container_width=True)

        if "Data (from Publicação Filtro)" in df_menu_trabalho.columns:
            linha_lanches = (
                df_menu_trabalho.groupby("Data (from Publicação Filtro)", as_index=False)["Count (Pedidos)"]
                .sum()
                .rename(columns={"Data (from Publicação Filtro)": "Data"})
            )
            if not linha_lanches.empty:
                chart_lanches = (
                    alt.Chart(linha_lanches)
                    .mark_line(point=True)
                    .encode(
                        x=alt.X("Data:T", title="Data"),
                        y=alt.Y("Count (Pedidos):Q", title="Marcações"),
                        tooltip=["Data:T", alt.Tooltip("Count (Pedidos):Q", title="Marcações")],
                    )
                    .properties(height=260)
                )
                st.altair_chart(chart_lanches, use_container_width=True)
    else:
        st.info("Não há dados publicados de lanches.")

    st.subheader("🙋 Voluntariado")
    if not df_volunt.empty:
        volunt = df_volunt.copy()
        volunt["Cancelado_flag"] = volunt.get("Cancelado", pd.Series(dtype=str)).astype(str).str.lower().isin({"true", "1", "yes"})
        total_registos = len(volunt)
        cancelamentos = volunt["Cancelado_flag"].sum()
        ativos = total_registos - cancelamentos

        volunt_cols = st.columns(3)
        volunt_cols[0].metric("Registos de voluntariado", str(total_registos))
        volunt_cols[1].metric("Cancelamentos", str(int(cancelamentos)))
        volunt_cols[2].metric("Ativos", str(int(ativos)))

        if "Week Nun Pai Voluntário" in volunt.columns:
            volunt["Semana"] = pd.to_numeric(volunt["Week Nun Pai Voluntário"], errors="coerce").fillna(-1).astype(int)
            contagem_semana = (
                volunt[volunt["Semana"] >= 0]
                .groupby("Semana", as_index=False)["id"]
                .count()
                .rename(columns={"id": "Voluntários"})
            )
            if not contagem_semana.empty:
                grafico_semana = (
                    alt.Chart(contagem_semana)
                    .mark_bar()
                    .encode(
                        x=alt.X("Semana:O", title="Semana"),
                        y=alt.Y("Voluntários:Q", title="Voluntários ativos"),
                        tooltip=["Semana", "Voluntários"],
                        color=alt.Color("Voluntários:Q", legend=None, scale=alt.Scale(scheme="tealblues")),
                    )
                    .properties(height=260)
                )
                st.altair_chart(grafico_semana, use_container_width=True)
    else:
        st.info("Ainda não existem registos de voluntariado.")


if __name__ == "__main__":
    main()
