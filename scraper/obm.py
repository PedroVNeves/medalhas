"""Coleta os premiados da OBM (www.obm.org.br/premiados-obm-AAAA/)."""
import re

from .common import clean, fetch

INDEX_URL = "https://www.obm.org.br/quem-somos/premiados-da-obm/"

HEADER_MAP = {
    "nome": "nome",
    "prêmio": "premio",
    "premio": "premio",
    "pontos": "pontos",
    "total": "pontos",
    "cidade – estado": "cidade",
    "cidade - estado": "cidade",
    "cidade": "cidade",
    "escola": "escola",
}

LEVEL_WORDS = [
    (r"universit", "Universitário"),
    (r"j[úu]nior", "Júnior"),
    (r"s[êe]nior", "Sênior"),
    (r"primeiro n[íi]vel|n[íi]vel\s*1\b", "1"),
    (r"segundo n[íi]vel|n[íi]vel\s*2\b", "2"),
    (r"terceiro n[íi]vel|n[íi]vel\s*3\b", "3"),
]


def year_urls() -> list[str]:
    page = fetch(INDEX_URL) or ""
    return sorted(set(re.findall(r"https://www\.obm\.org\.br/premiados-obm-\d{4}/", page)))


def detect_level(text: str) -> str | None:
    """Pega o último rótulo de nível que aparece no texto antes da tabela."""
    best, pos = None, -1
    for pattern, label in LEVEL_WORDS:
        for m in re.finditer(pattern, text, re.I):
            if m.start() > pos:
                best, pos = label, m.start()
    return best


def medal_category(premio: str) -> str:
    p = premio.lower()
    if "ouro" in p:
        return "Ouro"
    if "prata" in p:
        return "Prata"
    if "bronze" in p:
        return "Bronze"
    if "men" in p or "honros" in p:
        return "Menção Honrosa"
    return premio.strip() or "Demais Premiados"


def split_city(value: str) -> tuple[str | None, str | None]:
    value = (value or "").strip(" –—-")
    m = (re.match(r"^(.*?)\s*[–—\-/]\s*([A-Za-z]{2})\.?$", value) or re.match(r"^(.*?)\s*\(([A-Za-z]{2})\)$", value)
         or re.match(r"^(.*\S)\s+([A-Z]{2})$", value))
    if m:
        return m.group(1).strip() or None, m.group(2).upper()
    return value or None, None


def parse_page(text: str) -> tuple[int | None, list[dict]]:
    start = text.find("post-body")
    body = text[start:] if start >= 0 else text
    end = body.find("</main>")
    body = body[:end] if end >= 0 else body
    body = re.sub(r"<!--.*?-->|<script\b.*?</script>", " ", body, flags=re.S | re.I)

    m = re.search(r"Premiados\s*(?:&#8211;|–|-)?\s*OBM\s*(?:&#8211;|–|-)?\s*(\d{4})", text)
    year = int(m.group(1)) if m else None

    rows, last_end = [], 0
    for tm in re.finditer(r"<table\b.*?</table>", body, re.S | re.I):
        level = detect_level(clean(body[last_end:tm.start()]))
        last_end = tm.end()
        columns = None
        for chunk in re.split(r"<tr\b", tm.group(0), flags=re.I)[1:]:
            chunk = re.split(r"</tr>", chunk, flags=re.I)[0]
            cells = [clean(c) for c in re.split(r"<t[dh]\b[^>]*>", chunk, flags=re.I)[1:]]
            if not any(cells):
                continue
            lowered = [c.lower() for c in cells]
            if "nome" in lowered:
                columns = [HEADER_MAP.get(c) for c in lowered]
                continue
            if columns is None:  # tabela sem cabeçalho: assume Nome | Prêmio | Cidade
                columns = ["nome", "premio", "cidade"]
            rec = {col: cells[i] for i, col in enumerate(columns) if col and i < len(cells)}
            if rec.get("nome"):
                rec["nivel"] = level
                rows.append(rec)
    return year, rows


def scrape(log=print) -> list[dict]:
    records = []
    for url in year_urls():
        text = fetch(url)
        if not text:
            continue
        year, rows = parse_page(text)
        year = year or int(re.search(r"(\d{4})/?$", url).group(1))
        for r in rows:
            premio = r.get("premio") or ""
            municipio, uf = split_city(r.get("cidade"))
            pontos = r.get("pontos")
            records.append({
                "competicao": "OBM",
                "ano": year,
                "nivel": r.get("nivel"),
                "nome": r["nome"],
                "escola": r.get("escola") or None,
                "rede": None,
                "esfera": None,
                "municipio": municipio,
                "uf": uf,
                "premio": premio or None,
                "medalha": medal_category(premio),
                "pontos": pontos if pontos and re.fullmatch(r"[\d.,]+", pontos) else None,
                "fonte": url,
            })
        log(f"OBM {year} {len(rows):4} linhas")
    return records
