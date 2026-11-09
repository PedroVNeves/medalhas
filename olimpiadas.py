"""Cadastro das olimpíadas suportadas.

Para adicionar uma olimpíada nova:
  1. escreva o coletor em scraper/<sigla>.py com uma função scrape() que devolve registros no mesmo
     formato dos existentes (competicao, ano, nivel, nome, escola, municipio, uf, premio, medalha, fonte…);
  2. cadastre-a abaixo (nome, área, tabela de pontos e regra do IMPA Tech, se houver);
  3. rode `python build_db.py`.
A interface monta os filtros de olimpíada, área e nível a partir dos dados, sem mudar o front-end.
"""
from scraper import obm, obmep

# Tabela oficial do IMPA Tech — Edital do Processo Seletivo 2026, item 6.1
FONTE_PONTOS = {
    "nome": "Edital do Processo Seletivo 2026 do IMPA Tech, item 6.1",
    "url": "https://impatech.edu.br/wp-content/uploads/2025/10/Edital-IMPA-Tech-2026-versao-final-2025-10-23site.pdf",
}
PONTOS_MATEMATICA = {"Ouro": 18, "Prata": 6, "Bronze": 2}   # OBMEP e OBM no edital
PONTOS_OUTRAS_IMPA = {"Ouro": 9, "Prata": 3, "Bronze": 1}   # OBFEP, OBQ e OBI no mesmo edital

OLIMPIADAS = {
    "OBMEP": {
        "nome": "Olimpíada Brasileira de Matemática das Escolas Públicas",
        "area": "Matemática",
        "pontos": PONTOS_MATEMATICA,
        "impa_niveis": {"3"},          # edital: só Nível 3, premiação nacional
        "scrape": obmep.scrape,
        "site": "https://www.obmep.org.br",
    },
    "OBM": {
        "nome": "Olimpíada Brasileira de Matemática",
        "area": "Matemática",
        "pontos": PONTOS_MATEMATICA,
        "impa_niveis": {"3"},          # edital: só Nível 3
        "scrape": obm.scrape,
        "site": "https://www.obm.org.br",
    },
}


def pontos(competicao: str, medalha: str) -> int:
    """Pontos do site: tabela da olimpíada aplicada a todos os níveis (menção honrosa não pontua)."""
    return OLIMPIADAS.get(competicao, {}).get("pontos", {}).get(medalha, 0)


def pontos_impa(competicao: str, medalha: str, nivel: str | None) -> int:
    """Pontos aceitos no processo seletivo do IMPA Tech (0 se a olimpíada/nível não conta)."""
    info = OLIMPIADAS.get(competicao, {})
    if nivel in info.get("impa_niveis", set()):
        return info["pontos"].get(medalha, 0)
    return 0


def area(competicao: str) -> str | None:
    return OLIMPIADAS.get(competicao, {}).get("area")


def catalogo() -> list[dict]:
    """Versão serializável (para a API/front-end)."""
    return [{"sigla": s, "nome": o["nome"], "area": o["area"], "pontos": o["pontos"],
             "impa_niveis": sorted(o["impa_niveis"]), "site": o["site"]} for s, o in OLIMPIADAS.items()]
