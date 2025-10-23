from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Tuple

import streamlit as st
import toml

SESSION_CONTEXT_KEY = "airtable_context_key"


@dataclass(frozen=True)
class AirtableContext:
    """Empacota credenciais e metadados para uma combinação agrupamento/secção."""

    key: str
    agrupamento_label: str
    secao_label: str
    agrupamento_id: str
    secao_slug: str
    token: str
    base_id: str
    extras: Dict[str, str] = field(default_factory=dict)

    def extra(self, name: str, default: Optional[str] = None) -> Optional[str]:
        return self.extras.get(name.upper(), default)


def _to_plain_dict(value) -> Dict[str, str]:
    if isinstance(value, Mapping):
        return {k: _to_plain_dict(v) for k, v in value.items()}
    return value


def _load_raw_secrets() -> Dict[str, Dict[str, str]]:
    """Obtém os secrets como dicionário (Cloud ou local)."""
    try:
        keys: Iterable[str] = st.secrets.keys()  # type: ignore[attr-defined]
    except Exception:
        return toml.load(".streamlit/secrets.toml")
    else:
        return {key: _to_plain_dict(st.secrets[key]) for key in keys}  # type: ignore[index]


def _slug_to_label(slug: str) -> str:
    partes = slug.replace("-", " ").replace("_", " ").split()
    return " ".join(p.capitalize() for p in partes) if partes else slug.title()


@lru_cache(maxsize=1)
def _contexts_cache() -> Tuple[AirtableContext, ...]:
    raw = _load_raw_secrets()
    contexts: List[AirtableContext] = []

    for key, valores in raw.items():
        if not key.startswith("airtable_") or not isinstance(valores, dict):
            continue

        token = valores.get("AIRTABLE_TOKEN")
        base_id = valores.get("AIRTABLE_BASE_ID")
        if not token or not base_id:
            continue

        partes = key.split("_")
        agrupamento_id = valores.get("AGRUPAMENTO_ID")
        secao_slug = valores.get("SECAO_SLUG")

        if agrupamento_id is None or secao_slug is None:
            if len(partes) >= 3:
                agrupamento_id = partes[1]
                secao_slug = "_".join(partes[2:])
            else:
                agrupamento_id = partes[-1] if len(partes) > 1 else "default"
                secao_slug = partes[-1]

        agrupamento_label = valores.get("AGRUPAMENTO_LABEL") or f"Agrupamento {_slug_to_label(agrupamento_id)}"
        secao_label = valores.get("SECAO_LABEL") or _slug_to_label(secao_slug)

        extras = {
            k.upper(): str(v)
            for k, v in valores.items()
            if k
            not in {
                "AIRTABLE_TOKEN",
                "AIRTABLE_BASE_ID",
                "AGRUPAMENTO_ID",
                "SECAO_SLUG",
                "AGRUPAMENTO_LABEL",
                "SECAO_LABEL",
            }
        }

        contexts.append(
            AirtableContext(
                key=key,
                agrupamento_label=agrupamento_label,
                secao_label=secao_label,
                agrupamento_id=agrupamento_id,
                secao_slug=secao_slug,
                token=token,
                base_id=base_id,
                extras=extras,
            )
        )

    contexts.sort(key=lambda ctx: (ctx.agrupamento_label.lower(), ctx.secao_label.lower()))
    return tuple(contexts)


def get_available_contexts() -> List[AirtableContext]:
    """Lista todas as combinações agrupamento/secção disponíveis."""
    return list(_contexts_cache())


def get_context_by_key(key: str) -> Optional[AirtableContext]:
    for ctx in _contexts_cache():
        if ctx.key == key:
            return ctx
    return None


def current_context() -> Optional[AirtableContext]:
    key = st.session_state.get(SESSION_CONTEXT_KEY)
    if key:
        return get_context_by_key(str(key))
    return None


def set_current_context(key: str) -> None:
    st.session_state[SESSION_CONTEXT_KEY] = key


def ensure_context_selected() -> Optional[AirtableContext]:
    """Garante que existe alguma secção selecionada; atribui automaticamente se existir apenas uma."""
    ctx = current_context()
    if ctx is not None:
        return ctx

    contexts = get_available_contexts()
    if contexts and len(contexts) == 1:
        unico = contexts[0]
        set_current_context(unico.key)
        return unico
    return None


def clear_authentication(keep_context: bool = True) -> None:
    """Remove dados de autenticação/caches. Mantém a secção atual se indicado."""
    keys_to_keep = {SESSION_CONTEXT_KEY} if keep_context else set()
    keys_to_remove = [key for key in list(st.session_state.keys()) if key not in keys_to_keep]
    for key in keys_to_remove:
        st.session_state.pop(key, None)


def reset_context() -> None:
    """Limpa a secção atual e quaisquer dados de sessão."""
    clear_authentication(keep_context=False)


def get_airtable_credentials() -> Tuple[str, str]:
    ctx = current_context()
    if ctx is None:
        raise RuntimeError("Nenhuma secção Airtable selecionada.")
    return ctx.token, ctx.base_id


def context_labels() -> Optional[str]:
    ctx = current_context()
    if ctx is None:
        return None
    return f"{ctx.agrupamento_label} · {ctx.secao_label}"


def context_extra(name: str, default: Optional[str] = None) -> Optional[str]:
    ctx = current_context()
    if ctx is None:
        return default
    return ctx.extra(name, default)
