import pandas as pd


def mapear_lista(valor, mapping):
    if isinstance(valor, list):
        return ", ".join(mapping.get(v, v) for v in valor)
    if pd.isna(valor):
        return ""
    return mapping.get(valor, valor)


def formatar_moeda_euro(valor) -> str:
    if pd.isna(valor):
        return ""

    numero = valor
    if isinstance(valor, str):
        limpo = valor.replace("€", "").replace(" ", "")
        if "," in limpo and "." in limpo:
            limpo = limpo.replace(".", "").replace(",", ".")
        elif "," in limpo:
            limpo = limpo.replace(",", ".")
        try:
            numero = float(limpo)
        except ValueError:
            return valor
    try:
        numero = float(numero)
    except (TypeError, ValueError):
        return str(valor)

    texto = f"{numero:,.2f}"
    texto = texto.replace(",", "x").replace(".", ",").replace("x", ".")
    return f"{texto}€"


def construir_mapa_nomes_por_id(dataset: dict) -> dict[str, str]:
    """Cria um dicionário id -> nome usando quaisquer tabelas já carregadas."""

    def _score_coluna(coluna: str) -> tuple[int, str]:
        nome_lower = coluna.lower()
        if nome_lower in {"nome", "name"}:
            return (0, nome_lower)
        if "nome" in nome_lower:
            return (1, nome_lower)
        if "name" in nome_lower:
            return (2, nome_lower)
        if "email" in nome_lower:
            return (3, nome_lower)
        return (4, nome_lower)

    mapa: dict[str, str] = {}
    for df in dataset.values():
        if df is None or df.empty or "id" not in df.columns:
            continue

        colunas_texto: list[str] = []
        for coluna in df.columns:
            if coluna == "id":
                continue
            serie = df[coluna]
            if serie.dtype == object or serie.apply(lambda v: isinstance(v, list)).any():
                colunas_texto.append(coluna)

        if not colunas_texto:
            continue

        colunas_texto.sort(key=_score_coluna)

        for coluna in colunas_texto:
            serie = df.set_index("id")[coluna].dropna()
            if serie.empty:
                continue

            serie = serie.apply(lambda v: ", ".join(v) if isinstance(v, list) else v)
            algum_mapeado = False
            for idx, valor in serie.items():
                if not isinstance(valor, str):
                    valor = str(valor)
                valor_limpo = valor.strip()
                if not valor_limpo:
                    continue
                if idx not in mapa:
                    mapa[idx] = valor_limpo
                    algum_mapeado = True
            if algum_mapeado:
                break

    return mapa


def escolher_coluna(df: pd.DataFrame, candidatos: list[str]) -> str | None:
    if df is None or df.empty:
        return None

    colunas = list(df.columns)
    normalizados = {col.lower().strip(): col for col in colunas}
    for candidato in candidatos:
        chave = candidato.lower().strip()
        if chave in normalizados:
            return normalizados[chave]

    for candidato in candidatos:
        chave = candidato.lower().strip()
        for coluna in colunas:
            if chave in coluna.lower().strip():
                return coluna
    return None


