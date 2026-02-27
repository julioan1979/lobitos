from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from pyairtable import Api


TIPOS_MOVIMENTO = {"Entrada", "Saída", "Ajuste", "Transferência"}


_REQUIRED_TABLES: dict[str, dict[str, Any]] = {
    "Inventario": {
        "primary": {"name": "NomeItem", "type": "singleLineText"},
        "fields": {
            "Categoria": {"type": "singleLineText"},
            "QuantidadeAtual": {"type": "number", "options": {"precision": 0}},
            "Unidade": {"type": "singleLineText"},
            "Estado": {
                "type": "singleSelect",
                "options": {
                    "choices": [
                        {"name": "Disponível"},
                        {"name": "Danificado"},
                        {"name": "Esgotado"},
                    ]
                },
            },
            "CaixaAtual": {"type": "multipleRecordLinks", "link_to": "Caixas"},
            "Localizacao": {"type": "singleLineText"},
            "Observacoes": {"type": "multilineText"},
            "Foto": {"type": "multipleAttachments"},
            "Ativo": {"type": "checkbox"},
        },
    },
    "Caixas": {
        "primary": {"name": "CodigoCaixa", "type": "singleLineText"},
        "fields": {
            "Descricao": {"type": "singleLineText"},
            "Local": {"type": "singleLineText"},
            "Estado": {
                "type": "singleSelect",
                "options": {"choices": [{"name": "Ativa"}, {"name": "Arquivada"}]},
            },
        },
    },
    "Eventos": {
        "primary": {"name": "NomeEvento", "type": "singleLineText"},
        "fields": {
            "Tipo": {
                "type": "singleSelect",
                "options": {"choices": [{"name": "Tômbola"}, {"name": "Angariação"}, {"name": "Feira"}]},
            },
            "Data": {"type": "date"},
            "Local": {"type": "singleLineText"},
            "Estado": {
                "type": "singleSelect",
                "options": {
                    "choices": [{"name": "Planeamento"}, {"name": "A decorrer"}, {"name": "Concluído"}]
                },
            },
        },
    },
    "Movimentos": {
        "primary": {"name": "Tipo", "type": "singleLineText"},
        "fields": {
            "Item": {"type": "multipleRecordLinks", "link_to": "Inventario"},
            "Quantidade": {"type": "number", "options": {"precision": 0}},
            "CaixaOrigem": {"type": "multipleRecordLinks", "link_to": "Caixas"},
            "CaixaDestino": {"type": "multipleRecordLinks", "link_to": "Caixas"},
            "Evento": {"type": "multipleRecordLinks", "link_to": "Eventos"},
            "OrigemEntrada": {
                "type": "singleSelect",
                "options": {
                    "choices": [{"name": "Patrocínio"}, {"name": "Compra"}, {"name": "Stock antigo"}]
                },
            },
            "Patrocinador": {"type": "multipleRecordLinks", "link_to": "Patrocinadores"},
            "DataMovimento": {"type": "dateTime"},
            "Notas": {"type": "multilineText"},
            "ExecutadoPor": {"type": "singleLineText"},
        },
    },
    "Patrocinadores": {
        "primary": {"name": "Nome", "type": "singleLineText"},
        "fields": {
            "Contacto": {"type": "singleLineText"},
            "Notas": {"type": "multilineText"},
        },
    },
    "RegistoPatrocinios": {
        "primary": {"name": "PatrocinadorNome", "type": "singleLineText"},
        "fields": {
            "Contacto": {"type": "singleLineText"},
            "DescricaoItem": {"type": "singleLineText"},
            "Categoria": {"type": "singleLineText"},
            "Quantidade": {"type": "number", "options": {"precision": 0}},
            "CaixaSugerida": {"type": "multipleRecordLinks", "link_to": "Caixas"},
            "Evento": {"type": "multipleRecordLinks", "link_to": "Eventos"},
            "Estado": {
                "type": "singleSelect",
                "options": {
                    "choices": [{"name": "Prometido"}, {"name": "Recebido"}, {"name": "Recusado"}]
                },
            },
            "Observacoes": {"type": "multilineText"},
            "Processado": {"type": "checkbox"},
        },
    },
}


