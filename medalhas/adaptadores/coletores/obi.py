"""Coletor da OBI (Olimpíada Brasileira de Informática): o "Quadro de Medalhas" de cada edição.

Cada edição (olimpiada.ic.unicamp.br/passadas/OBIAAAA/) aponta para o quadro de cada modalidade
(qmerito/i1, i2, ij, p1, p2, pj, ps, pu…). A medalha vem da imagem medalhinha_<ouro|prata|bronze>.gif;
"HM" é Honra ao Mérito.
"""
import re

from ...dominio.premiacao import MENCAO, Premiacao
from .html import nota, texto
from .http import baixar

BASE = "https://olimpiada.ic.unicamp.br"
COLUNAS = {"nome": "nome", "escola": "escola", "cidade": "municipio", "estado": "uf",
           "pontos": "pontos", "nota": "pontos", "nota1": "pontos"}

# Código da página -> nível (os títulos das páginas antigas nem sempre trazem o nome)
NIVEIS = {
    "i1": "Iniciação Nível 1", "i2": "Iniciação Nível 2", "ij": "Iniciação Nível Júnior",
    "p0": "Programação", "p1": "Programação Nível 1", "p2": "Programação Nível 2",
    "pj": "Programação Nível Júnior", "ps": "Programação Nível Sênior",
    "pu": "Programação Nível Universitário",
}


def edicoes() -> list[tuple[int, str]]:
    pagina = baixar(f"{BASE}/passadas/") or ""
    return sorted({(int(a), f"{BASE}/passadas/OBI{a}/") for a in re.findall(r'href="/passadas/OBI(\d{4})/"', pagina)})


def nivel_da_pagina(pagina: str, codigo: str) -> str:
    if codigo.lower() in NIVEIS:
        return NIVEIS[codigo.lower()]
    m = re.search(r"<h2[^>]*>(.*?)</h2>", pagina, re.S | re.I)
    m = re.search(r"Modalidade\s+(.+)$", texto(m.group(1)) if m else "")
    return m.group(1).strip() if m else codigo.upper()


def ler_quadro(pagina: str) -> list[dict]:
    linhas, colunas = [], None
    for trecho in re.findall(r"<tr\b[^>]*>(.*?)</tr>", pagina, re.S | re.I):
        brutas = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", trecho, re.S | re.I)
        celulas = [texto(c) for c in brutas]
        chaves = [re.sub(r"[^a-z0-9]", "", c.lower()) for c in celulas]
        if "nome" in chaves:
            colunas = [COLUNAS.get(c) for c in chaves]
            continue
        if not colunas or not brutas:
            continue
        imagem = re.search(r"medalhinha_(ouro|prata|bronze)", brutas[0], re.I)
        medalha = imagem.group(1).capitalize() if imagem else (MENCAO if celulas[0].upper() == "HM" else None)
        if not medalha:
            continue
        # a coluna da medalha não tem cabeçalho em todos os anos: alinha as colunas pelo fim da linha
        deslocamento = len(celulas) - len(colunas)
        registro = {col: celulas[i + deslocamento] for i, col in enumerate(colunas)
                    if col and 0 <= i + deslocamento < len(celulas)}
        if registro.get("nome"):
            registro["medalha"] = medalha
            linhas.append(registro)
    return linhas


def coletar(log=print) -> list[Premiacao]:
    premiacoes: list[Premiacao] = []
    for ano, url in edicoes():
        indice = baixar(url) or ""
        for codigo in sorted(set(re.findall(rf'href="/passadas/OBI{ano}/qmerito/(\w+)/"', indice))):
            url_quadro = f"{BASE}/passadas/OBI{ano}/qmerito/{codigo}/"
            pagina = baixar(url_quadro)
            if not pagina:
                continue
            nivel = nivel_da_pagina(pagina, codigo)
            for r in ler_quadro(pagina):
                uf = (r.get("uf") or "").strip().upper()
                premiacoes.append({
                    "competicao": "OBI", "ano": ano, "nivel": nivel, "nome": r["nome"],
                    "escola": r.get("escola") or None, "rede": None, "esfera": None,
                    "municipio": r.get("municipio") or None, "uf": uf if re.fullmatch(r"[A-Z]{2}", uf) else None,
                    "premio": "Honra ao Mérito" if r["medalha"] == MENCAO else r["medalha"],
                    "medalha": r["medalha"], "pontos": nota(r.get("pontos")), "fonte": url_quadro,
                })
    anos = sorted({p["ano"] for p in premiacoes})
    log(f"OBI: {len(premiacoes)} premiações, {anos[0] if anos else '-'}–{anos[-1] if anos else '-'}")
    return premiacoes
