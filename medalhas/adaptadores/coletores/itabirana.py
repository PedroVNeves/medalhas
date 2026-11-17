"""Coletor da OITM (Olimpíada Itabirana de Matemática, MG): resultado final em PDF, por edição.

A página olimpiadaitabirana.com.br/noticias/premiados<ano>/ aponta para o PDF do resultado e, desde 2024,
para o da etapa "Elas em Destaque" (só para meninas). O layout muda a cada ano; a leitura usa a posição na
página (coletores.pdf) e reconhece cada coluna pelo conteúdo:
- a faixa vem num título ("MEDALHAS DE OURO", "Ouro", "Menção Honrosa") ou na coluna Premiação;
- nível ("1", "Nível 2"), rede ("Pública Não Seletiva", "Privada") e premiação têm formato próprio;
- 2018 e 2019 trazem a cidade; 2020 e 2021 juntam nome e escola num trecho só (separados pela primeira
  palavra típica de escola: Colégio, Escola, E. E. …; sem ela, a linha fica de fora para não errar o nome).
Só 2018 e 2019 informam a cidade (todas do Médio Piracicaba, MG); nos outros anos o estado é inferido pelo
nome nas outras olimpíadas (dominio.identidade), como na IMO. O PDF de 2023 é escaneado (sem texto).
"""
import re
import time

from ...dominio.premiacao import BRONZE, MENCAO, OURO, PRATA, Premiacao
from ...dominio.texto import normalizar
from .http import baixar, baixar_bytes
from .pdf import linhas, paginas

SITE = "https://www.olimpiadaitabirana.com.br"
PRIMEIRO_ANO = 2018
ELAS_EM_DESTAQUE = "Elas em Destaque"
_FAIXAS = {"OURO": OURO, "PRATA": PRATA, "BRONZE": BRONZE, "MENCAO HONROSA": MENCAO, "MENCOES HONROSAS": MENCAO,
           "ELAS EM DESTAQUE": ELAS_EM_DESTAQUE}
_NIVEL = re.compile(r"^(?:N[ií]vel\s*)?(\d)$", re.I)
_REDE = re.compile(r"^(P[uú]blica|Privada)", re.I)
_INICIO_ESCOLA = re.compile(
    r"\s(E\.\s?E\.|EE\b|E\.\s?M\.|EMEF\b|Col[eé]gio\b|Escola\b|Centro\b|Instituto\b|Funda[cç][aã]o\b|FIDE\b|Fide\b|"
    r"Sepro\b|SEPRO\b|Farias Brito\b|CEPI\b|Liceu\b|Educand[aá]rio\b|IF[A-Z]+\b)")


def _faixa(texto: str) -> str | None:
    """'MEDALHAS DE OURO', 'Medalha de Ouro', 'Ouro', 'Medalha Elas em Destaque' -> faixa; None se não é."""
    t = re.sub(r"^MEDALHAS? (DE )?", "", normalizar(texto))
    return _FAIXAS.get(t)


def _rede(texto: str | None) -> str | None:
    """'Pública Não Seletiva', 'Pública Seletiva' -> 'Pública'; 'Privada' -> 'Privada' (como a OBMEP)."""
    if not texto:
        return None
    return "Privada" if normalizar(texto).startswith("PRIVADA") else "Pública"


def ler_pdf(paginas_do_pdf) -> list[dict]:
    """(nome, escola, cidade, nível, faixa, rede) de cada premiado do PDF, na ordem do arquivo.

    A faixa de um título vale para as linhas seguintes até o próximo título; uma coluna Premiação na própria
    linha tem prioridade. Linhas sem nível, sem faixa ou com nome de uma palavra só ficam de fora, assim como
    as de nome e escola juntos quando não se acha onde a escola começa."""
    registros, faixa, tem_cidade = [], None, False
    for pagina in paginas_do_pdf:
        for _, linha in linhas(pagina):
            textos = [t for _, t in linha]
            junto = normalizar(" ".join(textos))
            if junto.startswith("NOME"):
                tem_cidade = "CIDADE" in junto
                continue
            titulo = _faixa(" ".join(textos))
            if titulo:
                faixa = titulo
                continue
            nome, resto = textos[0], textos[1:]
            nivel = next((t for t in resto if _NIVEL.match(t)), None)
            premio = next((_faixa(t) for t in resto if _faixa(t)), None)
            if not nivel or not (premio or faixa):
                continue   # título, rodapé ou observação
            rede = next((t for t in resto if _REDE.match(t)), None)   # "Pública Não Seletiva", "Privada" (2024+)
            outros = [t for t in resto if t != nivel and not _faixa(t) and not _REDE.match(t)]
            cidade = outros.pop() if tem_cidade and outros else None
            escola = " ".join(outros)
            if not escola:   # nome e escola num trecho só
                inicio = _INICIO_ESCOLA.search(nome)
                if not inicio:
                    continue
                nome, escola = nome[:inicio.start()], nome[inicio.start():]
            if len(nome.split()) < 2:
                continue   # "Gustavo", "Luna": sem sobrenome não dá para saber quem é
            registros.append({"nome": nome.strip(), "escola": escola.strip() or None, "cidade": cidade,
                              "nivel": _NIVEL.match(nivel).group(1), "faixa": premio or faixa,
                              "rede": _rede(rede)})
    return registros


def coletar(log=print) -> list[Premiacao]:
    """Premiações de todas as edições desde 2018: cada PDF linkado na página de premiados do ano.

    A UF só é preenchida (MG) quando o PDF traz a cidade; nos outros anos fica para dominio.identidade.
    O PDF escaneado de 2023 não tem texto e não rende ninguém."""
    premiacoes: list[Premiacao] = []
    for ano in range(PRIMEIRO_ANO, time.localtime().tm_year + 1):
        pagina = baixar(f"{SITE}/noticias/premiados{ano}/") or ""
        for href in dict.fromkeys(re.findall(r'href="(/static/pdfs/[^"]+\.pdf)"', pagina)):
            conteudo = baixar_bytes(SITE + href)
            if not conteudo:
                continue
            for r in ler_pdf(paginas(conteudo)):
                medalha = r["faixa"]
                premiacoes.append({
                    "competicao": "OITM", "ano": ano, "nivel": r["nivel"], "nome": r["nome"], "escola": r["escola"],
                    "rede": r["rede"], "esfera": None, "municipio": r["cidade"], "uf": "MG" if r["cidade"] else None,
                    "premio": medalha, "medalha": medalha, "pontos": None, "fonte": SITE + href,
                })
    anos = sorted({p["ano"] for p in premiacoes})
    log(f"OITM: {len(premiacoes)} premiações, {anos[0] if anos else '-'}–{anos[-1] if anos else '-'}")
    return premiacoes