def preparar_dataframe_estornos(
    dados: dict,
    escuteiros_map: dict[str, str],
    permissoes_map: dict[str, str],
    mapa_nomes_ids: dict[str, str],
) -> pd.DataFrame:
    possiveis_tabelas = [
        "Estorno de Recebimento",
        "Estornos de Recebimento",
        "Estorno Recebimento",
        "Estorno",
        "Estornos",
    ]
    df_origem = pd.DataFrame()
    origem_utilizada = None
    for nome in possiveis_tabelas:
        df_candidato = dados.get(nome)
        if isinstance(df_candidato, pd.DataFrame) and not df_candidato.empty:
            df_origem = df_candidato.copy()
            origem_utilizada = nome
            break

    if df_origem.empty:
        df_receb = dados.get("Recebimento", pd.DataFrame())
        if isinstance(df_receb, pd.DataFrame) and not df_receb.empty:
            df_origem = df_receb.copy()
            origem_utilizada = "Recebimento"
        else:
            return pd.DataFrame()

    df_trabalho = df_origem.copy()
    if origem_utilizada == "Recebimento":
        mask_estorno = pd.Series(False, index=df_trabalho.index)

        for coluna in ["Tipo de Movimento", "Tipo", "Categoria", "Movimento", "Motivo"]:
            if coluna in df_trabalho.columns:
                serie = df_trabalho[coluna].astype(str).str.lower()
                mask_estorno = mask_estorno | serie.str.contains("estorno", na=False)

        for coluna in ["É Estorno", "E Estorno", "Estorno?", "Estorno", "é Estorno", "é_estorno"]:
            if coluna in df_trabalho.columns:
                serie = df_trabalho[coluna]
                if serie.dtype == bool:
                    mask_estorno = mask_estorno | serie
                else:
                    serie_str = serie.astype(str).str.strip().str.lower()
                    mask_estorno = mask_estorno | serie_str.isin({"1", "true", "verdadeiro", "sim", "yes"})

        if "Valor Estornado" in df_trabalho.columns:
            valores = pd.to_numeric(df_trabalho["Valor Estornado"], errors="coerce").fillna(0).abs()
            mask_estorno = mask_estorno | (valores > 0)

        if "Valor Recebido" in df_trabalho.columns:
            valores = pd.to_numeric(df_trabalho["Valor Recebido"], errors="coerce")
            mask_estorno = mask_estorno | (valores < 0)

        df_trabalho = df_trabalho.loc[mask_estorno].copy()
        if df_trabalho.empty:
            return pd.DataFrame()

    coluna_escuteiro = escolher_coluna(df_trabalho, ["Escuteiros", "Escuteiro", "Escuteiro(s)", "Escuteiros Relacionados"])
    coluna_valor = escolher_coluna(
        df_trabalho,
        [
            "Valor Estornado",
            "Valor Estorno",
            "Valor do Estorno",
            "Valor",
            "Valor (€)",
            "Valor Recebido",
        ],
    )
    coluna_data = escolher_coluna(df_trabalho, ["Data do Estorno", "Date", "Data"])
    coluna_meio = escolher_coluna(
        df_trabalho,
        ["Meio de Pagamento", "Método de Pagamento", "Metodo de Pagamento", "Método", "Metodo"],
    )
    coluna_responsavel = escolher_coluna(
        df_trabalho,
        [
            "Quem Estornou?",
            "Quem Estornou",
            "Quem Recebeu?",
            "Registado Por",
            "Responsável",
            "Criado Por",
        ],
    )
    coluna_motivo = escolher_coluna(
        df_trabalho,
        [
            "Tag_Cancelamento",
            "Tag Cancelamento",
            "Motivo do Estorno",
            "Motivo Estorno",
            "Motivo",
            "Tag",
        ],
    )

    resultado = pd.DataFrame(index=df_trabalho.index)

    if coluna_escuteiro:
        resultado["Escuteiro"] = df_trabalho[coluna_escuteiro].apply(lambda valor: mapear_lista(valor, escuteiros_map))

    if coluna_valor:
        def _extrair_valor(valor):
            if isinstance(valor, list):
                return valor[0] if valor else None
            if isinstance(valor, dict) and "value" in valor:
                return valor["value"]
            return valor

        valores = df_trabalho[coluna_valor].apply(_extrair_valor)
        resultado["Valor (€)"] = pd.to_numeric(valores, errors="coerce").abs()

    if coluna_meio:
        resultado["Meio de Pagamento"] = df_trabalho[coluna_meio].apply(
            lambda valor: valor[0] if isinstance(valor, list) and valor else valor
        )

    if coluna_data:
        datas = df_trabalho[coluna_data].apply(lambda v: v[0] if isinstance(v, list) and v else v)
        resultado["Data"] = pd.to_datetime(datas, errors="coerce").dt.normalize()

    if coluna_responsavel:
        def _mapear_responsavel(valor):
            if permissoes_map:
                texto = mapear_lista(valor, permissoes_map)
                if texto:
                    return texto
            if mapa_nomes_ids:
                texto = mapear_lista(valor, mapa_nomes_ids)
                if texto:
                    return texto
            if escuteiros_map:
                texto = mapear_lista(valor, escuteiros_map)
                if texto:
                    return texto
            return mapear_lista(valor, {})

        resultado["Quem Estornou"] = df_trabalho[coluna_responsavel].apply(_mapear_responsavel)
    if coluna_motivo:
        resultado["Motivo do Estorno"] = df_trabalho[coluna_motivo].apply(lambda valor: mapear_lista(valor, {}))

    resultado = resultado.dropna(how="all")
    if "Valor (€)" in resultado.columns:
        resultado = resultado[resultado["Valor (€)"].notna()]

    return resultado


