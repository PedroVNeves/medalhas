"""Coletor da OBM: páginas www.obm.org.br/premiados-obm-AAAA/, uma tabela por nível."""
import re

from ...dominio.premiacao import BRONZE, MENCAO, OURO, PRATA, Premiacao
from .html import celulas_das_linhas, corpo_do_artigo, nota, texto
from .http import baixar

INDICE = "https://www.obm.org.br/quem-somos/premiados-da-obm/"

COLUNAS = {
    "nome": "nome", "prêmio": "premio", "premio": "premio", "pontos": "pontos", "total": "pontos",
    "cidade – estado": "cidade", "cidade - estado": "cidade", "cidade": "cidade", "escola": "escola",
}

# Rótulos de nível que aparecem no texto antes de cada tabela
_NIVEIS = [
    (r"universit", "Universitário"),
    (r"j[úu]nior", "Júnior"),
    (r"s[êe]nior", "Sênior"),
    (r"primeiro n[íi]vel|n[íi]vel\s*1\b", "1"),
    (r"segundo n[íi]vel|n[íi]vel\s*2\b", "2"),
    (r"terceiro n[íi]vel|n[íi]vel\s*3\b", "3"),
]


def paginas_dos_anos() -> list[str]:
    """Endereços das páginas premiados-obm-AAAA linkadas no índice da OBM, sem repetição."""
    pagina = baixar(INDICE, esperado="premiados-obm-") or ""
    return sorted(set(re.findall(r"https://www\.obm\.org\.br/premiados-obm-\d{4}/", pagina)))


def nivel_no_texto(t: str) -> str | None:
    """O último rótulo de nível que aparece no texto (o mais próximo da tabela seguinte)."""
    melhor, posicao = None, -1
    for padrao, rotulo in _NIVEIS:
        for m in re.finditer(padrao, t, re.I):
            if m.start() > posicao:
                melhor, posicao = rotulo, m.start()
    return melhor


def categoria_do_premio(premio: str) -> str:
    """Texto do prêmio -> categoria (Ouro, Prata, Bronze, Menção Honrosa ou o próprio texto)."""
    p = premio.lower()
    if "ouro" in p:
        return OURO
    if "prata" in p:
        return PRATA
    if "bronze" in p:
        return BRONZE
    if "men" in p or "honros" in p:
        return MENCAO
    return premio.strip() or "Demais Premiados"


def separar_cidade(valor: str | None) -> tuple[str | None, str | None]:
    """'Fortaleza – CE', 'Fortaleza/CE', 'Fortaleza (CE)' ou 'Fortaleza CE' -> ('Fortaleza', 'CE')."""
    valor = (valor or "").strip(" –—-")
    m = (re.match(r"^(.*?)\s*[–—\-/]\s*([A-Za-z]{2})\.?$", valor) or re.match(r"^(.*?)\s*\(([A-Za-z]{2})\)$", valor)
         or re.match(r"^(.*\S)\s+([A-Z]{2})$", valor))
    if m:
        return m.group(1).strip() or None, m.group(2).upper()
    return valor or None, None


def ler_pagina(pagina: str) -> tuple[int | None, list[dict]]:
    """(ano do título ou None, linhas) de uma página de premiados.

    Cada tabela recebe o nível citado no texto entre ela e a tabela anterior. As colunas vêm do cabeçalho
    (COLUNAS); tabela sem cabeçalho é lida como Nome | Prêmio | Cidade."""
    corpo = corpo_do_artigo(pagina)
    m = re.search(r"Premiados\s*(?:&#8211;|–|-)?\s*OBM\s*(?:&#8211;|–|-)?\s*(\d{4})", pagina)
    ano = int(m.group(1)) if m else None

    linhas, fim_anterior = [], 0
    for tabela in re.finditer(r"<table\b.*?</table>", corpo, re.S | re.I):
        nivel = nivel_no_texto(texto(corpo[fim_anterior:tabela.start()]))
        fim_anterior = tabela.end()
        colunas = None
        for celulas in celulas_das_linhas(tabela.group(0)):
            minusculas = [c.lower() for c in celulas]
            if "nome" in minusculas:
                colunas = [COLUNAS.get(c) for c in minusculas]
                continue
            if colunas is None:   # tabela sem cabeçalho: Nome | Prêmio | Cidade
                colunas = ["nome", "premio", "cidade"]
            registro = {col: celulas[i] for i, col in enumerate(colunas) if col and i < len(celulas)}
            if registro.get("nome"):
                registro["nivel"] = nivel
                linhas.append(registro)
    return ano, linhas


def coletar(log=print) -> list[Premiacao]:
    """Premiações de todos os anos. Sem ano no título, vale o do endereço; o texto original do prêmio fica
    em "premio" e a categoria (Ouro, Prata…) em "medalha"."""
    premiacoes: list[Premiacao] = []
    for url in paginas_dos_anos():
        pagina = baixar(url)
        if not pagina:
            continue
        ano, linhas = ler_pagina(pagina)
        ano = ano or int(re.search(r"(\d{4})/?$", url).group(1))
        for r in linhas:
            premio = r.get("premio") or ""
            municipio, uf = separar_cidade(r.get("cidade"))
            premiacoes.append({
                "competicao": "OBM", "ano": ano, "nivel": r.get("nivel"), "nome": r["nome"],
                "escola": r.get("escola") or None, "rede": None, "esfera": None,
                "municipio": municipio, "uf": uf, "premio": premio or None,
                "medalha": categoria_do_premio(premio), "pontos": nota(r.get("pontos")), "fonte": url,
            })
        log(f"OBM {ano} {len(linhas):4} linhas")
    return premiacoes
