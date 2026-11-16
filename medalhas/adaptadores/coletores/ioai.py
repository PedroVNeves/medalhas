"""Coletor da IOAI (International Olympiad in Artificial Intelligence): brasileiros nas tabelas de resultados.

Cada edição tem uma página de resultados em ioai-official.org com a tabela individual (nome, país ou equipe,
notas e prêmio). A edição de 2024 (Bulgária) só publicou resultados por equipe, sem nomes, e fica de fora.
"""
import re

from ...dominio.premiacao import BRONZE, MENCAO, OURO, PRATA, Premiacao
from .html import texto
from .http import baixar

EDICOES = {
    2025: "https://ioai-official.org/china-2025/results-2025/",
    2026: "https://ioai-official.org/republic-of-kazakhstan/results-2026/",
}
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


def coletar(log=print) -> list[Premiacao]:
    premiacoes: list[Premiacao] = []
    for ano, url in EDICOES.items():
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
