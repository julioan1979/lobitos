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
user_info = st.session_state.get("user", {})
allowed_escuteiros = set(user_info.get("escuteiros_ids", [])) if user_info else set()

st.session_state["debug_pedidos"] = st.sidebar.checkbox("Debug pedidos", value=st.session_state.get("debug_pedidos", False))

if role is None:
    st.stop()

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
        "pais": ["Pedidos", "Calendario", "Voluntariado Pais", "Escuteiros", "Recipes"],
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
            records = tbl.all()
            rows = [{"id": r["id"], **r["fields"]} for r in records]
            dados[nome] = pd.DataFrame(rows)
            time.sleep(0.25)  # evitar limite 5 requests/s
        except Exception as e:
            st.warning(f"⚠️ Não consegui carregar a tabela {nome}: {e}")
            dados[nome] = pd.DataFrame()
    return dados

def mostrar_barra_acoes(botoes: list[tuple[str, str]], espacador: int = 6) -> dict[str, bool]:
    """Renderiza uma barra de ações consistente e devolve o estado dos botões."""
    if not botoes:
        return {}

    colunas_config = [1] * len(botoes)
    if espacador > 0:
        colunas_config.append(espacador)

    colunas = st.columns(colunas_config)
    resultados = {}

    for coluna, (label, key) in zip(colunas, botoes):
        with coluna:
            resultados[key] = st.button(label, key=key, use_container_width=True)

    return resultados




