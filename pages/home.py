#pages/home.py
#-*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from pyairtable import Api
import toml
from menu import menu_with_redirect
import locale
import time
from datetime import datetime
import streamlit.components.v1 as components

import locale

try:
    locale.setlocale(locale.LC_ALL, "pt_PT.UTF-8")
except locale.Error:
    # fallback para não dar erro no Streamlit Cloud
    locale.setlocale(locale.LC_ALL, "")



st.set_page_config(page_title="Portal Lobitos", page_icon="🐾", layout="wide")

# ======================
# 1) Verificar login
# ======================
menu_with_redirect()
role = st.session_state.get("role")

#role = st.selectbox(
#    "Escolha o tipo de utilizador",
#    options=["admin", "tesoureiro", "pais"],
#    index=1  # por defeito tesoureiro
#)

# ======================
# 2) Função para carregar dados do Airtable
# ======================
if "AIRTABLE_TOKEN" in st.secrets:
    AIRTABLE_TOKEN = st.secrets["AIRTABLE_TOKEN"]
    BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
else:
    secrets = toml.load(".streamlit/secrets.toml")
    AIRTABLE_TOKEN = secrets["AIRTABLE_TOKEN"]
    BASE_ID = secrets["AIRTABLE_BASE_ID"]

api = Api(AIRTABLE_TOKEN)

def carregar_todas_as_tabelas(base_id: str, role: str) -> dict:
    dados = {}

    # Mapear tabelas necessárias por role
    tabelas_por_role = {
        "pais": ["Pedidos", "Calendario", "Voluntariado Pais", "Escuteiros"],
        "tesoureiro": ["Escuteiros", "Recebimento", "Publicar Menu do Scouts"],
        "admin": None  # admin carrega todas
    }

    if role == "admin":
        lista_tabelas = [tbl.name for tbl in api.base(base_id).tables()]
    else:
        lista_tabelas = tabelas_por_role.get(role, [])

    for nome in lista_tabelas:
        try:
            tbl = api.table(base_id, nome)
            records = tbl.all(max_records=200)
            rows = [{"id": r["id"], **r["fields"]} for r in records]
            dados[nome] = pd.DataFrame(rows)
            time.sleep(0.25)  # evitar limite 5 requests/s
        except Exception as e:
            st.warning(f"⚠️ Não consegui carregar a tabela {nome}: {e}")
            dados[nome] = pd.DataFrame()
    return dados

def mostrar_formulario(session_key: str, titulo: str, iframe_url: str, iframe_height: int = 600, container_height=None) -> None:
    if not st.session_state.get(session_key, False):
        return
    with st.container(border=True):
        col1, col2 = st.columns([8, 1])
        with col1:
            st.markdown(titulo)
        with col2:
            if st.button("❌", key=f"fechar_{session_key}"):
                st.session_state[session_key] = False
                st.rerun()

        altura_render = container_height if container_height is not None else iframe_height + 50

        components.html(
            f"""
            <iframe class="airtable-embed"
                src="{iframe_url}"
                frameborder="0" onmousewheel="" width="100%" height="{iframe_height}"
                style="background: transparent; border: 1px solid #ccc;">
            </iframe>
            """,
            height=altura_render,
            scrolling=True,
        )


# ======================
# 3) Cache e botão de refresh
# ======================
if "dados_cache" not in st.session_state:
    st.session_state["dados_cache"] = carregar_todas_as_tabelas(BASE_ID, role)
    st.session_state["last_update"] = datetime.now()

if st.button("🔄 Atualizar dados do Airtable"):
    st.session_state["dados_cache"] = carregar_todas_as_tabelas(BASE_ID, role)
    st.session_state["last_update"] = datetime.now()
    st.success("✅ Dados atualizados com sucesso!")

# Mostrar data/hora da última atualização
if "last_update" in st.session_state:
    st.caption(f"🕒 Última atualização: {st.session_state['last_update'].strftime('%d/%m/%Y %H:%M:%S')}")

dados = st.session_state["dados_cache"]

