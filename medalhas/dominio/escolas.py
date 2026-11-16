"""Identidade de escolas: abreviações, siglas (IFAL, ETEC, EE…) e a chave que agrupa grafias diferentes.

Tudo aqui opera sobre texto normalizado (sem acento, maiúsculo; ver texto.normalizar) e vale tanto
para os dados quanto para o que o usuário digita na busca.
"""
import re

from .texto import normalizar

PARTICULAS = {"DE", "DA", "DO", "DAS", "DOS", "E", "D"}
# Palavras ignoradas na chave de institutos e centros federais (cada edição escreve de um jeito)
_ENCHIMENTO_FEDERAL = {"EDUCACAO", "CIENCIA", "TECNOLOGIA", "CAMPUS", "UNIDADE", "AVANCADO"}

# Escolas que mudaram de nome: a chave do nome antigo passa a ser a do atual, e as premiações das duas épocas
# ficam numa página só. Mantida à mão, a pedido (correções chegam pelo contato do site).
ESCOLAS_RENOMEADAS: dict[str, str] = {
    # o CEFET-ES virou o Ifes em 2008 (Lei 11.892); a sede do CEFET em Vitória é o Ifes - Campus Vitória
    "CENTRO ESPIRITO FEDERAL SANTO TECNOLOGICA|VITORIA|ES": "ESPIRITO FEDERAL INSTITUTO SANTO VITORIA|VITORIA|ES",
    # o Instituto de Tecnologia ORT, no Rio, hoje se chama Escola ORT
    "INSTITUTO ORT TECNOLOGIA|RIO DE JANEIRO|RJ": "ESCOLA ORT|RIO DE JANEIRO|RJ",
}

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

# Sigla de tipo de escola -> expansão
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

Expansao = list[tuple[str, list[str]]]   # [(palavra digitada, palavras que ela representa)]


def _juntar_letras_soltas(palavras: list[str]) -> list[str]:
    """Siglas escritas com espaços viram uma palavra só: 'E E E F ABEL' -> 'EEEF ABEL'."""
    saida, sequencia = [], []
    for p in palavras + [""]:
        if len(p) == 1 and p.isalpha():
            sequencia.append(p)
            continue
        if len(sequencia) >= 2:
            saida.append("".join(sequencia))
        else:
            saida.extend(sequencia)
        sequencia = []
        if p:
            saida.append(p)
    return saida


def expandir_palavra(palavra: str) -> list[str]:
    """Expande uma sigla ou abreviação. Sem expansão conhecida, devolve [palavra]."""
    if palavra in SIGLAS:
        return SIGLAS[palavra].split()
    if palavra in ABREVIACOES:
        return ABREVIACOES[palavra].split()
    return [palavra]


def _expandir(palavras: list[str]) -> Expansao:
    pares = [(p, expandir_palavra(p)) for p in palavras]
    # em nomes de instituto/centro federal, a UF ("DO RN", "DE PE") vira o nome do estado
    if any("FEDERAL" in exp for _, exp in pares):
        pares = [(p, UF_NOMES[p].split() if p in UF_NOMES else exp) for p, exp in pares]
    return pares


def palavras_canonicas(normalizado: str) -> list[str]:
    """Palavras expandidas e sem partículas de um texto já normalizado."""
    palavras = [p for p in _juntar_letras_soltas(normalizado.split()) if p not in PARTICULAS]
    return [w for _, exp in _expandir(palavras) for w in exp if w not in PARTICULAS]


def palavras_da_chave(escola: str | None) -> set[str]:
    """Palavras que identificam a escola (sem acento, expandidas, sem partículas), a parte do nome na chave."""
    palavras = set(palavras_canonicas(normalizar(escola)))
    if "FEDERAL" in palavras:
        palavras -= _ENCHIMENTO_FEDERAL
    return palavras


def indexar_escola(escola: str | None, municipio: str | None, uf: str | None) -> tuple[str, str]:
    """(termos de busca, chave da escola).

    termos: palavras originais e expandidas, entre espaços, para busca por início de palavra.
    chave:  identifica a mesma escola apesar de acentos, ordem das palavras e abreviações, ex.:
            'IFAL CAMPUS X' == 'INSTITUTO FEDERAL DE EDUCACAO CIENCIA E TECNOLOGIA DE ALAGOAS CAMPUS X'.
            Sem UF (listas que não informam o estado) não há chave: o mesmo nome em estados diferentes é
            outra escola, então a premiação fica sem página de escola (o nome continua na premiação).
    """
    if not escola:
        return "", ""
    norm = normalizar(escola)
    canon = palavras_canonicas(norm)
    termos = " " + " ".join(dict.fromkeys(_juntar_letras_soltas(norm.split()) + canon)) + " "
    if not uf:
        return termos, ""
    chave = " ".join(sorted(palavras_da_chave(escola))) + "|" + normalizar(municipio) + "|" + uf
    if chave in ESCOLAS_RENOMEADAS:
        chave = ESCOLAS_RENOMEADAS[chave]
        # buscar pelo nome atual também acha as premiações do nome antigo
        novas = [w for w in chave.split("|")[0].split() if f" {w} " not in termos]
        termos += " ".join(novas) + " " if novas else ""
    return termos, chave


