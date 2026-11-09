"""Resultados do Brasil em competições internacionais, publicados pela OBM.

Cada competição tem uma página "Resultados" com uma tabela por edição (ex.: "41ª OIM, Buenos Aires (2026)")
no formato Nome | Cidade – Estado | [Pontos] | Prêmio. Um único parser serve para todas.
"""
import re

from .common import clean, fetch
from .obm import HEADER_MAP, detect_level, medal_category, split_city

BASE = "https://www.obm.org.br"

# sigla -> (página de resultados, nível fixo da competição, se houver)
COMPETICOES = {
    "OIM": ("resultados-do-brasil-olimpiada-ibero-americana-de-matematica", None),
    "CONESUL": ("resultados-olimpiada-de-matematica-do-cone-sul", None),
    "EGMO": ("resultados-european-girls-mathematical-olympiad", None),
    "APMO": ("resultados-apmo", None),
    "PAGMO": ("resultados-pagmo", None),
    "MAIO": ("resultados-olimpiada-de-maio", None),
    "OMCPLP": ("resultados-omcplp", None),
    "IGO": ("resultados-olimpiada-iraniana-de-geometria-igo", None),
    "OMOP": ("resultados-omop", None),
    "IMSC": ("resultados-international-mathematical-summer-camp", None),
    "GALOIS": ("resultados-concurso-galois-noether", None),
    "IMC": ("resultados-imc", "Universitário"),
    "OIMU": ("resultados-oimu", "Universitário"),
    "CIIM": ("resultados-ciim", "Universitário"),
}

EXTRA_HEADERS = {
    "participante": "nome",
    "cidade-estado": "cidade",
    "cidade – estado": "cidade",
    "instituição": "escola",
    "instituicao": "escola",
    "universidade": "escola",
}


def _year(text: str) -> int | None:
    anos = re.findall(r"\((\d{4})\)", text) or re.findall(r"\b(19[5-9]\d|20[0-4]\d)\b", text)
    return int(anos[-1]) if anos else None


def parse(text: str, nivel_fixo: str | None) -> list[dict]:
    start = text.find("post-body")
    body = text[start:] if start >= 0 else text
    end = body.find("</main>")
    body = body[:end] if end >= 0 else body
    body = re.sub(r"<!--.*?-->|<script\b.*?</script>", " ", body, flags=re.S | re.I)

    headers = {**HEADER_MAP, **EXTRA_HEADERS}
    rows, last_end, ano = [], 0, None
    for tm in re.finditer(r"<table\b.*?</table>", body, re.S | re.I):
        before = clean(body[last_end:tm.start()])
        last_end = tm.end()
        ano = _year(before) or ano  # tabelas sem título herdam o ano da anterior (ex.: 2 níveis da Maio)
        nivel = nivel_fixo or detect_level(before[-200:])
        columns = None
        for chunk in re.split(r"<tr\b", tm.group(0), flags=re.I)[1:]:
            chunk = re.split(r"</tr>", chunk, flags=re.I)[0]
            cells = [clean(c) for c in re.split(r"<t[dh]\b[^>]*>", chunk, flags=re.I)[1:]]
            if not any(cells):
                continue
            lowered = [c.lower() for c in cells]
            if "nome" in lowered or "participante" in lowered:
                columns = [headers.get(c) for c in lowered]
                continue
            if columns is None:
                columns = ["nome", "cidade", "premio"]
            rec = {col: cells[i] for i, col in enumerate(columns) if col and i < len(cells)}
            # algumas tabelas têm o cabeçalho trocado (Prêmio | Cidade) em relação aos dados
            if re.search(r"[–-]\s*[A-Z]{2}\.?$", rec.get("premio", "")) and not re.search(r"[–-]\s*[A-Z]{2}\.?$", rec.get("cidade", "")):
                rec["premio"], rec["cidade"] = rec.get("cidade", ""), rec["premio"]
            if rec.get("nome") and ano:
                rec["ano"], rec["nivel"] = ano, nivel
                rows.append(rec)
    return rows


def scrape_one(sigla: str, log=print) -> list[dict]:
    slug, nivel_fixo = COMPETICOES[sigla]
    url = f"{BASE}/{slug}/"
    text = fetch(url)
    if not text:
        log(f"{sigla}: página não encontrada ({url})")
        return []
    out = []
    for r in parse(text, nivel_fixo):
        premio = r.get("premio") or ""
        municipio, uf = split_city(r.get("cidade"))
        pontos = r.get("pontos")
        out.append({
            "competicao": sigla, "ano": r["ano"], "nivel": r["nivel"], "nome": r["nome"],
            "escola": r.get("escola") or None, "rede": None, "esfera": None,
            "municipio": municipio, "uf": uf, "premio": premio or None,
            "medalha": medal_category(premio),
            "pontos": pontos if pontos and re.fullmatch(r"[\d.,]+", pontos) else None,
            "fonte": url,
        })
    anos = sorted({r["ano"] for r in out})
    log(f"{sigla}: {len(out)} premiações, {anos[0] if anos else '-'}–{anos[-1] if anos else '-'}")
    return out


def scraper_for(sigla: str):
    return lambda log=print: scrape_one(sigla, log)
