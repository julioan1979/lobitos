from __future__ import annotations

from typing import Iterable, List, Tuple

import pandas as pd

LANCHES_LINK_COLUMN = "Pre_Field escolha semanal lanches"
ESCUTEIRO_NAME_COLUMNS = (
    "Nome do Escuteiro",
    "Nome",
    "Escuteiro",
)


def get_personalized_lanche_links(
    frame: pd.DataFrame | None, allowed_ids: Iterable[str] | None = None
) -> List[Tuple[str, str]]:
    """Extract the pre-filled lanche form links for the given escuteiros."""
    if frame is None or frame.empty:
        return []
    if "id" not in frame.columns or LANCHES_LINK_COLUMN not in frame.columns:
        return []

    subset = frame
    if allowed_ids:
        allowed_set = set(allowed_ids)
        subset = subset[subset["id"].isin(allowed_set)]

    links: List[Tuple[str, str]] = []
    for _, row in subset.iterrows():
        url = row.get(LANCHES_LINK_COLUMN)
        if isinstance(url, list):
            url = url[0] if url else ""
        url = (url or "").strip()
        if not url:
            continue

        nome = ""
        for coluna in ESCUTEIRO_NAME_COLUMNS:
            valor = row.get(coluna)
            if isinstance(valor, str) and valor.strip():
                nome = valor.strip()
                break
        if not nome:
            nome = str(row.get("id", ""))

        links.append((nome, url))

    return links
