"""Coletor da OBMEP: relatórios de premiados em premiacao.obmep.org.br, por edição, medalha e rede.

As menções honrosas ficam em listas por estado (verRelatorioPremiadosMencao-UF), fora da página nacional de
premiados; são cerca de 50 mil por edição. Entram com mencoes=True, o padrão do build_db.py
(ver docs/mencoes-obmep.md)."""
import re

from ...dominio.premiacao import BRONZE, MENCAO, OURO, PRATA, UFS, Premiacao
from .html import texto
from .http import baixar

INDICE = "https://www.obmep.org.br/premiados.htm"
BASE = "http://premiacao.obmep.org.br"
MEDALHAS = (OURO, PRATA, BRONZE)
REDES = ((".do.htm", "Pública"), (".privada.do.htm", "Privada"))
ESFERAS = {"E": "Estadual", "M": "Municipal", "F": "Federal", "P": "Privada"}
COLUNAS = {"nome": "nome", "escola": "escola", "tipo": "tipo", "municipio": "municipio", "município": "municipio",
           "uf": "uf", "medalha": "medalha"}


def pastas_das_edicoes() -> list[str]:
    """Pasta de cada edição, na ordem em que aparecem na página de premiados ('2014', '16aobmep'…)."""
    pagina = baixar(INDICE, esperado="premiacao.obmep.org.br") or ""
    return list(dict.fromkeys(re.findall(r"premiacao\.obmep\.org\.br/([^/\"]+)/mapa", pagina)))


def ano_da_pasta(pasta: str) -> int | None:
    """'2014' -> 2014; '16aobmep' -> 2021 (a 1ª edição foi em 2005 e não houve OBMEP em 2020)."""
    if re.fullmatch(r"\d{4}", pasta):
        return int(pasta)
    m = re.match(r"(\d+)", pasta)
    if not m:
        return None
    n = int(m.group(1))
    return 2004 + n if n <= 15 else 2005 + n


def ler_relatorio(pagina: str) -> tuple[int | None, list[dict]]:
    """(ano, linhas) de uma página verRelatorioPremiados*.htm. O nível vem do cabeçalho de cada bloco."""
    pagina = re.sub(r"<!--.*?-->|<script\b.*?</script>|<style\b.*?</style>", " ", pagina, flags=re.S | re.I)
    titulo = texto(" ".join(re.findall(r"<h1[^>]*>(.*?)</h1>", pagina, re.S | re.I)))
    m = re.search(r"OBMEP\s+(\d{4})", titulo)
    ano = int(m.group(1)) if m else None

    linhas, nivel, colunas = [], None, None
    for trecho in re.split(r"<tr\b", pagina, flags=re.I)[1:]:
        trecho = re.split(r"</tr>|</table>|</tbody>", trecho, flags=re.I)[0]
        if "<td" not in trecho.lower():   # linha de cabeçalho: "Nível 1" ou os nomes das colunas
            cabecalhos = [texto(c) for c in re.split(r"<th\b[^>]*>", trecho, flags=re.I)[1:]]
            achou_nivel = re.search(r"N[íi]vel\s+(\w+)", " ".join(cabecalhos))
            if achou_nivel and len([c for c in cabecalhos if c]) <= 1:
                nivel = achou_nivel.group(1)
            elif any(c.lower() == "nome" for c in cabecalhos):
                colunas = [COLUNAS.get(c.lower()) for c in cabecalhos]
            continue
        if not colunas:
            continue
        celulas = [texto(re.split(r"</td>", c, flags=re.I)[0])
                   for c in re.split(r"<td\b[^>]*>", trecho, flags=re.I)[1:]]
        registro = {col: celulas[i] for i, col in enumerate(colunas) if col and i < len(celulas)}
        if registro.get("nome"):
            registro["nivel"] = nivel
            linhas.append(registro)
    return ano, linhas


def _premiacoes(url: str, pasta: str, rede: str, medalha: str) -> tuple[int | None, list[Premiacao]]:
    """(ano, premiações) de um relatório; (None, []) se ele não existe ou vem sem tabela."""
    pagina = baixar(url)
    if not pagina or "<table" not in pagina.lower():
        return None, []
    ano, linhas = ler_relatorio(pagina)
    ano = ano or ano_da_pasta(pasta)
    premiacoes: list[Premiacao] = []
    for r in linhas:
        tipo = (r.get("tipo") or "").strip().upper()
        premiacoes.append({
            "competicao": "OBMEP", "ano": ano, "nivel": r.get("nivel"), "nome": r["nome"],
            "escola": r.get("escola") or None, "rede": rede, "esfera": ESFERAS.get(tipo, tipo or None),
            "municipio": r.get("municipio") or None, "uf": (r.get("uf") or "").upper() or None,
            "premio": medalha if medalha == MENCAO else (r.get("medalha") or medalha), "medalha": medalha,
            "pontos": None, "fonte": url,
        })
    return ano, premiacoes


def coletar(log=print, mencoes: bool = False) -> list[Premiacao]:
    """Premiações de todas as edições: um relatório por medalha (ouro, prata, bronze) e rede (pública, privada).
    Com mencoes=True, também as menções honrosas, numa lista por estado e rede.

    Relatórios que não existem ou vêm sem tabela são pulados. O ano vem do título do relatório ou, sem ele,
    do nome da pasta; a esfera (E, M, F, P) vira o nome por extenso."""
    premiacoes: list[Premiacao] = []
    for pasta in pastas_das_edicoes():
        redes_da_edicao = set()
        for medalha in MEDALHAS:
            for sufixo, rede in REDES:
                url = f"{BASE}/{pasta}/verRelatorioPremiados{medalha}{sufixo}"
                ano, achadas = _premiacoes(url, pasta, rede, medalha)
                if ano is None:
                    continue
                redes_da_edicao.add(sufixo)
                premiacoes += achadas
                log(f"OBMEP {ano} {medalha:6} {rede:7} {len(achadas):5} linhas  ({pasta})")
        if not mencoes:
            continue
        # só nas redes que a edição premiou (escolas privadas entraram em 2017): sem pedir 27 listas inexistentes
        for sufixo, rede in REDES:
            if sufixo not in redes_da_edicao:
                continue
            n, ano = 0, None
            for uf in UFS:
                ano_uf, achadas = _premiacoes(f"{BASE}/{pasta}/verRelatorioPremiadosMencao-{uf}{sufixo}", pasta, rede,
                                              MENCAO)
                ano, n = ano or ano_uf, n + len(achadas)
                premiacoes.extend(achadas)
            log(f"OBMEP {ano or ano_da_pasta(pasta)} Menção {rede:7} {n:5} linhas  ({pasta})")
    return premiacoes