# ======================
# 4) Dashboards
# ======================
def dashboard_pais():
    st.markdown("## 🏡 Bem-vindos, Famílias Lobitos!")
    st.info("Aqui podem gerir lanches, voluntariado e acompanhar as atividades.")

    # 🔘 Barra de Ações
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("🍞 Marcar Lanche"):
            st.session_state["mostrar_form_lanche"] = True
    with col2:
        if st.button("❌ Cancelar Lanche"):
            st.session_state["mostrar_form_cancelar"] = True

    # Formulário Escolha dos Lanches
    mostrar_formulario(
        session_key="mostrar_form_lanche",
        titulo="### 🍞 Formulário de Escolha dos Lanches",
        iframe_url="https://airtable.com/embed/appzwzHD5YUCyIx63/pagYSCRWOlZSk5hW8/form",
        iframe_height=600,
        container_height=650,
    )

    # Formulário Cancelar Lanche
    mostrar_formulario(
        session_key="mostrar_form_cancelar",
        titulo="### ❌ Formulário de Cancelamento de Lanche",
        iframe_url="https://airtable.com/embed/appzwzHD5YUCyIx63/shr5niXN6y71jcFRu",
        iframe_height=533,
        container_height=650,
    )

    st.divider()

    # 📊 Métricas resumidas
    col1, col2, col3, col4 = st.columns(4)
    df_pedidos = dados.get("Pedidos", pd.DataFrame())
    with col1:
        st.metric("📦 Pedidos registados", len(df_pedidos) if not df_pedidos.empty else 0)

    df_calendario = dados.get("Calendario", pd.DataFrame())
    with col2:
        st.metric("📅 Eventos futuros", len(df_calendario) if not df_calendario.empty else 0)

    df_volunt = dados.get("Voluntariado Pais", pd.DataFrame())
    with col3:
        st.metric("🙋 Voluntariado marcado", len(df_volunt) if not df_volunt.empty else 0)

    df_cc = dados.get("Escuteiros", pd.DataFrame())
    with col4:
        saldo_total = df_cc["Conta Corrente"].fillna(0).sum() if not df_cc.empty else 0
        st.metric("💰 Saldo Alcateia", f"{saldo_total:.2f} €")



