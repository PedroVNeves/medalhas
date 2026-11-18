"""Ponta a ponta com uma base pequena: coletor falso -> gerar_base -> SQLite -> servidor HTTP -> JSON/CSV.

Não usa a base real nem a internet.
"""
import http.client
import json
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock
from urllib.parse import quote

from medalhas.adaptadores.http import imagens, limites
from medalhas.adaptadores.http.servidor import Servidor
from medalhas.adaptadores.sqlite import LeituraSqlite, RepositorioSqlite
from medalhas.aplicacao.gerar_base import gerar_base
from medalhas.aplicacao.portas import Criterios
from medalhas.dominio.escolas import palavras_da_busca


def p(nome, uf, competicao, ano, medalha, nivel="3", escola=None, municipio=None) -> dict:
    return {"competicao": competicao, "ano": ano, "nivel": nivel, "nome": nome, "escola": escola, "rede": None,
            "esfera": None, "municipio": municipio, "uf": uf, "premio": medalha, "medalha": medalha,
            "pontos": None, "fonte": "https://exemplo"}


PREMIACOES = [
    p("MARIA SOUZA LIMA", "AL", "OBMEP", 2018, "Ouro", escola="IFAL - Campus Maceió", municipio="Maceió"),
    p("MARIA SOUZA LIMA", "AL", "OBMEP", 2019, "Prata", "2", escola="Instituto Federal de Alagoas Campus Maceio",
      municipio="MACEIO"),
    p("Maria Souza Lima", "AL", "OBM", 2019, "Bronze"),
    p("JOAO PEREIRA", "AL", "OBMEP", 2019, "Bronze", escola="IFAL Campus Maceió", municipio="Maceió"),
    p("ANA COSTA", "SP", "OBMEP", 2020, "Ouro", escola="ETEC Centro", municipio="São Paulo"),
]


class ColetorFalso:
    def __init__(self, sigla, premiacoes, falhar=False):
        self.sigla, self._premiacoes, self._falhar = sigla, premiacoes, falhar

    def coletar(self, log):
        if self._falhar:
            raise ConnectionError("fora do ar")
        return [dict(x) for x in self._premiacoes]


class TestSemEstado(unittest.TestCase):
    """Premiações de listas sem UF (Itabirana 2020+): sem posição estadual e sem página de escola."""

    def test_sem_posicao_estadual_e_busca_de_escolas_sem_grupo_vazio(self):
        com_uf = p("ANA COSTA", "SP", "OBMEP", 2020, "Ouro", escola="Colégio Kennedy", municipio="São Paulo")
        sem_uf = {**p("ZEBEDEU QUINTANILHA", None, "OITM", 2021, "Ouro", escola="Colégio Kennedy"),
                  "competicao": "OITM"}
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "medalhas.db"
            gerar_base([ColetorFalso("OBMEP", [com_uf]), ColetorFalso("OITM", [sem_uf])],
                       RepositorioSqlite(caminho), log=lambda _: None)
            with LeituraSqlite(caminho).sessao() as s:
                perfil = s.perfil_aluno("ZEBEDEU QUINTANILHA|", {"metodo": "site"})
                self.assertIsNotNone(perfil["rank"])
                self.assertIsNone(perfil["rank_uf"])   # "sem estado" não é um estado
                self.assertEqual(perfil["rank_uf_total"], 0)
                total, escolas = s.buscar_escolas(Criterios({}, (("escola", palavras_da_busca("kennedy")),)),
                                                  "p_site", 0, 10)
                self.assertEqual((total, len(escolas)), (1, 1))   # a premiação sem UF não vira escola


