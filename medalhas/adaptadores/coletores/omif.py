"""Coletor da OMIF (Olimpíada de Matemática das Instituições Federais): medalhistas em PDF, por edição.

A "Área de Imprensa" de cada edição (omif.com.br/imprensa/<ano>) aponta para os PDFs de premiados. O formato
muda de ano a ano, e a leitura vai pela posição na página (coletores.pdf):
- 2018: faixas com título ("Medalha de OURO", "Menção Honrosa") e colunas NOME | INSTITUTO - CAMPUS;
- 2020 e 2021 (1ª fase, na pandemia): um PDF por medalha, com NOME | INSTITUIÇÃO - CAMPUS;
- 2022 em diante: NOME | INSTITUIÇÃO | MEDALHA em cada linha.
2019 só publicou classificados (sem medalhas) e não houve edição em 2024 (a de 2023 terminou em 2024).
O estado sai da sigla do instituto (IFES -> ES); a cidade, do nome da escola nas outras listas.
"""
import re
import time

from ...dominio.premiacao import BRONZE, MENCAO, OURO, PRATA, Premiacao
from ...dominio.texto import normalizar
from .http import baixar, baixar_bytes
from .pdf import linhas, paginas

SITE = "https://omif.com.br"
PRIMEIRO_ANO = 2018
_PREMIOS = {"OURO": OURO, "PRATA": PRATA, "BRONZE": BRONZE, "MENCAO HONROSA": MENCAO, "MENCAO": MENCAO}
# Sigla da instituição (sem espaços e hífens) -> UF
SIGLAS = {
    "IFAC": "AC", "IFAL": "AL", "IFAM": "AM", "IFAP": "AP", "IFBA": "BA", "IFBAIANO": "BA", "IFCE": "CE",
    "IFB": "DF", "IFBRASILIA": "DF", "IFES": "ES", "IFG": "GO", "IFGOIAS": "GO", "IFGOIANO": "GO", "IFMA": "MA",
    "IFMG": "MG", "IFNMG": "MG", "IFSUDESTEMG": "MG", "IFSULDEMINAS": "MG", "IFTM": "MG", "CEFETMG": "MG",
    "IFMS": "MS", "IFMT": "MT", "IFPA": "PA", "IFPB": "PB", "IFPE": "PE", "IFSERTAOPE": "PE", "IFSERTAO": "PE",
    "IFPI": "PI", "IFPR": "PR", "IFRJ": "RJ", "IFF": "RJ", "IFFLUMINENSE": "RJ", "CEFETRJ": "RJ", "CPII": "RJ",
    "IFRN": "RN", "IFRO": "RO", "IFRR": "RR", "IFRS": "RS", "IFSUL": "RS", "IFFAR": "RS", "IFFARROUPILHA": "RS",
    "IFSC": "SC", "IFC": "SC", "IFCATARINENSE": "SC", "IFS": "SE", "IFSE": "SE", "IFSP": "SP", "IFTO": "TO",
    "IFMARANHAO": "MA", "IFMATOGROSSO": "MT", "UFRPE": "PE", "UFMG": "MG", "UFPR": "PR",
}
# "INSTITUTO FEDERAL DE SERGIPE - ITABAIANA": nome do estado por extenso
_ESTADOS = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAZONAS": "AM", "AMAPA": "AP", "BAIANO": "BA", "BAHIA": "BA", "CEARA": "CE",
    "BRASILIA": "DF", "ESPIRITO SANTO": "ES", "GOIANO": "GO", "GOIAS": "GO", "MARANHAO": "MA",
    "NORTE DE MINAS": "MG", "SUDESTE DE MINAS": "MG", "SUL DE MINAS": "MG", "TRIANGULO MINEIRO": "MG",
    "MINAS GERAIS": "MG", "MATO GROSSO DO SUL": "MS", "MATO GROSSO": "MT", "PARAIBA": "PB", "PARANA": "PR",
    "PARA": "PA", "PERNAMBUCO": "PE", "SERTAO PERNAMBUCANO": "PE", "PIAUI": "PI", "FLUMINENSE": "RJ",
    "RIO DE JANEIRO": "RJ", "RIO GRANDE DO NORTE": "RN", "RONDONIA": "RO", "RORAIMA": "RR", "FARROUPILHA": "RS",
    "SUL RIO GRANDENSE": "RS", "RIO GRANDE DO SUL": "RS", "CATARINENSE": "SC", "SANTA CATARINA": "SC",
    "SERGIPE": "SE", "SAO PAULO": "SP", "TOCANTINS": "TO", "PEDRO II": "RJ", "MATO DE GROSSO": "MT",
}
# onde começa a instituição quando o PDF junta "Nome do Aluno IFES - CAMPUS X" num trecho só
_INICIO_INSTITUICAO = re.compile(r"\s((?:IF|CEFET|CPII|UF)[A-Z]*\b.*"
                                 r"|(?:Instituto|INSTITUTO) Federal.*"
                                 r"|(?:Col[eé]gio|COL[EÉ]GIO) Pedro II.*)$")


