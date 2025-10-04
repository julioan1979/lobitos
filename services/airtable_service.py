from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

import pandas as pd
from pyairtable import Api

_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class AirtableConfig:
    token: str
    base_id: str


class AirtableService:
    def __init__(
        self,
        config: AirtableConfig,
        *,
        max_retries: int = 3,
        initial_backoff: float = 0.5,
    ) -> None:
        self._config = config
        self._max_retries = max_retries
        self._initial_backoff = initial_backoff
        self._api = Api(config.token)

    @property
    def base_id(self) -> str:
        return self._config.base_id

    def list_table_names(self) -> list[str]:
        base = self._api.base(self._config.base_id)
        tables = self._with_retry(base.tables)
        return [tbl.name for tbl in tables]

    def fetch_table(
        self,
        table_name: str,
        *,
        fields: Optional[Iterable[str]] = None,
        formula: Optional[str] = None,
        max_records: Optional[int] = None,
        sort: Optional[Iterable[Mapping[str, Any]]] = None,
    ) -> pd.DataFrame:
        table = self._api.table(self._config.base_id, table_name)
        records = self._with_retry(
            table.all,
            formula=formula,
            max_records=max_records,
            fields=list(fields) if fields is not None else None,
            sort=sort,
        )
        rows = [
            {"id": record.get("id"), **(record.get("fields") or {})}
            for record in records
        ]
        return pd.DataFrame(rows)

    def create_record(self, table_name: str, fields: Mapping[str, Any]) -> Mapping[str, Any]:
        table = self._api.table(self._config.base_id, table_name)
        return self._with_retry(table.create, dict(fields))

    def update_record(self, table_name: str, record_id: str, fields: Mapping[str, Any]) -> Mapping[str, Any]:
        table = self._api.table(self._config.base_id, table_name)
        return self._with_retry(table.update, record_id, dict(fields))

    def delete_record(self, table_name: str, record_id: str) -> None:
        table = self._api.table(self._config.base_id, table_name)
        self._with_retry(table.delete, record_id)

    def _with_retry(self, func, *args, **kwargs):
        backoff = self._initial_backoff
        attempt = 1
        while True:
            try:
                return func(*args, **kwargs)
            except Exception as exc:  # pragma: no cover
                status = _extract_status_code(exc)
                if attempt >= self._max_retries or status not in _RETRYABLE_STATUS:
                    raise
                time.sleep(backoff)
                backoff *= 2
                attempt += 1


def _extract_status_code(exc: Exception) -> Optional[int]:
    status = getattr(exc, "status_code", None)
    if status is not None:
        return status
    response = getattr(exc, "response", None)
    if response is not None:
        return getattr(response, "status_code", None)
    return None