def _to_int_positivo(valor: Any) -> int:
    try:
        quantidade = int(valor)
    except (TypeError, ValueError) as exc:
        raise ValueError("Quantidade inválida. Use um número inteiro.") from exc
    if quantidade <= 0:
        raise ValueError("A quantidade tem de ser maior que zero.")
    return quantidade


def _to_float(valor: Any) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def _first_link_id(valor: Any) -> Optional[str]:
    if isinstance(valor, list) and valor:
        return str(valor[0])
    if isinstance(valor, str) and valor.strip():
        return valor.strip()
    return None


def ensure_tombola_base_schema(api: Api, base_id: str) -> Dict[str, list[str]]:
    """Garante estrutura mínima de tabelas/campos para o módulo da Tômbola.

    Cria tabelas e campos em falta. Não altera tipo de campos existentes.
    """
    report: Dict[str, list[str]] = {"created_tables": [], "created_fields": [], "warnings": []}
    base = api.base(base_id)

    try:
        schema = base.schema(force=True)
    except Exception as exc:
        report["warnings"].append(f"Não foi possível ler schema da base: {exc}")
        return report

    table_by_name = {table.name: table for table in schema.tables}

    # 1) Criar tabelas em falta (com campo primário)
    for table_name, table_spec in _REQUIRED_TABLES.items():
        if table_name in table_by_name:
            continue
        primary = table_spec["primary"]
        try:
            created = base.create_table(table_name, [primary])
            report["created_tables"].append(table_name)
            table_by_name[table_name] = created.schema(force=True)
        except Exception as exc:
            report["warnings"].append(f"Falha ao criar tabela '{table_name}': {exc}")

    # Recarregar schema após criações
    try:
        schema = base.schema(force=True)
        table_by_name = {table.name: table for table in schema.tables}
    except Exception as exc:
        report["warnings"].append(f"Não foi possível recarregar schema após criação: {exc}")
        return report

    table_id_by_name = {table.name: table.id for table in schema.tables}

    # 2) Criar campos em falta
    for table_name, table_spec in _REQUIRED_TABLES.items():
        table_schema = table_by_name.get(table_name)
        if table_schema is None:
            report["warnings"].append(f"Tabela ausente após bootstrap: {table_name}")
            continue

        existing_fields = {field.name: field for field in table_schema.fields}
        table = api.table(base_id, table_name)

        for field_name, field_spec in table_spec["fields"].items():
            if field_name in existing_fields:
                current_type = getattr(existing_fields[field_name], "type", None)
                expected_type = field_spec["type"]
                if current_type and current_type != expected_type:
                    report["warnings"].append(
                        f"Campo '{table_name}.{field_name}' existe como '{current_type}' (esperado '{expected_type}')."
                    )
                continue

            try:
                options = dict(field_spec.get("options", {}))
                if field_spec.get("type") == "multipleRecordLinks":
                    linked = field_spec.get("link_to")
                    linked_id = table_id_by_name.get(str(linked))
                    if not linked_id:
                        report["warnings"].append(
                            f"Não foi possível criar link '{table_name}.{field_name}' (tabela destino '{linked}' ausente)."
                        )
                        continue
                    options["linkedTableId"] = linked_id

                table.create_field(field_name, field_spec["type"], options=options or None)
                report["created_fields"].append(f"{table_name}.{field_name}")
            except Exception as exc:
                report["warnings"].append(f"Falha ao criar campo '{table_name}.{field_name}': {exc}")

    return report


