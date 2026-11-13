"""Páginas com endereço próprio (/aluno/..., /escola/...) e o sitemap, para buscadores e IAs.

O site é montado no navegador (Alpine), a partir do mesmo index.html. Aqui o servidor entrega esse
index.html já com título, descrição, endereço canônico e um resumo em texto do aluno ou da escola:
- o Google lê o título e a descrição no resultado da busca;
- robôs de IA e leitores sem JavaScript leem o resumo, dentro de <noscript>.
"""
import html
import json
import re
from dataclasses import dataclass
from urllib.parse import quote
from xml.sax.saxutils import escape as escape_xml

from ...aplicacao.portas import SessaoDeLeitura
from ...config import PASTA_WEB
from ...dominio.enderecos import ALUNO, ESCOLA
from ...dominio.escolas import nome_de_exibicao
from ...dominio.texto import capitalizar_nome

URLS_POR_SITEMAP = 40_000   # o limite do protocolo é 50 mil por arquivo
MAX_PREMIACOES_NO_RESUMO = 60
MAX_ALUNOS_NO_RESUMO = 30
_ROTULO_MEDALHA = (("ouro", "ouro", "ouros"), ("prata", "prata", "pratas"), ("bronze", "bronze", "bronzes"),
                   ("mencao", "menção honrosa", "menções honrosas"))


@dataclass
class Pagina:
    status: int
    corpo: bytes = b""
    destino: str | None = None   # redirecionamento permanente para o endereço oficial


# ---------------------------------------------------------------- modelo (index.html)

_modelo: tuple[float, str] | None = None


def _index() -> str:
    global _modelo
    caminho = PASTA_WEB / "index.html"
    versao = caminho.stat().st_mtime
    if not _modelo or _modelo[0] != versao:
        _modelo = (versao, caminho.read_text(encoding="utf-8"))
    return _modelo[1]


# trechos do index.html trocados em cada página; se o index.html mudar e algum sumir, o teste acusa
_TROCAS = {
    "titulo": re.compile(r"<title>.*?</title>", re.S),
    "descricao": re.compile(r'<meta name="description" content="[^"]*">'),
    "canonico": re.compile(r'<link rel="canonical" href="[^"]*">'),
    "robots": re.compile(r'<meta name="robots" content="[^"]*">'),
    "og_url": re.compile(r'<meta property="og:url" content="[^"]*">'),
    "og_titulo": re.compile(r'<meta property="og:title" content="[^"]*">'),
    "og_descricao": re.compile(r'<meta property="og:description" content="[^"]*">'),
    "dados": re.compile(r'<script type="application/ld\+json">.*?</script>', re.S),
    "resumo": re.compile(r"<noscript><main.*?</main></noscript>", re.S),
}


def _montar(titulo: str, descricao: str, url: str, dados: dict | None, resumo: str, indexar: bool = True) -> bytes:
    a = lambda t: html.escape(t, quote=True)   # noqa: E731
    novos = {
        "titulo": f"<title>{a(titulo)}</title>",
        "descricao": f'<meta name="description" content="{a(descricao)}">',
        "canonico": f'<link rel="canonical" href="{a(url)}">',
        "robots": f'<meta name="robots" content="{"index, follow" if indexar else "noindex"}">',
        "og_url": f'<meta property="og:url" content="{a(url)}">',
        "og_titulo": f'<meta property="og:title" content="{a(titulo)}">',
        "og_descricao": f'<meta property="og:description" content="{a(descricao)}">',
        # </ dentro do JSON fecharia o <script> antes da hora
        "dados": ('<script type="application/ld+json">' + json.dumps(dados, ensure_ascii=False).replace("</", "<\\/")
                  + "</script>") if dados else "",
        "resumo": ('<noscript><main style="max-width:44rem;margin:2rem auto;padding:0 1rem;color:#e8ebf5;'
                   f'font:16px/1.6 system-ui,sans-serif">{resumo}</main></noscript>'),
    }
    texto = _index()
    for chave, padrao in _TROCAS.items():
        texto, n = padrao.subn(lambda _m, v=novos[chave]: v, texto, count=1)
        if not n:
            raise RuntimeError(f"index.html sem o trecho '{chave}' esperado por paginas.py")
    return texto.encode("utf-8")


# ---------------------------------------------------------------- textos

