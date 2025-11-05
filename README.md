## Portal Lobitos – Multi-Secção

### Escolha de secção
- Ao abrir a app, o utilizador escolhe agrupamento/secção.
- A escolha fica guardada na sessão e pode ser trocada mais tarde.

### Configuração nos secrets
Cada secção **tem de** definir um bloco irtable_<agrupamento>_<secao> com todas as chaves abaixo:

`	oml
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
`

Se alguma chave estiver em falta para a secção selecionada, o portal mostra uma mensagem de erro e não renderiza o formulário.

### Comportamento
- Trocar secção limpa a sessão e volta ao seletor inicial.
- Terminar sessão limpa apenas as credenciais, mantendo a secção.
- Cada página mostra o rótulo Agrupamento · Secção e usa sempre os links definidos nos secrets.
