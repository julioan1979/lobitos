#pages/home.py
#-*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import altair as alt
from pyairtable import Api
from menu import menu_with_redirect
import locale
import time
from datetime import date, datetime, timedelta
from urllib.parse import urlparse, urlunparse
import streamlit.components.v1 as components
from airtable_config import context_labels, current_context, get_airtable_credentials, resolve_form_url

import locale

try:
    locale.setlocale(locale.LC_ALL, "pt_PT.UTF-8")
except locale.Error:
    # fallback para não dar erro no Streamlit Cloud
    locale.setlocale(locale.LC_ALL, "")



st.set_page_config(page_title="Portal Escutista", page_icon="🐾", layout="wide")

# ======================
# 1) Verificar login
# ======================
menu_with_redirect()
role = st.session_state.get("role")
user_info = st.session_state.get("user", {})
allowed_escuteiros = set(user_info.get("escuteiros_ids", [])) if user_info else set()
permissions = st.session_state.get("permissions", {})
is_admin = bool(permissions.get("admin"))
is_tesoureiro = bool(permissions.get("tesoureiro"))
if not permissions:
    is_admin = role == "admin"
    is_tesoureiro = role == "tesoureiro"

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
contexto_atual = current_context()
if contexto_atual is None:
    st.switch_page("app.py")
    st.stop()

DEFAULT_LANCHE_FORM_URL = resolve_form_url("DEFAULT_LANCHE_FORM_URL", "Formulário de Escolha dos Lanches")
secao_legenda = context_labels()
if secao_legenda:
    st.caption(secao_legenda)
AIRTABLE_TOKEN, BASE_ID = get_airtable_credentials()
api = Api(AIRTABLE_TOKEN)

def carregar_todas_as_tabelas(base_id: str, role: str) -> dict:
    dados = {}

    # Mapear tabelas necessárias por role
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

    lista_tabelas = tabelas_por_role.get(role, [])
    tabelas_opcionais = set()

    for nome in lista_tabelas:
        try:
            tbl = api.table(base_id, nome)
            records = tbl.all()
            rows = [{"id": r["id"], **r["fields"]} for r in records]
            dados[nome] = pd.DataFrame(rows)
            time.sleep(0.25)  # evitar limite 5 requests/s
        except Exception as e:
            mensagem = str(e)
            if nome in tabelas_opcionais and "INVALID_PERMISSIONS_OR_MODEL_NOT_FOUND" in mensagem:
                dados[nome] = pd.DataFrame()
                continue
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


def formatar_moeda_euro(valor) -> str:
    if pd.isna(valor):
        return ""

    numero = valor
    if isinstance(valor, str):
        limpo = valor.replace("€", "").replace(" ", "")
        if "," in limpo and "." in limpo:
            limpo = limpo.replace(".", "").replace(",", ".")
        elif "," in limpo:
            limpo = limpo.replace(",", ".")
        try:
            numero = float(limpo)
        except ValueError:
            return valor
    try:
        numero = float(numero)
    except (TypeError, ValueError):
        return str(valor)

    texto = f"{numero:,.2f}"
    texto = texto.replace(",", "x").replace(".", ",").replace("x", ".")
    return f"{texto}€"


def construir_mapa_nomes_por_id(dataset: dict) -> dict[str, str]:
    """Cria um dicionário id -> nome usando quaisquer tabelas já carregadas."""

    def _score_coluna(coluna: str) -> tuple[int, str]:
        nome_lower = coluna.lower()
        if nome_lower in {"nome", "name"}:
            return (0, nome_lower)
        if "nome" in nome_lower:
            return (1, nome_lower)
        if "name" in nome_lower:
            return (2, nome_lower)
        if "email" in nome_lower:
            return (3, nome_lower)
        return (4, nome_lower)

    mapa: dict[str, str] = {}
    for df in dataset.values():
        if df is None or df.empty or "id" not in df.columns:
            continue

        colunas_texto: list[str] = []
        for coluna in df.columns:
            if coluna == "id":
                continue
            serie = df[coluna]
            if serie.dtype == object or serie.apply(lambda v: isinstance(v, list)).any():
                colunas_texto.append(coluna)

        if not colunas_texto:
            continue

        colunas_texto.sort(key=_score_coluna)

        for coluna in colunas_texto:
            serie = df.set_index("id")[coluna].dropna()
            if serie.empty:
                continue

            serie = serie.apply(lambda v: ", ".join(v) if isinstance(v, list) else v)
            algum_mapeado = False
            for idx, valor in serie.items():
                if not isinstance(valor, str):
                    valor = str(valor)
                valor_limpo = valor.strip()
                if not valor_limpo:
                    continue
                if idx not in mapa:
                    mapa[idx] = valor_limpo
                    algum_mapeado = True
            if algum_mapeado:
                break

    return mapa


def escolher_coluna(df: pd.DataFrame, candidatos: list[str]) -> str | None:
    if df is None or df.empty:
        return None

    colunas = list(df.columns)
    normalizados = {col.lower().strip(): col for col in colunas}
    for candidato in candidatos:
        chave = candidato.lower().strip()
        if chave in normalizados:
            return normalizados[chave]

    for candidato in candidatos:
        chave = candidato.lower().strip()
        for coluna in colunas:
            if chave in coluna.lower().strip():
                return coluna
    return None