def completar_municipios(premiacoes: list[dict]) -> int:
    """Cidade das escolas que vieram sem ela (a OBQ publica só nome e estado). Altera a lista.

    Se o mesmo nome de escola (as palavras da chave) aparece numa única cidade daquele estado nas outras
    listas, a premiação adota essa cidade e cai na mesma escola. Senão, se o nome traz o campus e ele é uma
    cidade conhecida do estado ("IFES - CAMPUS VITORIA"), adota essa cidade. Sem isso, fica sem cidade.
    Devolve quantas premiações ganharam cidade.
    """
    cidades: dict[tuple[str, str], dict[str, str]] = {}
    do_estado: dict[str, dict[str, str]] = {}   # UF -> cidade normalizada -> grafia
    for p in premiacoes:
        if p.get("municipio") and p.get("uf"):
            do_estado.setdefault(p["uf"], {}).setdefault(normalizar(p["municipio"]), p["municipio"])
            if p.get("escola"):
                palavras = indexar_escola(p["escola"], p["municipio"], p["uf"])[1].split("|")[0]
                cidades.setdefault((palavras, p["uf"]), {}).setdefault(normalizar(p["municipio"]), p["municipio"])
    completadas = 0
    for p in premiacoes:
        if p.get("escola") and not p.get("municipio") and p.get("uf"):
            achadas = cidades.get((indexar_escola(p["escola"], None, p["uf"])[1].split("|")[0], p["uf"]), {})
            campus = re.search(r"(?:CAMPUS|UNED|UNIDADE)\s+(?:AVANCADO\s+)?(.+)$|\s-\s+([^-]+)$", normalizar(p["escola"]))
            cidade_do_campus = (campus.group(1) or campus.group(2)).strip() if campus else ""
            if len(achadas) == 1:
                p["municipio"] = next(iter(achadas.values()))
            elif cidade_do_campus in do_estado.get(p["uf"], {}):
                p["municipio"] = do_estado[p["uf"]][cidade_do_campus]
            else:
                continue
            completadas += 1
    return completadas


def palavras_da_busca(texto: str) -> Expansao:
    """O que o usuário digitou, palavra a palavra, com a expansão de cada uma (partículas descartadas)."""
    palavras = [p for p in _juntar_letras_soltas(normalizar(texto).split()) if p not in PARTICULAS]
    return _expandir(palavras)


# ---------------------------------------------------------------- nome de exibição

# Palavras que continuam em maiúsculas (siglas e algarismos romanos). Cópia de KEEP_UPPER em web/js/util.js.
_SIGLAS_EXIBICAO = re.compile(
    r"^(I{1,3}|IV|V|VI{0,3}|IX|X|[A-Z]{1,2}|EE|EM|EMEF|EMEB|EMEIEF|EMEIF|EEEF|EEEFM|EEFM|EEF|EEM|EEEM|EEB|EEEP|"
    r"EEPSG|ETEC|ETE|CEFET\w*|IF\w{0,10}|CEF|CEM|CED|CIEP|SESI|SENAI|SESC|UNICAMP|USP|UFMG|UFRJ|UFC|UFPE|UTFPR|"
    r"EFM|EF|EI|LTDA|CMB|CMF|CMRJ|CAP|COC|ETAPA)$")
_MINUSCULAS_EXIBICAO = {"DE", "DA", "DO", "DAS", "DOS", "E", "EM", "NA", "NO", "NAS", "NOS"}


def nome_de_exibicao(nome: str | None) -> str:
    """Nome de escola em caixa alta para a forma de exibição (igual a prettySchool em web/js/util.js).

    >>> nome_de_exibicao("MILITAR DE FORTALEZA, COLEGIO")
    'Colegio Militar de Fortaleza'
    >>> nome_de_exibicao("EE PROF JOSE DA SILVA")
    'EE Prof Jose da Silva'
    """
    if not nome:
        return ""
    s = nome.strip()
    invertido = re.match(r"^(.*),\s*([^,]{2,40})$", s)
    if invertido:
        s = f"{invertido[2]} {invertido[1]}"
    if s != s.upper():   # já está em caixa mista
        return s
    partes = re.split(r"(\s+|-|/)", s)
    saida = []
    for i, w in enumerate(partes):
        if not any(c.isalpha() for c in w):
            saida.append(w)
            continue
        maiuscula = w.upper()
        if i > 0 and maiuscula in _MINUSCULAS_EXIBICAO:
            saida.append(w.lower())
        elif _SIGLAS_EXIBICAO.match(maiuscula.replace(".", "")):
            saida.append(maiuscula)
        else:
            saida.append(w[:1] + w[1:].lower())
    return "".join(saida)
