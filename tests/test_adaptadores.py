"""Adaptadores isolados: leitura das páginas oficiais, registro de coletores, limites por IP e validação da API."""
import unittest
from unittest import mock

from medalhas.adaptadores import coletores
from medalhas.adaptadores.coletores import obm, obmep
from medalhas.adaptadores.http import limites
from medalhas.adaptadores.http.api_v1 import ParametroInvalido, parametros
from medalhas.dominio.olimpiadas import CATALOGO


class TestColetores(unittest.TestCase):
    def test_toda_olimpiada_do_catalogo_tem_coletor(self):
        self.assertEqual([c.sigla for c in coletores.todos()], list(CATALOGO))

    def test_ano_da_pasta_da_obmep(self):
        self.assertEqual(obmep.ano_da_pasta("2014"), 2014)
        self.assertEqual(obmep.ano_da_pasta("15aobmep"), 2019)
        self.assertEqual(obmep.ano_da_pasta("16aobmep"), 2021)   # não houve OBMEP em 2020

    def test_relatorio_da_obmep(self):
        pagina = """<h1>OBMEP 2019</h1><table>
            <tr><th>Nível 1</th></tr>
            <tr><th>Nome</th><th>Escola</th><th>Município</th><th>UF</th></tr>
            <tr><td>ANA&nbsp;LIMA</td><td>EE X</td><td>Natal</td><td>RN</td></tr></table>"""
        esperado = {"nome": "ANA LIMA", "escola": "EE X", "municipio": "Natal", "uf": "RN", "nivel": "1"}
        self.assertEqual(obmep.ler_relatorio(pagina), (2019, [esperado]))

    def test_cidade_e_premio_da_obm(self):
        self.assertEqual(obm.separar_cidade("Fortaleza – CE"), ("Fortaleza", "CE"))
        self.assertEqual(obm.separar_cidade("Rio de Janeiro (RJ)"), ("Rio de Janeiro", "RJ"))
        self.assertEqual(obm.categoria_do_premio("Medalha de Ouro"), "Ouro")
        self.assertEqual(obm.categoria_do_premio("Menção Honrosa"), "Menção Honrosa")
        self.assertEqual(obm.categoria_do_premio("1º Prêmio"), "1º Prêmio")


class TestLimites(unittest.TestCase):
    def setUp(self):
        grupos = {"teste": {"quantidade": 3, "janela": 60, "por_dia": 5}}
        self.patch = mock.patch.dict(limites.GRUPOS, grupos)
        self.patch.start()
        self.limitador = limites.Limitador()

    def tearDown(self):
        self.patch.stop()

    def test_cota_por_minuto(self):
        resultados = [self.limitador.consumir("teste", "1.1.1.1")[0] for _ in range(4)]
        self.assertEqual(resultados, [True, True, True, False])
        ok, cab = self.limitador.consumir("teste", "1.1.1.1")
        self.assertEqual((ok, cab["X-RateLimit-Scope"]), (False, "min"))
        self.assertTrue(self.limitador.consumir("teste", "2.2.2.2")[0])   # outro IP tem a própria cota

    def test_insistir_bloqueia_o_ip(self):
        with mock.patch.object(limites, "ABUSO_REJEICOES", 3):
            for _ in range(6):
                self.limitador.consumir("teste", "3.3.3.3")
        self.assertGreater(self.limitador.bloqueio_restante("3.3.3.3"), 0)
        self.assertEqual(self.limitador.bloqueio_restante("4.4.4.4"), 0)

    def test_teto_de_conexoes_por_ip(self):
        conexoes = limites.Conexoes()
        with mock.patch.object(limites, "MAX_CONEXOES_IP", 2):
            self.assertEqual([conexoes.entrar("5.5.5.5") for _ in range(3)], [True, True, False])
            conexoes.sair("5.5.5.5")
            self.assertTrue(conexoes.entrar("5.5.5.5"))


class SessaoFalsa:
    def niveis(self):
        return {"1", "2", "3"}


class TestParametros(unittest.TestCase):
    def test_filtros_validos(self):
        f = parametros.filtros({"uf": "sp", "medalha": "ouro", "competicao": "OBMEP,OBM", "rede": "Pública",
                                "ano": "2019"}, SessaoFalsa())
        self.assertEqual(f, {"uf": "SP", "medalha": "Ouro", "competicao": "OBMEP,OBM", "rede": "Pública", "ano": 2019})

    def test_valores_invalidos(self):
        for params in ({"uf": "XX"}, {"medalha": "lata"}, {"competicao": "FOO"}, {"nivel": "9"}, {"ano": "abc"},
                       {"rede": "mista"}):
            with self.subTest(params=params), self.assertRaises(ParametroInvalido):
                parametros.filtros(params, SessaoFalsa())

    def test_limites_de_texto_e_pagina(self):
        with self.assertRaises(ParametroInvalido):
            parametros.texto({"nome": "x" * 101}, "nome")
        with self.assertRaises(ParametroInvalido):
            parametros.texto({"nome": "ana bia caio davi eva fabio gil hugo ivo"}, "nome")
        self.assertEqual(parametros.paginacao({"limite": "9999", "offset": "-3"}, "alunos"), (100, 0))


if __name__ == "__main__":
    unittest.main()