def dashboard_tesoureiro(dados: dict):
    st.markdown("## 💰 Dashboard Tesoureiro")

    # 🔘 Barra de Ações
    col1, col2, col3 = st.columns([1,1,6])
    with col1:
        if st.button("➕ Recebimento"):
            st.session_state["mostrar_form_receb"] = True
    with col2:
        if st.button("➖ Estorno"):
            st.session_state["mostrar_form_estorno"] = True

    

    # Mostrar formulário Recebimento
    mostrar_formulario(
        session_key="mostrar_form_receb",
        titulo="### 📋 Formulário de Recebimento",
        iframe_url="https://airtable.com/embed/appzwzHD5YUCyIx63/shrJKmfQLKx223tjS",
        iframe_height=600,
        container_height=650,
    )


    # Mostrar formulário Estorno
    mostrar_formulario(
        session_key="mostrar_form_estorno",
        titulo="### 📋 Formulário de Estorno",
        iframe_url="https://airtable.com/embed/appzwzHD5YUCyIx63/shrWikw7lhXnZFnL6",
        iframe_height=600,
        container_height=650,
    )




    col1, col2, col3, col4 = st.columns(4)

    # Saldo total
    saldo_total = 0
    df_tes = dados.get("Escuteiros", pd.DataFrame())
    if not df_tes.empty and "Conta Corrente" in df_tes.columns:
        saldo_total = df_tes["Conta Corrente"].fillna(0).sum()

    # Rentabilidade da semana corrente
    rentabilidade_semana = 0
    semana_numero = None
    df_semana = dados.get("Publicar Menu do Scouts", pd.DataFrame())
    if (
        not df_semana.empty
        and "Rentabilidade Semana" in df_semana.columns
        and "Week Num Menu Publicado" in df_semana.columns
    ):
        df_semana["Date (from Marcação dos Pais na preparação do Lanche)"] = pd.to_datetime(
            df_semana["Date (from Marcação dos Pais na preparação do Lanche)"],
            errors="coerce"
        )
        ano_atual = pd.Timestamp.today().year
        df_atual = df_semana[
            df_semana["Date (from Marcação dos Pais na preparação do Lanche)"].dt.year == ano_atual
        ]
        if not df_atual.empty:
            idx = df_atual["Week Num Menu Publicado"].idxmax()
            rentabilidade_semana = df_atual.loc[idx, "Rentabilidade Semana"]
            semana_numero = df_atual.loc[idx, "Week Num Menu Publicado"]

    # Nº escuteiros em débito
    n_escuteiros_debito = 0
    if not df_tes.empty and "Conta Corrente" in df_tes.columns:
        n_escuteiros_debito = (df_tes["Conta Corrente"] < 0).sum()

    # Total dívida
    divida_total = 0
    if not df_tes.empty and "Conta Corrente" in df_tes.columns:
        divida_total = df_tes.loc[df_tes["Conta Corrente"] < 0, "Conta Corrente"].sum()

    # Exibir métricas
    with col1:
        st.metric("💰 Saldo Total", f"{saldo_total:.2f} €")
    with col2:
        if semana_numero:
            st.metric("📅 Valor Semana", f"{rentabilidade_semana:.2f} €", delta=f"Semana {semana_numero}")
        else:
            st.metric("📅 Valor Semana", f"{rentabilidade_semana:.2f} €")
    with col3:
        st.metric("👦 Nº Escuteiros Devedores", n_escuteiros_debito)
    with col4:
        st.metric("❌ Total em Dívida", f"{divida_total:.2f} €")

    st.divider()

    # Ranking de Escuteiros
    st.markdown("### 🏆 Ranking de Escuteiros")
    if not df_tes.empty and "Conta Corrente" in df_tes.columns and "Escuteiro" in df_tes.columns:
        top_ricos = df_tes.sort_values("Conta Corrente", ascending=False).head(5).copy()
        df_divida = df_tes[df_tes["Conta Corrente"] < 0].sort_values("Conta Corrente", ascending=True).head(5).copy()

        # formatar como moeda
        for df_temp in [top_ricos, df_divida]:
            if not df_temp.empty:
                df_temp["Conta Corrente"] = pd.to_numeric(df_temp["Conta Corrente"], errors="coerce").map("{:.2f} €".format)

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("💎 Top 5 com maior saldo")
            if not top_ricos.empty:
                styler_ricos = top_ricos[["Escuteiro", "Conta Corrente"]].style.set_properties(
                    subset=["Conta Corrente"], **{"text-align": "center"}
                )
                st.table(styler_ricos)
            else:
                st.info("ℹ️  Nenhum escuteiro com saldo.")

        with col2:
            st.subheader("🚨 Top 5 em dívida")
            if not df_divida.empty:
                styler_divida = df_divida[["Escuteiro", "Conta Corrente"]].style.set_properties(
                    subset=["Conta Corrente"], **{"text-align": "center"}
                )
                st.table(styler_divida)
            else:
                st.info("ℹ️ Nenhum escuteiro em dívida.")
    else:
        st.info("ℹ️ Não há dados suficientes para ranking.")

    # Conta Corrente
    st.divider()
    st.markdown("### 💰 Conta Corrente dos Escuteiros")

    df_cc = dados.get("Escuteiros", pd.DataFrame())
    if df_cc.empty:
        st.info("ℹ️ Não há movimentos financeiros registados.")
    else:
        # Selecionar e renomear colunas
        colunas_uteis = [
            "Nome do Escuteiro", "Numero de Lanches", "Lanches", "Conta Corrente",
            "Valores recebidos", "Valor Estornado", "Valores doados"
        ]
        colunas_existentes = [c for c in colunas_uteis if c in df_cc.columns]

        df_limpo = df_cc[colunas_existentes].rename(columns={
            "Nome do Escuteiro": "Escuteiro",
            "Numero de Lanches": "Nº de Lanches",
            "Lanches": "Valor dos Lanches",
            "Conta Corrente": "Saldo Conta Corrente",
            "Valores recebidos": "Recebimentos",
            "Valor Estornado": "Estornos",
            "Valores doados": "Doações",
        })

        # Ordenar colunas na ordem correta
        ordem = [
            "Escuteiro", "Nº de Lanches", "Valor dos Lanches",
            "Recebimentos", "Doações", "Estornos", "Saldo Conta Corrente"
        ]
        df_limpo = df_limpo[[c for c in ordem if c in df_limpo.columns]]

        # Garantir que colunas numéricas mantêm tipo numérico para filtros/ordenar
        colunas_numericas = [
            "Nº de Lanches",
            "Valor dos Lanches",
            "Recebimentos",
            "Doações",
            "Estornos",
            "Saldo Conta Corrente",
        ]
        for coluna in colunas_numericas:
            if coluna in df_limpo.columns:
                df_limpo[coluna] = pd.to_numeric(df_limpo[coluna], errors="coerce")

        if "Nº de Lanches" in df_limpo.columns:
            df_limpo["Nº de Lanches"] = df_limpo["Nº de Lanches"].astype("Int64")

        column_config = {
            "Escuteiro": st.column_config.TextColumn("Escuteiro", width="medium"),
        }
        if "Nº de Lanches" in df_limpo.columns:
            column_config["Nº de Lanches"] = st.column_config.NumberColumn("Nº de Lanches", format="%d", width="small")

        for coluna in ["Valor dos Lanches", "Recebimentos", "Doações", "Estornos", "Saldo Conta Corrente"]:
            if coluna in df_limpo.columns:
                column_config[coluna] = st.column_config.NumberColumn(coluna, format="%.2f €", width="small")

        st.dataframe(
            df_limpo,
            use_container_width=True,
            column_config=column_config,
        )

    # Recebimentos
    st.divider()
    st.markdown("### 🧾 Recebimentos")

    df_rec = dados.get("Recebimento", pd.DataFrame())
    if df_rec.empty:
        st.info("ℹ️ Não há recebimentos registados.")
    else:
        colunas_uteis = ["Nome do Escuteiro", "Valor Recebido", "Meio de Pagamento", "Date", "Quem recebeu?_OLD"]
        colunas_existentes = [c for c in colunas_uteis if c in df_rec.columns]
        df_rec_limpo = df_rec[colunas_existentes].copy()

        df_rec_limpo = df_rec_limpo.rename(columns={
            "Nome do Escuteiro": "Escuteiro",
            "Valor Recebido": "Valor (€)",
            "Meio de Pagamento": "Meio de Pagamento",
            "Date": "Data",
            "Quem recebeu?_OLD": "Quem Recebeu"
        })

        if "Data" in df_rec_limpo.columns:
            df_rec_limpo["Data"] = pd.to_datetime(df_rec_limpo["Data"], errors="coerce").dt.strftime("%d/%m/%Y")

        st.dataframe(df_rec_limpo, use_container_width=True)



