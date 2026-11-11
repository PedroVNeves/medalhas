"""Coletor da IMO (Olimpíada Internacional de Matemática): resultados do Brasil em imo-official.org."""
import re
import time

from ...dominio.premiacao import Premiacao
from .html import texto
from .http import baixar

URL = "https://www.imo-official.org/results/team/year/{ano}/country/BRA/"
PREMIOS = {"G": "Ouro", "S": "Prata", "B": "Bronze", "HM": "Menção Honrosa"}
PRIMEIRA_PARTICIPACAO = 1979


def ler_resultados(pagina: str) -> list[dict]:
    linhas = []
    for trecho in re.findall(r"<tr\b[^>]*>(.*?)</tr>", pagina, re.S | re.I):
        celulas = [texto(c) for c in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", trecho, re.S | re.I)]
        if len(celulas) < 5 or celulas[0] in ("Contestant", "Team Results") or celulas[0].startswith("*"):
            continue   # cabeçalho, linha da equipe e nomes não divulgados ("*")
        nome, _posicao, _percentil, premio, pontos = celulas[:5]
        linhas.append({"nome": nome, "premio": premio, "pontos": pontos})
    return linhas


def coletar(log=print) -> list[Premiacao]:
    premiacoes: list[Premiacao] = []
    for ano in range(PRIMEIRA_PARTICIPACAO, time.localtime().tm_year + 1):
        url = URL.format(ano=ano)
        pagina = baixar(url)
        if not pagina or "Contestant" not in pagina:
            continue
        for r in ler_resultados(pagina):
            premio = PREMIOS.get(r["premio"], r["premio"] or "Participação")
            if premio == "Participação":
                continue   # só premiações
            premiacoes.append({
                "competicao": "IMO", "ano": ano, "nivel": None, "nome": r["nome"], "escola": None,
                "rede": None, "esfera": None, "municipio": None,
                "uf": None,   # a IMO não publica a UF: é inferida em dominio.identidade
                "premio": premio, "medalha": premio,
                "pontos": r["pontos"] if re.fullmatch(r"\d+", r["pontos"] or "") else None,
                "fonte": url,
            })
    anos = sorted({p["ano"] for p in premiacoes})
    log(f"IMO: {len(premiacoes)} premiações, {anos[0] if anos else '-'}–{anos[-1] if anos else '-'}")
    return premiacoes
