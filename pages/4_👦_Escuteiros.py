import pandas as pd
import streamlit as st
from menu import menu_with_redirect
from utils import get_personalized_lanche_links

menu_with_redirect()

st.title("🧒 Escuteiros")

dados = st.session_state.get("dados_cache", {})
df_recipes = dados.get("Recipes", pd.DataFrame())
user_info = st.session_state.get("user", {})
escuteiros_ids = user_info.get("escuteiros_ids", []) if user_info else []
df_escuteiros = dados.get("Escuteiros", pd.DataFrame())
lanche_links = get_personalized_lanche_links(df_escuteiros, escuteiros_ids)

def _first_existing(frame: pd.DataFrame, columns: list[str]) -> str | None:
    if frame is None or frame.empty:
        return None
    for col in columns:
        if col in frame.columns:
            return col
    return None

df_menu = dados.get("Publicar Menu do Scouts", pd.DataFrame())
recipes_name_col = _first_existing(df_recipes, ['Menu', 'Nome', 'Nome do Item']) if df_recipes is not None else None
recipes_map = {}
if recipes_name_col:
    recipes_map = df_recipes.set_index('id')[recipes_name_col].dropna().astype(str).to_dict()


possible_date_columns = [
    "Date (from Publicação Filtro)",
    "Date (from Marcação dos Pais na preparação do Lanche)",
    "Date ( calendário )",
    "Date (calendário)",
    "Date",
]

def _normalizar_data_menu(frame: pd.DataFrame) -> pd.DataFrame | None:
    if frame is None or frame.empty:
        return None
    frame_local = frame.copy()
    for coluna in possible_date_columns:
        if coluna not in frame_local.columns:
            continue
        serie = frame_local[coluna].apply(
            lambda valor: valor[0] if isinstance(valor, list) and valor else valor
        )
        serie = pd.to_datetime(serie, errors="coerce")
        if serie.notna().any():
            frame_local["__data_menu"] = serie
            return frame_local
    return None

item_columns = [
    ("Entrada", ["Entrada", "Entradas"]),
    ("Lanches", ["Lanches", "Lanche"]),
    ("Bebidas", ["Bebidas", "Bebida"]),
    ("Sobremesa", ["Sobremesa", "Sobremesas"]),
    ("Fruta", ["Fruta", "Frutas"]),
]

def _render_menu_info(frame: pd.DataFrame) -> None:
    if frame is None or frame.empty:
        st.info('Sem menu publicado para os pr\u00f3ximos lanches.')
        return
    frame = frame.copy()
    col_data = _first_existing(frame, possible_date_columns)
    if col_data is None:
        st.info('Sem menu publicado para os pr\u00f3ximos lanches.')
        return
    frame['__data_menu'] = frame[col_data].apply(
        lambda valor: valor[0] if isinstance(valor, list) and valor else valor
    )
    frame['__data_menu'] = pd.to_datetime(frame['__data_menu'], errors='coerce')
    frame = frame[frame['__data_menu'].notna()].sort_values('__data_menu')
    if frame.empty:
        st.info('Sem menu publicado para os pr\u00f3ximos lanches.')
        return

    iso = frame['__data_menu'].dt.isocalendar()
    frame['__iso_year'] = iso['year']
    frame['__iso_week'] = iso['week']

    hoje = pd.Timestamp.today().normalize()
    hoje_iso = hoje.isocalendar()

    desta_semana = frame[
        (frame['__iso_year'] == hoje_iso.year) & (frame['__iso_week'] == hoje_iso.week)
    ]
    if not desta_semana.empty:
        destaque = desta_semana.iloc[0]
        titulo = 'Menu desta semana'
    else:
        proximo = frame[frame['__data_menu'] >= hoje]
        if not proximo.empty:
            destaque = proximo.iloc[0]
            titulo = 'Menu do pr\u00f3ximo lanche'
        else:
            destaque = frame.iloc[-1]
            titulo = '\u00daltimo menu publicado'

    data_txt = destaque['__data_menu'].strftime('%d/%m/%Y')

    def _format_valor(valor):
        if isinstance(valor, list):
            valores = []
            for item in valor:
                item_str = str(item).strip() if not isinstance(item, list) else ''
                if item_str in recipes_map:
                    valores.append(recipes_map[item_str])
                elif item_str:
                    valores.append(item_str)
            return ', '.join(v for v in valores if v)
        valor_str = str(valor).strip()
        if not valor_str:
            return ''
        return recipes_map.get(valor_str, valor_str)

    itens = []
    for rotulo, campos in item_columns:
        valor_campo = None
        for campo in campos:
            if campo in destaque and pd.notna(destaque.get(campo)):
                valor_campo = destaque.get(campo)
                break
        if valor_campo is None:
            continue
        texto = _format_valor(valor_campo)
        if not texto:
            texto = '-'
        itens.append(f'- **{rotulo}:** {texto}')

    with st.container(border=True):
        st.markdown(f'### {titulo} ({data_txt})')
        if itens:
            st.markdown('\n'.join(itens))
        else:
            st.markdown('Menu ainda n\u00e3o publicado.')


_render_menu_info(_normalizar_data_menu(df_menu))

st.markdown(
    """
    ### 🧺 Formulario de Marcacao de Lanche
    Preencha o formulario abaixo para marcar o lanche do seu escuteiro.
    """
)

iframe_src = ""
if lanche_links:
    if len(lanche_links) == 1:
        idx_selecionado = 0
    else:
        idx_selecionado = st.selectbox(
            "Escolha o escuteiro para preencher o formulario",
            list(range(len(lanche_links))),
            format_func=lambda idx: lanche_links[idx][0],
            key="selecionar_escuteiro_form_lanche",
        )
    nome_selecionado, iframe_src = lanche_links[idx_selecionado]
    st.caption(f"O formulario abaixo ja esta preparado para {nome_selecionado}.")

if iframe_src:
    st.components.v1.html(
        f"""
        <iframe class="airtable-embed"
            src="{iframe_src}"
            frameborder="0" onmousewheel="" width="100%" height="650"
            style="background: transparent; border: 1px solid #ccc;">
        </iframe>
        """,
        height=700,
        scrolling=True,
    )
else:
    st.info("Sem link de marcacao para os escuteiros selecionados.")

st.markdown("---")
st.info(
    "Precisa cancelar uma marcação? Utilize a opção **Cancelar Lanche** no dashboard principal."
)
