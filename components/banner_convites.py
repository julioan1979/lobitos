"""Componentes reutilizáveis para banners de convites.

Para activar um convite:
1. Adicione ou actualize entradas em ``CONVITES`` com as datas, link e posições desejadas.
2. Use ``mostrar_convites("login")`` ou ``mostrar_convites("principal")`` para renderizar.
3. Quando a campanha terminar, ajuste ``ativo_ate`` ou remova a configuração.
"""

from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Tuple

import streamlit as st


_CSS_SESSION_KEY = "_convite_banner_css_injected"
_BASE_DIR = Path(__file__).resolve().parent.parent


def _inject_css() -> None:
    if st.session_state.get(_CSS_SESSION_KEY):
        return

    st.session_state[_CSS_SESSION_KEY] = True
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Poppins:wght@400;600;700&display=swap');

            :root {
                --convite-font-title: 'Inter', 'Poppins', sans-serif;
                --convite-font-body: 'Inter', 'Poppins', sans-serif;
                --convite-bg-start: #1d275a;
                --convite-bg-end: #162447;
                --convite-shadow: 0 16px 40px rgba(6, 9, 24, 0.45);
                --convite-text-strong: rgba(255, 255, 255, 0.96);
                --convite-text-body: rgba(255, 255, 255, 0.88);
                --convite-cta-bg: #FFC857;
                --convite-cta-bg-hover: #ffd673;
                --convite-cta-text: #1b1f35;
            }

            .convite-card {
                position: relative;
                border-radius: 20px;
                padding: 1.8rem;
                margin: 1.4rem 0;
                background: linear-gradient(145deg, var(--convite-bg-start), var(--convite-bg-end));
                box-shadow: var(--convite-shadow);
                overflow: hidden;
                font-family: var(--convite-font-body);
                color: var(--convite-text-body);
                border: 1px solid rgba(255, 255, 255, 0.04);
                backdrop-filter: blur(8px);
                transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
            }

            .convite-card:not(.convite-sidebar) {
                max-width: 600px;
                margin-left: auto;
                margin-right: auto;
            }

            .convite-card:hover {
                transform: translateY(-3px);
                box-shadow: 0 24px 46px rgba(6, 9, 24, 0.6);
                border-color: rgba(255, 255, 255, 0.1);
            }

            .convite-card::before {
                content: "";
                position: absolute;
                inset: 0;
                background: radial-gradient(circle at 18% 22%, rgba(255, 255, 255, 0.15), transparent 60%);
                pointer-events: none;
            }

            .convite-card .convite-layout {
                display: flex;
                flex-direction: column;
                gap: 1.5rem;
                position: relative;
                z-index: 1;
            }

            .convite-card .convite-imagem {
                border-radius: 16px;
                overflow: hidden;
                width: 100%;
                max-height: 220px;
                box-shadow: 0 12px 28px rgba(6, 9, 24, 0.45);
            }

            .convite-card .convite-imagem img {
                width: 100%;
                height: 100%;
                object-fit: cover;
            }

            .convite-card .convite-conteudo {
                display: flex;
                flex-direction: column;
                gap: 0.75rem;
            }

            .convite-card .convite-header {
                font-family: var(--convite-font-title);
                font-weight: 700;
                font-size: 1.35rem;
                letter-spacing: 0.01em;
                color: var(--convite-text-strong);
            }

            .convite-card .convite-meta {
                font-size: 0.95rem;
                font-weight: 500;
                color: rgba(255, 255, 255, 0.72);
            }

            .convite-card .convite-descricao {
                font-size: 1rem;
                font-weight: 400;
                line-height: 1.6;
                color: var(--convite-text-body);
            }

            .convite-card .convite-cta {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 0.5rem;
                padding: 0.65rem 1.4rem;
                border-radius: 999px;
                background: var(--convite-cta-bg);
                color: var(--convite-cta-text);
                font-family: var(--convite-font-title);
                font-weight: 600;
                text-decoration: none !important;
                letter-spacing: 0.01em;
                transition: transform 0.18s ease, background 0.18s ease, box-shadow 0.18s ease;
            }

            .convite-card .convite-cta span:first-child {
                font-size: 1.1rem;
            }

            .convite-card .convite-cta:hover {
                background: var(--convite-cta-bg-hover);
                transform: translateY(-2px);
                box-shadow: 0 14px 26px rgba(255, 200, 87, 0.35);
            }

            .convite-card.convite-sidebar {
                padding: 1.2rem 1.3rem;
                margin-top: 1.1rem;
            }

            .convite-card.convite-sidebar .convite-layout {
                gap: 1.1rem;
            }

            .convite-card.convite-sidebar .convite-imagem {
                max-height: 180px;
            }

            @media (min-width: 768px) {
                .convite-card .convite-layout {
                    flex-direction: row;
                    align-items: center;
                }

                .convite-card .convite-imagem {
                    width: 38%;
                    max-height: 240px;
                }

                .convite-card .convite-conteudo {
                    width: 62%;
                }

                .convite-card.convite-sidebar .convite-layout {
                    flex-direction: column;
                    align-items: flex-start;
                }

                .convite-card.convite-sidebar .convite-imagem,
                .convite-card.convite-sidebar .convite-conteudo {
                    width: 100%;
                }
            }

            @media (max-width: 480px) {
                .convite-card {
                    padding: 1.4rem;
                }

                .convite-card .convite-header {
                    font-size: 1.2rem;
                }

                .convite-card .convite-cta {
                    width: 100%;
                }
            }

            .convite-card.convite-banner-only {
                padding: 0;
                border: none;
                background: none;
                box-shadow: none;
                max-width: 720px;
            }

            .convite-card.convite-banner-only .convite-banner-link {
                display: block;
                border-radius: 24px;
                overflow: hidden;
                box-shadow: 0 20px 40px rgba(6, 9, 24, 0.4);
                transition: transform 0.25s ease, box-shadow 0.25s ease;
            }

            .convite-card.convite-banner-only .convite-banner-link:hover {
                transform: translateY(-4px);
                box-shadow: 0 28px 52px rgba(6, 9, 24, 0.55);
            }

            .convite-card.convite-banner-only img {
                display: block;
                width: 100%;
                height: auto;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _resolver_imagem_src(caminho: str | None) -> str | None:
    if not caminho:
        return None
    caminho = caminho.strip()
    if caminho.startswith(("http://", "https://", "data:")):
        return caminho

    caminho_path = Path(caminho)
    if not caminho_path.is_absolute():
        caminho_path = (_BASE_DIR / caminho_path).resolve()

    if not caminho_path.exists():
        return None

    mime, _ = mimetypes.guess_type(str(caminho_path))
    if not mime:
        mime = "image/png"

    try:
        dados = caminho_path.read_bytes()
    except OSError:
        return None

    encoded = base64.b64encode(dados).decode("ascii")
    return f"data:{mime};base64,{encoded}"


@dataclass(frozen=True)
class ConviteConfig:
    chave: str
    titulo: str
    data_local: str
    descricao: str
    link: str
    posicoes: Tuple[str, ...]
    imagem_url: str | None = None
    ativo_desde: date | None = None
    ativo_ate: date | None = None
    background: str = "#162447"
    accent: str = "#F6C65B"
    texto: str = "#FFFFFF"

    def esta_ativo(self, hoje: date | None = None) -> bool:
        hoje = hoje or date.today()
        if self.ativo_desde and hoje < self.ativo_desde:
            return False
        if self.ativo_ate and hoje > self.ativo_ate:
            return False
        return True


CONVITES: Tuple[ConviteConfig, ...] = (
    ConviteConfig(
        chave="planeta-magusto",
        titulo="O Planeta do Magusto",
        data_local="15 de Novembro · 19h30 · Escola Secundária da Senhora da Hora (Amarela)",
        descricao="Garanta a sua presença na festa do magusto: escolha o menu preferido e inscreva-se já.",
        link="https://forms.fillout.com/t/3myp9UYEgZus",
        posicoes=("login", "principal"),
        imagem_url="static/planeta-magusto-banner.svg",
        ativo_desde=None,  # Ajuste estas datas quando quiser controlar a campanha.
        ativo_ate=None,
        background="#142146",
        accent="#F6C65B",
    ),
)


def _iterar_convites_ativos(posicao: str) -> Iterable[ConviteConfig]:
    for convite in CONVITES:
        if posicao not in convite.posicoes:
            continue
        if not convite.esta_ativo():
            continue
        yield convite


def _renderizar_convite(convite: ConviteConfig, *, destino_sidebar: bool) -> None:
    _inject_css()

    card_classes = "convite-card"
    if destino_sidebar:
        card_classes += " convite-sidebar"

    imagem_src = _resolver_imagem_src(convite.imagem_url)
    destino = st.sidebar if destino_sidebar else st

    if imagem_src and not destino_sidebar:
        html = (
            f'<div class="{card_classes} convite-banner-only">'
            f'<a class="convite-banner-link" href="{convite.link}" target="_blank" rel="noopener noreferrer">'
            f'<img src="{imagem_src}" alt="{convite.titulo}">'
            "</a>"
            "</div>"
        )
        destino.markdown(html, unsafe_allow_html=True)
        return

    imagem_html = ""
    if imagem_src:
        imagem_html = (
            '<div class="convite-imagem">'
            f'<img src="{imagem_src}" alt="{convite.titulo}">'
            "</div>"
        )

    html = (
        f'<div class="{card_classes}" '
        f'style="background:{convite.background};color:{convite.texto};border-left:6px solid {convite.accent};">'
        '<div class="convite-layout">'
        f"{imagem_html}"
        '<div class="convite-conteudo">'
        f'<div class="convite-header">{convite.titulo}</div>'
        f'<div class="convite-meta">{convite.data_local}</div>'
        f'<div class="convite-descricao">{convite.descricao}</div>'
        f'<a class="convite-cta" href="{convite.link}" target="_blank" '
        f'style="background:{convite.accent};color:{convite.background};">'
        "<span>🎟️</span><span>Inscreve-te já</span>"
        "</a>"
        "</div>"
        "</div>"
        "</div>"
    )

    destino.markdown(html, unsafe_allow_html=True)


def mostrar_convites(posicao: str) -> None:
    """Renderiza convites activos para uma determinada posição lógica.

    Parâmetros
    ----------
    posicao:
        Identificador lógico onde o convite deve aparecer. Exemplos:
        - ``"login"`` para páginas antes do login.
        - ``"sidebar"`` para menus laterais após login.
    """
    destino_sidebar = posicao == "sidebar"
    for convite in _iterar_convites_ativos(posicao):
        _renderizar_convite(convite, destino_sidebar=destino_sidebar)