class TestPontaAPonta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.TemporaryDirectory()
        caminho = Path(cls.pasta.name) / "medalhas.db"
        cls.relatorio = gerar_base([ColetorFalso("OBMEP", PREMIACOES), ColetorFalso("OBI", [], falhar=True)],
                                   RepositorioSqlite(caminho), log=lambda _: None, permitir_parcial=True)
        cls.servidor = Servidor(("127.0.0.1", 0), LeituraSqlite(caminho))
        cls.base = f"http://127.0.0.1:{cls.servidor.server_address[1]}"
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()
        cls.pasta.cleanup()

    def get(self, caminho: str) -> tuple[int, dict, bytes]:
        try:
            with urllib.request.urlopen(self.base + caminho, timeout=10) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def json(self, caminho: str, status: int = 200) -> dict:
        codigo, _, corpo = self.get(caminho)
        self.assertEqual(codigo, status, corpo[:300])
        return json.loads(corpo)

    def test_fonte_fora_do_ar_nao_derruba_a_geracao(self):
        self.assertEqual(self.relatorio.premiacoes, len(PREMIACOES))
        self.assertEqual(len(self.relatorio.falhas), 1)
        self.assertIn("OBI", self.relatorio.falhas[0])

    def test_busca_de_aluno_reune_as_premiacoes(self):
        r = self.json("/api/v1/alunos?nome=maria+lima")
        self.assertEqual(r["total"], 1)
        aluno = r["alunos"][0]
        self.assertEqual(aluno["id"], "MARIA SOUZA LIMA|AL")
        self.assertEqual(aluno["nome"], "Maria Souza Lima")   # grafia da OBM, com caixa mista
        self.assertEqual(aluno["medalhas"]["total"], 3)
        self.assertEqual(aluno["pontos"]["impa3"], 18 + 2)    # ouro OBMEP e bronze OBM no Nível 3; a prata N2 não
        self.assertEqual(len(aluno["escolas"]), 1)            # duas grafias do IFAL: a mesma escola

    def test_escola_por_sigla_e_medalhistas(self):
        escolas = self.json("/api/v1/escolas?nome=ifal")["escolas"]
        self.assertEqual(len(escolas), 1)
        r = self.json(f"/api/v1/escolas/{quote(escolas[0]['id'], safe='')}/medalhistas")
        self.assertEqual(sorted(m["nome"] for m in r["medalhistas"]), ["Joao Pereira", "Maria Souza Lima"])

    def test_ranking_por_estado(self):
        r = self.json("/api/v1/ranking/estados?metodo=site")
        self.assertEqual([i["id"] for i in r["itens"]], ["AL", "SP"])
        self.assertEqual(r["itens"][0]["posicao"], 1)

    def test_paginas_do_site(self):
        self.assertIn("totais", self.json("/api/overview"))
        self.assertEqual(self.json("/api/busca?q=costa")["total"], 1)
        self.assertEqual(self.json("/api/aluno?id=" + quote("ANA COSTA|SP"))["nome"], "Ana Costa")

    def test_sugestoes_enquanto_digita(self):
        r = self.json("/api/sugestoes?q=ma&campo=nome")
        self.assertEqual([a["id"] for a in r["alunos"]], ["MARIA SOUZA LIMA|AL"])   # início de palavra: não "ANA"
        self.assertEqual(r["alunos"][0]["ouro"], 1)
        self.assertEqual(r["escolas"], [])
        # sigla casa pela expansão; em "tudo" vêm alunos e escolas, os mais premiados primeiro
        self.assertEqual(len(self.json("/api/sugestoes?q=instituto+federal&campo=escola")["escolas"]), 1)
        self.assertEqual(len(self.json("/api/sugestoes?q=ifal&campo=escola")["escolas"]), 1)
        tudo = self.json("/api/sugestoes?q=costa&campo=tudo")
        self.assertEqual([a["nome"] for a in tudo["alunos"]], ["Ana Costa"])
        self.assertEqual(self.json("/api/sugestoes?q=m"), {"alunos": [], "escolas": []})   # curto demais
        _, cab, _ = self.get("/api/sugestoes?q=maria")
        self.assertIn("s-maxage", cab["Cache-Control"])   # o CDN guarda: sem consulta a cada letra repetida

    def test_filtro_de_meninas(self):
        # na base de teste ninguém fez EGMO, PAGMO ou EGOI: o filtro fica vazio em vez de adivinhar pelo nome
        self.assertEqual(self.json("/api/v1/ranking/alunos?sexo=F")["total"], 0)
        self.assertIn("sexo", self.json("/api/v1/ranking/alunos?sexo=M", 400)["erro"])
        aluno = self.json("/api/v1/alunos?nome=maria+lima")["alunos"][0]
        self.assertNotIn("sexo", json.dumps(aluno))

    def test_exportacao_filtrada_em_csv(self):
        status, cab, corpo = self.get("/api/v1/exportar?aluno_id=" + quote("MARIA SOUZA LIMA|AL", safe=""))
        self.assertEqual(status, 200)
        self.assertEqual(cab["X-Total-Rows"], "3")
        self.assertIn("attachment", cab["Content-Disposition"])
        linhas = corpo.decode("utf-8-sig").splitlines()
        self.assertEqual(len(linhas), 4)   # cabeçalho + 3 premiações
        self.assertTrue(linhas[0].startswith("id,olimpiada,"))

    def test_erros(self):
        self.assertIn("erro", self.json("/api/v1/alunos", 400))
        self.assertIn("UF inválida", self.json("/api/v1/alunos?nome=ana&uf=XX", 400)["erro"])
        self.json("/api/v1/alunos/" + quote("NINGUEM|SP", safe=""), 404)
        self.json("/api/v1/ranking/planetas", 404)
        self.json("/api/v1/nada", 404)

    def test_links_usam_o_dominio_publico_atras_do_proxy(self):
        caminho = "/api/v1/alunos?nome=costa"
        cabecalhos = {"X-Forwarded-Host": "medalhas.exemplo.com.br", "X-Forwarded-Proto": "https"}
        pedido = urllib.request.Request(self.base + caminho, headers=cabecalhos)
        self.servidor.confiar_proxy = True
        aceitos = self.servidor.hosts_publicos
        self.servidor.hosts_publicos = (*aceitos, "medalhas.exemplo.com.br")
        try:
            with urllib.request.urlopen(pedido, timeout=10) as r:
                corpo = r.read().decode()
            # domínio que não é do site (cabeçalho forjado por quem chama o servidor direto): endereço oficial
            forjado = urllib.request.Request(self.base + caminho, headers={"X-Forwarded-Host": "malicioso.example"})
            with urllib.request.urlopen(forjado, timeout=10) as r:
                self.assertNotIn("malicioso.example", r.read().decode())
        finally:
            self.servidor.confiar_proxy = False
            self.servidor.hosts_publicos = aceitos
        self.assertIn("https://medalhas.exemplo.com.br/api/v1/alunos/", corpo)
        # sem --trust-proxy o cabeçalho é ignorado (qualquer um poderia forjá-lo)
        with urllib.request.urlopen(urllib.request.Request(self.base + caminho, headers=cabecalhos)) as r:
            self.assertNotIn("medalhas.exemplo.com.br", r.read().decode())

    def test_arquivos_estaticos(self):
        self.assertEqual(self.get("/")[0], 200)
        self.assertEqual(self.get("/js/app.js")[0], 200)
        self.assertEqual(self.get("/../server.py")[0], 404)

    def test_json_compactado_quando_o_cliente_aceita_gzip(self):
        import gzip
        pedido = urllib.request.Request(self.base + "/api/overview", headers={"Accept-Encoding": "gzip"})
        with urllib.request.urlopen(pedido, timeout=10) as r:
            self.assertEqual(r.headers["Content-Encoding"], "gzip")
            self.assertIn("Accept-Encoding", r.headers["Vary"])
            dados = json.loads(gzip.decompress(r.read()))
        _, cab, corpo = self.get("/api/overview")   # sem Accept-Encoding: texto puro, mesmo conteúdo
        self.assertNotIn("Content-Encoding", cab)
        self.assertEqual(json.loads(corpo), dados)

    def test_visao_geral_pode_ficar_no_cdn(self):
        _, cab, _ = self.get("/api/overview")
        self.assertIn("s-maxage=", cab["Cache-Control"])
        self.assertNotIn("X-RateLimit-Remaining", cab)   # a cota é de um IP: não pode ir para o cache
        _, cab, _ = self.get("/api/busca?q=maria")
        self.assertEqual(cab["Cache-Control"], "no-cache")


    def sem_redirecionar(self, caminho: str) -> tuple[int, dict]:
        con = http.client.HTTPConnection("127.0.0.1", self.servidor.server_address[1], timeout=10)
        try:
            con.request("GET", caminho)
            r = con.getresponse()
            return r.status, dict(r.getheaders())
        finally:
            con.close()

    def test_pagina_do_aluno_tem_titulo_e_resumo(self):
        status, cab, corpo = self.get("/aluno/maria-souza-lima-al")
        self.assertEqual(status, 200)
        pagina = corpo.decode()
        self.assertRegex(pagina, r"<title>Maria Souza Lima \(AL\): medalhas na OBMEP e OBM · Medalhas</title>")
        self.assertIn('<link rel="canonical" href="https://medalhas.online/aluno/maria-souza-lima-al">', pagina)
        self.assertIn("1 ouro, 1 prata e 1 bronze", re.search(r'name="description" content="([^"]*)"', pagina)[1])
        self.assertIn("2018 · OBMEP · Ouro", pagina)                # resumo para quem não roda JavaScript
        self.assertIn('"@type": "BreadcrumbList"', pagina)
        self.assertNotIn('"@type": "Dataset"', pagina)              # o conjunto de dados é só da página inicial
        self.assertIn("s-maxage", cab["Cache-Control"])

    def test_pagina_da_escola_redireciona_para_o_endereco_oficial(self):
        escola = self.json("/api/v1/escolas?nome=etec")["escolas"][0]
        status, cab = self.sem_redirecionar("/escola/" + re.sub(r"[^a-z0-9]+", "-", escola["id"].lower()).strip("-"))
        self.assertEqual(status, 301)
        self.assertTrue(cab["Location"].startswith("/escola/etec-centro-"), cab["Location"])
        status, _, corpo = self.get(cab["Location"])
        self.assertEqual(status, 200)
        self.assertIn("Ana Costa", corpo.decode())

    def test_pagina_inexistente(self):
        status, _, corpo = self.get("/aluno/ninguem-xx")
        self.assertEqual(status, 404)
        self.assertIn('content="noindex"', corpo.decode())

    def test_perfil_pelo_endereco(self):
        r = self.json("/api/aluno?endereco=maria-souza-lima-al")
        self.assertEqual(r["id"], "MARIA SOUZA LIMA|AL")
        self.assertEqual(r["endereco"], "/aluno/maria-souza-lima-al")

    def test_sitemap_dividido_em_fatias(self):
        from medalhas.adaptadores.http import paginas
        with mock.patch.object(paginas, "URLS_POR_SITEMAP", 1):   # um endereço por arquivo
            indice = self.get("/sitemap.xml")[2].decode()
            arquivos = re.findall(r"<loc>https://medalhas.online/(sitemaps/alunos-\d+\.xml)</loc>", indice)
            enderecos = [re.findall(r"<loc>([^<]+)</loc>", self.get("/" + a)[2].decode()) for a in arquivos]
        self.assertGreater(len(arquivos), 1)
        self.assertTrue(all(len(e) == 1 for e in enderecos))
        todos = [e[0] for e in enderecos]
        self.assertEqual(todos, sorted(set(todos)))   # em ordem, sem repetir nem pular

    def test_sitemap(self):
        status, cab, corpo = self.get("/sitemap.xml")
        self.assertEqual(status, 200)
        self.assertIn("xml", cab["Content-Type"])
        arquivos = re.findall(r"<loc>https://medalhas.online/([^<]+)</loc>", corpo.decode())
        self.assertEqual(arquivos, ["sitemaps/paginas.xml", "sitemaps/alunos-1.xml", "sitemaps/escolas-1.xml",
                                    "sitemaps/cidades-1.xml"])
        self.assertIn("<loc>https://medalhas.online/cidade/maceio-al</loc>",
                      self.get("/sitemaps/cidades-1.xml")[2].decode())
        alunos = self.get("/sitemaps/alunos-1.xml")[2].decode()
        self.assertIn("<loc>https://medalhas.online/aluno/maria-souza-lima-al</loc>", alunos)
        self.assertEqual(self.get("/sitemaps/nada.xml")[0], 404)
        self.assertIn("<loc>https://medalhas.online/sobre</loc>", self.get("/sitemaps/paginas.xml")[2].decode())

    def test_ranking_e_pagina_de_cidade(self):
        r = self.json("/api/v1/ranking/cidades?metodo=site")
        self.assertEqual([(i["nome"], i["uf"]) for i in r["itens"]], [("Maceió", "AL"), ("São Paulo", "SP")])
        self.assertEqual(r["itens"][0]["alunos_premiados"], 2)   # Maria e João (a OBM de Maria não tem cidade)
        self.assertTrue(r["itens"][0]["perfil"].endswith("/cidade/maceio-al"))
        cidade = self.json("/api/cidade?endereco=maceio-al")
        self.assertEqual((cidade["nome"], cidade["rank"], cidade["rank_uf"], cidade["escolas"]), ("Maceió", 1, 1, 1))
        self.assertEqual([a["nome"] for a in cidade["top_alunos"]], ["Maria Souza Lima", "Joao Pereira"])
        self.assertEqual(self.json("/api/cidade?endereco=nao-existe-xx")["erro"], "Cidade não encontrada")
        status, _, corpo = self.get("/cidade/maceio-al")
        self.assertEqual(status, 200)
        pagina = corpo.decode()
        self.assertIn("<title>Medalhistas de Maceió (AL) em olimpíadas · Medalhas</title>", pagina)
        self.assertIn('href="/aluno/maria-souza-lima-al"', pagina)
        self.assertEqual(self.get("/cidade/nada-xx")[0], 404)
        self.assertEqual(self.get("/og/cidade/maceio-al.png")[0], 404)   # cidades usam a imagem do site
        csv = self.get("/api/v1/exportar?conjunto=cidades")
        self.assertEqual(csv[0], 200)

    def test_pagina_de_erro_em_enderecos_de_pagina(self):
        from unittest import mock

        from medalhas.adaptadores.http import paginas
        with mock.patch.object(paginas, "tela", side_effect=RuntimeError("bug")):
            status, cab, corpo = self.get("/sobre")
        self.assertEqual(status, 500)
        self.assertIn("text/html", cab["Content-Type"])
        pagina = corpo.decode()
        self.assertIn("Algo deu errado", pagina)
        self.assertNotIn("{{", pagina)   # todos os marcadores preenchidos
        with mock.patch.object(paginas, "tela", side_effect=RuntimeError("bug")):
            self.assertEqual(self.get("/api/v1/olimpiadas")[0], 200)   # a API segue com JSON, sem a página

    def test_pagina_sobre(self):
        status, cab, corpo = self.get("/sobre")
        self.assertEqual(status, 200)
        pagina = corpo.decode()
        self.assertIn("<title>Sobre o Medalhas: por que reunimos os medalhistas das olimpíadas</title>", pagina)
        self.assertIn('<link rel="canonical" href="https://medalhas.online/sobre">', pagina)
        self.assertIn('"@type": "AboutPage"', pagina)
        resumo = re.search(r"<noscript>(.*?)</noscript>", pagina, re.S)[1]   # o texto da tela, sem JavaScript
        self.assertIn("Por que o Medalhas existe", resumo)
        self.assertIn("projeto independente", resumo)
        self.assertIn("mailto:", resumo)                                     # contato para correção e remoção
        self.assertNotIn("x-text", resumo)
        self.assertIn("s-maxage", cab["Cache-Control"])

    def test_telas_com_endereco_proprio(self):
        status, _, corpo = self.get("/ranking/alunos")
        self.assertEqual(status, 200)
        pagina = corpo.decode()
        self.assertIn('<link rel="canonical" href="https://medalhas.online/ranking/alunos">', pagina)
        self.assertIn('<a href="/aluno/maria-souza-lima-al">Maria Souza Lima</a>', pagina)   # ranking sem JavaScript
        self.assertIn("Alagoas", self.get("/ranking/estados")[2].decode())
        self.assertIn("/escola/", self.get("/ranking/escolas")[2].decode())
        self.assertIn('content="noindex"', self.get("/busca?q=ana")[2].decode())   # resultado de busca fica fora
        self.assertEqual(self.get("/dados/")[0], 200)                               # barra no fim também vale
        status, cab = self.sem_redirecionar("/ranking")
        self.assertEqual((status, cab["Location"]), (301, "/ranking/alunos"))
        sitemap = self.get("/sitemaps/paginas.xml")[2].decode()
        self.assertIn("<loc>https://medalhas.online/ranking/escolas</loc>", sitemap)
        self.assertNotIn("/busca", sitemap)

    def test_titulos_do_site_iguais_aos_do_servidor(self):
        from medalhas.adaptadores.http.paginas import TELAS
        app_js = (Path(__file__).parent.parent / "web" / "js" / "app.js").read_text(encoding="utf-8")
        for caminho, tela in TELAS.items():
            self.assertIn(f'"{caminho}": "{tela.titulo}"', app_js)

    def test_links_da_api_para_o_site_usam_o_endereco_real(self):
        aluno = self.json("/api/v1/alunos?nome=maria+souza")["alunos"][0]
        self.assertEqual(aluno["perfil"], f"{self.base}/aluno/maria-souza-lima-al")

    def test_endereco_inexistente(self):
        status, cab, corpo = self.get("/nada/aqui")
        self.assertEqual(status, 404)
        self.assertIn("Página não encontrada", corpo.decode())
        self.assertIn('content="noindex"', corpo.decode())
        self.assertEqual(self.get("/ranking/planetas")[0], 404)

    def test_paginas_apontam_para_a_imagem_de_compartilhamento(self):
        aluno = self.get("/aluno/maria-souza-lima-al")[2].decode()
        self.assertIn('<meta property="og:image" content="https://medalhas.online/og/aluno/maria-souza-lima-al.png">',
                      aluno)
        self.assertIn('<meta name="twitter:card" content="summary_large_image">', aluno)
        self.assertIn('content="https://medalhas.online/og/site.png"', self.get("/sobre")[2].decode())

    @unittest.skipUnless(imagens.DISPONIVEL, "Pillow não instalado")
    def test_imagens_de_compartilhamento(self):
        for caminho in ("/og/aluno/maria-souza-lima-al.png", "/og/site.png"):
            status, cab, corpo = self.get(caminho)
            self.assertEqual(status, 200, caminho)
            self.assertEqual(cab["Content-Type"], "image/png")
            self.assertTrue(corpo.startswith(b"\x89PNG"))
            largura, altura = int.from_bytes(corpo[16:20], "big"), int.from_bytes(corpo[20:24], "big")
            self.assertEqual((largura, altura), (1200, 630))
            self.assertIn("s-maxage", cab["Cache-Control"])
        escola = self.json("/api/v1/escolas?nome=etec")["escolas"][0]
        endereco = re.sub(r"[^a-z0-9]+", "-", escola["id"].lower()).strip("-")
        self.assertEqual(self.get(f"/og/escola/{endereco}.png")[0],
                         200)
        self.assertEqual(self.get("/og/aluno/ninguem-xx.png")[0], 404)
        # story do Instagram: vertical, 1080×1920
        corpo = self.get("/og/story/aluno/maria-souza-lima-al.png")[2]
        self.assertEqual((int.from_bytes(corpo[16:20], "big"), int.from_bytes(corpo[20:24], "big")), (1080, 1920))
        self.assertEqual(self.get("/og/story/aluno/ninguem-xx.png")[0], 404)
        self.assertEqual(self.get("/og/story/planeta/x.png")[0], 404)
        self.assertEqual(self.get("/og/planeta/x.png")[0], 404)

    def test_css_gerado_no_build(self):
        web = Path(__file__).parent.parent / "web"
        css = (web / "css" / "site.css").read_text(encoding="utf-8")
        self.assertIn(".bg-ink-900", css)   # cor própria do tema: o CSS veio da nossa configuração
        for pagina in ("index.html", "404.html"):
            html = (web / pagina).read_text(encoding="utf-8")
            self.assertIn('href="/css/site.css"', html)
            self.assertNotIn("cdn.tailwindcss.com", html)


