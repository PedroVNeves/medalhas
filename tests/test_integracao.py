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
from urllib.parse import quote

from medalhas.adaptadores.http.servidor import Servidor
from medalhas.adaptadores.sqlite import LeituraSqlite, RepositorioSqlite
from medalhas.aplicacao.gerar_base import gerar_base


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


class TestPontaAPonta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.TemporaryDirectory()
        caminho = Path(cls.pasta.name) / "medalhas.db"
        cls.relatorio = gerar_base([ColetorFalso("OBMEP", PREMIACOES), ColetorFalso("OBI", [], falhar=True)],
                                   RepositorioSqlite(caminho), log=lambda _: None)
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
        try:
            with urllib.request.urlopen(pedido, timeout=10) as r:
                corpo = r.read().decode()
        finally:
            self.servidor.confiar_proxy = False
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

    def test_sitemap(self):
        status, cab, corpo = self.get("/sitemap.xml")
        self.assertEqual(status, 200)
        self.assertIn("xml", cab["Content-Type"])
        arquivos = re.findall(r"<loc>https://medalhas.online/([^<]+)</loc>", corpo.decode())
        self.assertEqual(arquivos, ["sitemaps/paginas.xml", "sitemaps/alunos-1.xml", "sitemaps/escolas-1.xml"])
        alunos = self.get("/sitemaps/alunos-1.xml")[2].decode()
        self.assertIn("<loc>https://medalhas.online/aluno/maria-souza-lima-al</loc>", alunos)
        self.assertEqual(self.get("/sitemaps/nada.xml")[0], 404)
        self.assertIn("<loc>https://medalhas.online/sobre</loc>", self.get("/sitemaps/paginas.xml")[2].decode())

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

    def test_css_gerado_no_build(self):
        web = Path(__file__).parent.parent / "web"
        css = (web / "css" / "site.css").read_text(encoding="utf-8")
        self.assertIn(".bg-ink-900", css)   # cor própria do tema: o CSS veio da nossa configuração
        for pagina in ("index.html", "404.html"):
            html = (web / pagina).read_text(encoding="utf-8")
            self.assertIn('href="/css/site.css"', html)
            self.assertNotIn("cdn.tailwindcss.com", html)


if __name__ == "__main__":
    unittest.main()