def criar_movimento(
    api: Api,
    base_id: str,
    *,
    tipo: str,
    item_id: str,
    quantidade: int,
    executado_por: str,
    caixa_origem_id: Optional[str] = None,
    caixa_destino_id: Optional[str] = None,
    evento_id: Optional[str] = None,
    origem_entrada: Optional[str] = None,
    patrocinador_id: Optional[str] = None,
    notas: str = "",
) -> Dict[str, Any]:
    if tipo not in TIPOS_MOVIMENTO:
        raise ValueError(f"Tipo de movimento inválido: {tipo}")

    quantidade = _to_int_positivo(quantidade)
    campos: Dict[str, Any] = {
        "Tipo": tipo,
        "Item": [item_id],
        "Quantidade": quantidade,
        "ExecutadoPor": executado_por or "sistema",
    }

    if caixa_origem_id:
        campos["CaixaOrigem"] = [caixa_origem_id]
    if caixa_destino_id:
        campos["CaixaDestino"] = [caixa_destino_id]
    if evento_id:
        campos["Evento"] = [evento_id]
    if origem_entrada:
        campos["OrigemEntrada"] = origem_entrada
    if patrocinador_id:
        campos["Patrocinador"] = [patrocinador_id]
    if notas and notas.strip():
        campos["Notas"] = notas.strip()

    return api.table(base_id, "Movimentos").create(campos)


def ajustar_stock_item(
    api: Api,
    base_id: str,
    *,
    item_id: str,
    delta: int,
    executado_por: str,
    tipo_movimento: str,
    notas: str = "",
    evento_id: Optional[str] = None,
    origem_entrada: Optional[str] = None,
    patrocinador_id: Optional[str] = None,
) -> Dict[str, Any]:
    if tipo_movimento not in {"Entrada", "Saída", "Ajuste"}:
        raise ValueError("Tipo de movimento inválido para ajuste de stock.")

    if delta == 0:
        raise ValueError("A alteração de stock não pode ser zero.")

    tabela_inv = api.table(base_id, "Inventario")
    item = tabela_inv.get(item_id)
    campos_item = item.get("fields", {})
    atual = _to_float(campos_item.get("QuantidadeAtual"))
    novo_valor = atual + float(delta)

    if novo_valor < 0:
        raise ValueError("Operação inválida: stock não pode ficar negativo.")

    tabela_inv.update(item_id, {"QuantidadeAtual": novo_valor})

    caixa_origem_id = _first_link_id(campos_item.get("CaixaAtual"))

    return criar_movimento(
        api,
        base_id,
        tipo=tipo_movimento,
        item_id=item_id,
        quantidade=abs(int(delta)),
        executado_por=executado_por,
        caixa_origem_id=caixa_origem_id,
        evento_id=evento_id,
        origem_entrada=origem_entrada,
        patrocinador_id=patrocinador_id,
        notas=notas,
    )


def transferir_item_caixa(
    api: Api,
    base_id: str,
    *,
    item_id: str,
    caixa_destino_id: str,
    quantidade: int,
    executado_por: str,
    notas: str = "",
) -> Dict[str, Any]:
    quantidade = _to_int_positivo(quantidade)

    tabela_inv = api.table(base_id, "Inventario")
    item = tabela_inv.get(item_id)
    campos_item = item.get("fields", {})
    caixa_origem_id = _first_link_id(campos_item.get("CaixaAtual"))

    tabela_inv.update(item_id, {"CaixaAtual": [caixa_destino_id]})

    return criar_movimento(
        api,
        base_id,
        tipo="Transferência",
        item_id=item_id,
        quantidade=quantidade,
        executado_por=executado_por,
        caixa_origem_id=caixa_origem_id,
        caixa_destino_id=caixa_destino_id,
        notas=notas,
    )


def normalizar_nome_item(valor: Any) -> str:
    if valor is None:
        return ""
    return " ".join(str(valor).strip().lower().split())


def encontrar_item_por_nome(registos_inventario: Iterable[Dict[str, Any]], nome_item: str) -> Optional[Dict[str, Any]]:
    alvo = normalizar_nome_item(nome_item)
    if not alvo:
        return None
    for registo in registos_inventario:
        campos = registo.get("fields", {})
        nome = normalizar_nome_item(campos.get("NomeItem"))
        if nome == alvo:
            return registo
    return None
