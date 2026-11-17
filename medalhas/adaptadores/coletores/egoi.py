"""Coletor da EGOI (European Girls' Olympiad in Informatics): resultados do Brasil em stats.egoi.org.

A página do país lista, por ano, cada participante com as notas das tarefas. A medalha não vem em texto:
é a cor de fundo da linha (ouro, prata, bronze; sem cor, sem medalha).
"""
import re

from ...dominio.premiacao import BRONZE, OURO, PRATA, Premiacao
from .html import registrar_periodo, texto
from .http import baixar

URL = "https://stats.egoi.org/countries/BRA/results/"
CORES = {"#fee101": OURO, "#d7d7d7": PRATA, "#d28140": BRONZE}


def ler_resultados(pagina: str) -> list[dict]:
    """(ano, nome, medalha, pontos) de cada medalhista da página do Brasil; quem ficou sem medalha fica de fora.

    O ano só aparece na primeira linha de cada edição (rowspan) e vale para as seguintes. A nota total é a
    penúltima coluna (a última é a colocação)."""
    linhas, ano = [], None
    for trecho in re.findall(r"<tr\b[^>]*>(.*?)</tr>", pagina, re.S | re.I):
        brutas = re.findall(r"<td\b([^>]*)>(.*?)</td>", trecho, re.S | re.I)
        if not brutas:
            continue   # cabeçalho
        if re.fullmatch(r"\d{4}", texto(brutas[0][1])):   # o ano ocupa a primeira linha de cada edição
            ano = int(texto(brutas[0][1]))
            brutas = brutas[1:]
        if not ano or len(brutas) < 3:
            continue
        atributos, nome = brutas[0][0], texto(brutas[0][1])
        cor = re.search(r"background:\s*(#[0-9a-fA-F]{6})", atributos)
        medalha = CORES.get(cor.group(1).lower()) if cor else None
        if nome and medalha:
            linhas.append({"ano": ano, "nome": nome, "medalha": medalha, "pontos": texto(brutas[-2][1])})
    return linhas


def coletar(log=print) -> list[Premiacao]:
    """Medalhas do Brasil em todas as edições da EGOI. Sem a página, devolve lista vazia."""
    pagina = baixar(URL, esperado="<td") or ""
    premiacoes: list[Premiacao] = [{
        "competicao": "EGOI", "ano": r["ano"], "nivel": None, "nome": r["nome"], "escola": None, "rede": None,
        "esfera": None, "municipio": None,
        "uf": None,   # a EGOI não publica a UF: é inferida em dominio.identidade
        "premio": r["medalha"], "medalha": r["medalha"],
        "pontos": r["pontos"] if re.fullmatch(r"\d+", r["pontos"] or "") else None, "fonte": URL,
    } for r in ler_resultados(pagina)]
    registrar_periodo(log, "EGOI", premiacoes)
    return premiacoes
