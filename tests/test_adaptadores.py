"""Adaptadores isolados: leitura das páginas oficiais, registro de coletores, limites por IP e validação da API."""
import unittest
from unittest import mock

from medalhas.adaptadores import coletores
from medalhas.adaptadores.coletores import egoi, ioai, obm, obmep, obq
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

    def test_resultados_da_egoi_pela_cor_da_linha(self):
        pagina = """<table><tr><th>Year</th><th>Name</th><th>Score</th><th>Rank</th></tr>
            <tr><td rowspan="2">2025</td><td style="background: #fee101"><a>Ana Lima</a></td>
                <td style="background: #fee101">596</td><td>3</td></tr>
            <tr><td><a>Bia Souza</a></td><td>120</td><td>140</td></tr>
            <tr><td>2024</td><td style="background: #D28140">Ana Lima</td><td>300</td><td>80</td></tr></table>"""
        self.assertEqual(egoi.ler_resultados(pagina), [   # Bia não tem cor: sem medalha
            {"ano": 2025, "nome": "Ana Lima", "medalha": "Ouro", "pontos": "596"},
            {"ano": 2024, "nome": "Ana Lima", "medalha": "Bronze", "pontos": "300"}])

    def test_linha_da_obq_em_colunas_e_num_trecho_so(self):
        colunas = [(60, "MATO GROSSO DO SUL"), (143, "ANA LIMA(1)"), (354, "2º ANO EM"), (395, "COLÉGIO X"),
                   (701, "64,60"), (749, "77,83")]
        self.assertEqual(obq._registro(colunas), {"uf": "MS", "nome": "ANA LIMA(1)", "serie": "2º ANO EM",
                                                  "escola": "COLÉGIO X", "nota": "64,60"})
        junto = [(60, "MATO GROSSO DO SUL BIA REIS (PCD) 3º ANO EM INSTITUTO FEDERAL CAMPUS"), (701, "61,40 72,28")]
        r = obq._registro(junto)
        self.assertEqual((r["uf"], obq._limpar_nome(r["nome"]), r["escola"], r["nota"]),
                         ("MS", "BIA REIS", "INSTITUTO FEDERAL CAMPUS", "61,40"))
        self.assertIsNone(obq._registro([(395, "NILOPOLIS")]))   # resto do nome da escola, linha de baixo

    def test_resultados_da_ioai_so_do_brasil(self):
        pagina = """<table><tr><th>rank</th><th>name</th><th>team</th><th>total</th><th>award</th></tr>
            <tr><td>1</td><td>Artem G</td><td>Russia 1</td><td>428</td><td>Gold + 1st Place</td></tr>
            <tr><td>56</td><td>Miguel Vale</td><td>Brazil 1 🇧🇷</td><td>171,1</td><td>Silver</td></tr>
            <tr><td>90</td><td>Rafa Lima</td><td>Brazil</td><td>18</td><td>Honourable Mention</td></tr>
            <tr><td>99</td><td>Caio Reis</td><td>Brazil</td><td>10</td><td></td></tr></table>"""
        self.assertEqual(ioai.ler_resultados(pagina), [
            {"nome": "Miguel Vale", "medalha": "Prata", "pontos": "171,1"},
            {"nome": "Rafa Lima", "medalha": "Menção Honrosa", "pontos": "18"}])


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
