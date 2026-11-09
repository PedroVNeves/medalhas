"""Coleta os medalhistas da OBMEP (premiacao.obmep.org.br)."""
import re

from .common import clean, fetch

INDEX_URL = "https://www.obmep.org.br/premiados.htm"
BASE = "http://premiacao.obmep.org.br"
MEDALS = ("Ouro", "Prata", "Bronze")
ESFERA = {"E": "Estadual", "M": "Municipal", "F": "Federal", "P": "Privada"}

HEADER_MAP = {
    "nome": "nome",
    "escola": "escola",
    "tipo": "tipo",
    "municipio": "municipio",
    "município": "municipio",
    "uf": "uf",
    "medalha": "medalha",
}


def edition_folders() -> list[str]:
    """Descobre as pastas de cada edição a partir da página de premiados."""
    page = fetch(INDEX_URL) or ""
    folders = re.findall(r"premiacao\.obmep\.org\.br/([^/\"]+)/mapa", page)
    seen, out = set(), []
    for f in folders:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def folder_year(folder: str) -> int | None:
    """'2014' -> 2014; '16aobmep' -> 2021 (a 1ª foi em 2005 e não houve OBMEP em 2020)."""
    if re.fullmatch(r"\d{4}", folder):
        return int(folder)
    m = re.match(r"(\d+)", folder)
    if not m:
        return None
    n = int(m.group(1))
    return 2004 + n if n <= 15 else 2005 + n


def parse_report(text: str) -> tuple[int | None, list[dict]]:
    """Extrai (ano, linhas) de uma página verRelatorioPremiados*.htm."""
    text = re.sub(r"<!--.*?-->|<script\b.*?</script>|<style\b.*?</style>", " ", text, flags=re.S | re.I)
    title = clean(" ".join(re.findall(r"<h1[^>]*>(.*?)</h1>", text, re.S | re.I)))
    m = re.search(r"OBMEP\s+(\d{4})", title)
    year = int(m.group(1)) if m else None

    rows, level, columns = [], None, None
    for chunk in re.split(r"<tr\b", text, flags=re.I)[1:]:
        chunk = re.split(r"</tr>|</table>|</tbody>", chunk, flags=re.I)[0]
        if "<td" not in chunk.lower():
            ths = [clean(c) for c in re.split(r"<th\b[^>]*>", chunk, flags=re.I)[1:]]
            joined = " ".join(ths)
            lv = re.search(r"N[íi]vel\s+(\w+)", joined)
            if lv and len([t for t in ths if t]) <= 1:
                level = lv.group(1)
            elif any(t.lower() == "nome" for t in ths):
                columns = [HEADER_MAP.get(t.lower()) for t in ths]
            continue
        if not columns:
            continue
        cells = [clean(c.split("</td>")[0]) for c in re.split(r"<td\b[^>]*>", chunk, flags=re.I)[1:]]
        rec = {col: cells[i] for i, col in enumerate(columns) if col and i < len(cells)}
        if not rec.get("nome"):
            continue
        rec["nivel"] = level
        rows.append(rec)
    return year, rows


def scrape(log=print) -> list[dict]:
    records = []
    for folder in edition_folders():
        for medal in MEDALS:
            for suffix, rede in ((".do.htm", "Pública"), (".privada.do.htm", "Privada")):
                url = f"{BASE}/{folder}/verRelatorioPremiados{medal}{suffix}"
                text = fetch(url)
                if not text or "<table" not in text.lower():
                    continue
                year, rows = parse_report(text)
                if year is None:
                    year = folder_year(folder)
                for r in rows:
                    tipo = (r.get("tipo") or "").strip().upper()
                    records.append({
                        "competicao": "OBMEP",
                        "ano": year,
                        "nivel": r.get("nivel"),
                        "nome": r["nome"],
                        "escola": r.get("escola") or None,
                        "rede": "Privada" if rede == "Privada" else "Pública",
                        "esfera": ESFERA.get(tipo, tipo or None),
                        "municipio": r.get("municipio") or None,
                        "uf": (r.get("uf") or "").upper() or None,
                        "premio": r.get("medalha") or medal,
                        "medalha": medal,
                        "pontos": None,
                        "fonte": url,
                    })
                log(f"OBMEP {year} {medal:6} {rede:7} {len(rows):5} linhas  ({folder})")
    return records