def uf_da_instituicao(instituicao: str) -> str | None:
    """'IFES - CAMPUS VITORIA' -> 'ES'; 'IF Sudeste MG - Campus Muriaé' -> 'MG'; None se não reconhece."""
    sigla = re.sub(r"[^A-Z]", "", normalizar(re.split(r"\s+-\s*|\s*-\s+|\s+campus\b", instituicao, flags=re.I)[0]))
    if sigla in SIGLAS:
        return SIGLAS[sigla]
    texto = f" {normalizar(instituicao)} "
    return next((uf for nome, uf in sorted(_ESTADOS.items(), key=lambda e: -len(e[0]))
                 if f" {nome} " in texto), None)


def _premio(texto: str) -> str | None:
    t = normalizar(texto)
    t = re.sub(r"^MEDALHA DE ", "", t)
    return _PREMIOS.get(t)


def ler_pdf(paginas_do_pdf, premio_do_arquivo: str | None = None) -> list[dict]:
    """(nome, instituição, prêmio) de cada premiado do PDF."""
    registros, premio = [], premio_do_arquivo
    for pagina in paginas_do_pdf:
        for _, linha in linhas(pagina):
            textos = [t for _, t in linha]
            titulo = _premio(" ".join(textos))
            if titulo:
                premio = titulo
                continue
            if len(textos) < 2 or normalizar(textos[0]).startswith("NOME"):
                continue   # título, cabeçalho ou rodapé
            ultimo = _premio(textos[-1])
            if ultimo and len(textos) == 2:   # nome e instituição num trecho só
                junto = _INICIO_INSTITUICAO.search(textos[0])
                if junto:
                    textos = [textos[0][:junto.start()], junto.group(1), textos[1]]
            instituicao = " - ".join(textos[1:-1] if ultimo else textos[1:])
            if (ultimo or premio) and instituicao:
                registros.append({"nome": re.sub(r"\s+", " ", textos[0]).strip(), "instituicao": instituicao,
                                  "premio": ultimo or premio})
    return registros


def _pdfs_da_edicao(ano: int) -> list[tuple[str, str | None]]:
    """(url, prêmio do arquivo) dos PDFs de premiados listados na página de imprensa da edição."""
    pagina = baixar(f"{SITE}/imprensa/{ano}") or ""
    vistos, pdfs = set(), []
    for href in re.findall(r'href="([^"]+\.pdf)"', pagina, re.I):
        nome = href.rsplit("/", 1)[-1].lower()
        if not re.search(r"medalh|resultado_final|premiacao", nome) or "campus" in nome or "classif" in nome:
            continue
        url = href if href.startswith("http") else SITE + "/" + href.lstrip("/")
        if url.lower() in vistos:
            continue
        vistos.add(url.lower())
        premio = next((p for chave, p in (("ouro", OURO), ("prata", PRATA), ("bronze", BRONZE), ("mencao", MENCAO))
                       if chave in nome), None)
        pdfs.append((url, premio))
    return pdfs


def coletar(log=print) -> list[Premiacao]:
    premiacoes: list[Premiacao] = []
    for ano in range(PRIMEIRO_ANO, time.localtime().tm_year + 1):
        for url, premio in _pdfs_da_edicao(ano):
            conteudo = baixar_bytes(url)
            if not conteudo:
                continue
            for r in ler_pdf(paginas(conteudo), premio):
                premiacoes.append({
                    "competicao": "OMIF", "ano": ano, "nivel": None, "nome": r["nome"], "escola": r["instituicao"],
                    "rede": "Pública", "esfera": "Federal", "municipio": None,
                    "uf": uf_da_instituicao(r["instituicao"]),
                    "premio": r["premio"], "medalha": r["premio"], "pontos": None, "fonte": url,
                })
    anos = sorted({p["ano"] for p in premiacoes})
    log(f"OMIF: {len(premiacoes)} premiações, {anos[0] if anos else '-'}–{anos[-1] if anos else '-'}")
    return premiacoes