def mapear_lista(valor, mapping):
    if isinstance(valor, list):
        return ", ".join(mapping.get(v, v) for v in valor)
    if pd.isna(valor):
        return ""
    return mapping.get(valor, valor)

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

    df_pedidos = dados.get("Pedidos", pd.DataFrame())
    df_calendario = dados.get("Calendario", pd.DataFrame())
    df_volunt = dados.get("Voluntariado Pais", pd.DataFrame())
    df_escuteiros = dados.get("Escuteiros", pd.DataFrame())
    df_recipes = dados.get("Recipes", pd.DataFrame())

    if df_escuteiros is None or df_escuteiros.empty or "id" not in df_escuteiros.columns:
        st.warning("ℹ️ Ainda não há escuteiros registados ou a tabela não está completa.")
        return

    df_escuteiros = df_escuteiros.copy()

    if allowed_escuteiros:
        df_escuteiros = df_escuteiros[df_escuteiros["id"].isin(allowed_escuteiros)]
        if df_escuteiros.empty:
            st.warning("⚠️ Não existem dados para os escuteiros associados a esta conta.")
            return
    elif role == "pais":
        st.warning("ℹ️ A sua conta ainda não tem escuteiros associados. Contacte a equipa de administração.")
        return

    def _formatar_label(row: pd.Series) -> str:
        nome = row.get("Nome do Escuteiro")
        codigo = row.get("ID_Escuteiro")
        if pd.isna(nome) or not str(nome).strip():
            nome = "Lobito sem nome"
        if pd.notna(codigo) and str(codigo).strip():
            return f"{nome} ({codigo})"
        return str(nome)

    df_escuteiros["__label"] = df_escuteiros.apply(_formatar_label, axis=1)
    df_escuteiros = df_escuteiros.sort_values("__label")

    escuteiros_ids = df_escuteiros["id"].tolist()
    label_por_id = dict(zip(df_escuteiros["id"], df_escuteiros["__label"]))

    sess_key = "escuteiro_selecionado"
    if sess_key not in st.session_state or st.session_state[sess_key] not in escuteiros_ids:
        st.session_state[sess_key] = escuteiros_ids[0]

    escuteiro_id = st.selectbox(
        "Escolha o Lobito",
        options=escuteiros_ids,
        format_func=lambda value: label_por_id.get(value, value),
        key=sess_key,
    )
    escuteiro_nome = label_por_id.get(escuteiro_id, "")
    escuteiro_row = df_escuteiros[df_escuteiros["id"] == escuteiro_id].iloc[0]

    # 🔘 Barra de Ações
    acoes_pais = mostrar_barra_acoes([
        ("🍞 Marcar Lanche", "btn_marcar_lanche"),
        ("❌ Cancelar Lanche", "btn_cancelar_lanche"),
    ])

    if acoes_pais.get("btn_marcar_lanche"):
        st.session_state["mostrar_form_lanche"] = True
    if acoes_pais.get("btn_cancelar_lanche"):
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

    def _formatar_euro(valor) -> str:
        if pd.isna(valor):
            return "—"
        try:
            return locale.currency(valor, grouping=True)
        except Exception:
            return f"{valor:,.2f} €"

    saldo = pd.to_numeric(escuteiro_row.get("Conta Corrente"), errors="coerce")
    valor_lanches = pd.to_numeric(escuteiro_row.get("Lanches"), errors="coerce")
    recebimentos = pd.to_numeric(escuteiro_row.get("Valores recebidos"), errors="coerce")
    doacoes = pd.to_numeric(escuteiro_row.get("Valores doados"), errors="coerce")
    estornos = pd.to_numeric(escuteiro_row.get("Valor Estornado"), errors="coerce")
    n_lanches = pd.to_numeric(escuteiro_row.get("Numero de Lanches"), errors="coerce")

    st.subheader("💰 Situação financeira")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Saldo atual", _formatar_euro(saldo))
    with col2:
        st.metric("Recebimentos", _formatar_euro(recebimentos))
    with col3:
        st.metric("Valor dos Lanches", _formatar_euro(valor_lanches))
    with col4:
        st.metric("Lanches registados", int(n_lanches) if not pd.isna(n_lanches) else 0)

    col5, col6 = st.columns(2)
    with col5:
        st.metric("Doações", _formatar_euro(doacoes))
    with col6:
        st.metric("Estornos", _formatar_euro(estornos))

    st.divider()

    recipes_map = {}
    if df_recipes is not None and not df_recipes.empty and "id" in df_recipes.columns:
        if "Menu" in df_recipes.columns:
            recipes_map = df_recipes.set_index("id")["Menu"].to_dict()

    def _resolver_lista(valor, mapping) -> str:
        if isinstance(valor, list):
            nomes = [mapping.get(item, item) for item in valor]
            return ", ".join(filter(None, nomes))
        if pd.isna(valor):
            return ""
        return mapping.get(valor, valor)

    def _contem_escuteiro(valor) -> bool:
        if isinstance(valor, list):
            return escuteiro_id in valor
        if pd.isna(valor):
            return False
        return valor == escuteiro_id

    pedidos_escuteiro = pd.DataFrame()
    if df_pedidos is not None and not df_pedidos.empty:
        if "Escuteiros" in df_pedidos.columns:
            mask_pedidos = df_pedidos["Escuteiros"].apply(_contem_escuteiro)
        elif "Escuteiro" in df_pedidos.columns:
            mask_pedidos = df_pedidos["Escuteiro"].apply(_contem_escuteiro)
        else:
            mask_pedidos = pd.Series(False, index=df_pedidos.index)
        pedidos_escuteiro = df_pedidos[mask_pedidos].copy()
        if not pedidos_escuteiro.empty:
            if "Date" in pedidos_escuteiro.columns:
                pedidos_escuteiro["__data"] = pd.to_datetime(pedidos_escuteiro["Date"], errors="coerce")
            elif "Created" in pedidos_escuteiro.columns:
                pedidos_escuteiro["__data"] = pd.to_datetime(pedidos_escuteiro["Created"], errors="coerce")
            else:
                pedidos_escuteiro["__data"] = pd.NaT
            pedidos_escuteiro = pedidos_escuteiro.sort_values("__data", ascending=False)

    if st.session_state.get("debug_pedidos", False):
        with st.expander("Debug pedidos", expanded=False):
            preview_cols = [c for c in ["Date", "Created", "__data", "Escuteiros"] if c in pedidos_escuteiro.columns]
            st.dataframe(pedidos_escuteiro[preview_cols].head(10), use_container_width=True)

    st.subheader("📖 Últimos pedidos")
    if pedidos_escuteiro.empty:
        st.info("ℹ️ Ainda não há pedidos registados para este lobito.")
    else:
        pedidos_mostrar = pedidos_escuteiro.head(5).copy()
        if "__data" in pedidos_mostrar.columns:
            pedidos_mostrar["Data"] = pedidos_mostrar["__data"].dt.strftime("%d/%m/%Y")
        for coluna in ["Bebida", "Lanche", "Fruta"]:
            if coluna in pedidos_mostrar.columns:
                pedidos_mostrar[coluna] = pedidos_mostrar[coluna].apply(lambda valor: _resolver_lista(valor, recipes_map))
        if "Restrição alimentar" in pedidos_mostrar.columns:
            pedidos_mostrar["Restrição alimentar"] = pedidos_mostrar["Restrição alimentar"].fillna("")
        colunas_exibir = [c for c in ["Data", "Lanche", "Bebida", "Fruta", "Restrição alimentar"] if c in pedidos_mostrar.columns]
        st.dataframe(pedidos_mostrar[colunas_exibir], use_container_width=True)

    st.divider()

    hoje = pd.Timestamp.today().normalize()
    metricas_pedidos = pedidos_escuteiro.copy()
    if not metricas_pedidos.empty and "__data" in metricas_pedidos.columns:
        ult30 = metricas_pedidos[metricas_pedidos["__data"] >= hoje - pd.Timedelta(days=30)]
        total_30 = len(ult30)
        total_all = len(metricas_pedidos)
        ultimo_registo = metricas_pedidos.iloc[0]["__data"]
        bebidas_freq = None
        if "Bebida" in metricas_pedidos.columns:
            bebidas_expandidas = []
            for valor in metricas_pedidos["Bebida"].dropna():
                if isinstance(valor, list):
                    bebidas_expandidas.extend(valor)
                else:
                    bebidas_expandidas.append(valor)
            if bebidas_expandidas:
                bebidas_freq = pd.Series(bebidas_expandidas).value_counts().idxmax()
                bebidas_freq = recipes_map.get(bebidas_freq, bebidas_freq)
    else:
        total_30 = 0
        total_all = len(pedidos_escuteiro)
        ultimo_registo = None
        bebidas_freq = None

    col7, col8, col9 = st.columns(3)
    with col7:
        st.metric("Pedidos (30 dias)", total_30)

    senha_mais_recente = None
    if not metricas_pedidos.empty and "Senha_marcações" in metricas_pedidos.columns:
        # usa a mesma ordenação descendente em __data para obter a última senha usada
        senha_mais_recente = metricas_pedidos.iloc[0].get("Senha_marcações")

    with col8:
        st.metric("Senhas (última marcação)", senha_mais_recente or "—")

    with col9:
        st.metric("Último pedido", ultimo_registo.strftime("%d/%m/%Y") if isinstance(ultimo_registo, pd.Timestamp) and not pd.isna(ultimo_registo) else "—")

    if bebidas_freq:
        st.caption(f"🍹 Bebida favorita recente: {bebidas_freq}")

    st.divider()

    calendario_por_id = {}
    if df_calendario is not None and not df_calendario.empty and "id" in df_calendario.columns:
        df_calendario = df_calendario.copy()
        df_calendario["__data"] = pd.to_datetime(df_calendario.get("Data"), errors="coerce")
        calendario_por_id = df_calendario.set_index("id").to_dict(orient="index")

    def _info_calendario(valor):
        ids = []
        if isinstance(valor, list):
            ids = valor
        elif pd.notna(valor):
            ids = [valor]
        infos = []
        for id_cal in ids:
            info = calendario_por_id.get(id_cal)
            if info:
                data = pd.to_datetime(info.get("Data"), errors="coerce")
                agenda = info.get("Agenda")
                infos.append((data, agenda))
        infos = [i for i in infos if i[0] is not None]
        if not infos:
            return None
        return sorted(infos, key=lambda item: item[0])[0]

    proximo_volunt = None
    if df_volunt is not None and not df_volunt.empty and "Escuteiro" in df_volunt.columns:
        df_volunt = df_volunt.copy()
        df_volunt = df_volunt[df_volunt["Escuteiro"].apply(_contem_escuteiro)].copy()
        if "Cancelado" in df_volunt.columns:
            df_volunt = df_volunt[~df_volunt["Cancelado"].astype(str).str.lower().eq("true")]
        if not df_volunt.empty:
            if "Date (calendário)" in df_volunt.columns:
                df_volunt["__info"] = df_volunt["Date (calendário)"].apply(_info_calendario)
            else:
                df_volunt["__info"] = None
            df_volunt = df_volunt[df_volunt["__info"].notna()]
            if not df_volunt.empty:
                df_volunt["__data"] = df_volunt["__info"].apply(lambda item: item[0])
                df_volunt["__agenda"] = df_volunt["__info"].apply(lambda item: item[1])
                df_volunt = df_volunt[df_volunt["__data"] >= hoje]
                if not df_volunt.empty:
                    proximo_volunt = df_volunt.sort_values("__data").iloc[0]

    st.subheader("📅 Próximos compromissos")
    if proximo_volunt is not None:
        data_vol = proximo_volunt["__data"].strftime("%d/%m/%Y") if not pd.isna(proximo_volunt["__data"]) else "Data a confirmar"
        agenda_vol = proximo_volunt["__agenda"] or "Voluntariado"
        st.success(f"✅ {escuteiro_nome} está inscrito no voluntariado de {data_vol}: {agenda_vol}")
    else:
        proximo_evento = None
        if calendario_por_id:
            df_cal_future = df_calendario[df_calendario["__data"] >= hoje].sort_values("__data")
            if not df_cal_future.empty:
                proximo_evento = df_cal_future.iloc[0]
        if proximo_evento is not None:
            data_evt = proximo_evento["__data"].strftime("%d/%m/%Y") if not pd.isna(proximo_evento["__data"]) else "Data a definir"
            agenda_evt = proximo_evento.get("Agenda", "Atividade da Alcateia")
            st.info(f"📅 Próximo evento da Alcateia: {data_evt} – {agenda_evt}")
        else:
            st.info("ℹ️ Não há eventos futuros registados neste momento.")


