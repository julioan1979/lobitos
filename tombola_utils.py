from __future__ import annotations

import unicodedata
from typing import Any, Dict, Iterable, List, Optional

from pyairtable import Api

from airtable_config import get_tombola_table_ref


TIPOS_MOVIMENTO = {"Entrada", "Saída", "Ajuste", "Transferência"}


def _tombola_table(table_key: str, default_name: str) -> str:
    return get_tombola_table_ref(table_key, default_name)


def _validar_notas_acao_critica(tipo: str, notas: str) -> None:
    """Stock real vive no Inventário; Movimentos é auditoria e ações críticas exigem notas."""
    if tipo in {"Saída", "Ajuste", "Transferência"} and not (notas or "").strip():
        raise ValueError("Notas são obrigatórias para Saída, Ajuste e Transferência.")


def _to_int_positivo(valor: Any) -> int:
    if isinstance(valor, bool):
        raise ValueError("Quantidade inválida. Use um número inteiro.")
    if isinstance(valor, float) and not valor.is_integer():
        raise ValueError("Quantidade inválida. Use um número inteiro.")
    try:
        quantidade = int(valor)
    except (TypeError, ValueError) as exc:
        raise ValueError("Quantidade inválida. Use um número inteiro.") from exc
    if str(valor).strip() != str(quantidade) and not (isinstance(valor, float) and valor.is_integer()):
        raise ValueError("Quantidade inválida. Use um número inteiro.")
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
    """Stock real vive no Inventário; Movimentos é auditoria de operações."""
    if tipo not in TIPOS_MOVIMENTO:
        raise ValueError(f"Tipo de movimento inválido: {tipo}")

    _validar_notas_acao_critica(tipo, notas)
    if not (executado_por or "").strip():
        raise ValueError("ExecutadoPor é obrigatório com o email do utilizador autenticado.")

    quantidade = _to_int_positivo(quantidade)
    campos: Dict[str, Any] = {
        "Tipo": tipo,
        "Item": [item_id],
        "Quantidade": quantidade,
        "ExecutadoPor": executado_por.strip(),
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

    return api.table(base_id, _tombola_table("MOVIMENTOS", "Movimentos")).create(campos)


def _atualizar_inventario_e_movimento(
    api: Api,
    base_id: str,
    *,
    item_id: str,
    quantidade_atual_anterior: float,
    quantidade_nova: float,
    dados_movimento: Dict[str, Any],
    caixa_anterior: Optional[str] = None,
    caixa_nova: Optional[str] = None,
) -> Dict[str, Any]:
    tabela_inv = api.table(base_id, _tombola_table("INVENTARIO", "Inventario"))
    payload_update: Dict[str, Any] = {"QuantidadeAtual": quantidade_nova}
    if caixa_nova:
        payload_update["CaixaAtual"] = [caixa_nova]

    tabela_inv.update(item_id, payload_update)
    try:
        return criar_movimento(api, base_id, item_id=item_id, **dados_movimento)
    except Exception as exc:
        rollback_payload: Dict[str, Any] = {"QuantidadeAtual": quantidade_atual_anterior}
        if caixa_nova:
            rollback_payload["CaixaAtual"] = [caixa_anterior] if caixa_anterior else []
        try:
            tabela_inv.update(item_id, rollback_payload)
        except Exception as rollback_exc:
            raise RuntimeError(
                "Falha ao criar movimento e não foi possível repor o inventário automaticamente."
            ) from rollback_exc
        raise RuntimeError("Falha ao criar movimento; atualização de inventário revertida.") from exc


def registrar_entrada(
    api: Api,
    base_id: str,
    *,
    item_id: str,
    quantidade: int,
    executado_por: str,
    evento_id: Optional[str] = None,
    caixa_origem_id: Optional[str] = None,
    caixa_destino_id: Optional[str] = None,
    patrocinador_id: Optional[str] = None,
    origem_entrada: Optional[str] = None,
    notas: str = "",
) -> Dict[str, Any]:
    quantidade = _to_int_positivo(quantidade)
    tabela_inv = api.table(base_id, _tombola_table("INVENTARIO", "Inventario"))
    item = tabela_inv.get(item_id)
    atual = _to_float(item.get("fields", {}).get("QuantidadeAtual"))
    novo_valor = atual + quantidade
    return _atualizar_inventario_e_movimento(
        api,
        base_id,
        item_id=item_id,
        quantidade_atual_anterior=atual,
        quantidade_nova=novo_valor,
        dados_movimento={
            "tipo": "Entrada",
            "quantidade": quantidade,
            "executado_por": executado_por,
            "caixa_origem_id": caixa_origem_id,
            "caixa_destino_id": caixa_destino_id,
            "evento_id": evento_id,
            "origem_entrada": origem_entrada,
            "patrocinador_id": patrocinador_id,
            "notas": notas,
        },
    )


def registrar_saida(
    api: Api,
    base_id: str,
    *,
    item_id: str,
    quantidade: int,
    executado_por: str,
    evento_id: Optional[str] = None,
    caixa_origem_id: Optional[str] = None,
    caixa_destino_id: Optional[str] = None,
    patrocinador_id: Optional[str] = None,
    notas: str = "",
) -> Dict[str, Any]:
    quantidade = _to_int_positivo(quantidade)
    tabela_inv = api.table(base_id, _tombola_table("INVENTARIO", "Inventario"))
    item = tabela_inv.get(item_id)
    atual = _to_float(item.get("fields", {}).get("QuantidadeAtual"))
    novo_valor = atual - quantidade
    if novo_valor < 0:
        raise ValueError("Operação inválida: stock não pode ficar negativo.")
    return _atualizar_inventario_e_movimento(
        api,
        base_id,
        item_id=item_id,
        quantidade_atual_anterior=atual,
        quantidade_nova=novo_valor,
        dados_movimento={
            "tipo": "Saída",
            "quantidade": quantidade,
            "executado_por": executado_por,
            "caixa_origem_id": caixa_origem_id,
            "caixa_destino_id": caixa_destino_id,
            "evento_id": evento_id,
            "patrocinador_id": patrocinador_id,
            "notas": notas,
        },
    )


def registrar_ajuste(
    api: Api,
    base_id: str,
    *,
    item_id: str,
    quantidade: int,
    executado_por: str,
    reduzir: bool = False,
    evento_id: Optional[str] = None,
    caixa_origem_id: Optional[str] = None,
    caixa_destino_id: Optional[str] = None,
    patrocinador_id: Optional[str] = None,
    notas: str = "",
) -> Dict[str, Any]:
    quantidade = _to_int_positivo(quantidade)
    tabela_inv = api.table(base_id, _tombola_table("INVENTARIO", "Inventario"))
    item = tabela_inv.get(item_id)
    atual = _to_float(item.get("fields", {}).get("QuantidadeAtual"))
    novo_valor = atual - quantidade if reduzir else atual + quantidade
    if novo_valor < 0:
        raise ValueError("Operação inválida: stock não pode ficar negativo.")
    return _atualizar_inventario_e_movimento(
        api,
        base_id,
        item_id=item_id,
        quantidade_atual_anterior=atual,
        quantidade_nova=novo_valor,
        dados_movimento={
            "tipo": "Ajuste",
            "quantidade": quantidade,
            "executado_por": executado_por,
            "caixa_origem_id": caixa_origem_id,
            "caixa_destino_id": caixa_destino_id,
            "evento_id": evento_id,
            "patrocinador_id": patrocinador_id,
            "notas": notas,
        },
    )


def registrar_transferencia(
    api: Api,
    base_id: str,
    *,
    item_id: str,
    quantidade: int,
    caixa_destino_id: str,
    executado_por: str,
    evento_id: Optional[str] = None,
    patrocinador_id: Optional[str] = None,
    notas: str = "",
) -> Dict[str, Any]:
    quantidade = _to_int_positivo(quantidade)
    tabela_inv = api.table(base_id, _tombola_table("INVENTARIO", "Inventario"))
    item = tabela_inv.get(item_id)
    campos_item = item.get("fields", {})
    caixa_origem_id = _first_link_id(campos_item.get("CaixaAtual"))
    atual = _to_float(campos_item.get("QuantidadeAtual"))
    if quantidade > atual:
        raise ValueError("Operação inválida: quantidade transferida excede stock disponível.")
    return _atualizar_inventario_e_movimento(
        api,
        base_id,
        item_id=item_id,
        quantidade_atual_anterior=atual,
        quantidade_nova=atual,
        caixa_anterior=caixa_origem_id,
        caixa_nova=caixa_destino_id,
        dados_movimento={
            "tipo": "Transferência",
            "quantidade": quantidade,
            "executado_por": executado_por,
            "caixa_origem_id": caixa_origem_id,
            "caixa_destino_id": caixa_destino_id,
            "evento_id": evento_id,
            "patrocinador_id": patrocinador_id,
            "notas": notas,
        },
    )


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
    """Stock real vive no Inventário; Movimentos é auditoria de ajustes e saídas."""
    if tipo_movimento not in {"Entrada", "Saída", "Ajuste"}:
        raise ValueError("Tipo de movimento inválido para ajuste de stock.")

    if delta == 0:
        raise ValueError("A alteração de stock não pode ser zero.")

    tabela_inv = api.table(base_id, _tombola_table("INVENTARIO", "Inventario"))
    item = tabela_inv.get(item_id)
    campos_item = item.get("fields", {})
    caixa_origem_id = _first_link_id(campos_item.get("CaixaAtual"))
    quantidade = abs(int(delta))

    if tipo_movimento == "Entrada":
        if delta < 0:
            raise ValueError("Entrada deve usar um delta positivo.")
        return registrar_entrada(
            api,
            base_id,
            item_id=item_id,
            quantidade=quantidade,
            executado_por=executado_por,
            evento_id=evento_id,
            caixa_origem_id=caixa_origem_id,
            origem_entrada=origem_entrada,
            patrocinador_id=patrocinador_id,
            notas=notas,
        )

    if tipo_movimento == "Saída":
        if delta > 0:
            raise ValueError("Saída deve usar um delta negativo.")
        return registrar_saida(
            api,
            base_id,
            item_id=item_id,
            quantidade=quantidade,
            executado_por=executado_por,
            evento_id=evento_id,
            caixa_origem_id=caixa_origem_id,
            patrocinador_id=patrocinador_id,
            notas=notas,
        )

    return registrar_ajuste(
        api,
        base_id,
        item_id=item_id,
        quantidade=quantidade,
        executado_por=executado_por,
        reduzir=delta < 0,
        evento_id=evento_id,
        caixa_origem_id=caixa_origem_id,
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
    """Stock real vive no Inventário; Movimentos é auditoria de transferências."""
    quantidade = _to_int_positivo(quantidade)

    tabela_inv = api.table(base_id, _tombola_table("INVENTARIO", "Inventario"))
    item = tabela_inv.get(item_id)
    campos_item = item.get("fields", {})
    caixa_origem_id = _first_link_id(campos_item.get("CaixaAtual"))

    tabela_inv.update(item_id, {"CaixaAtual": [caixa_destino_id]})
    try:
        return criar_movimento(
            api,
            base_id,
            tipo="Transferência",
            item_id=item_id,
            caixa_origem_id=caixa_origem_id,
            caixa_destino_id=caixa_destino_id,
            quantidade=quantidade,
            executado_por=executado_por,
            notas=notas,
        )
    except Exception as exc:
        rollback_payload: Dict[str, Any] = {"CaixaAtual": [caixa_origem_id] if caixa_origem_id else []}
        try:
            tabela_inv.update(item_id, rollback_payload)
        except Exception as rollback_exc:
            raise RuntimeError(
                "Falha ao criar movimento e não foi possível repor a caixa do inventário automaticamente."
            ) from rollback_exc
        raise RuntimeError("Falha ao criar movimento; atualização de caixa revertida.") from exc


def processar_movimentos_lote(
    api: Api,
    base_id: str,
    *,
    operacoes: Iterable[Dict[str, Any]],
    executado_por: str,
) -> Dict[str, Any]:
    """Processa uma lista de operações e devolve um relatório de sucessos/falhas.

    Cada operação deve indicar pelo menos `item_id` e `tipo`.
    Campos suportados por operação:

    - Comuns: `item_id`, `tipo`, `notas` (opcional), `evento_id` (opcional),
      `executado_por` (opcional; faz override do argumento da função).
    - Entrada/Saída/Ajuste: `delta` **ou** `quantidade`.
      - Em `Entrada`, o valor deve ser positivo.
      - Em `Saída`, o valor deve ser negativo quando usar `delta`.
      - Em `Ajuste`, o valor pode ser positivo ou negativo.
    - Transferência: `quantidade` e `caixa_destino_id`.

    Exemplo de payload (útil para integração na página Streamlit):

    ```python
    operacoes = [
        {
            "item_id": "recItem001",
            "tipo": "Entrada",
            "delta": 5,
            "notas": "Reposição semanal",
            "evento_id": "recEvt001",
        },
        {
            "item_id": "recItem002",
            "tipo": "Saída",
            "quantidade": 2,
            "notas": "Consumo no evento",
            "evento_id": "recEvt001",
        },
        {
            "item_id": "recItem003",
            "tipo": "Transferência",
            "quantidade": 1,
            "caixa_destino_id": "recBox002",
            "notas": "Movido para caixa VIP",
        },
    ]

    relatorio = processar_movimentos_lote(
        api,
        base_id,
        operacoes=operacoes,
        executado_por="operador@empresa.com",
    )
    ```
    """
    if not (executado_por or "").strip():
        raise ValueError("ExecutadoPor é obrigatório com o email do utilizador autenticado.")

    sucessos: List[Dict[str, Any]] = []
    falhas: List[Dict[str, Any]] = []

    for indice, operacao in enumerate(operacoes):
        item_id = str(operacao.get("item_id") or "").strip()
        tipo = str(operacao.get("tipo") or "").strip()
        notas = str(operacao.get("notas") or "")
        evento_id = operacao.get("evento_id")
        executado_por_operacao = str(operacao.get("executado_por") or executado_por).strip()

        try:
            if not item_id:
                raise ValueError("item_id é obrigatório.")

            if tipo == "Transferência":
                caixa_destino_id = str(operacao.get("caixa_destino_id") or "").strip()
                if not caixa_destino_id:
                    raise ValueError("caixa_destino_id é obrigatório para Transferência.")

                resultado = transferir_item_caixa(
                    api,
                    base_id,
                    item_id=item_id,
                    caixa_destino_id=caixa_destino_id,
                    quantidade=operacao.get("quantidade"),
                    executado_por=executado_por_operacao,
                    notas=notas,
                )
            else:
                if tipo not in {"Entrada", "Saída", "Ajuste"}:
                    raise ValueError(f"Tipo de operação inválido: {tipo}")

                delta = operacao.get("delta")
                if delta is None:
                    quantidade = _to_int_positivo(operacao.get("quantidade"))
                    delta = -quantidade if tipo == "Saída" else quantidade

                resultado = ajustar_stock_item(
                    api,
                    base_id,
                    item_id=item_id,
                    delta=int(delta),
                    executado_por=executado_por_operacao,
                    tipo_movimento=tipo,
                    notas=notas,
                    evento_id=evento_id,
                    origem_entrada=operacao.get("origem_entrada"),
                    patrocinador_id=operacao.get("patrocinador_id"),
                )

            sucessos.append(
                {
                    "indice": indice,
                    "item_id": item_id,
                    "tipo": tipo,
                    "movimento_id": resultado.get("id"),
                }
            )
        except Exception as exc:
            falhas.append(
                {
                    "indice": indice,
                    "item_id": item_id,
                    "tipo": tipo,
                    "motivo": str(exc),
                }
            )

    return {
        "sucessos": sucessos,
        "falhas": falhas,
        "totais": {
            "processadas": len(sucessos) + len(falhas),
            "sucessos": len(sucessos),
            "falhas": len(falhas),
        },
    }


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
