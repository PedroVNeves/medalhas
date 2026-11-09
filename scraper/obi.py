"""Medalhistas da OBI (Olimpíada Brasileira de Informática), do "Quadro de Medalhas" de cada edição.

Cada edição (olimpiada.ic.unicamp.br/passadas/OBIAAAA/) lista links para o quadro de cada modalidade
(qmerito/i1, i2, ij, p1, p2, pj, ps, pu…). A medalha vem da imagem medalhinha_<ouro|prata|bronze>.gif;
"HM" é Honra ao Mérito.
"""
import re

from .common import clean, fetch

BASE = "https://olimpiada.ic.unicamp.br"
HEADERS = {
    "nome": "nome", "escola": "escola", "cidade": "municipio", "estado": "uf",
    "pontos": "pontos", "nota": "pontos", "nota1": "pontos",
}


def edicoes() -> list[tuple[int, str]]:
    page = fetch(f"{BASE}/passadas/") or ""
    return sorted({(int(a), f"{BASE}/passadas/OBI{a}/") for a in re.findall(r'href="/passadas/OBI(\d{4})/"', page)})


# código da página -> nome do nível (os títulos das páginas antigas nem sempre trazem o nome)
NIVEIS = {
    "i1": "Iniciação Nível 1", "i2": "Iniciação Nível 2", "ij": "Iniciação Nível Júnior",
    "p0": "Programação", "p1": "Programação Nível 1", "p2": "Programação Nível 2",
    "pj": "Programação Nível Júnior", "ps": "Programação Nível Sênior", "pu": "Programação Nível Universitário",
}


def nivel_da_pagina(text: str, codigo: str) -> str:
    if codigo.lower() in NIVEIS:
        return NIVEIS[codigo.lower()]
    m = re.search(r"<h2[^>]*>(.*?)</h2>", text, re.S | re.I)
    m = re.search(r"Modalidade\s+(.+)$", clean(m.group(1)) if m else "")
    return m.group(1).strip() if m else codigo.upper()


def parse(text: str) -> list[dict]:
    rows, columns = [], None
    for chunk in re.findall(r"<tr\b[^>]*>(.*?)</tr>", text, re.S | re.I):
        raw = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", chunk, re.S | re.I)
        cells = [clean(c) for c in raw]
        lowered = [re.sub(r"[^a-z0-9]", "", c.lower()) for c in cells]
        if "nome" in lowered:
            columns = [HEADERS.get(c) for c in lowered]
            continue
        if not columns or not raw:
            continue
        img = re.search(r"medalhinha_(ouro|prata|bronze)", raw[0], re.I)
        medalha = img.group(1).capitalize() if img else ("Menção Honrosa" if cells[0].upper() == "HM" else None)
        if not medalha:
            continue
        # a coluna da medalha não tem cabeçalho próprio em todos os anos: alinha pelo fim da linha
        offset = len(cells) - len(columns)
        rec = {col: cells[i + offset] for i, col in enumerate(columns) if col and 0 <= i + offset < len(cells)}
        if rec.get("nome"):
            rec["medalha"] = medalha
            rows.append(rec)
    return rows


def scrape(log=print) -> list[dict]:
    out = []
    for ano, url in edicoes():
        page = fetch(url) or ""
        codigos = sorted(set(re.findall(rf'href="/passadas/OBI{ano}/qmerito/(\w+)/"', page)))
        for codigo in codigos:
            qurl = f"{BASE}/passadas/OBI{ano}/qmerito/{codigo}/"
            text = fetch(qurl)
            if not text:
                continue
            nivel = nivel_da_pagina(text, codigo)
            for r in parse(text):
                premio = "Honra ao Mérito" if r["medalha"] == "Menção Honrosa" else r["medalha"]
                uf = (r.get("uf") or "").strip().upper()
                out.append({
                    "competicao": "OBI", "ano": ano, "nivel": nivel, "nome": r["nome"],
                    "escola": r.get("escola") or None, "rede": None, "esfera": None,
                    "municipio": r.get("municipio") or None, "uf": uf if re.fullmatch(r"[A-Z]{2}", uf) else None,
                    "premio": premio, "medalha": r["medalha"],
                    "pontos": r.get("pontos") if re.fullmatch(r"[\d.,]+", r.get("pontos") or "") else None,
                    "fonte": qurl,
                })
    anos = sorted({r["ano"] for r in out})
    log(f"OBI: {len(out)} premiações, {anos[0] if anos else '-'}–{anos[-1] if anos else '-'}")
    return out
