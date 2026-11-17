"""Páginas com endereço próprio (/aluno/..., /escola/..., /cidade/..., /ranking/..., /sobre...) e o sitemap, para buscadores e IAs.

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
from ...config import PASTA_WEB, URL_SITE
from ...dominio.enderecos import ALUNO, CIDADE, ESCOLA
from ...dominio.escolas import nome_de_exibicao
from ...dominio.texto import capitalizar_nome

IMAGEM_SITE = "/og/site.png"
URLS_POR_SITEMAP = 40_000   # o limite do protocolo é 50 mil por arquivo
MAX_PREMIACOES_NO_RESUMO = 60
MAX_ALUNOS_NO_RESUMO = 30
_ROTULO_MEDALHA = (("ouro", "ouro", "ouros"), ("prata", "prata", "pratas"), ("bronze", "bronze", "bronzes"),
                   ("mencao", "menção honrosa", "menções honrosas"))


@dataclass
class Pagina:
    """Resposta de uma página: o HTML pronto, ou um redirecionamento (destino) para o endereço oficial."""
    status: int
    corpo: bytes = b""
    destino: str | None = None   # redirecionamento permanente para o endereço oficial


# ---------------------------------------------------------------- modelo (index.html)

_modelo: tuple[float, str] | None = None


def _index() -> str:
    """O index.html do site, relido só quando o arquivo muda."""
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
    "og_imagem": re.compile(r'<meta property="og:image" content="[^"]*">'),
    "og_imagem_alt": re.compile(r'<meta property="og:image:alt" content="[^"]*">'),
    "dados": re.compile(r'<script type="application/ld\+json">.*?</script>', re.S),
    "resumo": re.compile(r"<noscript><main.*?</main></noscript>", re.S),
}


def _montar(titulo: str, descricao: str, url: str, dados: dict | None, resumo: str, indexar: bool = True,
            imagem: str | None = None, imagem_alt: str | None = None) -> bytes:
    """imagem: endereço da imagem do cartão de compartilhamento (padrão: a do site)."""
    a = lambda t: html.escape(t, quote=True)   # noqa: E731
    imagem = imagem or URL_SITE + IMAGEM_SITE
    novos = {
        "titulo": f"<title>{a(titulo)}</title>",
        "descricao": f'<meta name="description" content="{a(descricao)}">',
        "canonico": f'<link rel="canonical" href="{a(url)}">',
        "robots": f'<meta name="robots" content="{"index, follow" if indexar else "noindex"}">',
        "og_url": f'<meta property="og:url" content="{a(url)}">',
        "og_titulo": f'<meta property="og:title" content="{a(titulo)}">',
        "og_descricao": f'<meta property="og:description" content="{a(descricao)}">',
        "og_imagem": f'<meta property="og:image" content="{a(imagem)}">',
        "og_imagem_alt": f'<meta property="og:image:alt" content="{a(imagem_alt or titulo)}">',
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
    """['a', 'b', 'c'] -> 'a, b e c'"""
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


def _linha_premiacao(r: dict, com_aluno: bool) -> str:
    """'2024 · OBMEP · Ouro · nível 3 · Escola X' em HTML escapado; com_aluno troca a escola pelo nome do aluno."""
    partes = [str(r["ano"] or ""), r["competicao"], r["premio"] or r["medalha"] or ""]
    if r.get("nivel"):
        partes.append(f"nível {r['nivel']}")
    if com_aluno:
        partes.append(r["nome"])
    elif r.get("escola"):
        partes.append(nome_de_exibicao(r["escola"]))
    return " · ".join(html.escape(str(p)) for p in partes if p)


def _rodape(base: str, api: str) -> str:
    """Parágrafo final do resumo: fonte dos dados, o mesmo conteúdo na API e o llms.txt."""
    e = html.escape
    return (f'<p>Dados das listas oficiais de cada olimpíada. Os mesmos dados em JSON: <a href="{e(api)}">{e(api)}</a>. '
            f'Sobre o site e a API: <a href="{e(base)}/llms.txt">{e(base)}/llms.txt</a>.</p>')


def _migalhas(base: str, nome: str, url: str) -> dict:
    """Trilha de navegação (schema.org BreadcrumbList) Medalhas > página, para os buscadores."""
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Medalhas", "item": base + "/"},
        {"@type": "ListItem", "position": 2, "name": nome, "item": url}]}


# ---------------------------------------------------------------- páginas

# Telas do site com endereço próprio além dos perfis. O título de cada uma também está em web/js/app.js
# (TITULOS), que o troca ao navegar sem recarregar; o teste confere que os dois batem.
SOBRE = "/sobre"
CONTATO = "pedro.vasconcelosneves@gmail.com"
MAX_RANKING_NO_RESUMO = 100
UF_NOMES = {
    "AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá", "BA": "Bahia", "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MG": "Minas Gerais",
    "MS": "Mato Grosso do Sul", "MT": "Mato Grosso", "PA": "Pará", "PB": "Paraíba", "PE": "Pernambuco",
    "PI": "Piauí", "PR": "Paraná", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RO": "Rondônia",
    "RR": "Roraima", "RS": "Rio Grande do Sul", "SC": "Santa Catarina", "SE": "Sergipe", "SP": "São Paulo",
    "TO": "Tocantins"}


@dataclass(frozen=True)
class Tela:
    """Título e descrição de uma tela do site; indexar=False pede aos buscadores que não a listem."""
    titulo: str
    descricao: str
    indexar: bool = True


TELAS = {
    "/ranking/alunos": Tela(
        "Ranking dos maiores medalhistas das olimpíadas do Brasil · Medalhas",
        "Os alunos com mais medalhas na OBMEP, OBM, OBI, IMO e outras olimpíadas científicas, de 1979 até hoje. "
        "Filtre por estado, olimpíada, nível, ano e rede de ensino."),
    "/ranking/escolas": Tela(
        "Ranking das escolas com mais medalhas em olimpíadas · Medalhas",
        "As escolas brasileiras com mais alunos premiados na OBMEP, OBI e outras olimpíadas científicas. "
        "Filtre por estado, olimpíada, ano e escola pública ou privada."),
    "/ranking/cidades": Tela(
        "Ranking das cidades com mais medalhas em olimpíadas · Medalhas",
        "As cidades do Brasil com mais medalhas na OBMEP, OBM, OBI e outras olimpíadas científicas, com alunos "
        "e escolas premiados em cada uma. Filtre por estado, olimpíada, ano e nível."),
    "/ranking/estados": Tela(
        "Ranking dos estados em medalhas nas olimpíadas · Medalhas",
        "Quais estados do Brasil têm mais medalhas na OBMEP, OBM, OBI, IMO e outras olimpíadas científicas, "
        "com alunos e escolas premiados em cada um."),
    "/estados": Tela(
        "Mapa das medalhas em olimpíadas por estado do Brasil · Medalhas",
        "Mapa do Brasil com as medalhas de cada estado na OBMEP, OBM, OBI, IMO e outras olimpíadas científicas: "
        "ouros, total de premiações, alunos e escolas."),
    "/dados": Tela(
        "API e dados abertos dos medalhistas das olimpíadas · Medalhas",
        "Baixe as premiações da OBMEP, OBM, OBI, IMO e outras olimpíadas em CSV ou JSON, ou consulte pela API "
        "pública, gratuita e sem cadastro."),
    "/busca": Tela("Busca · Medalhas", "Busque alunos e escolas premiados em olimpíadas científicas.", indexar=False),
    SOBRE: Tela(
        "Sobre o Medalhas: por que reunimos os medalhistas das olimpíadas",
        "Os resultados das olimpíadas científicas são públicos, mas espalhados e difíceis de achar. O Medalhas "
        "reúne em um só lugar as premiações de estudantes brasileiros, com link para a fonte oficial."),
}
_TRECHO_SOBRE = re.compile(r"<!-- sobre:inicio -->(.*?)<!-- sobre:fim -->", re.S)


def tela(sessao: SessaoDeLeitura, caminho: str, base: str) -> Pagina | None:
    """Página de uma tela do site (caminho sem barra no fim). None se o caminho não é uma tela."""
    if caminho == "/ranking":
        return Pagina(301, destino="/ranking/alunos")
    t = TELAS.get(caminho)
    if not t:
        return None
    url = base + caminho
    nome = t.titulo.split(" · ")[0].split(":")[0]
    dados = {"@context": "https://schema.org", "@graph": [
        {"@type": "AboutPage" if caminho == SOBRE else "WebPage", "@id": url, "url": url, "name": t.titulo,
         "description": t.descricao, "inLanguage": "pt-BR", "isPartOf": {"@id": base + "/#site"}},
        _migalhas(base, nome, url)]}
    if caminho == SOBRE:
        corpo = _resumo_sobre()
    elif caminho.startswith("/ranking/"):
        corpo = _resumo_ranking(sessao, caminho.rsplit("/", 1)[1], t)
    elif caminho == "/estados":
        corpo = _resumo_ranking(sessao, "estados", t)
    else:
        corpo = f"<h1>{html.escape(nome)}</h1><p>{html.escape(t.descricao)}</p>"
    resumo = corpo + _rodape(base, base + "/api/v1")
    return Pagina(200, _montar(t.titulo, t.descricao, url, dados if t.indexar else None, resumo, t.indexar))


def _resumo_sobre() -> str:
    """O texto da tela Sobre, tirado do index.html: um texto só para a tela e para quem não roda JavaScript."""
    trecho = _TRECHO_SOBRE.search(_index())
    if not trecho:
        raise RuntimeError("index.html sem os marcadores sobre:inicio / sobre:fim esperados por paginas.py")
    return trecho[1]


def _resumo_ranking(sessao: SessaoDeLeitura, tipo: str, t: Tela) -> str:
    """Os MAX_RANKING_NO_RESUMO primeiros do ranking (alunos, escolas, cidades ou estados) em HTML, com links
    para os perfis. Sempre pela tabela do IMPA, o método padrão do site."""
    e = html.escape
    r = sessao.ranking({"tipo": tipo, "limite": MAX_RANKING_NO_RESUMO, "metodo": "impa"})
    enderecos = sessao.enderecos()
    linhas = []
    for it in r["itens"]:
        if tipo == "alunos":
            nome = f'<a href="/aluno/{enderecos.de(ALUNO, it["id"])}">{e(it["nome"])}</a>'
            lugar = ", ".join(p for p in (it.get("escola") and nome_de_exibicao(it["escola"]), it.get("uf")) if p)
        elif tipo == "escolas":
            nome = f'<a href="/escola/{enderecos.de(ESCOLA, it["id"])}">{e(nome_de_exibicao(it["nome"]))}</a>'
            lugar = ", ".join(p for p in (it.get("municipio") and capitalizar_nome(it["municipio"]), it.get("uf")) if p)
        elif tipo == "cidades":
            nome = f'<a href="/cidade/{enderecos.de(CIDADE, it["id"])}">{e(it["nome"])}</a>'
            lugar = f"{it['uf']}, {it['alunos']} alunos, {it['escolas']} escolas"
        else:
            nome, lugar = e(UF_NOMES.get(it["id"], it["id"])), f"{it['alunos']} alunos, {it['escolas']} escolas"
        linhas.append(f"<li>{nome}{' (' + e(lugar) + ')' if lugar else ''}: {e(_medalhas(it))}, "
                      f"{it['xp']} pontos</li>")
    titulo = e(t.titulo.split(" · ")[0])
    return (f"<h1>{titulo}</h1><p>{e(t.descricao)}</p>"
            f"<p>Os {len(linhas)} primeiros de {r['total']}, pela tabela de pontos do IMPA Tech "
            f"(ouro 18, prata 6, bronze 2).</p><ol>{''.join(linhas)}</ol>")


def perfil(sessao: SessaoDeLeitura, tipo: str, endereco: str, base: str) -> Pagina:
    """Página de um aluno, escola ou cidade. base: URL pública do site, sem barra no fim."""
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
    if tipo == CIDADE:
        return Pagina(200, _cidade(sessao.perfil_cidade(ident, {}), sessao, base, url))
    return Pagina(200, _escola(sessao.perfil_escola(ident, {}), sessao, base, url))


def _aluno(d: dict, base: str, url: str) -> bytes:
    """index.html da página do aluno: título curto (nome e olimpíadas), descrição com medalhas, escola e posição,
    resumo com as premiações e o cartão de compartilhamento do aluno."""
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
    return _montar(titulo, descricao, url, _migalhas(base, d["nome"], url), resumo,
                   imagem=imagem_de(base, url), imagem_alt=f"{nome_uf}: {medalhas}")


def _escola(d: dict, sessao: SessaoDeLeitura, base: str, url: str) -> bytes:
    """index.html da página da escola: alunos premiados, medalhas e posição; o resumo lista os destaques e as
    premiações recentes."""
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
    return _montar(titulo, descricao, url, _migalhas(base, nome, url), resumo,
                   imagem=imagem_de(base, url), imagem_alt=f"{nome_lugar}: {medalhas}")


def _cidade(d: dict, sessao: SessaoDeLeitura, base: str, url: str) -> bytes:
    """index.html da página da cidade: alunos, escolas e medalhas; o resumo lista as escolas e os alunos que
    mais pontuam. Usa a imagem de compartilhamento do site."""
    e = html.escape
    enderecos = sessao.enderecos()
    nome_uf = f"{d['nome']} ({d['uf']})"
    medalhas = _medalhas(d["medalhas"])
    siglas = [o["sigla"] for o in d["olimpiadas"]]
    anos = d["anos"]
    periodo = f"em {anos[0]}" if len(anos) == 1 else f"de {anos[0]} a {anos[-1]}"
    plural = "aluno premiado" if d["alunos"] == 1 else "alunos premiados"

    titulo = f"Medalhistas de {nome_uf} em olimpíadas · Medalhas"
    descricao = (f"{d['nome']} ({UF_NOMES.get(d['uf'], d['uf'])}) em olimpíadas científicas {periodo}: "
                 f"{d['alunos']} {plural} de {d['escolas']} escolas, {medalhas}"
                 + (f" na {_lista(siglas[:4])}" if siglas else "") + "."
                 + (f" {d['rank']}ª cidade no ranking nacional." if d.get("rank") else ""))
    escolas = "".join(
        f'<li><a href="/escola/{enderecos.de(ESCOLA, x["id"])}">{e(nome_de_exibicao(x["nome"]))}</a> · {e(_medalhas(x))}</li>'
        for x in d["top_escolas"] if enderecos.de(ESCOLA, x["id"]))
    alunos = "".join(
        f'<li><a href="/aluno/{enderecos.de(ALUNO, a["id"])}">{e(a["nome"])}</a> · {e(_medalhas(a))}</li>'
        for a in d["top_alunos"] if enderecos.de(ALUNO, a["id"]))
    resumo = (f"<h1>{e(nome_uf)}</h1><p>{e(descricao)}</p>"
              + (f"<h2>Escolas com mais medalhas</h2><ol>{escolas}</ol>" if escolas else "")
              + (f"<h2>Alunos com mais medalhas</h2><ol>{alunos}</ol>" if alunos else "")
              + _rodape(base, f"{base}/api/v1/ranking/cidades?uf={d['uf']}"))
    return _montar(titulo, descricao, url, _migalhas(base, nome_uf, url), resumo)


def imagem_de(base: str, url: str) -> str:
    """https://site/aluno/x -> https://site/og/aluno/x.png"""
    return base + "/og" + url[len(base):] + ".png"


