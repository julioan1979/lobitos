from __future__ import annotations

from typing import Iterable, List, Tuple
from urllib.parse import urlsplit, urlunsplit

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
        url = _normalize_airtable_form_url(url)
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


def _normalize_airtable_form_url(raw_url: str | None) -> str:
    url = (raw_url or "").strip()
    if not url:
        return ""
    if "/embed/" in url:
        return url

    parsed = urlsplit(url)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or "airtable.com"
    path = parsed.path.lstrip("/")

    if not path:
        return ""

    if not path.startswith("embed/"):
        path = f"embed/{path}"

    return urlunsplit((scheme, netloc, f"/{path}", parsed.query, parsed.fragment))
