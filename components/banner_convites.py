"""Componentes reutilizáveis para banners de convites.

Para activar um convite:
1. Adicione ou actualize entradas em ``CONVITES`` com as datas, link e posições desejadas.
2. Use ``mostrar_convites("login")`` ou ``mostrar_convites("sidebar")`` para renderizar.
3. Quando a campanha terminar, ajuste ``ativo_ate`` ou remova a configuração.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Tuple

import streamlit as st


_CSS_SESSION_KEY = "_convite_banner_css_injected"


def _inject_css() -> None:
    if st.session_state.get(_CSS_SESSION_KEY):
        return

    st.session_state[_CSS_SESSION_KEY] = True
    st.markdown(
        """
        <style>
            .convite-card {
                border-radius: 16px;
                padding: 1.1rem 1.4rem;
                margin: 1rem 0;
                color: #ffffff;
                position: relative;
                overflow: hidden;
                box-shadow: 0 12px 30px rgba(0, 0, 0, 0.08);
            }

            .convite-card::after {
                content: "";
                position: absolute;
                inset: 0;
                background: radial-gradient(circle at top right, rgba(255, 255, 255, 0.14), transparent 60%);
                pointer-events: none;
            }

            .convite-card .convite-header {
                font-size: 1.2rem;
                font-weight: 700;
                margin-bottom: 0.4rem;
            }

            .convite-card .convite-meta {
                font-size: 0.95rem;
                opacity: 0.92;
                margin-bottom: 0.75rem;
            }

            .convite-card .convite-descricao {
                font-size: 0.95rem;
                line-height: 1.45;
                margin-bottom: 1rem;
            }

            .convite-card .convite-cta {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 0.4rem;
                padding: 0.55rem 1.1rem;
                border-radius: 999px;
                font-weight: 600;
                text-decoration: none;
                transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
            }

            .convite-card .convite-cta:hover {
                transform: translateY(-1px);
                text-decoration: none;
                box-shadow: 0 8px 20px rgba(0, 0, 0, 0.18);
            }

            .convite-card .convite-layout {
                display: flex;
                flex-direction: column;
                gap: 1rem;
            }

            .convite-card .convite-imagem {
                border-radius: 12px;
                overflow: hidden;
                max-height: 200px;
            }

            .convite-card .convite-imagem img {
                width: 100%;
                height: 100%;
                object-fit: cover;
            }

            @media (min-width: 768px) {
                .convite-card .convite-layout {
                    flex-direction: row;
                    align-items: center;
                }

                .convite-card .convite-imagem {
                    width: 42%;
                    max-height: 220px;
                }

                .convite-card .convite-conteudo {
                    width: 58%;
                }
            }

            .convite-card.convite-sidebar {
                padding: 0.9rem 1rem;
                margin-top: 0.8rem;
            }

            .convite-card.convite-sidebar .convite-layout {
                flex-direction: column;
            }

            .convite-card.convite-sidebar .convite-imagem {
                max-height: 160px;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


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
        posicoes=("login", "sidebar"),
        imagem_url=None,  # Substitua por um caminho local ou URL público quando disponível.
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

    imagem_html = ""
    if convite.imagem_url:
        imagem_html = f"""
            <div class="convite-imagem">
                <img src="{convite.imagem_url}" alt="{convite.titulo}">
            </div>
        """

    html = f"""
        <div class="{card_classes}"
             style="background:{convite.background};color:{convite.texto};border-left:6px solid {convite.accent};">
            <div class="convite-layout">
                {imagem_html}
                <div class="convite-conteudo">
                    <div class="convite-header">{convite.titulo}</div>
                    <div class="convite-meta">{convite.data_local}</div>
                    <div class="convite-descricao">{convite.descricao}</div>
                    <a class="convite-cta" href="{convite.link}" target="_blank" style="background:{convite.accent};color:{convite.background};">
                        <span>🎟️</span><span>Inscreve-te já</span>
                    </a>
                </div>
            </div>
        </div>
    """

    destino = st.sidebar if destino_sidebar else st
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