def preparar_dataframe_estornos(
    dados: dict,
    escuteiros_map: dict[str, str],
    permissoes_map: dict[str, str],
    mapa_nomes_ids: dict[str, str],
) -> pd.DataFrame:
    possiveis_tabelas = [
        "Estorno de Recebimento",
        "Estornos de Recebimento",
        "Estorno Recebimento",
        "Estorno",
        "Estornos",
    ]
    df_origem = pd.DataFrame()
    origem_utilizada = None
    for nome in possiveis_tabelas:
        df_candidato = dados.get(nome)
        if isinstance(df_candidato, pd.DataFrame) and not df_candidato.empty:
            df_origem = df_candidato.copy()
            origem_utilizada = nome
            break

    if df_origem.empty:
        df_receb = dados.get("Recebimento", pd.DataFrame())
        if isinstance(df_receb, pd.DataFrame) and not df_receb.empty:
            df_origem = df_receb.copy()
            origem_utilizada = "Recebimento"
        else:
            return pd.DataFrame()

    df_trabalho = df_origem.copy()
    if origem_utilizada == "Recebimento":
        mask_estorno = pd.Series(False, index=df_trabalho.index)

        for coluna in ["Tipo de Movimento", "Tipo", "Categoria", "Movimento", "Motivo"]:
            if coluna in df_trabalho.columns:
                serie = df_trabalho[coluna].astype(str).str.lower()
                mask_estorno = mask_estorno | serie.str.contains("estorno", na=False)

        for coluna in ["É Estorno", "E Estorno", "Estorno?", "Estorno", "é Estorno", "é_estorno"]:
            if coluna in df_trabalho.columns:
                serie = df_trabalho[coluna]
                if serie.dtype == bool:
                    mask_estorno = mask_estorno | serie
                else:
                    serie_str = serie.astype(str).str.strip().str.lower()
                    mask_estorno = mask_estorno | serie_str.isin({"1", "true", "verdadeiro", "sim", "yes"})

        if "Valor Estornado" in df_trabalho.columns:
            valores = pd.to_numeric(df_trabalho["Valor Estornado"], errors="coerce").fillna(0).abs()
            mask_estorno = mask_estorno | (valores > 0)

        if "Valor Recebido" in df_trabalho.columns:
            valores = pd.to_numeric(df_trabalho["Valor Recebido"], errors="coerce")
            mask_estorno = mask_estorno | (valores < 0)

        df_trabalho = df_trabalho.loc[mask_estorno].copy()
        if df_trabalho.empty:
            return pd.DataFrame()

    coluna_escuteiro = escolher_coluna(df_trabalho, ["Escuteiros", "Escuteiro", "Escuteiro(s)", "Escuteiros Relacionados"])
    coluna_valor = escolher_coluna(
        df_trabalho,
        [
            "Valor Estornado",
            "Valor Estorno",
            "Valor do Estorno",
            "Valor",
            "Valor (€)",
            "Valor Recebido",
        ],
    )
    coluna_data = escolher_coluna(df_trabalho, ["Data do Estorno", "Date", "Data"])
    coluna_meio = escolher_coluna(
        df_trabalho,
        ["Meio de Pagamento", "Método de Pagamento", "Metodo de Pagamento", "Método", "Metodo"],
    )
    coluna_responsavel = escolher_coluna(
        df_trabalho,
        [
            "Quem Estornou?",
            "Quem Estornou",
            "Quem Recebeu?",
            "Registado Por",
            "Responsável",
            "Criado Por",
        ],
    )

    resultado = pd.DataFrame(index=df_trabalho.index)

    if coluna_escuteiro:
        resultado["Escuteiro"] = df_trabalho[coluna_escuteiro].apply(lambda valor: mapear_lista(valor, escuteiros_map))

    if coluna_valor:
        resultado["Valor (€)"] = pd.to_numeric(df_trabalho[coluna_valor], errors="coerce").abs()

    if coluna_meio:
        resultado["Meio de Pagamento"] = df_trabalho[coluna_meio]

    if coluna_data:
        resultado["Data"] = pd.to_datetime(df_trabalho[coluna_data], errors="coerce").dt.normalize()

    if coluna_responsavel:
        def _mapear_responsavel(valor):
            if permissoes_map:
                texto = mapear_lista(valor, permissoes_map)
                if texto:
                    return texto
            if mapa_nomes_ids:
                texto = mapear_lista(valor, mapa_nomes_ids)
                if texto:
                    return texto
            if escuteiros_map:
                texto = mapear_lista(valor, escuteiros_map)
                if texto:
                    return texto
            return mapear_lista(valor, {})

        resultado["Quem Estornou"] = df_trabalho[coluna_responsavel].apply(_mapear_responsavel)

    resultado = resultado.dropna(how="all")
    if "Valor (€)" in resultado.columns:
        resultado = resultado[resultado["Valor (€)"].notna()]

    return resultado

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


def normalizar_url_airtable(valor_url, fallback: str) -> str:
    """Garante que o URL do Airtable está no formato embed e devolve um fallback se estiver vazio."""
    bruto = valor_url
    if isinstance(bruto, list):
        bruto = bruto[0] if bruto else ""
    if pd.isna(bruto) or not str(bruto).strip():
        return fallback

    candidato = str(bruto).strip()
    try:
        parsed = urlparse(candidato)
    except ValueError:
        return fallback

    if not parsed.netloc:
        parsed = urlparse(f"https://{candidato.lstrip('/')}")
    if "airtable.com" not in parsed.netloc:
        return urlunparse(parsed._replace(scheme=parsed.scheme or "https"))

    path = parsed.path or ""
    if not path.startswith("/embed/"):
        path = "/embed/" + path.lstrip("/")

    normalizado = parsed._replace(
        scheme="https",
        path=path,
    )
    return urlunparse(normalizado)


