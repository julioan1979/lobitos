import streamlit as st
from pyairtable import Api
import toml
from typing import List, Dict, Any

st.set_page_config(page_title="Portal Lobitos - Login", page_icon="🐾", layout="centered")


def _obter_airtable_client() -> tuple[Api, str]:
    if "AIRTABLE_TOKEN" in st.secrets:
        token = st.secrets["AIRTABLE_TOKEN"]
        base_id = st.secrets["AIRTABLE_BASE_ID"]
    else:
        secrets = toml.load(".streamlit/secrets.toml")
        token = secrets["AIRTABLE_TOKEN"]
        base_id = secrets["AIRTABLE_BASE_ID"]
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


def _buscar_escuteiros(email: str) -> List[Dict[str, Any]]:
    api, base_id = _obter_airtable_client()
    tabela = api.table(base_id, "Escuteiros")
    email_filtrado = email.replace("'", "\'")
    formula = (
        f"OR("
        f"LOWER({{Email}})='{email_filtrado}',"
        f"LOWER({{Email Alternativo}})='{email_filtrado}'"
        f")"
    )
    return tabela.all(formula=formula, max_records=50)


def _determinar_role(registos: List[Dict[str, Any]]) -> str:
    campos = [r.get("fields", {}) for r in registos]
    if any(_campo_com_conteudo(f.get("Admin")) for f in campos):
        return "admin"
    if any(_campo_com_conteudo(f.get("CPP_Tesoureiros")) for f in campos):
        return "tesoureiro"
    return "pais"


st.title("🐾 Portal Lobitos")
st.write("Bem-vindo ao Portal dos Lanches Lobitos! Faça login para continuar.")

email_input = st.text_input("Email")
senha_input = st.text_input("Senha", type="password")

if st.button("Entrar 🚀"):
    email_normalizado = _normalizar_email(email_input)

    if not email_normalizado or not senha_input:
        st.error("Indique email e senha.")
    else:
        try:
            registos = _buscar_escuteiros(email_normalizado)
        except Exception as exc:
            st.error(f"Não consegui validar as credenciais: {exc}")
        else:
            if not registos:
                st.error("Não encontrei escuteiros associados a este email.")
            else:
                correspondencias = []
                for r in registos:
                    campos = r.get("fields", {})
                    senha_registo = campos.get("Senha_Painel")
                    if senha_registo is None:
                        continue
                    if str(senha_registo).strip() == senha_input.strip():
                        correspondencias.append(r)
                if not correspondencias:
                    st.error("Senha incorreta.")
                else:
                    role = _determinar_role(correspondencias)

                    if role in {"tesoureiro", "admin"}:
                        escuteiros_ids = [r["id"] for r in registos]
                        nomes_escuteiros = [
                            r.get("fields", {}).get("Nome do Escuteiro")
                            for r in registos
                            if _campo_com_conteudo(r.get("fields", {}).get("Nome do Escuteiro"))
                        ]
                    else:
                        escuteiros_ids = [r["id"] for r in correspondencias]
                        nomes_escuteiros = [
                            r.get("fields", {}).get("Nome do Escuteiro")
                            for r in correspondencias
                            if _campo_com_conteudo(r.get("fields", {}).get("Nome do Escuteiro"))
                        ]

                    st.session_state["role"] = role
                    st.session_state["logged_in"] = True
                    st.session_state["user"] = {
                        "email": email_normalizado,
                        "escuteiros_ids": escuteiros_ids,
                        "nomes": nomes_escuteiros,
                        "all_access": role in {"admin", "tesoureiro"},
                    }

                    st.success(f"✅ Login como {role.capitalize()}!")
                    st.switch_page("pages/home.py")