class TestRevisao(TestPontaAPonta):
    """Comportamentos que entraram com a revisão do back-end, de ponta a ponta."""

    def test_busca_devolve_os_grupos_ja_somados(self):
        d = self.json("/api/busca?q=maria&metodo=site")
        self.assertEqual((d["total"], d["total_grupos"]), (3, 1))
        maria = d["grupos"][0]
        self.assertEqual((maria["id"], maria["ouro"], maria["prata"], maria["bronze"], maria["total"]),
                         ("MARIA SOUZA LIMA|AL", 1, 1, 1, 3))
        self.assertEqual((maria["nome"], maria["uf"]), ("Maria Souza Lima", "AL"))   # da ficha do aluno
        self.assertEqual(len({r["id"] for r in maria["premiacoes"]}), 3)   # id da premiação: chave das listas da tela
        self.assertEqual([r["ano"] for r in maria["premiacoes"]], sorted((r["ano"] for r in maria["premiacoes"]),
                                                                          reverse=True))   # mais recentes primeiro
        # só o que a linha do cartão mostra: nada de pontos, rede, campos de busca
        usados = {"id", "ano", "competicao", "medalha", "premio", "nivel", "fonte", "escola", "escola_chave",
                  "municipio", "uf"}
        self.assertTrue(all(set(r) <= usados for r in maria["premiacoes"]))
        self.assertNotIn("xp", maria)
        escolas = self.json("/api/busca?q=ifal&campo=escola")
        self.assertEqual([g["total"] for g in escolas["grupos"]], [3])   # as três grafias, uma escola só

    def test_busca_pagina_os_cartoes(self):
        from medalhas.adaptadores.sqlite import consultas_site
        with mock.patch.object(consultas_site, "GRUPOS_POR_PAGINA_BUSCA", 1):
            todos = self.json("/api/busca?uf=AL")
            seguinte = self.json("/api/busca?uf=AL&offset=1")
        self.assertEqual(len(todos["grupos"]), 1)
        self.assertGreater(todos["total_grupos"], 1)
        self.assertFalse({g["id"] for g in todos["grupos"]} & {g["id"] for g in seguinte["grupos"]})

    def test_limite_negativo_nao_devolve_o_ranking_inteiro(self):
        self.assertEqual(self.json("/api/ranking?tipo=alunos&limite=-1")["itens"], [])
        self.json("/api/ranking?limite=abc", 400)
        self.json("/api/v1/premiacoes?ano=99999999999999999999999", 400)
        self.assertEqual(self.json("/api/v1/premiacoes?offset=999999999999")["premiacoes"], [])

    def test_exportar_ranking_recusa_filtro_que_nao_se_aplica(self):
        erro = self.json("/api/v1/exportar?conjunto=estados&nome=maria", 400)["erro"]
        self.assertIn("conjunto=premiacoes", erro)

    def test_ip_do_visitante_e_contado_da_direita(self):
        self.servidor.confiar_proxy, self.servidor.saltos_proxy = True, 2
        try:
            with mock.patch.dict(limites.GRUPOS, {"v1": {"quantidade": 2, "janela": 3600, "por_dia": None}}):
                def chamar(forjado: str) -> int:
                    pedido = urllib.request.Request(
                        self.base + "/api/v1/olimpiadas",
                        headers={"X-Forwarded-For": f"{forjado}, 203.0.113.9, 10.0.0.1"})
                    try:
                        with urllib.request.urlopen(pedido, timeout=10) as r:
                            return r.status
                    except urllib.error.HTTPError as e:
                        return e.code
                # trocar o valor da esquerda (o que o cliente manda) não dá cota nova
                self.assertEqual([chamar("1.1.1.1"), chamar("2.2.2.2"), chamar("3.3.3.3")], [200, 200, 429])
        finally:
            self.servidor.confiar_proxy, self.servidor.saltos_proxy = False, 1

    def test_base_nao_e_gravada_com_fonte_faltando(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "medalhas.db"
            relatorio = gerar_base([ColetorFalso("OBMEP", PREMIACOES), ColetorFalso("OBI", [])],
                                   RepositorioSqlite(caminho), log=lambda _: None)
            self.assertFalse(relatorio.gravada)
            self.assertIn("OBI", relatorio.falhas[0])   # fonte que não devolve nada também é falha
            self.assertFalse(caminho.exists())

    def test_base_nao_e_gravada_se_uma_olimpiada_encolhe_muito(self):
        with tempfile.TemporaryDirectory() as pasta:
            repositorio = RepositorioSqlite(Path(pasta) / "medalhas.db")
            self.assertEqual(repositorio.premiacoes_por_olimpiada(), {})   # ainda não há base
            completa = [ColetorFalso("OBMEP", PREMIACOES)]
            self.assertTrue(gerar_base(completa, repositorio, log=lambda _: None).gravada)
            total = repositorio.premiacoes_por_olimpiada()["OBMEP"]

            pela_metade = [ColetorFalso("OBMEP", PREMIACOES[:len(PREMIACOES) // 2])]
            relatorio = gerar_base(pela_metade, repositorio, log=lambda _: None)
            self.assertFalse(relatorio.gravada)
            self.assertIn("queda", relatorio.falhas[0])
            self.assertEqual(repositorio.premiacoes_por_olimpiada()["OBMEP"], total)   # a base anterior ficou
            # perder uma linha ou outra (correção da lista oficial) não é falha; e dá para forçar
            self.assertTrue(gerar_base(pela_metade, repositorio, log=lambda _: None, permitir_parcial=True).gravada)

    def test_posicao_do_perfil_e_a_da_lista(self):
        lista = {i["id"]: i["pos"] for i in self.json("/api/ranking?tipo=alunos&metodo=site")["itens"]}
        for ident, pos in lista.items():
            self.assertEqual(self.json("/api/aluno?metodo=site&id=" + quote(ident))["rank"], pos)



class TestGrafiasJuntadas(unittest.TestCase):
    """Perfis de grafias diferentes juntados (identidade.juntar_grafias): o endereço antigo leva ao perfil que
    ficou, e o nome exibido é a grafia do id, mesmo quando a premiação mais recente é a abreviada."""

    def test_endereco_antigo_e_nome_exibido(self):
        premiacoes = [p(nome, "AL", "OBMEP", ano, medalha, nivel, escola="EE Um", municipio="Maceió")
                      for nome, ano, medalha, nivel in (("ZULEICA MARTA PRADO LINS", 2020, "Ouro", "1"),
                                                        ("ZULEICA MARTA P LINS", 2021, "Prata", "2"))]
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "medalhas.db"
            gerar_base([ColetorFalso("OBMEP", premiacoes)], RepositorioSqlite(caminho), log=lambda _: None)
            with LeituraSqlite(caminho).sessao() as s:
                self.assertEqual(s.enderecos().resolver("aluno", "zuleica-marta-p-lins-al"),
                                 ("ZULEICA MARTA PRADO LINS|AL", "zuleica-marta-prado-lins-al"))
                resumo, lista = s.aluno("ZULEICA MARTA PRADO LINS|AL", Criterios())
                self.assertIsNone(s.aluno("ZULEICA MARTA P LINS|AL", Criterios()))
        self.assertEqual((resumo["nome"], resumo["total"], len(lista)), ("Zuleica Marta Prado Lins", 2, 2))


class TestPerfisQueSumiram(unittest.TestCase):
    """Um perfil da base anterior que deixa de existir (as regras de identidade mudaram) continua acessível pelo
    endereço antigo, que leva ao perfil que ficou com as premiações dele."""

    def test_endereco_antigo_leva_ao_perfil_que_ficou(self):
        def base(ano_do_ouro):
            return [p("TEODORA VILAR", "AL", "OBMEP", ano_do_ouro, "Ouro", "1", escola="EE Um", municipio="Maceió"),
                    p("TEODORA VILAR", "AL", "OBMEP", 2021, "Prata", "2", escola="EE Um", municipio="Maceió"),
                    p("TEODORA VILAR", "AL", "OBMEP", 2020, "Bronze", "1", escola="EE Dois", municipio="Arapiraca")]
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "medalhas.db"
            # a mesma edição (2020) em duas cidades: homônimas, e a menor ganha a cidade no id
            gerar_base([ColetorFalso("OBMEP", base(2020))], RepositorioSqlite(caminho), log=lambda _: None)
            with LeituraSqlite(caminho).sessao() as s:
                self.assertIsNotNone(s.enderecos().resolver("aluno", "teodora-vilar-al-arapiraca"))
            # na geração seguinte o ouro é de 2019: tudo cabe numa pessoa só e o perfil com a cidade some,
            # com o bronze dele intacto
            gerar_base([ColetorFalso("OBMEP", base(2019))], RepositorioSqlite(caminho), log=lambda _: None)
            with LeituraSqlite(caminho).sessao() as s:
                self.assertEqual(s.enderecos().resolver("aluno", "teodora-vilar-al-arapiraca"),
                                 ("TEODORA VILAR|AL", "teodora-vilar-al"))


class TestPerfisSoComMencao(unittest.TestCase):
    """Perfis só com menções da OBMEP existem e aparecem na busca, mas ficam fora do sitemap e com noindex."""

    def test_fora_do_google(self):
        from medalhas.adaptadores.http import paginas
        premiacoes = [p("BIA MEDALHA COSTA", "AL", "OBMEP", 2020, "Ouro", escola="EE Um", municipio="Maceió"),
                      p("CAIO SO MENCAO", "AL", "OBMEP", 2020, "Menção Honrosa", escola="EE Dois", municipio="Maceió")]
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "medalhas.db"
            gerar_base([ColetorFalso("OBMEP", premiacoes)], RepositorioSqlite(caminho), log=lambda _: None)
            with LeituraSqlite(caminho).sessao() as s:
                medalhista = paginas.perfil(s, "aluno", "bia-medalha-costa-al", "https://x").corpo.decode()
                so_mencao = paginas.perfil(s, "aluno", "caio-so-mencao-al", "https://x").corpo.decode()
                sitemap = paginas.sitemap(s, "sitemaps/alunos-1.xml", "https://x").decode()
                escolas = paginas.sitemap(s, "sitemaps/escolas-1.xml", "https://x").decode()
        self.assertIn('content="index, follow"', medalhista)
        self.assertIn('content="noindex"', so_mencao)
        self.assertIn("bia-medalha-costa-al", sitemap)
        self.assertNotIn("caio-so-mencao-al", sitemap)
        self.assertEqual(escolas.count("<loc>"), 1)   # a escola só com menção também fica de fora


class TestRankingPeloBanco(unittest.TestCase):
    """O ranking que o banco ordena e pagina (consultas_ranking) dá as mesmas posições que a definição de
    referência em Python (dominio.ranking.ordenar e posicionar), com empates de propósito."""

    @classmethod
    def setUpClass(cls):
        import random
        sorteio = random.Random(7)
        cidades = [("Maceió", "AL"), ("Arapiraca", "AL"), ("Recife", "PE"), ("Sobral", "CE")]
        premiacoes = []
        for i in range(400):
            municipio, uf = sorteio.choice(cidades)
            competicao = sorteio.choice(["OBMEP", "OBMEP", "OBM"])
            premiacoes.append(p(f"ALUNO {sorteio.randrange(60)} SILVA", uf, competicao,
                                sorteio.randrange(2010, 2016),
                                sorteio.choice(["Ouro", "Prata", "Bronze", "Menção Honrosa"]),
                                escola=f"Escola {sorteio.randrange(12)}", municipio=municipio,
                                nivel=sorteio.choice(["1", "2", "3"])))
        cls.pasta = tempfile.TemporaryDirectory()
        caminho = Path(cls.pasta.name) / "medalhas.db"
        gerar_base([ColetorFalso("OBMEP", [x for x in premiacoes if x["competicao"] == "OBMEP"]),
                    ColetorFalso("OBM", [x for x in premiacoes if x["competicao"] == "OBM"])],
                   RepositorioSqlite(caminho), log=lambda _: None)
        cls.leitura = LeituraSqlite(caminho)

    @classmethod
    def tearDownClass(cls):
        cls.pasta.cleanup()

    def referencia(self, sessao, tipo, ordem, metodo, uf=None):
        """id -> posição, calculada em Python a partir das premiações do recorte."""
        from medalhas.dominio import pontuacao, ranking
        _, coluna = pontuacao.resolver_metodo(metodo)
        niveis = (pontuacao.restringir_niveis(metodo, None) or "").split(",")
        chave = {"alunos": "aluno_id", "escolas": "escola_chave", "estados": "uf",
                 "cidades": "municipio_busca || '|' || uf"}[tipo]
        itens: dict = {}
        for r in sessao._con.execute(f"SELECT {chave} AS id, medalha, nivel, uf, municipio_busca, escola_chave, "
                                     f"p_impa3, {coluna} AS pts FROM medalhas"):
            if (uf and r["uf"] != uf) or not r["id"] or (tipo == "cidades" and not r["municipio_busca"]):
                continue
            if metodo == "impa3" and (r["p_impa3"] <= 0 or r["nivel"] not in niveis):
                continue
            it = itens.setdefault(r["id"], {"id": r["id"], "nome": "", "p": 0, "ouro": 0, "prata": 0, "bronze": 0})
            it["p"] += r["pts"] or 0
            campo = {"Ouro": "ouro", "Prata": "prata", "Bronze": "bronze"}.get(r["medalha"])
            if campo:
                it[campo] += 1
        ordenados = ranking.ordenar(list(itens.values()), ordem, "p")
        return {i["id"]: pos for pos, i in ranking.posicionar(ordenados, ranking.chave_de_ordenacao(ordem, "p"))}

    def test_mesmas_posicoes_que_a_referencia(self):
        from medalhas.adaptadores.sqlite import consultas_ranking
        with self.leitura.sessao() as s:
            for tipo in ("alunos", "escolas", "estados", "cidades"):
                for ordem in ("xp", "medalhas", "total"):
                    for metodo in ("impa", "impa3", "site"):
                        for uf in (None, "AL"):
                            with self.subTest(tipo=tipo, ordem=ordem, metodo=metodo, uf=uf):
                                params = {"tipo": tipo, "ordem": ordem, "metodo": metodo, "uf": uf}
                                pagina = consultas_ranking.pagina(s._con, params, 0, 500)
                                esperado = self.referencia(s, tipo, ordem, metodo, uf)
                                self.assertEqual({i["id"]: i["pos"] for i in pagina.itens}, esperado)
                                self.assertEqual(pagina.total, len(esperado))
                                # paginar não muda nada: a 2ª página continua de onde a 1ª parou
                                dividida = (consultas_ranking.pagina(s._con, params, 0, 7).itens
                                            + consultas_ranking.pagina(s._con, params, 7, 500).itens)
                                self.assertEqual([i["id"] for i in dividida], [i["id"] for i in pagina.itens])

    def test_com_filtros_paginas_pequenas_e_posicao_do_perfil(self):
        # com filtros, alunos e cidades numeram só a página: o empate na virada de página e a posição de um item
        # sozinho têm de dar o mesmo que a lista inteira
        from medalhas.adaptadores.sqlite import consultas_ranking
        with self.leitura.sessao() as s:
            for tipo in ("alunos", "cidades"):
                for ordem in ("xp", "medalhas", "total"):
                    for filtros in ({"uf": "AL"}, {"ano_de": "2012", "competicao": "OBMEP"}):
                        with self.subTest(tipo=tipo, ordem=ordem, filtros=filtros):
                            params = {"tipo": tipo, "ordem": ordem, "metodo": "site", **filtros}
                            inteira = consultas_ranking.pagina(s._con, params, 0, 500)
                            for tamanho in (1, 2, 3, 4):
                                em_partes = [i for o in range(0, inteira.total + tamanho, tamanho)
                                             for i in consultas_ranking.pagina(s._con, params, o, tamanho).itens]
                                self.assertEqual([(i["id"], i["pos"]) for i in em_partes],
                                                 [(i["id"], i["pos"]) for i in inteira.itens])
                            for i in inteira.itens:
                                self.assertEqual(consultas_ranking.posicao(s._con, params, i["id"]),
                                                 (i["pos"], inteira.total))
                            self.assertEqual(consultas_ranking.posicao(s._con, params, "NINGUEM|AL"),
                                             (None, inteira.total))

    def test_tela_recebe_so_os_campos_que_mostra(self):
        from medalhas.adaptadores.sqlite import consultas_site
        with self.leitura.sessao() as s:
            item = consultas_site.ranking(s._con, {"tipo": "alunos"})["itens"][0]
            self.assertEqual(set(item), {"id", "pos", "xp", "ouro", "prata", "bronze", "mencao", "nome", "uf",
                                         "escola", "municipio", "de", "ate", "tier"})
            self.assertEqual(set(item["tier"]), {"nome", "cor"})

if __name__ == "__main__":
    unittest.main()
