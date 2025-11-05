## Portal Multi-Secção

Aplicação Streamlit que permite alternar entre diferentes secções/agrupamentos (ex.: Lobitos, Exploradores) mantendo uma interface comum.

### Configuração dos secrets
Cada secção **tem de** definir um bloco `[airtable_<agrupamento>_<secao>]` com as chaves abaixo:

```toml
[airtable_521_lobitos]
AIRTABLE_TOKEN = "..."
AIRTABLE_BASE_ID = "..."
AGRUPAMENTO_LABEL = "Agrupamento 521"
SECAO_LABEL = "Lobitos"
DEFAULT_LANCHE_FORM_URL = "https://airtable.com/embed/..."
DEFAULT_VOLUNT_FORM_URL = "https://airtable.com/embed/..."
CANCEL_LANCHE_FORM_URL = "https://airtable.com/embed/..."
RECEBIMENTO_FORM_URL = "https://airtable.com/embed/..."
ESTORNO_FORM_URL = "https://airtable.com/embed/..."
FORCED_CANCEL_FORM_URL = "https://airtable.com/embed/..."
FORCED_ORDER_FORM_URL = "https://airtable.com/embed/..."
MANAGE_ESCUTEIROS_FORM_URL = "https://airtable.com/embed/..."
```

Se algum campo estiver em falta para a secção selecionada, a aplicação informa o utilizador e não mostra o formulário correspondente.

A função `context_extra("NOME", fallback)` devolve qualquer URL configurado (ou o fallback indicado).

### Fluxo de utilização
1. Ao entrar, o utilizador escolhe a secção; a escolha fica em `st.session_state`.
2. O login valida o utilizador na base Airtable dessa secção.
3. Cada página mostra o rótulo `Agrupamento · Secção` e usa os formulários configurados.
4. “Trocar secção” limpa a sessão completa e regressa ao seletor inicial.
5. “Terminar sessão” mantém a secção mas limpa credenciais e cache.

### Scripts de apoio
- `update_header.py`: utilitário para actualizar cabeçalhos das páginas (usa ficheiros em `pages/`).
