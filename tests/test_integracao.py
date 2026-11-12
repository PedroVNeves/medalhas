"""Ponta a ponta com uma base pequena: coletor falso -> gerar_base -> SQLite -> servidor HTTP -> JSON/CSV.

Não usa a base real nem a internet.
"""
import json
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


if __name__ == "__main__":
    unittest.main()
