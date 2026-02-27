from __future__ import annotations

import unicodedata
from typing import Any, Dict, Iterable, Optional

from pyairtable import Api


TIPOS_MOVIMENTO = {"Entrada", "Saída", "Ajuste", "Transferência"}


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
    texto = " ".join(str(valor).strip().lower().split())
    texto_sem_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return texto_sem_acentos


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
