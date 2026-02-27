from __future__ import annotations

from typing import Any, Dict, List

from pyairtable import Api


def _table_exists(base, table_ref: str) -> bool:
    refs = {tbl.id: tbl for tbl in base.tables()}
    names = {tbl.name: tbl for tbl in base.tables()}
    return table_ref in refs or table_ref in names


def _get_table(base, table_ref: str):
    if table_ref.startswith("tbl"):
        return base.table(table_ref)
    return base.table(table_ref)


def _field_exists(table, field_name: str) -> bool:
    try:
        schema = table.schema()
    except Exception:
        return False
    return any(field.name == field_name for field in schema.fields)


def _normalize_field_options(field_type: str, options: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Normaliza opções para tipos que exigem payload explícito na Meta API."""
    if options is not None:
        return options

    if field_type in {"checkbox", "date"}:
        return {}

    return None


def _create_field_with_explicit_payload(table, name: str, field_type: str, options: Dict[str, Any] | None = None) -> None:
    """Cria campo garantindo envio explícito de `options` quando necessário.

    O `pyairtable.Table.create_field` omite a chave `options` quando recebe
    um dict vazio (`{}`), porque faz `if options:`. Para tipos como `checkbox`
    e `date`, a Meta API exige a presença explícita de `options`, mesmo vazio.
    """
    request: Dict[str, Any] = {"name": name, "type": field_type}
    if options is not None:
        request["options"] = options
    table.api.post(table.urls.fields, json=request)


def _ensure_field(table, name: str, field_type: str, options: Dict[str, Any] | None = None) -> bool:
    if _field_exists(table, name):
        return False
    _create_field_with_explicit_payload(table, name, field_type, options=_normalize_field_options(field_type, options))
    return True


def _primary_field_for_create(fields: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Escolhe um campo primário compatível para criação da tabela.

    A API de criação de tabelas é mais restritiva para o campo primário
    (ex.: não aceita `singleSelect` como primário), por isso usamos um
    `singleLineText` já previsto no schema quando possível.
    """
    for field in fields:
        if field.get("type") == "singleLineText":
            return {"name": field["name"], "type": "singleLineText"}
    return {"name": "Nome", "type": "singleLineText"}




def _ensure_base_fields(table, fields: List[Dict[str, Any]], table_ref: str, created_fields: List[str], errors: List[str]) -> None:
    for field in fields:
        try:
            created = _ensure_field(table, field["name"], field["type"], field.get("options"))
            if created:
                created_fields.append(f"{table_ref}.{field['name']}")
        except Exception as exc:
            errors.append(f"{table_ref}.{field['name']}: falha ao criar campo: {exc}")


def ensure_tombola_schema(api: Api, base_id: str, table_refs: Dict[str, str]) -> Dict[str, List[str]]:
    """Cria o schema mínimo da Tômbola numa base nova mantendo compatibilidade.

    Retorna resumo de ações: tabelas/fields criados e eventuais erros.
    """
    base = api.base(base_id)
    created_tables: List[str] = []
    created_fields: List[str] = []
    errors: List[str] = []

    table_defs = {
        "INVENTARIO": [
            {"name": "NomeItem", "type": "singleLineText"},
            {"name": "Categoria", "type": "singleLineText"},
            {"name": "QuantidadeAtual", "type": "number", "options": {"precision": 0}},
            {
                "name": "Estado",
                "type": "singleSelect",
                "options": {
                    "choices": [{"name": "Disponível"}, {"name": "Danificado"}, {"name": "Esgotado"}]
                },
            },
            {"name": "Ativo", "type": "checkbox"},
        ],
        "CAIXAS": [
            {"name": "CodigoCaixa", "type": "singleLineText"},
            {"name": "Descricao", "type": "multilineText"},
            {"name": "Local", "type": "singleLineText"},
            {
                "name": "Estado",
                "type": "singleSelect",
                "options": {"choices": [{"name": "Ativa"}, {"name": "Arquivada"}]},
            },
        ],
        "PATROCINADORES": [{"name": "Nome", "type": "singleLineText"}],
        "EVENTOS": [
            {"name": "NomeEvento", "type": "singleLineText"},
            {
                "name": "Tipo",
                "type": "singleSelect",
                "options": {"choices": [{"name": "Tômbola"}, {"name": "Angariação"}, {"name": "Feira"}]},
            },
            {"name": "Data", "type": "date"},
            {"name": "Local", "type": "singleLineText"},
            {
                "name": "Estado",
                "type": "singleSelect",
                "options": {"choices": [{"name": "Planeamento"}, {"name": "A decorrer"}, {"name": "Concluído"}]},
            },
        ],
        "REGISTO_PATROCINIOS": [
            {"name": "PatrocinadorNome", "type": "singleLineText"},
            {"name": "DescricaoItem", "type": "singleLineText"},
            {"name": "Quantidade", "type": "number", "options": {"precision": 0}},
            {
                "name": "Estado",
                "type": "singleSelect",
                "options": {"choices": [{"name": "Pendente"}, {"name": "Recebido"}]},
            },
            {"name": "Processado", "type": "checkbox"},
            {"name": "Categoria", "type": "singleLineText"},
            {"name": "Observacoes", "type": "multilineText"},
        ],
        "MOVIMENTOS": [
            {"name": "ExecutadoPor", "type": "singleLineText"},
            {
                "name": "Tipo",
                "type": "singleSelect",
                "options": {
                    "choices": [
                        {"name": "Entrada"},
                        {"name": "Saída"},
                        {"name": "Ajuste"},
                        {"name": "Transferência"},
                    ]
                },
            },
            {"name": "Quantidade", "type": "number", "options": {"precision": 0}},
            {"name": "OrigemEntrada", "type": "singleLineText"},
            {"name": "Notas", "type": "multilineText"},
        ],
    }

    # 1) Criar tabelas base quando necessário e garantir colunas mínimas
    for key, fields in table_defs.items():
        table_ref = table_refs[key]

        if table_ref.startswith("tbl") and not _table_exists(base, table_ref):
            errors.append(f"{key}: referência por ID ({table_ref}) não existe na base.")
            continue

        if not _table_exists(base, table_ref):
            if table_ref.startswith("tbl"):
                errors.append(f"{key}: não é possível criar tabela quando referência é ID ({table_ref}).")
                continue
            try:
                base.create_table(table_ref, [_primary_field_for_create(fields)])
                created_tables.append(table_ref)
            except Exception as exc:
                errors.append(f"{key}: falha ao criar tabela '{table_ref}': {exc}")
                continue

        try:
            table = _get_table(base, table_ref)
            _ensure_base_fields(table, fields, table_ref, created_fields, errors)
        except Exception as exc:
            errors.append(f"{key}: falha ao validar campos base da tabela '{table_ref}': {exc}")

    # 2) Garantir campos de links após todas as tabelas existirem
    link_defs = [
        ("INVENTARIO", "CaixaAtual", "CAIXAS"),
        ("REGISTO_PATROCINIOS", "CaixaSugerida", "CAIXAS"),
        ("REGISTO_PATROCINIOS", "Evento", "EVENTOS"),
        ("MOVIMENTOS", "Item", "INVENTARIO"),
        ("MOVIMENTOS", "CaixaOrigem", "CAIXAS"),
        ("MOVIMENTOS", "CaixaDestino", "CAIXAS"),
        ("MOVIMENTOS", "Evento", "EVENTOS"),
        ("MOVIMENTOS", "Patrocinador", "PATROCINADORES"),
    ]

    # ids para links
    table_id_by_key: Dict[str, str] = {}
    for key, table_ref in table_refs.items():
        try:
            table_id_by_key[key] = _get_table(base, table_ref).id
        except Exception:
            pass

    for src_key, field_name, dst_key in link_defs:
        if src_key not in table_id_by_key or dst_key not in table_id_by_key:
            errors.append(f"{src_key}.{field_name}: tabela origem/destino indisponível.")
            continue
        try:
            table = _get_table(base, table_refs[src_key])
            created = _ensure_field(
                table,
                field_name,
                "multipleRecordLinks",
                options={"linkedTableId": table_id_by_key[dst_key]},
            )
            if created:
                created_fields.append(f"{table_refs[src_key]}.{field_name}")
        except Exception as exc:
            errors.append(f"{src_key}.{field_name}: falha ao criar campo: {exc}")

    return {"created_tables": created_tables, "created_fields": created_fields, "errors": errors}
