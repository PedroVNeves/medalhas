"""Coletor das competições internacionais com resultados do Brasil publicados pela OBM.

Cada competição tem uma página "Resultados" (o `site` dela no catálogo) com uma tabela por edição
(ex.: "41ª OIM, Buenos Aires (2026)") no formato Nome | Cidade – Estado | [Pontos] | Prêmio.
Um único leitor serve para todas.
"""
import re

from ...dominio.olimpiadas import CATALOGO
from ...dominio.premiacao import Premiacao
from .html import corpo_do_artigo, nota, texto
from .http import baixar
from .obm import COLUNAS as COLUNAS_OBM
from .obm import categoria_do_premio, nivel_no_texto, separar_cidade

SIGLAS = ("OIM", "CONESUL", "EGMO", "APMO", "PAGMO", "MAIO", "OMCPLP", "IGO", "OMOP", "IMSC", "GALOIS",
          "IMC", "OIMU", "CIIM")
NIVEL_FIXO = {"IMC": "Universitário", "OIMU": "Universitário", "CIIM": "Universitário"}

COLUNAS = {**COLUNAS_OBM, "participante": "nome", "cidade-estado": "cidade", "cidade – estado": "cidade",
           "instituição": "escola", "instituicao": "escola", "universidade": "escola"}
_TERMINA_EM_UF = r"[–-]\s*[A-Z]{2}\.?$"


def _ano(t: str) -> int | None:
    """Ano da edição no título antes da tabela: o último "(AAAA)", senão o último ano solto; None se não há."""
    anos = re.findall(r"\((\d{4})\)", t) or re.findall(r"\b(19[5-9]\d|20[0-4]\d)\b", t)
    return int(anos[-1]) if anos else None


def ler_pagina(pagina: str, nivel_fixo: str | None) -> list[dict]:
    """Linhas de todas as tabelas da página, cada uma com o ano e o nível da sua edição.

    O nível é nivel_fixo (competições universitárias) ou o citado logo antes da tabela. Linhas sem ano
    conhecido ficam de fora."""
    corpo = corpo_do_artigo(pagina)
    linhas, fim_anterior, ano = [], 0, None
    for tabela in re.finditer(r"<table\b.*?</table>", corpo, re.S | re.I):
        antes = texto(corpo[fim_anterior:tabela.start()])
        fim_anterior = tabela.end()
        ano = _ano(antes) or ano   # tabela sem título herda o ano da anterior (ex.: os 2 níveis da Maio)
        nivel = nivel_fixo or nivel_no_texto(antes[-200:])
        colunas = None
        for trecho in re.split(r"<tr\b", tabela.group(0), flags=re.I)[1:]:
            trecho = re.split(r"</tr>", trecho, flags=re.I)[0]
            celulas = [texto(c) for c in re.split(r"<t[dh]\b[^>]*>", trecho, flags=re.I)[1:]]
            if not any(celulas):
                continue
            minusculas = [c.lower() for c in celulas]
            if "nome" in minusculas or "participante" in minusculas:
                colunas = [COLUNAS.get(c) for c in minusculas]
                continue
            if colunas is None:
                colunas = ["nome", "cidade", "premio"]
            registro = {col: celulas[i] for i, col in enumerate(colunas) if col and i < len(celulas)}
            # algumas tabelas têm o cabeçalho trocado (Prêmio | Cidade) em relação aos dados
            if (re.search(_TERMINA_EM_UF, registro.get("premio", ""))
                    and not re.search(_TERMINA_EM_UF, registro.get("cidade", ""))):
                registro["premio"], registro["cidade"] = registro.get("cidade", ""), registro["premio"]
            if registro.get("nome") and ano:
                registro["ano"], registro["nivel"] = ano, nivel
                linhas.append(registro)
    return linhas


def coletar(sigla: str, log=print) -> list[Premiacao]:
    """Premiações do Brasil na competição `sigla` (uma de SIGLAS), lidas da página `site` dela no catálogo.
    Sem a página, registra no log e devolve lista vazia."""
    url = CATALOGO[sigla].site
    pagina = baixar(url)
    if not pagina:
        log(f"{sigla}: página não encontrada ({url})")
        return []
    premiacoes: list[Premiacao] = []
    for r in ler_pagina(pagina, NIVEL_FIXO.get(sigla)):
        premio = r.get("premio") or ""
        municipio, uf = separar_cidade(r.get("cidade"))
        premiacoes.append({
            "competicao": sigla, "ano": r["ano"], "nivel": r["nivel"], "nome": r["nome"],
            "escola": r.get("escola") or None, "rede": None, "esfera": None,
            "municipio": municipio, "uf": uf, "premio": premio or None,
            "medalha": categoria_do_premio(premio), "pontos": nota(r.get("pontos")), "fonte": url,
        })
    anos = sorted({p["ano"] for p in premiacoes})
    log(f"{sigla}: {len(premiacoes)} premiações, {anos[0] if anos else '-'}–{anos[-1] if anos else '-'}")
    return premiacoes
