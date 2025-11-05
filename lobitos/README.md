## Portal Multi-Secção

Esta app Streamlit permite alternar entre diferentes secções/agrupamentos (ex.: Lobitos, Exploradores) partilhando a mesma interface.

### Configuração dos secrets

Cada combinação deve ter um bloco `airtable_<agrupamento>_<secao>`:

```toml
[airtable_521_lobitos]
AIRTABLE_TOKEN = "..."
AIRTABLE_BASE_ID = "..."
AGRUPAMENTO_LABEL = "Agrupamento 521"
SECAO_LABEL = "Lobitos"
DEFAULT_LANCHE_FORM_URL = "https://airtable.com/embed/..."
DEFAULT_VOLUNT_FORM_URL = "https://airtable.com/embed/..."
# chaves opcionais:
CANCEL_LANCHE_FORM_URL = "https://airtable.com/embed/..."
RECEBIMENTO_FORM_URL = "https://airtable.com/embed/..."
ESTORNO_FORM_URL = "https://airtable.com/embed/..."
FORCED_CANCEL_FORM_URL = "https://airtable.com/embed/..."
FORCED_ORDER_FORM_URL = "https://airtable.com/embed/..."
MANAGE_ESCUTEIROS_FORM_URL = "https://airtable.com/embed/..."
```

`context_extra("NOME", fallback)` devolve qualquer URL configurado (ou o _fallback_).

### Fluxo de utilização

1. Ao entrar, o utilizador escolhe a secção (guardada em `st.session_state`).
2. O login valida o utilizador com a base Airtable correspondente.
3. Páginas mostram o rótulo `Agrupamento · Secção` e usam formulários específicos.
4. Botão “Trocar secção” limpa a sessão e regressa ao seletor inicial.
5. “Terminar sessão” mantém a secção, mas limpa credenciais/cache.