def preparar_dataframe_recebimentos(
    dados: dict,
) -> tuple[pd.DataFrame, dict[str, str], dict[str, str], dict[str, str]]:
    """Normaliza e enriquece a tabela de Recebimento para reutilização nas vistas."""
    df_rec = dados.get("Recebimento", pd.DataFrame())
    df_rec_limpo = pd.DataFrame()

    df_escuteiros = dados.get("Escuteiros", pd.DataFrame())
    escuteiros_map: dict[str, str] = {}
    if isinstance(df_escuteiros, pd.DataFrame) and not df_escuteiros.empty and "id" in df_escuteiros.columns:
        for coluna_nome in ("Nome do Escuteiro", "Escuteiro", "Nome"):
            if coluna_nome in df_escuteiros.columns:
                escuteiros_map = (
                    df_escuteiros.set_index("id")[coluna_nome].dropna().to_dict()
                )
                break

    if isinstance(df_rec, pd.DataFrame) and not df_rec.empty:
        colunas_uteis = ["Escuteiros", "Valor Recebido", "Meio de Pagamento", "Date", "Quem Recebeu?"]
        colunas_existentes = [c for c in colunas_uteis if c in df_rec.columns]
        df_rec_limpo = df_rec[colunas_existentes].copy()

        df_rec_limpo = df_rec_limpo.rename(columns={
            "Escuteiros": "Escuteiro",
            "Valor Recebido": "Valor (€)",
            "Meio de Pagamento": "Meio de Pagamento",
            "Date": "Data",
            "Quem Recebeu?": "Quem Recebeu",
        })

        if escuteiros_map and "Escuteiro" in df_rec_limpo.columns:
            df_rec_limpo["Escuteiro"] = df_rec_limpo["Escuteiro"].apply(
                lambda valor: mapear_lista(valor, escuteiros_map)
            )

    df_permissoes = dados.get("Permissoes", pd.DataFrame())
    permissoes_map: dict[str, str] = {}
    if isinstance(df_permissoes, pd.DataFrame) and not df_permissoes.empty:
        permissoes_map = construir_mapa_nomes_por_id({"Permissoes": df_permissoes})

    mapa_nomes_ids = construir_mapa_nomes_por_id(dados)

    if not df_rec_limpo.empty and "Quem Recebeu" in df_rec_limpo.columns:
        df_rec_original = dados.get("Recebimento", pd.DataFrame())
        candidatos_quem_recebeu = []
        if isinstance(df_rec_original, pd.DataFrame):
            candidatos_quem_recebeu = [
                col
                for col in df_rec_original.columns
                if col not in {"Quem Recebeu?", "Quem recebeu?_OLD"}
                and col.lower().startswith("quem recebeu")
            ]

        def _score_coluna(coluna: str) -> tuple[int, str]:
            nome_lower = coluna.lower()
            if "nome" in nome_lower or "name" in nome_lower:
                return (0, nome_lower)
            if "lookup" in nome_lower:
                return (1, nome_lower)
            return (2, nome_lower)

        coluna_nome_quem_recebeu = None
        if candidatos_quem_recebeu:
            candidatos_quem_recebeu.sort(key=_score_coluna)
            coluna_nome_quem_recebeu = candidatos_quem_recebeu[0]

        if coluna_nome_quem_recebeu and isinstance(df_rec_original, pd.DataFrame):
            df_rec_limpo["Quem Recebeu"] = df_rec_original[coluna_nome_quem_recebeu].apply(
                lambda valor: mapear_lista(valor, {})
            )
        elif permissoes_map:
            df_rec_limpo["Quem Recebeu"] = df_rec_limpo["Quem Recebeu"].apply(
                lambda valor: mapear_lista(valor, permissoes_map)
            )
        elif mapa_nomes_ids:
            df_rec_limpo["Quem Recebeu"] = df_rec_limpo["Quem Recebeu"].apply(
                lambda valor: mapear_lista(valor, mapa_nomes_ids)
            )
        elif escuteiros_map:
            df_rec_limpo["Quem Recebeu"] = df_rec_limpo["Quem Recebeu"].apply(
                lambda valor: mapear_lista(valor, escuteiros_map)
            )

    if not df_rec_limpo.empty and "Valor (€)" in df_rec_limpo.columns:
        df_rec_limpo["Valor (€)"] = pd.to_numeric(df_rec_limpo["Valor (€)"], errors="coerce")

    if not df_rec_limpo.empty and "Data" in df_rec_limpo.columns:
        df_rec_limpo["Data"] = pd.to_datetime(df_rec_limpo["Data"], errors="coerce").dt.normalize()

    return df_rec_limpo, escuteiros_map, permissoes_map, mapa_nomes_ids