def _medalhas(m: dict) -> str:
    """'2 ouros, 1 prata e 3 bronzes'"""
    partes = [f"{m[c]} {um if m[c] == 1 else varios}" for c, um, varios in _ROTULO_MEDALHA if m.get(c)]
    if not partes:
        return "premiações"
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " e " + partes[-1]


def _olimpiadas(premiacoes: list[dict]) -> list[str]:
    """Siglas da que mais premiou para a que menos."""
    contagem: dict[str, int] = {}
    for r in premiacoes:
        contagem[r["competicao"]] = contagem.get(r["competicao"], 0) + 1
    return sorted(contagem, key=lambda s: (-contagem[s], s))


def _lista(itens: list[str]) -> str:
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


def _linha_premiacao(r: dict, com_aluno: bool) -> str:
    partes = [str(r["ano"] or ""), r["competicao"], r["premio"] or r["medalha"] or ""]
    if r.get("nivel"):
        partes.append(f"nível {r['nivel']}")
    if com_aluno:
        partes.append(r["nome"])
    elif r.get("escola"):
        partes.append(nome_de_exibicao(r["escola"]))
    return " · ".join(html.escape(str(p)) for p in partes if p)


def _rodape(base: str, api: str) -> str:
    e = html.escape
    return (f'<p>Dados das listas oficiais de cada olimpíada. Os mesmos dados em JSON: <a href="{e(api)}">{e(api)}</a>. '
            f'Sobre o site e a API: <a href="{e(base)}/llms.txt">{e(base)}/llms.txt</a>.</p>')


def _migalhas(base: str, nome: str, url: str) -> dict:
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Medalhas", "item": base + "/"},
        {"@type": "ListItem", "position": 2, "name": nome, "item": url}]}


# ---------------------------------------------------------------- páginas

def perfil(sessao: SessaoDeLeitura, tipo: str, endereco: str, base: str) -> Pagina:
    """Página de um aluno ou escola. base: URL pública do site, sem barra no fim."""
    achado = sessao.enderecos().resolver(tipo, endereco)
    if not achado:
        return Pagina(404, _montar("Página não encontrada · Medalhas", "Este endereço não existe no Medalhas.",
                                   base + "/", None, "<h1>Página não encontrada</h1>", indexar=False))
    ident, oficial = achado
    if endereco != oficial:
        return Pagina(301, destino=f"/{tipo}/{oficial}")
    url = f"{base}/{tipo}/{oficial}"
    if tipo == ALUNO:
        return Pagina(200, _aluno(sessao.perfil_aluno(ident, {}), base, url))
    return Pagina(200, _escola(sessao.perfil_escola(ident, {}), sessao, base, url))


def _aluno(d: dict, base: str, url: str) -> bytes:
    e = html.escape
    premiacoes = d["premiacoes"]
    siglas = _olimpiadas(premiacoes)
    medalhas = _medalhas(d["medalhas"])
    anos = d["anos"]
    periodo = f"{anos[0]}" if len(anos) == 1 else f"de {anos[0]} a {anos[-1]}"
    escola = nome_de_exibicao(d["escolas"][0]["escola"]) if d["escolas"] else None
    nome_uf = f"{d['nome']} ({d['uf']})" if d["uf"] else d["nome"]

    # o Google corta o título perto de 60 caracteres: nome e olimpíadas primeiro, a contagem vai na descrição
    titulo = f"{nome_uf}: medalhas na {_lista(siglas[:3])} · Medalhas"
    descricao = (f"Premiações de {d['nome']} em olimpíadas científicas {periodo}: {medalhas} "
                 f"({_lista(siglas)})." + (f" Escola: {escola}." if escola else "")
                 + (f" {d['rank']}º no ranking nacional." if d.get("rank") else ""))
    linhas = "".join(f"<li>{_linha_premiacao(r, com_aluno=False)}</li>" for r in premiacoes[:MAX_PREMIACOES_NO_RESUMO])
    escolas = "".join(f"<li>{e(nome_de_exibicao(x['escola']))}"
                      f"{' · ' + e(capitalizar_nome(x['municipio'])) if x.get('municipio') else ''}</li>"
                      for x in d["escolas"])
    resumo = (f"<h1>{e(nome_uf)}</h1><p>{e(descricao)}</p>"
              f"<h2>Premiações</h2><ul>{linhas}</ul>"
              + (f"<h2>Escolas</h2><ul>{escolas}</ul>" if escolas else "")
              + _rodape(base, f"{base}/api/v1/alunos/{_quote(d['id'])}"))
    return _montar(titulo, descricao, url, _migalhas(base, d["nome"], url), resumo)


