"""Canonicalização de nomes de escola: abreviações, siglas (IFAL, ETEC, EE…) e chave de agrupamento.

Tudo aqui opera sobre texto já normalizado (sem acento, maiúsculo — ver common.normalize),
e é aplicado tanto aos dados quanto ao texto digitado na busca.
"""
import re

from .common import normalize

STOPWORDS = {"DE", "DA", "DO", "DAS", "DOS", "E", "D"}
# Palavras ignoradas na chave de agrupamento de institutos/centros federais
FEDERAL_FILLER = {"EDUCACAO", "CIENCIA", "TECNOLOGIA", "CAMPUS", "UNIDADE", "AVANCADO"}

UF_NOMES = {
    "AC": "ACRE", "AL": "ALAGOAS", "AM": "AMAZONAS", "AP": "AMAPA", "BA": "BAHIA", "CE": "CEARA",
    "DF": "DISTRITO FEDERAL", "ES": "ESPIRITO SANTO", "GO": "GOIAS", "MA": "MARANHAO",
    "MG": "MINAS GERAIS", "MS": "MATO GROSSO SUL", "MT": "MATO GROSSO", "PA": "PARA",
    "PB": "PARAIBA", "PE": "PERNAMBUCO", "PI": "PIAUI", "PR": "PARANA", "RJ": "RIO JANEIRO",
    "RN": "RIO GRANDE NORTE", "RO": "RONDONIA", "RR": "RORAIMA", "RS": "RIO GRANDE SUL",
    "SC": "SANTA CATARINA", "SE": "SERGIPE", "SP": "SAO PAULO", "TO": "TOCANTINS",
}

# Palavra abreviada -> palavra completa
ABREVIACOES = {
    "ESC": "ESCOLA", "EST": "ESTADUAL", "ESTAD": "ESTADUAL", "MUN": "MUNICIPAL", "MUL": "MUNICIPAL",
    "MUNIC": "MUNICIPAL", "COL": "COLEGIO", "ENS": "ENSINO", "FUND": "FUNDAMENTAL",
    "FUN": "FUNDAMENTAL", "MED": "MEDIO", "INST": "INSTITUTO", "FED": "FEDERAL",
    "EDUC": "EDUCACAO", "EDUCAC": "EDUCACAO", "CIENC": "CIENCIA", "TECNOL": "TECNOLOGIA",
    "BAS": "BASICA", "INF": "INFANTIL", "UNID": "UNIDADE", "GR": "GRUPO",
    "PROF": "PROFESSOR", "PROFA": "PROFESSOR", "PROFO": "PROFESSOR", "PROFESSORA": "PROFESSOR",
    "DR": "DOUTOR", "DRA": "DOUTOR", "DOUTORA": "DOUTOR", "CEL": "CORONEL", "DEP": "DEPUTADO",
    "PRES": "PRESIDENTE", "GOV": "GOVERNADOR", "PREF": "PREFEITO", "MONS": "MONSENHOR",
    "SEN": "SENADOR", "GAL": "GENERAL", "GEN": "GENERAL", "MAL": "MARECHAL", "VER": "VEREADOR",
    "PDE": "PADRE", "PE": "PADRE", "ALM": "ALMIRANTE", "CONS": "CONSELHEIRO",
    "DES": "DESEMBARGADOR", "ENG": "ENGENHEIRO", "MIN": "MINISTRO", "STA": "SANTA",
    "STO": "SANTO", "NSA": "NOSSA SENHORA", "NS": "NOSSA SENHORA", "SRA": "SENHORA",
    "PROFISS": "PROFISSIONAL", "TECN": "TECNICA", "INTEGR": "INTEGRAL",
}

