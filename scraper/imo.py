"""Resultados do Brasil na IMO (Olimpíada Internacional de Matemática), do site oficial imo-official.org."""
import re
import time

from .common import clean, fetch

URL = "https://www.imo-official.org/results/team/year/{ano}/country/BRA/"
PREMIOS = {"G": "Ouro", "S": "Prata", "B": "Bronze", "HM": "Menção Honrosa"}
PRIMEIRA_PARTICIPACAO = 1979


def parse(text: str) -> list[dict]:
    rows = []
    for chunk in re.findall(r"<tr\b[^>]*>(.*?)</tr>", text, re.S | re.I):
        cells = [clean(c) for c in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", chunk, re.S | re.I)]
        if len(cells) < 5 or cells[0] in ("Contestant", "Team Results") or cells[0].startswith("*"):
            continue  # cabeçalho, linha de equipe e nomes não divulgados ("*")
        nome, _rank, _pct, award, pontos = cells[:5]
        rows.append({"nome": nome, "award": award, "pontos": pontos})
    return rows


def scrape(log=print) -> list[dict]:
    out = []
    for ano in range(PRIMEIRA_PARTICIPACAO, time.localtime().tm_year + 1):
        url = URL.format(ano=ano)
        text = fetch(url)
        if not text or "Contestant" not in text:
            continue
        for r in parse(text):
            premio = PREMIOS.get(r["award"], r["award"] or "Participação")
            if premio == "Participação":
                continue  # só premiações
            out.append({
                "competicao": "IMO", "ano": ano, "nivel": None, "nome": r["nome"], "escola": None,
                "rede": None, "esfera": None, "municipio": None, "uf": None,  # UF é inferida no build
                "premio": premio, "medalha": premio,
                "pontos": r["pontos"] if re.fullmatch(r"\d+", r["pontos"] or "") else None,
                "fonte": url,
            })
    anos = sorted({r["ano"] for r in out})
    log(f"IMO: {len(out)} premiações, {anos[0] if anos else '-'}–{anos[-1] if anos else '-'}")
    return out