def _quote(ident: str) -> str:
    """Id codificado para caber num trecho de URL (| vira %7C, / vira %2F)."""
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
    """nome -> XML de todos os sitemaps: as telas, os perfis em arquivos de até URLS_POR_SITEMAP endereços e o
    índice sitemap.xml. lastmod é a data da última atualização da base."""
    data = (sessao.resumo_base().get("atualizado_em") or "")[:10]
    lastmod = f"<lastmod>{data}</lastmod>" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", data) else ""
    enderecos = sessao.enderecos()

    def urlset(urls: list[str]) -> bytes:
        corpo = "".join(f"<url><loc>{escape_xml(u)}</loc>{lastmod}</url>" for u in urls)
        return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                f"{corpo}</urlset>\n").encode("utf-8")

    telas = [base + c for c, t in TELAS.items() if t.indexar]
    arquivos = {"sitemaps/paginas.xml": urlset([base + "/", *telas])}
    for tipo, plural in ((ALUNO, "alunos"), (ESCOLA, "escolas"), (CIDADE, "cidades")):
        urls = [f"{base}/{tipo}/{e}" for e in enderecos.todos(tipo)]
        for i in range(0, len(urls), URLS_POR_SITEMAP):
            arquivos[f"sitemaps/{plural}-{i // URLS_POR_SITEMAP + 1}.xml"] = urlset(urls[i:i + URLS_POR_SITEMAP])
    indice = "".join(f"<sitemap><loc>{base}/{nome}</loc>{lastmod}</sitemap>" for nome in arquivos)
    arquivos["sitemap.xml"] = ('<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex '
                               f'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{indice}</sitemapindex>\n'
                               ).encode("utf-8")
    return arquivos