# Siglas de tipo de escola -> expansão
SIGLAS = {
    "EE": "ESCOLA ESTADUAL",
    "EM": "ESCOLA MUNICIPAL",
    "EEF": "ESCOLA ESTADUAL ENSINO FUNDAMENTAL",
    "EEEF": "ESCOLA ESTADUAL ENSINO FUNDAMENTAL",
    "EEM": "ESCOLA ESTADUAL ENSINO MEDIO",
    "EEEM": "ESCOLA ESTADUAL ENSINO MEDIO",
    "EEFM": "ESCOLA ESTADUAL ENSINO FUNDAMENTAL MEDIO",
    "EEEFM": "ESCOLA ESTADUAL ENSINO FUNDAMENTAL MEDIO",
    "EEIEF": "ESCOLA ESTADUAL EDUCACAO INFANTIL ENSINO FUNDAMENTAL",
    "EEB": "ESCOLA EDUCACAO BASICA",
    "EEEP": "ESCOLA ESTADUAL EDUCACAO PROFISSIONAL",
    "EEPSG": "ESCOLA ESTADUAL PRIMEIRO SEGUNDO GRAU",
    "EMEF": "ESCOLA MUNICIPAL ENSINO FUNDAMENTAL",
    "EMEB": "ESCOLA MUNICIPAL EDUCACAO BASICA",
    "EMEIEF": "ESCOLA MUNICIPAL EDUCACAO INFANTIL ENSINO FUNDAMENTAL",
    "EMEIF": "ESCOLA MUNICIPAL EDUCACAO INFANTIL ENSINO FUNDAMENTAL",
    "EMPG": "ESCOLA MUNICIPAL PRIMEIRO GRAU",
    "ETEC": "ESCOLA TECNICA ESTADUAL",
    "ETE": "ESCOLA TECNICA ESTADUAL",
    "EETEPA": "ESCOLA ESTADUAL TECNICA PARA",
    "CEF": "CENTRO ENSINO FUNDAMENTAL",
    "CEM": "CENTRO ENSINO MEDIO",
    "CED": "CENTRO EDUCACIONAL",
    "CEFET": "CENTRO FEDERAL EDUCACAO TECNOLOGICA",
    "CIEP": "CENTRO INTEGRADO EDUCACAO PUBLICA",
    "SESI": "SERVICO SOCIAL INDUSTRIA",
    "SENAI": "SERVICO NACIONAL APRENDIZAGEM INDUSTRIAL",
    "IF": "INSTITUTO FEDERAL",
    "IFB": "INSTITUTO FEDERAL BRASILIA",
    "IFC": "INSTITUTO FEDERAL CATARINENSE",
    "IFS": "INSTITUTO FEDERAL SERGIPE",
    "IFG": "INSTITUTO FEDERAL GOIAS",
    "IFF": "INSTITUTO FEDERAL FLUMINENSE",
    "IFFAR": "INSTITUTO FEDERAL FARROUPILHA",
    "IFSUL": "INSTITUTO FEDERAL SUL RIO GRANDENSE",
    "IFBAIANO": "INSTITUTO FEDERAL BAIANO",
    "IFGOIANO": "INSTITUTO FEDERAL GOIANO",
    "IFNMG": "INSTITUTO FEDERAL NORTE MINAS GERAIS",
    "IFTM": "INSTITUTO FEDERAL TRIANGULO MINEIRO",
    "IFSULDEMINAS": "INSTITUTO FEDERAL SUL MINAS GERAIS",
    "IFSUDESTEMG": "INSTITUTO FEDERAL SUDESTE MINAS GERAIS",
    "IFSERTAOPE": "INSTITUTO FEDERAL SERTAO PERNAMBUCANO",
}
for _uf, _nome in UF_NOMES.items():
    SIGLAS.setdefault(f"IF{_uf}", f"INSTITUTO FEDERAL {_nome}")
    SIGLAS.setdefault(f"CEFET{_uf}", f"CENTRO FEDERAL EDUCACAO TECNOLOGICA {_nome}")


def _collapse_letters(tokens: list[str]) -> list[str]:
    """'E E E F ABEL' -> 'EEEF ABEL' (siglas escritas com espaços)."""
    out, run = [], []
    for t in tokens + [""]:
        if len(t) == 1 and t.isalpha():
            run.append(t)
            continue
        if len(run) >= 2:
            out.append("".join(run))
        else:
            out.extend(run)
        run = []
        if t:
            out.append(t)
    return out


def expand_token(tok: str) -> list[str]:
    """Expande uma única palavra (abreviação ou sigla). Retorna [tok] se não houver expansão."""
    if tok in SIGLAS:
        return SIGLAS[tok].split()
    if tok in ABREVIACOES:
        return ABREVIACOES[tok].split()
    return [tok]


def canon_tokens(normalized: str) -> list[str]:
    """Tokens canônicos (expandidos, sem stopwords) de um texto já normalizado."""
    tokens = [t for t in _collapse_letters(normalized.split()) if t not in STOPWORDS]
    return [w for _, exp in _expand_all(tokens) for w in exp if w not in STOPWORDS]


def _expand_all(tokens: list[str]) -> list[tuple[str, list[str]]]:
    pairs = [(t, expand_token(t)) for t in tokens]
    # Em nomes de instituto/centro federal, siglas de UF ('DO RN', 'DE PE') viram o nome do estado
    if any("FEDERAL" in exp for _, exp in pairs):
        pairs = [(t, UF_NOMES[t].split() if t in UF_NOMES else exp) for t, exp in pairs]
    return pairs


def school_fields(escola: str | None, municipio: str | None, uf: str | None) -> tuple[str, str]:
    """Retorna (escola_termos, escola_chave).

    escola_termos: texto pesquisável com palavras originais + expandidas.
    escola_chave:  identifica a mesma escola mesmo com acento/ordem/abreviação diferentes.
    """
    if not escola:
        return "", ""
    norm = normalize(escola)
    canon = canon_tokens(norm)
    termos = " " + " ".join(dict.fromkeys(_collapse_letters(norm.split()) + canon)) + " "
    key_tokens = set(canon)
    if "FEDERAL" in key_tokens:  # 'IFAL CAMPUS X' == 'INSTITUTO FEDERAL DE EDUCACAO CIENCIA E TECNOLOGIA DE ALAGOAS CAMPUS X'
        key_tokens -= FEDERAL_FILLER
    chave = " ".join(sorted(key_tokens)) + "|" + normalize(municipio or "") + "|" + (uf or "")
    return termos, chave


def query_tokens(q: str) -> list[tuple[str, list[str]]]:
    """Para cada palavra digitada: (palavra, expansão). Stopwords são descartadas."""
    tokens = [t for t in _collapse_letters(normalize(q).split()) if t not in STOPWORDS]
    return _expand_all(tokens)
