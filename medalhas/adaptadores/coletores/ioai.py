"""Coletor da IOAI (International Olympiad in Artificial Intelligence): brasileiros nas tabelas de resultados.

O menu de ioai-official.org lista a página de resultados de cada edição ("2025 Results", "Results 2026"…),
com a tabela individual (nome, país ou equipe, notas e prêmio). A página de 2024 (Bulgária) só tem
resultados por equipe e não traz brasileiros nos certificados individuais: a leitura dela não acha ninguém.
"""
import re

from ...dominio.premiacao import BRONZE, MENCAO, OURO, PRATA, Premiacao
from .html import texto
from .http import baixar

SITE = "https://ioai-official.org/"
PREMIOS = {"gold": OURO, "silver": PRATA, "bronze": BRONZE, "honourable mention": MENCAO,
           "honorable mention": MENCAO}


def ler_resultados(pagina: str) -> list[dict]:
    linhas, colunas = [], None
    for trecho in re.findall(r"<tr\b[^>]*>(.*?)</tr>", pagina, re.S | re.I):
        celulas = [texto(c) for c in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", trecho, re.S | re.I)]
        chaves = [c.lower() for c in celulas]
        if "name" in chaves:
            colunas = {"nome": chaves.index("name"),
                       "pais": next(i for i, c in enumerate(chaves) if c in ("team", "country or region")),
                       "premio": next(i for i, c in enumerate(chaves) if c in ("award", "medal")),
                       "pontos": next((i for i, c in enumerate(chaves) if "total" in c), None)}
            continue
        if not colunas or len(celulas) <= colunas["premio"]:
            continue
        if not re.match(r"brazil\b", celulas[colunas["pais"]], re.I):
            continue
        # "Gold + 1st Place 🏆": vale o metal
        premio = next((v for k, v in PREMIOS.items() if celulas[colunas["premio"]].lower().startswith(k)), None)
        if premio:
            pontos = celulas[colunas["pontos"]] if colunas["pontos"] is not None else None
            linhas.append({"nome": celulas[colunas["nome"]], "medalha": premio, "pontos": pontos})
    return linhas


def edicoes() -> dict[int, str]:
    """Ano -> página de resultados, a partir dos links do menu do site (o ano está no endereço)."""
    pagina = baixar(SITE) or ""
    achadas = {}
    for url in re.findall(r"""href=["'](https://ioai-official\.org/[^"']*results?[^"']*)["']""", pagina, re.I):
        ano = re.search(r"(20\d{2})", url)
        if ano:
            achadas.setdefault(int(ano.group(1)), url)
    return dict(sorted(achadas.items()))


def coletar(log=print) -> list[Premiacao]:
    premiacoes: list[Premiacao] = []
    for ano, url in edicoes().items():
        for r in ler_resultados(baixar(url) or ""):
            premiacoes.append({
                "competicao": "IOAI", "ano": ano, "nivel": None, "nome": r["nome"], "escola": None, "rede": None,
                "esfera": None, "municipio": None,
                "uf": None,   # a IOAI não publica a UF: é inferida em dominio.identidade
                "premio": r["medalha"], "medalha": r["medalha"],
                "pontos": r["pontos"].replace(",", ".") if r["pontos"] else None, "fonte": url,
            })
    anos = sorted({p["ano"] for p in premiacoes})
    log(f"IOAI: {len(premiacoes)} premiações, {anos[0] if anos else '-'}–{anos[-1] if anos else '-'}")
    return premiacoes