def dashboard_tesoureiro(dados: dict):
    st.markdown("## 💰 Dashboard Tesoureiro")

    # 🔘 Barra de Ações
    acoes_tesoureiro = mostrar_barra_acoes([
        ("➕ Recebimento", "btn_recebimento"),
        ("➖ Estorno", "btn_estorno"),
    ])

    if acoes_tesoureiro.get("btn_recebimento"):
        st.session_state["mostrar_form_receb"] = True
    if acoes_tesoureiro.get("btn_estorno"):
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

    st.markdown("### 📝 Ações rápidas")
    acoes_admin = mostrar_barra_acoes([
        ("🚫 Cancelar lanche (forçado)", "btn_admin_cancelar"),
        ("📝 Novo pedido (forçado)", "btn_admin_pedido"),
    ])
    st.caption("Use estas ações apenas em casos excecionais; os formulários abrem em modo forçado.")

    if acoes_admin.get("btn_admin_cancelar"):
        st.session_state["mostrar_form_registo"] = True
    if acoes_admin.get("btn_admin_pedido"):
        st.session_state["mostrar_form_pedido"] = True

    mostrar_formulario(
        session_key="mostrar_form_registo",
        titulo="### 🗂️ Cancelamento de Lanche (Forçado)",
        iframe_url="https://airtable.com/embed/appDSu6pj0DJmZSn8/pagsw4PQrv9RaTdJS/form",
        iframe_height=533,
        container_height=600,
    )

    mostrar_formulario(
        session_key="mostrar_form_pedido",
        titulo="### 📝 Forçar Novo Pedido",
        iframe_url="https://airtable.com/embed/appDSu6pj0DJmZSn8/pag7lEBWX2SdxlWXn/form",
        iframe_height=533,
        container_height=600,
    )

    st.divider()

    df_pedidos = dados.get("Pedidos", pd.DataFrame())
    df_calendario = dados.get("Calendario", pd.DataFrame())
    df_volunt = dados.get("Voluntariado Pais", pd.DataFrame())
    df_receb = dados.get("Recebimento", pd.DataFrame())
    df_esc = dados.get("Escuteiros", pd.DataFrame())
    df_recipes = dados.get("Recipes", pd.DataFrame())

    hoje = pd.Timestamp.today().normalize()

    recipes_map = {}
    if df_recipes is not None and not df_recipes.empty and "id" in df_recipes.columns:
        recipes_map = df_recipes.set_index("id").get("Menu", pd.Series(dtype=str)).dropna().to_dict()

    escuteiros_map = {}
    if df_esc is not None and not df_esc.empty and "id" in df_esc.columns:
        escuteiros_map = df_esc.set_index("id").get("Nome do Escuteiro", pd.Series(dtype=str)).dropna().to_dict()

    col1, col2, col3, col4 = st.columns(4)

    pendentes_cancel = 0
    if not df_pedidos.empty and "Pendente de Cancelamento" in df_pedidos.columns:
        pendentes_cancel = df_pedidos["Pendente de Cancelamento"].astype(str).str.lower().eq("true").sum()
    with col1:
        st.metric("Cancelamentos pendentes", int(pendentes_cancel))

    eventos_proximos = 0
    if not df_calendario.empty and "Data" in df_calendario.columns:
        datas = pd.to_datetime(df_calendario["Data"], errors="coerce")
        eventos_proximos = ((datas >= hoje) & (datas <= hoje + pd.Timedelta(days=14))).sum()
    with col2:
        st.metric("Eventos (próx. 14 dias)", int(eventos_proximos))

    voluntariado_em_falta = 0
    if not df_volunt.empty:
        df_volunt_check = df_volunt.copy()
        if "Cancelado" in df_volunt_check.columns:
            df_volunt_check = df_volunt_check[~df_volunt_check["Cancelado"].astype(str).str.lower().eq("true")]
        if "Pais" in df_volunt_check.columns:
            voluntariado_em_falta = df_volunt_check["Pais"].apply(lambda x: not isinstance(x, list) or len(x) == 0).sum()
    with col3:
        st.metric("Turnos sem voluntário", int(voluntariado_em_falta))

    escuteiros_sem_email = 0
    if not df_esc.empty:
        cols = [c for c in ["Email", "Email Alternativo"] if c in df_esc.columns]
        if cols:
            escuteiros_sem_email = df_esc[cols].fillna("").apply(lambda row: all(not str(v).strip() for v in row), axis=1).sum()
    with col4:
        st.metric("Escuteiros sem contacto", int(escuteiros_sem_email))

    st.divider()

    st.markdown("### ⚠️ Pedidos com pedidos de cancelamento")
    if df_pedidos.empty or "Pendente de Cancelamento" not in df_pedidos.columns:
        st.info("Nenhum pedido pendente.")
    else:
        df_pend = df_pedidos[df_pedidos["Pendente de Cancelamento"].astype(str).str.lower().eq("true")].copy()
        if df_pend.empty:
            st.info("Nenhum pedido pendente.")
        else:
            if "Date" in df_pend.columns:
                df_pend["Date"] = pd.to_datetime(df_pend["Date"], errors="coerce").dt.strftime("%d/%m/%Y")
            if "Escuteiros" in df_pend.columns:
                df_pend["Escuteiros"] = df_pend["Escuteiros"].apply(lambda v: mapear_lista(v, escuteiros_map))
            for coluna in ["Lanche", "Bebida", "Fruta"]:
                if coluna in df_pend.columns:
                    df_pend[coluna] = df_pend[coluna].apply(lambda v: mapear_lista(v, recipes_map))
            if "Senha_marcações" in df_pend.columns:
                df_pend["Senha_marcações"] = df_pend["Senha_marcações"].fillna("")
            cols = [c for c in ["Date", "Escuteiros", "Lanche", "Bebida", "Fruta", "Senha_marcações", "Cancelado?", "Pendente de Cancelamento"] if c in df_pend.columns]
            st.dataframe(df_pend[cols], use_container_width=True, hide_index=True)

    st.markdown("### 📅 Eventos sem voluntários")
    if df_calendario.empty:
        st.info("Sem eventos registados.")
    else:
        df_cal = df_calendario.copy()
        if "Data" in df_cal.columns:
            df_cal["__data"] = pd.to_datetime(df_cal["Data"], errors="coerce")
        else:
            df_cal["__data"] = pd.NaT

        eventos_com_vol = set()
        if not df_volunt.empty and "Date (calendário)" in df_volunt.columns:
            df_volunt_valid = df_volunt.copy()
            if "Cancelado" in df_volunt_valid.columns:
                df_volunt_valid = df_volunt_valid[~df_volunt_valid["Cancelado"].astype(str).str.lower().eq("true")]
            for val in df_volunt_valid["Date (calendário)"].dropna():
                if isinstance(val, list):
                    eventos_com_vol.update(val)
                else:
                    eventos_com_vol.add(val)

        if "id" in df_cal.columns:
            df_cal["__tem_volunt"] = df_cal["id"].apply(lambda x: x in eventos_com_vol)
            sem_vol = df_cal[~df_cal["__tem_volunt"] & (df_cal["__data"] >= hoje)].copy()
            sem_vol = sem_vol.sort_values("__data")
            if not sem_vol.empty:
                sem_vol["Data"] = sem_vol["__data"].dt.strftime("%d/%m/%Y")
                cols = [c for c in ["Data", "Agenda", "Haverá preparação de Lanches?", "Local"] if c in sem_vol.columns]
                st.dataframe(sem_vol[cols], use_container_width=True, hide_index=True)
            else:
                st.success("Todos os eventos futuros têm voluntários associados.")
        else:
            st.info("Não foi possível cruzar eventos sem voluntários (sem coluna 'id').")

        st.markdown("#### Gestão de eventos e lanches")
        if "id" not in df_cal.columns:
            st.info("Gestão indisponível (sem coluna 'id' no calendário).")
        else:
            futuros = df_cal[df_cal["__data"].notna() & (df_cal["__data"] >= hoje)].sort_values("__data")

            with st.expander("Criar novo evento", expanded=False):
                with st.form("admin_criar_evento"):
                    data_nova = st.date_input("Data do evento", key="admin_novo_data")
                    agenda_nova = st.text_input("Agenda/Descrição", key="admin_novo_agenda")
                    local_novo = st.text_input("Local", value="", key="admin_novo_local") if "Local" in df_cal.columns else None
                    prepara_novo = st.checkbox("Haverá preparação de Lanches?", value=True, key="admin_novo_prepara")
                    submetido = st.form_submit_button("Criar evento")
                if submetido:
                    campos = {
                        "Data": data_nova.strftime("%Y-%m-%d"),
                        "Agenda": agenda_nova,
                        "Haverá preparação de Lanches?": prepara_novo,
                    }
                    if local_novo is not None:
                        campos["Local"] = local_novo
                    try:
                        api.table(BASE_ID, "Calendario").create(campos)
                    except Exception as exc:
                        st.error(f"Não consegui criar o evento: {exc}")
                    else:
                        st.success("Evento criado com sucesso.")
                        st.experimental_rerun()

            with st.expander("Editar evento futuro", expanded=False):
                if futuros.empty:
                    st.info("Sem eventos futuros para atualizar.")
                else:
                    options = list(futuros.index)
                    def _label(idx):
                        row = futuros.loc[idx]
                        data = row.get("__data")
                        data_str = data.strftime("%d/%m/%Y") if pd.notna(data) else "Sem data"
                        agenda = row.get("Agenda") or ""
                        return f"{data_str} – {agenda}"
                    evento_idx = st.selectbox(
                        "Escolha o evento",
                        options,
                        format_func=_label,
                        key="admin_evento_sel",
                    )

                    evento_id = futuros.loc[evento_idx, "id"]
                    evento_row = futuros.loc[evento_idx]
                    nova_data = st.date_input(
                        "Data",
                        value=evento_row.get("__data", hoje).date() if pd.notna(evento_row.get("__data")) else hoje.date(),
                        key=f"admin_evento_data_{evento_id}",
                    )
                    nova_agenda = st.text_input(
                        "Agenda/Descrição",
                        value=evento_row.get("Agenda", ""),
                        key=f"admin_evento_agenda_{evento_id}",
                    )
                    novo_local = None
                    if "Local" in df_cal.columns:
                        novo_local = st.text_input(
                            "Local",
                            value=evento_row.get("Local", ""),
                            key=f"admin_evento_local_{evento_id}",
                        )
                    atual_flag = bool(evento_row.get("Haverá preparação de Lanches?"))
                    novo_flag = st.checkbox(
                        "Haverá preparação de Lanches?",
                        value=atual_flag,
                        key=f"admin_evento_flag_{evento_id}",
                    )
                    if st.button("Guardar alterações", key=f"admin_evento_guardar_{evento_id}"):
                        campos_update = {
                            "Data": nova_data.strftime("%Y-%m-%d"),
                            "Agenda": nova_agenda,
                            "Haverá preparação de Lanches?": novo_flag,
                        }
                        if novo_local is not None:
                            campos_update["Local"] = novo_local
                        try:
                            api.table(BASE_ID, "Calendario").update(evento_id, campos_update)
                        except Exception as exc:
                            st.error(f"Não consegui atualizar o evento: {exc}")
                        else:
                            st.success("Evento atualizado com sucesso.")
                            st.experimental_rerun()

            with st.expander("Cancelar evento", expanded=False):
                if futuros.empty:
                    st.info("Sem eventos futuros para cancelar.")
                else:
                    options = list(futuros.index)
                    evento_idx = st.selectbox(
                        "Escolha o evento para cancelar",
                        options,
                        format_func=lambda idx: futuros.loc[idx, "Agenda"] or futuros.loc[idx, "Data"],
                        key="admin_evento_cancelar_sel",
                    )
                    evento_id = futuros.loc[evento_idx, "id"]
                    if st.button("Cancelar evento", key=f"admin_evento_cancelar_{evento_id}"):
                        try:
                            api.table(BASE_ID, "Calendario").update(evento_id, {"Cancelado": True})
                        except Exception as exc:
                            st.error(f"Não consegui cancelar o evento: {exc}")
                        else:
                            st.success("Evento marcado como cancelado.")
                            st.experimental_rerun()

    st.markdown("### 🧾 Registos recentes")
    col1, col2, col3 = st.columns(3)
    if not df_pedidos.empty and "Created" in df_pedidos.columns:
        df_recent = df_pedidos.sort_values("Created", ascending=False).head(5).copy()
        if "Escuteiros" in df_recent.columns:
            df_recent["Escuteiros"] = df_recent["Escuteiros"].apply(lambda v: mapear_lista(v, escuteiros_map))
        if "Senha_marcações" in df_recent.columns:
            df_recent["Senha_marcações"] = df_recent["Senha_marcações"].fillna("")
        for coluna in ["Lanche", "Bebida", "Fruta"]:
            if coluna in df_recent.columns:
                df_recent[coluna] = df_recent[coluna].apply(lambda v: mapear_lista(v, recipes_map))
        cols = [c for c in ["Created", "Escuteiros", "Lanche", "Bebida", "Fruta", "Senha_marcações"] if c in df_recent.columns]
        with col1:
            st.caption("Pedidos")
            st.dataframe(df_recent[cols], use_container_width=True, hide_index=True)
    if not df_receb.empty and "Created" in df_receb.columns:
        df_recent_rec = df_receb.sort_values("Created", ascending=False).head(5)
        cols = [c for c in ["Created", "Nome do Escuteiro", "Valor Recebido", "Meio de Pagamento"] if c in df_recent_rec.columns]
        with col2:
            st.caption("Recebimentos")
            st.dataframe(df_recent_rec[cols], use_container_width=True, hide_index=True)
    if not df_esc.empty and "Created" in df_esc.columns:
        df_recent_esc = df_esc.sort_values("Created", ascending=False).head(5)
        cols = [c for c in ["Created", "Nome do Escuteiro", "Email", "Status Inativo"] if c in df_recent_esc.columns]
        with col3:
            st.caption("Escuteiros")
            st.dataframe(df_recent_esc[cols], use_container_width=True, hide_index=True)


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