def obter_form_url(extra_key: str, label: str) -> str:
    """Obtém URL de formulário a partir dos extras da secção, validando obrigatoriedade."""
    return resolve_form_url(extra_key, label)


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
    st.markdown("## 🏡 Bem-vindo, Família Escutista!")
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
            nome = "Escuteiro sem nome"
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
        "Escolha o Escuteiro",
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

    url_escolha_lanche = normalizar_url_airtable(
        escuteiro_row.get("Pre_Field escolha semanal lanches", ""),
        DEFAULT_LANCHE_FORM_URL,
    )

    # Formulário Escolha dos Lanches
    mostrar_formulario(
        session_key="mostrar_form_lanche",
        titulo="### 🍞 Formulário de Escolha dos Lanches",
        iframe_url=url_escolha_lanche,
        iframe_height=600,
        container_height=650,
    )

    # Formulário Cancelar Lanche
    mostrar_formulario(
        session_key="mostrar_form_cancelar",
        titulo="### ❌ Formulário de Cancelamento de Lanche",
        iframe_url=obter_form_url("CANCEL_LANCHE_FORM_URL", "Formulário de Cancelamento de Lanche"),
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

    st.subheader("📖 Últimos pedidos")
    if pedidos_escuteiro.empty:
        st.info("ℹ️ Ainda não há pedidos registados para este Escuteiro.")
    else:
        pedidos_mostrar = pedidos_escuteiro.head(5).copy()
        if "__data" in pedidos_mostrar.columns:
            pedidos_mostrar["Data"] = pedidos_mostrar["__data"].dt.strftime('%d/%m/%Y')
        if "Created" in pedidos_mostrar.columns:
            horarios = pd.to_datetime(pedidos_mostrar["Created"], errors="coerce")
            pedidos_mostrar["Hora"] = horarios.dt.strftime("%H:%M").fillna("")
        elif "__data" in pedidos_mostrar.columns:
            pedidos_mostrar["Hora"] = pedidos_mostrar["__data"].dt.strftime("%H:%M").fillna("")
        for coluna in ["Bebida", "Lanche", "Fruta"]:
            if coluna in pedidos_mostrar.columns:
                pedidos_mostrar[coluna] = pedidos_mostrar[coluna].apply(lambda valor: _resolver_lista(valor, recipes_map))
        if "Restrição alimentar" in pedidos_mostrar.columns:
            pedidos_mostrar["Restrição alimentar"] = pedidos_mostrar["Restrição alimentar"].fillna("")
        colunas_exibir = [c for c in ["Data", "Lanche", "Bebida", "Fruta", "Restrição alimentar"] if c in pedidos_mostrar.columns]
        if "Hora" in pedidos_mostrar.columns:
            if "Data" in colunas_exibir:
                colunas_exibir.insert(colunas_exibir.index("Data") + 1, "Hora")
            else:
                colunas_exibir.insert(0, "Hora")
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
        st.metric("Último pedido", ultimo_registo.strftime('%d/%m/%Y') if isinstance(ultimo_registo, pd.Timestamp) and not pd.isna(ultimo_registo) else "—")

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
        data_vol = proximo_volunt["__data"].strftime('%d/%m/%Y') if not pd.isna(proximo_volunt["__data"]) else "Data a confirmar"
        agenda_vol = proximo_volunt["__agenda"] or "Voluntariado"
        st.success(f"✅ {escuteiro_nome} está inscrito no voluntariado de {data_vol}: {agenda_vol}")
    else:
        proximo_evento = None
        if calendario_por_id:
            df_cal_future = df_calendario[df_calendario["__data"] >= hoje].sort_values("__data")
            if not df_cal_future.empty:
                proximo_evento = df_cal_future.iloc[0]
        if proximo_evento is not None:
            data_evt = proximo_evento["__data"].strftime('%d/%m/%Y') if not pd.isna(proximo_evento["__data"]) else "Data a definir"
            agenda_evt = proximo_evento.get("Agenda", "Atividade da Tropa")
            st.info(f"📅 Próximo evento da Tropa: {data_evt} – {agenda_evt}")
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
        iframe_url=obter_form_url("RECEBIMENTO_FORM_URL", "Formulário de Recebimento"),
        iframe_height=600,
        container_height=650,
    )


    # Mostrar formulário Estorno
    mostrar_formulario(
        session_key="mostrar_form_estorno",
        titulo="### 📋 Formulário de Estorno",
        iframe_url=obter_form_url("ESTORNO_FORM_URL", "Formulário de Estorno"),
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
        df_ranking = df_tes.copy()
        df_ranking["__saldo"] = pd.to_numeric(df_ranking["Conta Corrente"], errors="coerce").fillna(0)

        top_ricos = (
            df_ranking[df_ranking["__saldo"] > 0]
            .sort_values("__saldo", ascending=False)
            .head(5)
            .copy()
        )
        df_divida = (
            df_ranking[df_ranking["__saldo"] < 0]
            .sort_values("__saldo", ascending=True)
            .head(5)
            .copy()
        )

        # formatar como moeda
        for df_temp in [top_ricos, df_divida]:
            if not df_temp.empty:
                df_temp["Conta Corrente"] = df_temp["__saldo"].map(lambda valor: f"{valor:.2f} €")
                df_temp.drop(columns="__saldo", inplace=True)

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("💎 Top 5 com maior saldo")
            if not top_ricos.empty:
                styler_ricos = top_ricos[["Escuteiro", "Conta Corrente"]].style.set_properties(
                    subset=["Conta Corrente"], **{"text-align": "center"}
                )
                st.table(styler_ricos)
            else:
                st.info("ℹ️ Nenhum escuteiro com saldo positivo.")

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
            "Nome do Escuteiro",
            "Numero de Lanches",
            "Lanches",
            "Conta Corrente",
            "Valores recebidos",
            "Valor Estornado",
            "Valores doados",
            "Quota Mensal",
            "Quota Anual",
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
            "Recebimentos", "Doações", "Estornos", "Quota Mensal", "Quota Anual", "Saldo Conta Corrente"
        ]
        df_limpo = df_limpo[[c for c in ordem if c in df_limpo.columns]]

        # Garantir que colunas numéricas mantêm tipo numérico para filtros/ordenar
        colunas_numericas = [
            "Nº de Lanches",
            "Valor dos Lanches",
            "Recebimentos",
            "Doações",
            "Estornos",
            "Quota Mensal",
            "Quota Anual",
            "Saldo Conta Corrente"
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

        for coluna in ["Valor dos Lanches", "Recebimentos", "Doações", "Estornos", "Quota Mensal", "Quota Anual", "Saldo Conta Corrente"]:
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

    def _preparar_recebimentos(dados: dict) -> tuple[pd.DataFrame, dict[str, str], dict[str, str], dict[str, str]]:
        df_rec = dados.get("Recebimento", pd.DataFrame())
        expected_columns = ["Escuteiro", "Valor (€)", "Meio de Pagamento", "Data", "Quem Recebeu"]
        if df_rec is None or df_rec.empty:
            vazio = pd.DataFrame(columns=expected_columns)
            vazio["Valor (€)"] = pd.Series(dtype="float64")
            vazio["Data"] = pd.Series(dtype="datetime64[ns]")
            return vazio, {}, {}, construir_mapa_nomes_por_id(dados)

        colunas_uteis = ["Escuteiros", "Valor Recebido", "Meio de Pagamento", "Date", "Quem Recebeu?"]
        colunas_existentes = [col for col in colunas_uteis if col in df_rec.columns]
        if not colunas_existentes:
            vazio = pd.DataFrame(columns=expected_columns)
            vazio["Valor (€)"] = pd.Series(dtype="float64")
            vazio["Data"] = pd.Series(dtype="datetime64[ns]")
            return vazio, {}, {}, construir_mapa_nomes_por_id(dados)

        df_limpo = df_rec[colunas_existentes].copy().rename(
            columns={
                "Escuteiros": "Escuteiro",
                "Valor Recebido": "Valor (€)",
                "Meio de Pagamento": "Meio de Pagamento",
                "Date": "Data",
                "Quem Recebeu?": "Quem Recebeu",
            }
        )

        df_escuteiros = dados.get("Escuteiros", pd.DataFrame())
        escuteiros_map: dict[str, str] = {}
        if isinstance(df_escuteiros, pd.DataFrame) and not df_escuteiros.empty and "id" in df_escuteiros.columns:
            for coluna_nome in ("Nome do Escuteiro", "Escuteiro", "Nome"):
                if coluna_nome in df_escuteiros.columns:
                    escuteiros_map = df_escuteiros.set_index("id")[coluna_nome].dropna().to_dict()
                    break

        if escuteiros_map and "Escuteiro" in df_limpo.columns:
            df_limpo["Escuteiro"] = df_limpo["Escuteiro"].apply(lambda valor: mapear_lista(valor, escuteiros_map))

        df_permissoes = dados.get("Permissoes", pd.DataFrame())
        permissoes_map: dict[str, str] = {}
        if isinstance(df_permissoes, pd.DataFrame) and not df_permissoes.empty:
            permissoes_map = construir_mapa_nomes_por_id({"Permissoes": df_permissoes})

        mapa_nomes_ids = construir_mapa_nomes_por_id(dados)

        if "Quem Recebeu" in df_limpo.columns:
            candidatos_quem_recebeu = [
                coluna
                for coluna in df_rec.columns
                if coluna not in {"Quem Recebeu?", "Quem recebeu?_OLD"} and coluna.lower().startswith("quem recebeu")
            ]

            def _score_coluna(nome_coluna: str) -> tuple[int, str]:
                nome_lower = nome_coluna.lower()
                if "nome" in nome_lower or "name" in nome_lower:
                    return (0, nome_lower)
                if "lookup" in nome_lower:
                    return (1, nome_lower)
                return (2, nome_lower)

            coluna_escolhida = None
            if candidatos_quem_recebeu:
                candidatos_quem_recebeu.sort(key=_score_coluna)
                coluna_escolhida = candidatos_quem_recebeu[0]

            if coluna_escolhida:
                df_limpo["Quem Recebeu"] = df_rec[coluna_escolhida].apply(lambda valor: mapear_lista(valor, {}))
            elif permissoes_map:
                df_limpo["Quem Recebeu"] = df_limpo["Quem Recebeu"].apply(
                    lambda valor: mapear_lista(valor, permissoes_map)
                )
            elif mapa_nomes_ids:
                df_limpo["Quem Recebeu"] = df_limpo["Quem Recebeu"].apply(
                    lambda valor: mapear_lista(valor, mapa_nomes_ids)
                )
            elif escuteiros_map:
                df_limpo["Quem Recebeu"] = df_limpo["Quem Recebeu"].apply(
                    lambda valor: mapear_lista(valor, escuteiros_map)
                )

        if "Valor (€)" in df_limpo.columns:
            df_limpo["Valor (€)"] = pd.to_numeric(df_limpo["Valor (€)"], errors="coerce")
        else:
            df_limpo["Valor (€)"] = pd.Series(dtype="float64")

        if "Data" in df_limpo.columns:
            df_limpo["Data"] = pd.to_datetime(df_limpo["Data"], errors="coerce").dt.normalize()
        else:
            df_limpo["Data"] = pd.Series(dtype="datetime64[ns]")

        for coluna in ("Escuteiro", "Meio de Pagamento", "Quem Recebeu"):
            if coluna not in df_limpo.columns:
                df_limpo[coluna] = ""

        df_limpo = df_limpo[expected_columns]
        return df_limpo, escuteiros_map, permissoes_map, mapa_nomes_ids

    def _normalizar_estornos(df_estornos: pd.DataFrame | None) -> pd.DataFrame:
        expected_columns = ["Escuteiro", "Valor (€)", "Motivo", "Data", "Quem Recebeu"]
        if df_estornos is None or not isinstance(df_estornos, pd.DataFrame) or df_estornos.empty:
            vazio = pd.DataFrame(columns=expected_columns)
            vazio["Valor (€)"] = pd.Series(dtype="float64")
            vazio["Data"] = pd.Series(dtype="datetime64[ns]")
            return vazio

        resultado = df_estornos.copy()
        if "Valor (€)" in resultado.columns:
            resultado["Valor (€)"] = pd.to_numeric(resultado["Valor (€)"], errors="coerce")
        else:
            resultado["Valor (€)"] = pd.Series(dtype="float64")

        if "Data" in resultado.columns:
            resultado["Data"] = pd.to_datetime(resultado["Data"], errors="coerce").dt.normalize()
        else:
            resultado["Data"] = pd.Series(dtype="datetime64[ns]")

        for coluna in expected_columns:
            if coluna not in resultado.columns:
                if coluna == "Valor (€)":
                    resultado[coluna] = pd.Series(dtype="float64")
                elif coluna == "Data":
                    resultado[coluna] = pd.Series(dtype="datetime64[ns]")
                else:
                    resultado[coluna] = ""

        return resultado[expected_columns]

    def _aplicar_formatacao_display(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        display_df = df.copy()
        if "Valor (€)" in display_df.columns:
            display_df["Valor (€)"] = display_df["Valor (€)"].apply(
                lambda valor: formatar_moeda_euro(valor) if pd.notna(valor) else ""
            )
        if "Data" in display_df.columns:
            display_df["Data"] = pd.to_datetime(display_df["Data"], errors="coerce").dt.strftime("%d/%m/%Y").fillna("")
        return display_df

    def _renderizar_tabela(df_base: pd.DataFrame, mensagem_vazio: str) -> None:
        if df_base.empty:
            st.info(mensagem_vazio)
            return
        st.dataframe(_aplicar_formatacao_display(df_base), use_container_width=True)

    df_rec_origem = dados.get("Recebimento", pd.DataFrame())
    df_rec_limpo, escuteiros_map, permissoes_map, mapa_nomes_ids = _preparar_recebimentos(dados)
    df_estornos = _normalizar_estornos(
        preparar_dataframe_estornos(dados, escuteiros_map, permissoes_map, mapa_nomes_ids)
    )

    periodo_key = "tesouraria_periodo_movimentos"
    hoje = pd.Timestamp.today().date()
    periodo_padrao: tuple[date, date] = (hoje, hoje)

    def _converter_para_date(valor):
        if isinstance(valor, date):
            return valor
        if isinstance(valor, datetime):
            return valor.date()
        if isinstance(valor, pd.Timestamp):
            return valor.date()
        return None

    def _normalizar_periodo(valor):
        if isinstance(valor, (tuple, list)):
            valores = [_converter_para_date(item) for item in valor]
            valores = [item for item in valores if item is not None]
        else:
            item = _converter_para_date(valor)
            valores = [item] if item is not None else []

        if len(valores) >= 2:
            inicio, fim = valores[0], valores[1]
        elif len(valores) == 1:
            inicio = fim = valores[0]
        else:
            inicio, fim = periodo_padrao

        if inicio > fim:
            inicio, fim = fim, inicio
        return inicio, fim

    def _periodo_mes_atual(referencia: date) -> tuple[date, date]:
        primeiro_dia = date(referencia.year, referencia.month, 1)
        if referencia.month == 12:
            proximo_mes = date(referencia.year + 1, 1, 1)
        else:
            proximo_mes = date(referencia.year, referencia.month + 1, 1)
        return primeiro_dia, proximo_mes - timedelta(days=1)

    periodo_atual = _normalizar_periodo(st.session_state.get(periodo_key, periodo_padrao))

    st.markdown("### 📊 Posição de Caixa")

    filtro_cols = st.columns([2, 3])
    novo_periodo: tuple[date, date] | None = None

    atalhos_periodo = {
        "Hoje": lambda referencia: (referencia, referencia),
        "Últimos 3 dias": lambda referencia: (referencia - timedelta(days=2), referencia),
        "Esta semana": lambda referencia: (
            referencia - timedelta(days=referencia.weekday()),
            min(referencia - timedelta(days=referencia.weekday()) + timedelta(days=6), referencia),
        ),
        "Este mês": _periodo_mes_atual,
    }

    with filtro_cols[1]:
        botoes = st.columns(len(atalhos_periodo))
        for (rotulo, funcao_periodo), coluna in zip(atalhos_periodo.items(), botoes):
            if coluna.button(rotulo, use_container_width=True):
                novo_periodo = funcao_periodo(hoje)
                break

    valor_inicial = novo_periodo or periodo_atual
    with filtro_cols[0]:
        periodo_escolhido = st.date_input(
            "Intervalo personalizado",
            value=valor_inicial,
            format="DD/MM/YYYY",
        )

    periodo_atual = _normalizar_periodo(novo_periodo if novo_periodo is not None else periodo_escolhido)
    st.session_state[periodo_key] = periodo_atual

    data_inicio, data_fim = periodo_atual
    data_inicio_ts = pd.Timestamp(data_inicio)
    data_fim_ts = pd.Timestamp(data_fim)

    df_rec_periodo = df_rec_limpo[df_rec_limpo["Data"].between(data_inicio_ts, data_fim_ts, inclusive="both")].copy()
    df_rec_periodo.sort_values("Data", ascending=False, inplace=True)

    df_estornos_periodo = df_estornos[df_estornos["Data"].between(data_inicio_ts, data_fim_ts, inclusive="both")].copy()
    df_estornos_periodo.sort_values("Data", ascending=False, inplace=True)

    total_recebimentos = df_rec_periodo["Valor (€)"].sum()
    total_estornos = df_estornos_periodo["Valor (€)"].sum()
    saldo = total_recebimentos - total_estornos

    st.markdown("#### 🧾 Recebimentos")
    mensagem_recebimentos = (
        "ℹ️ Não há recebimentos registados."
        if df_rec_origem is None or df_rec_origem.empty
        else "ℹ️ Nenhum recebimento no período selecionado."
    )
    _renderizar_tabela(df_rec_periodo, mensagem_recebimentos)

    st.markdown("### ↩️ Estornos de Recebimento")
    if df_estornos.empty:
        st.info("ℹ️ Nenhum estorno registado.")
    else:
        _renderizar_tabela(df_estornos_periodo, "ℹ️ Nenhum estorno no período selecionado.")

    st.caption(
        f"Período selecionado: {data_inicio_ts.strftime('%d/%m/%Y')} - {data_fim_ts.strftime('%d/%m/%Y')}"
    )

    col_metricas = st.columns(3)
    col_metricas[0].metric("Recebido no período", formatar_moeda_euro(total_recebimentos))
    col_metricas[1].metric("Estornado no período", formatar_moeda_euro(total_estornos))
    col_metricas[2].metric("Saldo do período", formatar_moeda_euro(saldo))

def dashboard_admin(dados: dict):
    st.markdown("## 👑 Dashboard Admin")

    def refrescar_dados():
        st.session_state["dados_cache"] = carregar_todas_as_tabelas(BASE_ID, role)
        st.session_state["last_update"] = datetime.now()

    st.markdown("### 📝 Ações rápidas")
    acoes_admin = mostrar_barra_acoes([
        ("🚫 Cancelar lanche (forçado)", "btn_admin_cancelar"),
        ("📝 Novo pedido (forçado)", "btn_admin_pedido"),
        ("🧒 Gestão de escuteiro", "btn_admin_escuteiro"),
    ])
    st.caption("Use estas ações apenas em casos excecionais; os formulários abrem em modo forçado.")

    if acoes_admin.get("btn_admin_cancelar"):
        st.session_state["mostrar_form_registo"] = True
    if acoes_admin.get("btn_admin_pedido"):
        st.session_state["mostrar_form_pedido"] = True
    if acoes_admin.get("btn_admin_escuteiro"):
        st.session_state["mostrar_form_escuteiro"] = True

    mostrar_formulario(
        session_key="mostrar_form_registo",
        titulo="### 🗂️ Cancelamento de Lanche (Forçado)",
        iframe_url=obter_form_url("FORCED_CANCEL_FORM_URL", "Cancelamento de Lanche (forçado)"),
        iframe_height=533,
        container_height=600,
    )

    mostrar_formulario(
        session_key="mostrar_form_pedido",
        titulo="### 📝 Forçar Novo Pedido",
        iframe_url=obter_form_url("FORCED_ORDER_FORM_URL", "Forçar novo pedido"),
        iframe_height=533,
        container_height=600,
    )

    mostrar_formulario(
        session_key="mostrar_form_escuteiro",
        titulo="### 🧒 Gestão de Escuteiros",
        iframe_url=obter_form_url("MANAGE_ESCUTEIROS_FORM_URL", "Gestão de Escuteiros"),
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
        eventos_proximos = ((datas >= hoje) & (datas <= hoje + pd.Timedelta(days=30))).sum()
    with col2:
        st.metric("Lanches (próx. 30 dias)", int(eventos_proximos))

    voluntariado_em_falta = 0
    total_turnos_preparacao = 0
    turnos_com_voluntario = 0
    col_preparacao = "Haver\u00e1 prepara\u00e7\u00e3o de Lanches?"
    col_voluntarios = "Voluntariado Pais"
    if not df_calendario.empty and col_preparacao in df_calendario.columns:
        df_cal_check = df_calendario.copy()
        if "Data" in df_cal_check.columns:
            df_cal_check["__data"] = pd.to_datetime(df_cal_check["Data"], errors="coerce")
            df_cal_check = df_cal_check[df_cal_check["__data"].isna() | (df_cal_check["__data"] >= hoje)]
        df_cal_check = df_cal_check[df_cal_check[col_preparacao].apply(lambda v: isinstance(v, bool) and v)]
        total_turnos_preparacao = len(df_cal_check)

        def _tem_voluntarios(valor) -> bool:
            if isinstance(valor, list):
                return any(str(item).strip() for item in valor)
            if pd.isna(valor):
                return False
            return bool(str(valor).strip())

        if total_turnos_preparacao:
            if col_voluntarios in df_cal_check.columns:
                faltam_series = df_cal_check[col_voluntarios].apply(lambda v: not _tem_voluntarios(v))
                voluntariado_em_falta = int(faltam_series.sum())
                turnos_com_voluntario = int(total_turnos_preparacao - voluntariado_em_falta)
            else:
                voluntariado_em_falta = len(df_cal_check)
                turnos_com_voluntario = 0
    with col3:
        st.metric("Lanches sem voluntario", int(voluntariado_em_falta))

    if total_turnos_preparacao:
        cobertura_percent = (turnos_com_voluntario / total_turnos_preparacao) * 100
        cobertura_texto = f"{cobertura_percent:.0f}%"
        cobertura_delta = f"{turnos_com_voluntario}/{total_turnos_preparacao} com voluntario"
    else:
        cobertura_texto = "N/A"
        cobertura_delta = None
    with col4:
        st.metric("Cobertura de voluntariado", cobertura_texto, delta=cobertura_delta, help="Lanches com voluntario / lanches com preparacao agendada nos próximos 30 dias.")

    st.divider()

    st.markdown("### ⚠️ Pedidos com pedidos de cancelamento")

    def _serie_bool(df_like: pd.DataFrame, col: str) -> pd.Series:
        if col not in df_like.columns:
            return pd.Series(False, index=df_like.index)
        serie = df_like[col]
        if pd.api.types.is_bool_dtype(serie):
            return serie.fillna(False)
        return serie.fillna(False).astype(str).str.lower().eq("true")

    def _preparar_df_pedidos(df_like: pd.DataFrame) -> pd.DataFrame:
        df_display = df_like.copy()
        if df_display.empty:
            return df_display
        if "Date" in df_display.columns:
            df_display["Date"] = pd.to_datetime(df_display["Date"], errors="coerce").dt.strftime("%d/%m/%Y")
        if "Escuteiros" in df_display.columns:
            df_display["Escuteiros"] = df_display["Escuteiros"].apply(lambda v: mapear_lista(v, escuteiros_map))
        for coluna in ["Lanche", "Bebida", "Fruta"]:
            if coluna in df_display.columns:
                df_display[coluna] = df_display[coluna].apply(lambda v: mapear_lista(v, recipes_map))
        if "Senha_marcações" in df_display.columns:
            df_display["Senha_marcações"] = df_display["Senha_marcações"].fillna("")
        colunas_exibicao = [c for c in ["Date", "Escuteiros", "Lanche", "Bebida", "Fruta", "Senha_marcações"] if c in df_display.columns]
        return df_display[colunas_exibicao]

    if df_pedidos.empty or "Pendente de Cancelamento" not in df_pedidos.columns:
        st.info("Nenhum pedido pendente.")
    else:
        pendentes_mask = _serie_bool(df_pedidos, "Pendente de Cancelamento")
        cancelados_mask = _serie_bool(df_pedidos, "Cancelado?")

        df_pend = df_pedidos[pendentes_mask & (~cancelados_mask)].copy()
        df_cancelados = df_pedidos[cancelados_mask].copy()
        df_todos = df_pedidos.copy()

        df_pend_display = _preparar_df_pedidos(df_pend)
        if df_pend_display.empty:
            st.info("Nenhum pedido pendente.")
        else:
            st.dataframe(df_pend_display, use_container_width=True, hide_index=True)

        st.markdown("#### ✅ Pedidos cancelados")
        df_cancelados_display = _preparar_df_pedidos(df_cancelados)
        if df_cancelados_display.empty:
            st.info("Ainda não existem pedidos cancelados.")
        else:
            st.dataframe(df_cancelados_display, use_container_width=True, hide_index=True)

        st.markdown("#### 📋 Todos os pedidos")
        df_todos_display = _preparar_df_pedidos(df_todos)
        if df_todos_display.empty:
            st.info("Sem registos de pedidos.")
        else:
            st.dataframe(df_todos_display, use_container_width=True, hide_index=True)

    st.markdown("### 📅 Eventos sem voluntários")
    if df_calendario.empty:
        st.info("Sem eventos registados.")
    else:
        df_cal = df_calendario.copy()
        if "Data" in df_cal.columns:
            df_cal["__data"] = pd.to_datetime(df_cal["Data"], errors="coerce")
        else:
            df_cal["__data"] = pd.NaT

        def _first_existing_col(df_like, candidates):
            for col_name in candidates:
                if col_name in df_like.columns:
                    return col_name
            return None

        eventos_com_vol = set()
        if not df_volunt.empty:
            df_volunt_valid = df_volunt.copy()
            if "Cancelado" in df_volunt_valid.columns:
                df_volunt_valid = df_volunt_valid[~df_volunt_valid["Cancelado"].astype(str).str.lower().eq("true")]
            coluna_ligacao = _first_existing_col(
                df_volunt_valid,
                [
                    "Record_ID Calendário (from Date ( calendário ))",
                    "Record_ID Calendário (from Date (calendário))",
                    "Record_ID Calendario (from Date ( calendario ))",
                    "Date ( calendário )",
                    "Date (calendário)",
                    "Date ( calendario )",
                ],
            )
            if coluna_ligacao:
                for val in df_volunt_valid[coluna_ligacao].dropna():
                    if isinstance(val, list):
                        eventos_com_vol.update(val)
                    else:
                        eventos_com_vol.add(val)

        if "id" in df_cal.columns:
            df_cal["__tem_volunt"] = df_cal["id"].apply(lambda x: x in eventos_com_vol)
            sem_vol = df_cal[(df_cal["__data"] >= hoje) & (~df_cal["__tem_volunt"])].copy()
            sem_vol = sem_vol.sort_values("__data")
            if sem_vol.empty:
                st.success("Todos os eventos futuros têm voluntários associados.")
            else:
                sem_vol_display = sem_vol.copy()
                sem_vol_display["Data"] = sem_vol_display["__data"].dt.strftime('%d/%m/%Y')
                if "Agenda" not in sem_vol_display.columns:
                    sem_vol_display["Agenda"] = ""
                else:
                    sem_vol_display["Agenda"] = sem_vol_display["Agenda"].fillna("")
                if "Local" in sem_vol_display.columns:
                    sem_vol_display["Local"] = sem_vol_display["Local"].fillna("")

                cols = [c for c in ["Data", "Agenda", "Local"] if c in sem_vol_display.columns]
                col_tabela, col_grafico = st.columns([3, 2])
                with col_tabela:
                    st.dataframe(
                        sem_vol_display[cols],
                        use_container_width=True,
                        hide_index=True,
                        height=360,
                    )
                    st.caption(f"{len(sem_vol_display)} turnos sem voluntarios.")

                with col_grafico:
                    if "__data" not in df_cal.columns:
                        st.info("Sem datas disponiveis para os graficos.")
                    else:
                        tab_faltas, tab_cobertura = st.tabs(["Faltas por mes", "Cobertura por mes"])

                        with tab_faltas:
                            if not sem_vol.empty and "__data" in sem_vol.columns:
                                agrupamento = (
                                    sem_vol["__data"]
                                    .dt.to_period("M")
                                    .value_counts()
                                    .sort_index()
                                )
                                if not agrupamento.empty:
                                    df_barras = (
                                        agrupamento.rename_axis("Periodo")
                                        .to_frame("Turnos em falta")
                                        .reset_index()
                                    )
                                    df_barras["Periodo"] = df_barras["Periodo"].astype(str)
                                    st.bar_chart(
                                        df_barras,
                                        x="Periodo",
                                        y="Turnos em falta",
                                        use_container_width=True,
                                        height=320,
                                    )
                                else:
                                    st.info("Sem turnos em falta neste periodo.")
                            else:
                                st.info("Todos os turnos estao com voluntarios.")

                        with tab_cobertura:
                            df_cobertura = df_cal.copy()
                            df_cobertura = df_cobertura[
                                df_cobertura["__data"].notna()
                                & (df_cobertura["__data"] >= hoje)
                            ].copy()
                            col_pre_evento = "Haverá preparação de Lanches?"
                            if col_pre_evento in df_cobertura.columns:
                                df_cobertura = df_cobertura[
                                    df_cobertura[col_pre_evento].apply(lambda v: isinstance(v, bool) and v)
                                ]

                            if df_cobertura.empty:
                                st.info("Sem dados para agrupar por periodo.")
                            else:
                                df_cobertura["Periodo"] = df_cobertura["__data"].dt.to_period("M").astype(str)
                                df_cobertura["status"] = df_cobertura["id"].apply(
                                    lambda eid: "Com voluntario" if eid in eventos_com_vol else "Sem voluntario"
                                )
                                contagem = (
                                    df_cobertura.groupby(["Periodo", "status"])
                                    .size()
                                    .reset_index(name="Turnos")
                                    .sort_values("Periodo")
                                )
                                if contagem.empty:
                                    st.info("Sem dados para agrupar por periodo.")
                                else:
                                    chart = (
                                        alt.Chart(contagem)
                                        .mark_bar()
                                        .encode(
                                            x=alt.X("Periodo:N", title="Periodo"),
                                            y=alt.Y("Turnos:Q", title="Turnos"),
                                            color=alt.Color(
                                                "status:N",
                                                title="Situacao",
                                                scale=alt.Scale(
                                                    domain=["Com voluntario", "Sem voluntario"],
                                                    range=["#4CAF50", "#F44336"],
                                                ),
                                            ),
                                        )
                                        .properties(height=320)
                                    )
                                    st.altair_chart(chart, use_container_width=True)
        else:
            st.info("Não foi possível cruzar eventos sem voluntários (sem coluna 'id').")

    st.markdown("#### Gestão de eventos e lanches")
    if "id" not in df_calendario.columns:
        st.info("Gestão indisponível (sem coluna 'id' no calendário).")
    else:
        df_cal_full = df_calendario.copy()
        df_cal_full["__data"] = pd.to_datetime(df_cal_full.get("Data"), errors="coerce")
        futuros = df_cal_full[df_cal_full["__data"].notna() & (df_cal_full["__data"] >= hoje)].sort_values("__data")

        def _format_evento(idx):
            row = futuros.loc[idx]
            data = row.get("__data")
            if pd.notna(data):
                data_str = data.strftime('%d/%m/%Y')
            else:
                data_raw = row.get("Data")
                data_str = data_raw if isinstance(data_raw, str) and data_raw else "Sem data"
            agenda = row.get("Agenda") or ""
            return f"{data_str} – {agenda}" if agenda else data_str

        with st.expander("Criar novo evento", expanded=False):
            with st.form("admin_criar_evento"):
                data_nova = st.date_input("Data do evento", key="admin_novo_data")
                agenda_nova = st.text_input("Agenda/Descrição", key="admin_novo_agenda")
                local_novo = st.text_input("Local", value="", key="admin_novo_local") if "Local" in df_cal_full.columns else None
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
                    refrescar_dados()
                    st.rerun()

        st.markdown("##### Editar / cancelar eventos futuros")
        if futuros.empty:
            st.info("Sem eventos futuros para editar.")
        else:
            df_manage = futuros.copy()
            df_manage["ID"] = df_manage["id"]
            df_manage["Data"] = df_manage["__data"].dt.date
            try:
                df_manage["Dia da semana"] = df_manage["__data"].dt.day_name(locale="pt_PT")
            except Exception:
                df_manage["Dia da semana"] = df_manage["__data"].dt.day_name()
            df_manage["Semana"] = df_manage["__data"].dt.isocalendar().week
            if "Agenda" in df_manage.columns:
                df_manage["_agenda_raw"] = df_manage["Agenda"].fillna("")
            else:
                df_manage["_agenda_raw"] = pd.Series("", index=df_manage.index)

            def _limpar_agenda(valor: str) -> str:
                if isinstance(valor, str) and valor.strip().startswith("[CANCELADO]"):
                    return valor.replace("[CANCELADO]", "", 1).strip()
                return valor or ""

            df_manage["Agenda"] = df_manage["_agenda_raw"].apply(_limpar_agenda)
            col_local = "Local" if "Local" in df_manage.columns else None
            if "Haverá preparação de Lanches?" in df_manage.columns:
                df_manage["Preparação"] = df_manage["Haverá preparação de Lanches?"].fillna(False).astype(bool)
            else:
                df_manage["Preparação"] = False
            df_manage["Estado"] = df_manage["_agenda_raw"].apply(lambda txt: "Cancelado" if isinstance(txt, str) and txt.strip().startswith("[CANCELADO]") else "Ativo")
            df_manage["Apagar"] = False

            display_cols = ["Data", "Dia da semana", "Semana", "Agenda"]
            if col_local:
                display_cols.append(col_local)
            display_cols += ["Preparação", "Estado", "Apagar", "ID"]
            df_display = df_manage[display_cols].copy()
            rename_map = {
                "Data": "Data",
                "Dia da semana": "Dia",
                "Semana": "Semana",
                "Agenda": "Agenda",
                "Preparação": "Preparação",
                "Estado": "Estado",
                "Apagar": "Apagar",
                "ID": "ID",
            }
            if col_local:
                rename_map[col_local] = "Local"
            df_display = df_display.rename(columns=rename_map)

            column_config = {
                "Data": st.column_config.DateColumn("Data", format="YYYY-MM-DD"),
                "Dia": st.column_config.Column("Dia"),
                "Semana": st.column_config.NumberColumn("Semana", format="%d", width="small"),
                "Agenda": st.column_config.TextColumn("Agenda/Descrição"),
                "Preparação": st.column_config.CheckboxColumn("Preparação de Lanches?"),
                "Estado": st.column_config.SelectboxColumn("Estado", options=["Ativo", "Cancelado"]),
                "Apagar": st.column_config.CheckboxColumn("Apagar"),
                "ID": st.column_config.Column("ID", disabled=True, width="small"),
            }
            if "Local" in df_display.columns:
                column_config["Local"] = st.column_config.TextColumn("Local")

            st.caption("Marque 'Apagar' para remover um evento sem voluntários associados e clique em 'Guardar alterações da tabela'.")

            editado = st.data_editor(
                df_display,
                use_container_width=True,
                hide_index=True,
                column_config=column_config,
                key="admin_event_editor",
            )
            if st.button("Guardar alterações da tabela", key="admin_event_table_save"):
                edited_records = editado.to_dict("records")
                original_records = df_display.to_dict("records")

                def _normalize_id(value):
                    if value is None:
                        return None
                    if isinstance(value, float) and pd.isna(value):
                        return None
                    value = str(value).strip()
                    return value or None

                def _to_iso(value):
                    if isinstance(value, pd.Timestamp):
                        return value.strftime("%Y-%m-%d")
                    if hasattr(value, "isoformat"):
                        return value.isoformat()
                    if isinstance(value, str) and value:
                        try:
                            return pd.to_datetime(value).strftime("%Y-%m-%d")
                        except Exception:
                            return None
                    return None

                original_map = {}
                for rec in original_records:
                    norm_id = _normalize_id(rec.get("ID"))
                    if norm_id:
                        original_map[norm_id] = rec

                atualizados = 0
                removidos = 0
                bloqueados = []
                tbl_cal = api.table(BASE_ID, "Calendario")

                def _tem_voluntarios(evento_id: str) -> bool:
                    if df_volunt.empty or "Date (calendário)" not in df_volunt.columns:
                        return False
                    return df_volunt["Date (calendário)"].apply(
                        lambda v: evento_id in v if isinstance(v, list) else v == evento_id
                    ).any()

                for row in edited_records:
                    event_id = _normalize_id(row.get("ID"))
                    if not event_id:
                        continue
                    original = original_map.get(event_id)
                    if original is None:
                        continue

                    if row.get("Apagar"):
                        if _tem_voluntarios(event_id):
                            bloqueados.append((event_id, "Existe voluntariado associado"))
                            continue
                        try:
                            tbl_cal.delete(event_id)
                        except Exception as exc:
                            st.error(f"Não consegui apagar o evento {event_id}: {exc}")
                        else:
                            removidos += 1
                        continue

                    campos_update = {}
                    iso_novo = _to_iso(row.get("Data"))
                    iso_original = _to_iso(original.get("Data"))
                    if iso_novo and iso_novo != iso_original:
                        campos_update["Data"] = iso_novo

                    estado_novo = row.get("Estado", "Ativo") or "Ativo"
                    agenda_nova = (row.get("Agenda") or "").strip()
                    if estado_novo == "Cancelado":
                        if not agenda_nova:
                            agenda_nova = "CANCELADO"
                        if not agenda_nova.startswith("[CANCELADO]"):
                            agenda_nova = f"[CANCELADO] {agenda_nova}".strip()
                        campos_update["Haverá preparação de Lanches?"] = False
                    else:
                        if agenda_nova.startswith("[CANCELADO]"):
                            agenda_nova = agenda_nova.replace("[CANCELADO]", "", 1).strip()

                    agenda_original = df_manage.loc[df_manage["ID"] == event_id, "_agenda_raw"].iloc[0] if event_id in df_manage["ID"].values else ""
                    if agenda_nova != (agenda_original or ""):
                        campos_update["Agenda"] = agenda_nova

                    prep_novo = bool(row.get("Preparação", False))
                    prep_original = bool(df_manage.loc[df_manage["ID"] == event_id, "Preparação"].iloc[0]) if event_id in df_manage["ID"].values else False
                    if estado_novo != "Cancelado" and prep_novo != prep_original:
                        campos_update["Haverá preparação de Lanches?"] = prep_novo

                    if "Local" in row:
                        local_novo = row.get("Local", "")
                        local_original = df_manage.loc[df_manage["ID"] == event_id, "Local"].iloc[0] if (col_local and event_id in df_manage["ID"].values) else ""
                        if (local_novo or "") != (local_original or ""):
                            campos_update["Local"] = local_novo

                    if not campos_update:
                        continue

                    try:
                        tbl_cal.update(event_id, campos_update)
                    except Exception as exc:
                        st.error(f"Não consegui atualizar o evento {event_id}: {exc}")
                    else:
                        atualizados += 1

                if atualizados or removidos:
                    mensagens = []
                    if atualizados:
                        mensagens.append(f"{atualizados} evento(s) atualizados")
                    if removidos:
                        mensagens.append(f"{removidos} evento(s) apagados")
                    st.success("; ".join(mensagens) + ".")
                    refrescar_dados()
                    st.rerun()
                else:
                    st.info("Nenhuma alteração para guardar.")

                if bloqueados:
                    detalhes = ", ".join(f"{rid} ({motivo})" for rid, motivo in bloqueados)
                    st.warning(f"Não foi possível eliminar os eventos: {detalhes}.")


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
sections_a_mostrar: list[str] = []
if is_admin:
    sections_a_mostrar.append("admin")
if is_tesoureiro:
    sections_a_mostrar.append("tesoureiro")
sections_a_mostrar.append("pais")

for idx, sec in enumerate(sections_a_mostrar):
    if sec == "admin":
        dashboard_admin(dados)
    elif sec == "tesoureiro":
        dashboard_tesoureiro(dados)
    else:
        dashboard_pais()

    if idx < len(sections_a_mostrar) - 1:
        st.divider()