def dashboard_admin(dados: dict):
    st.markdown("## 👑 Dashboard Admin")

    # 🔘 Barra de Ações
    col1, col2, col3 = st.columns([1,1,6])
    with col1:
        if st.button("📝 Novo Registo"):
            st.session_state["mostrar_form_registo"] = True
    with col2:
        if st.button("📋 Novo Pedido"):
            st.session_state["mostrar_form_pedido"] = True

    # Formulário: Novo Registo
    mostrar_formulario(
        session_key="mostrar_form_registo",
        titulo="### 📍 Formulário de Novo Registo",
        iframe_url="https://airtable.com/embed/appDSu6pj0DJmZSn8/pagsw4PQrv9RaTdJS/form",
        iframe_height=533,
        container_height=600,
    )

    # Formulário: Novo Pedido
    mostrar_formulario(
        session_key="mostrar_form_pedido",
        titulo="### 📋 Formulário de Novo Pedido",
        iframe_url="https://airtable.com/embed/appDSu6pj0DJmZSn8/pag7lEBWX2SdxlWXn/form",
        iframe_height=533,
        container_height=600,
    )

    st.divider()

    # Listagem de tabelas (como já estava)
    for nome, df in dados.items():
        st.subheader(f"📂 {nome} ({len(df)} registos)")
        if df.empty:
            st.info("ℹ️ Sem registos.")
        else:
            df_bruto = df.copy()
            for c in df_bruto.columns:
                df_bruto[c] = df_bruto[c].apply(lambda x: str(x) if isinstance(x, (list, dict)) else x)
            st.dataframe(df_bruto.head(20), use_container_width=True)


# ======================
# 5) Mostrar dashboards consoante role
# ======================
if role == "admin":
    dashboard_admin(dados)
    st.divider()
    dashboard_tesoureiro(dados)
    st.divider()
    dashboard_pais()
elif role == "tesoureiro":
    dashboard_tesoureiro(dados)
    st.divider()
    dashboard_pais()
elif role == "pais":
    dashboard_pais()

