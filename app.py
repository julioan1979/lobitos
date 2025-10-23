import streamlit as st
from pyairtable import Api
from typing import Any, Dict, List, Tuple

from airtable_config import (
    clear_authentication,
    context_labels,
    current_context,
    get_available_contexts,
    get_airtable_credentials,
    set_current_context,
)
from menu import _hide_streamlit_sidebar_nav

st.set_page_config(page_title="Portal Lobitos - Login", page_icon="\U0001F43E", layout="centered")
_hide_streamlit_sidebar_nav()

def _obter_airtable_client() -> Tuple[Api, str]:
    token, base_id = get_airtable_credentials()
    return Api(token), base_id


def _normalizar_email(valor: str) -> str:
    return (valor or "").strip().lower()


def _campo_com_conteudo(valor: Any) -> bool:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return valor != 0
    if isinstance(valor, str):
        return valor.strip() != ""
    if isinstance(valor, list):
        return len(valor) > 0
    return False


def _checkbox_marcado(valor: Any) -> bool:
    """Reconhece checkboxes marcados, incluindo lookups em formatos diversos."""
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, list):
        return any(_checkbox_marcado(item) for item in valor)
    if isinstance(valor, (int, float)):
        return valor != 0
    if isinstance(valor, str):
        normalizado = valor.strip().lower()
        return normalizado in {
            "true",
            "1",
            "yes",
            "y",
            "sim",
            "checked",
            "marcado",
            "✅",
            "✔",
            "☑",
        }
    return False


def _buscar_escuteiros(email: str) -> List[Dict[str, Any]]:
    api, base_id = _obter_airtable_client()
    tabela = api.table(base_id, "Escuteiros")
    email_filtrado = email.replace("'", "\\'")
    formula = (
        "OR("
        f"LOWER({{Email}})='{email_filtrado}',"
        f"LOWER({{Email Alternativo}})='{email_filtrado}'"
        ")"
    )
    return tabela.all(formula=formula, max_records=50)


def _determinar_role(registos: List[Dict[str, Any]]) -> str:
    campos = [r.get("fields", {}) for r in registos]

    def _tem_flag_admin(campos_esc: Dict[str, Any]) -> bool:
        for chave, valor in campos_esc.items():
            if "admin" in chave.lower():
                if _checkbox_marcado(valor):
                    return True
        return False

    if any(_tem_flag_admin(f) for f in campos):
        return "admin"

    def _tem_flag_tesoureiro(campos_esc: Dict[str, Any]) -> bool:
        for chave, valor in campos_esc.items():
            chave_low = chave.lower()
            if "tesoureiro" in chave_low or "tesouraria" in chave_low:
                if _checkbox_marcado(valor) or _campo_com_conteudo(valor):
                    return True
        return False

    if any(_tem_flag_tesoureiro(f) for f in campos):
        return "tesoureiro"

    return "pais"



contextos_disponiveis = get_available_contexts()
if not contextos_disponiveis:
    st.error("Nenhuma configuração Airtable encontrada. Crie blocos 'airtable_*' nos secrets.")
    st.stop()

contexto_atual = current_context()
if contexto_atual is None and len(contextos_disponiveis) == 1:
    set_current_context(contextos_disponiveis[0].key)
    contexto_atual = contextos_disponiveis[0]

opcoes_contexto = [f"{ctx.agrupamento_label} · {ctx.secao_label}" for ctx in contextos_disponiveis]
mapa_contexto = {opcao: ctx for opcao, ctx in zip(opcoes_contexto, contextos_disponiveis)}
indice_default = 0
if contexto_atual is not None:
    for idx, ctx in enumerate(contextos_disponiveis):
        if ctx.key == contexto_atual.key:
            indice_default = idx
            break

selecionado_label = st.selectbox(
    "Secção",
    options=opcoes_contexto,
    index=indice_default,
    key="login_context_selectbox",
)
ctx_selecionado = mapa_contexto[selecionado_label]
if contexto_atual is None or ctx_selecionado.key != contexto_atual.key:
    set_current_context(ctx_selecionado.key)
    clear_authentication(keep_context=True)
    contexto_atual = ctx_selecionado


secao_legenda = context_labels() or "Portal"
titulo_ctx = contexto_atual.secao_label if contexto_atual else "Portal"
st.title(f"\U0001F43E {titulo_ctx} - Portal")
st.write("Bem-vindo! Faça login para continuar.")
st.caption("Pedidos, calendários e voluntariado reunidos num só painel.")

st.info(secao_legenda)

email_input = st.text_input("Email", value=st.session_state.get("login_email", ""))
senha_input = st.text_input("Senha", type="password")

if st.button("Entrar no portal \U0001F680"):
    email_normalizado = _normalizar_email(email_input)

    if not email_normalizado or not senha_input:
        st.error("Indique email e senha.")
    else:
        with st.spinner("A validar credenciais..."):
            try:
                registos = _buscar_escuteiros(email_normalizado)
            except Exception as exc:
                st.error(f"Não consegui validar as credenciais: {exc}")
            else:
                if not registos:
                    st.error("Não encontrei escuteiros associados a este email.")
                else:
                    correspondencias = []
                    for registo in registos:
                        campos = registo.get("fields", {})
                        senha_registo = campos.get("Senha_Painel")
                        if senha_registo is None:
                            continue
                        if str(senha_registo).strip() == senha_input.strip():
                            correspondencias.append(registo)

                    if not correspondencias:
                        st.error("Senha incorreta.")
                    else:
                        role = _determinar_role(correspondencias)

                        if role in {"tesoureiro", "admin"}:
                            escuteiros_ids = [registo["id"] for registo in registos]
                            nomes_escuteiros = [
                                registo.get("fields", {}).get("Nome do Escuteiro")
                                for registo in registos
                                if _campo_com_conteudo(
                                    registo.get("fields", {}).get("Nome do Escuteiro")
                                )
                            ]
                        else:
                            escuteiros_ids = [registo["id"] for registo in correspondencias]
                            nomes_escuteiros = [
                                registo.get("fields", {}).get("Nome do Escuteiro")
                                for registo in correspondencias
                                if _campo_com_conteudo(
                                    registo.get("fields", {}).get("Nome do Escuteiro")
                                )
                            ]

                        st.session_state["login_email"] = email_input
                        st.session_state["role"] = role
                        st.session_state["logged_in"] = True
                        st.session_state["user"] = {
                            "email": email_normalizado,
                            "escuteiros_ids": escuteiros_ids,
                            "nomes": nomes_escuteiros,
                            "all_access": role in {"admin", "tesoureiro"},
                        }

                        st.success(f"✨ Login como {role.capitalize()}!")
                        st.switch_page("pages/home.py")