def _escola(d: dict, sessao: SessaoDeLeitura, base: str, url: str) -> bytes:
    e = html.escape
    enderecos = sessao.enderecos()
    nome = nome_de_exibicao(d["nome"])
    municipio = capitalizar_nome(d["municipio"]) if d.get("municipio") else None
    lugar = ", ".join(p for p in (municipio, d.get("uf")) if p)
    nome_lugar = f"{nome} ({lugar})" if lugar else nome
    siglas = _olimpiadas(d["recentes"])
    medalhas = _medalhas(d["medalhas"])
    plural = "aluno premiado" if d["alunos"] == 1 else "alunos premiados"

    titulo = f"{nome_lugar}: {d['alunos']} {plural} em olimpíadas · Medalhas"
    descricao = (f"Medalhistas da escola {nome}" + (f" em {lugar}" if lugar else "")
                 + f": {d['alunos']} {plural}, {medalhas}" + (f" na {_lista(siglas[:4])}" if siglas else "")
                 + "." + (f" {d['rank']}ª no ranking nacional de escolas." if d.get("rank") else ""))
    alunos = "".join(
        f'<li><a href="/aluno/{enderecos.de(ALUNO, a["id"])}">{e(a["nome"])}</a> · {e(_medalhas(a))}</li>'
        for a in d["top_alunos"][:MAX_ALUNOS_NO_RESUMO] if enderecos.de(ALUNO, a["id"]))
    recentes = "".join(f"<li>{_linha_premiacao(r, com_aluno=True)}</li>" for r in d["recentes"])
    resumo = (f"<h1>{e(nome_lugar)}</h1><p>{e(descricao)}</p>"
              + (f"<h2>Destaques</h2><ul>{alunos}</ul>" if alunos else "")
              + f"<h2>Premiações recentes</h2><ul>{recentes}</ul>"
              + _rodape(base, f"{base}/api/v1/escolas/{_quote(d['id'])}/medalhistas"))
    return _montar(titulo, descricao, url, _migalhas(base, nome, url), resumo)


def _quote(ident: str) -> str:
    return quote(ident, safe="")


# ---------------------------------------------------------------- sitemap

_sitemaps: dict[tuple, dict[str, bytes]] = {}


def sitemap(sessao: SessaoDeLeitura, nome: str, base: str, versao: int) -> bytes | None:
    """nome: 'sitemap.xml' (índice) ou um dos arquivos listados nele. None se não existe."""
    chave = (versao, base)
    if chave not in _sitemaps:
        _sitemaps.clear()
        _sitemaps[chave] = _gerar_sitemaps(sessao, base)
    return _sitemaps[chave].get(nome)


def _gerar_sitemaps(sessao: SessaoDeLeitura, base: str) -> dict[str, bytes]:
    data = (sessao.resumo_base().get("atualizado_em") or "")[:10]
    lastmod = f"<lastmod>{data}</lastmod>" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", data) else ""
    enderecos = sessao.enderecos()

    def urlset(urls: list[str]) -> bytes:
        corpo = "".join(f"<url><loc>{escape_xml(u)}</loc>{lastmod}</url>" for u in urls)
        return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                f"{corpo}</urlset>\n").encode("utf-8")

    arquivos = {"sitemaps/paginas.xml": urlset([base + "/"])}
    for tipo, plural in ((ALUNO, "alunos"), (ESCOLA, "escolas")):
        urls = [f"{base}/{tipo}/{e}" for e in enderecos.todos(tipo)]
        for i in range(0, len(urls), URLS_POR_SITEMAP):
            arquivos[f"sitemaps/{plural}-{i // URLS_POR_SITEMAP + 1}.xml"] = urlset(urls[i:i + URLS_POR_SITEMAP])
    indice = "".join(f"<sitemap><loc>{base}/{nome}</loc>{lastmod}</sitemap>" for nome in arquivos)
    arquivos["sitemap.xml"] = ('<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex '
                               f'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{indice}</sitemapindex>\n'
                               ).encode("utf-8")
    return arquivos
