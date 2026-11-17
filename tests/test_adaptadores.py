"""Adaptadores isolados: leitura das páginas oficiais, registro de coletores, limites por IP e validação da API."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from medalhas.adaptadores import coletores
from medalhas.adaptadores.coletores import egoi, ioai, itabirana, obm, obmep, obq, omif
from medalhas.adaptadores.http import limites
from medalhas.adaptadores.http.api_v1 import ParametroInvalido, parametros
from medalhas.adaptadores.sqlite import conexao
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

    def test_tabelas_da_obm_e_das_internacionais(self):
        tabela = ('<table><tr><th>Nome</th><th>Prêmio</th><th>Cidade – Estado</th></tr>'
                  '<tr><td>Ana <b>Lima</b></td><td>Ouro</td><td>Fortaleza – CE</td></tr><tr><td> </td></tr>'
                  '<TR><TD>Bia Souza</TD><TD>Prata</TD><TD>Recife – PE</TD></TR></table>')
        pagina = f'<title>Premiados – OBM – 2023</title><div class="post-body"><p>Nível 1</p>{tabela}</main>'
        ano, linhas = obm.ler_pagina(pagina)
        self.assertEqual(ano, 2023)
        self.assertEqual(linhas, [
            {"nome": "Ana Lima", "premio": "Ouro", "cidade": "Fortaleza – CE", "nivel": "1"},
            {"nome": "Bia Souza", "premio": "Prata", "cidade": "Recife – PE", "nivel": "1"}])
        from medalhas.adaptadores.coletores import obm_internacional
        pagina = f'<div class="post-body"><p>41ª OIM, Buenos Aires (2026)</p>{tabela}</main>'
        linhas = obm_internacional.ler_pagina(pagina, None)
        self.assertEqual([(r["nome"], r["ano"], r["premio"]) for r in linhas],
                         [("Ana Lima", 2026, "Ouro"), ("Bia Souza", 2026, "Prata")])

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
                                                  "x_serie": 354, "escola": "COLÉGIO X", "nota": "64,60"})
        junto = [(60, "MATO GROSSO DO SUL BIA REIS (PCD) 3º ANO EM INSTITUTO FEDERAL CAMPUS"), (701, "61,40 72,28")]
        r = obq._registro(junto)
        self.assertEqual((r["uf"], obq._limpar_nome(r["nome"]), r["escola"], r["nota"]),
                         ("MS", "BIA REIS", "INSTITUTO FEDERAL CAMPUS", "61,40"))
        self.assertIsNone(obq._registro([(395, "NILOPOLIS")]))   # resto do nome da escola, linha de baixo

    def test_estado_da_instituicao_federal(self):
        self.assertEqual(omif.uf_da_instituicao("IFES - CAMPUS VITORIA"), "ES")
        self.assertEqual(omif.uf_da_instituicao("IF Sudeste MG - Campus Muriaé"), "MG")
        self.assertEqual(omif.uf_da_instituicao("IFSUL - CAMPUS PASSO FUNDO"), "RS")      # não confunde com IFS (SE)
        self.assertEqual(omif.uf_da_instituicao("IFPE CAMPUS RECIFE"), "PE")
        self.assertEqual(omif.uf_da_instituicao("INSTITUTO FEDERAL DE SERGIPE - ITABAIANA"), "SE")
        self.assertIsNone(omif.uf_da_instituicao("ESCOLA X"))

    def test_faixas_da_itabirana(self):
        self.assertEqual(itabirana._faixa("MEDALHAS DE OURO"), "Ouro")
        self.assertEqual(itabirana._faixa("Medalha de Prata"), "Prata")
        self.assertEqual(itabirana._faixa("Medalha Elas em Destaque"), "Elas em Destaque")
        self.assertIsNone(itabirana._faixa("Nível 1"))

    def test_edicoes_da_ioai_pelo_menu_do_site(self):
        menu = """<a href='https://ioai-official.org/bulgaria-2024/results/'>2024 Results &amp; awards</a>
                  <a href='https://ioai-official.org/china-2025/results-2025/'>2025 Results</a>
                  <a href='https://ioai-official.org/about/'>About</a>"""
        with mock.patch.object(ioai, "baixar", return_value=menu):
            self.assertEqual(ioai.edicoes(), {2024: "https://ioai-official.org/bulgaria-2024/results/",
                                              2025: "https://ioai-official.org/china-2025/results-2025/"})

    def test_rede_da_itabirana(self):
        self.assertEqual(itabirana._rede("Pública Não Seletiva"), "Pública")
        self.assertEqual(itabirana._rede("Privada"), "Privada")
        self.assertIsNone(itabirana._rede(None))

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

    def test_teto_diario_vira_a_meia_noite_de_brasilia(self):
        import time
        from datetime import datetime
        falta = limites._meia_noite() - time.time()
        self.assertTrue(0 < falta <= 24 * 3600)
        self.assertEqual(datetime.fromtimestamp(limites._meia_noite(), limites.BRASILIA).strftime("%H:%M"), "00:00")

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


class TestRevisao(unittest.TestCase):
    """Comportamentos que entraram com a revisão do back-end."""

    def test_pedido_recusado_devolve_a_ficha(self):
        with mock.patch.dict(limites.GRUPOS, {"teste": {"quantidade": 2, "janela": 3600, "por_dia": 2}}):
            limitador = limites.Limitador()
            for _ in range(5):   # cada pedido inválido gasta e devolve: a cota não acaba
                self.assertTrue(limitador.consumir("teste", "1.1.1.1")[0])
                limitador.devolver("teste", "1.1.1.1")
            self.assertTrue(limitador.consumir("teste", "1.1.1.1")[0])
            self.assertTrue(limitador.consumir("teste", "1.1.1.1")[0])
            self.assertFalse(limitador.consumir("teste", "1.1.1.1")[0])

    def test_inteiros_fora_da_faixa_sao_ajustados(self):
        self.assertEqual(parametros.paginacao({"offset": "9" * 18}, "premiacoes")[1], parametros.OFFSET_MAXIMO)
        with self.assertRaises(ParametroInvalido):
            parametros.inteiro({"ano": "9" * 30}, "ano")
        self.assertEqual(parametros.inteiro({"ano": "99999"}, "ano", None, *parametros.ANOS), parametros.ANOS[1])

    def test_cache_limita_pelo_tamanho_e_descarta_o_menos_usado(self):
        with tempfile.TemporaryDirectory() as pasta:
            base = Path(pasta) / "base.db"
            base.write_text("v1")
            cache = conexao.Cache(base)
            with mock.patch.object(conexao, "_MAX_LINHAS_CACHE", 10):
                cache.obter("a", lambda: [0] * 4)
                cache.obter("b", lambda: [0] * 4)
                cache.obter("a", lambda: self.fail("a estava no cache"))   # usar "a" o deixa por último na fila
                cache.obter("c", lambda: [0] * 4)                          # 12 linhas: sai "b", o menos usado
                cache.obter("a", lambda: self.fail("a deveria ter ficado"))
                self.assertEqual(cache.obter("b", lambda: "recalculado"), "recalculado")
                cache.obter("d", lambda: [0] * 80, leve=True)              # lista leve: 80 linhas pesam 10

    def test_cache_usa_a_versao_da_base_que_a_conexao_abriu(self):
        with tempfile.TemporaryDirectory() as pasta:
            base = Path(pasta) / "base.db"
            base.write_text("v1")
            cache = conexao.Cache(base)
            versao_antiga = cache.versao()
            depois = time.time() + 5
            base.write_text("v2")
            os.utime(base, (depois, depois))   # a base foi trocada no meio da requisição
            self.assertEqual(cache.obter("k", lambda: "dado antigo", versao_antiga), "dado antigo")
            self.assertEqual(cache.obter("k", lambda: "dado novo"), "dado novo")   # não herdou o antigo

    def test_ioai_ignora_tabela_sem_as_colunas_esperadas(self):
        pagina = ("<table><tr><th>Name</th><th>Score</th></tr><tr><td>Team A</td><td>9</td></tr></table>"
                  "<table><tr><th>Name</th><th>Team</th><th>Award</th></tr>"
                  "<tr><td>Ana Lima</td><td>Brazil</td><td>Gold</td></tr></table>")
        self.assertEqual([r["nome"] for r in ioai.ler_resultados(pagina)], ["Ana Lima"])


class TestDownload(unittest.TestCase):
    """Uma resposta 200 sem o conteúdo esperado (manutenção, erro) não pode ficar no cache."""

    def baixar_com(self, respostas, pasta, **kw):
        from medalhas.adaptadores.coletores import http

        class Resposta:
            def __init__(self, corpo):
                self.corpo = corpo

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return self.corpo
        fila = iter(respostas)
        with (mock.patch.object(http, "PASTA_CACHE", Path(pasta)),
              mock.patch.object(http, "PAUSA_ENTRE_DOWNLOADS", 0),
              mock.patch.object(http.urllib.request, "urlopen", lambda *a, **k: Resposta(next(fila)))):
            return http.baixar("https://exemplo.org/indice", **kw)

    def test_pagina_sem_o_conteudo_esperado_nao_entra_no_cache(self):
        from medalhas.adaptadores.coletores.http import RespostaInesperada
        with tempfile.TemporaryDirectory() as pasta:
            with self.assertRaises(RespostaInesperada):
                self.baixar_com([b"<h1>Em manutencao</h1>"], pasta, esperado="premiados-")
            self.assertEqual(list(Path(pasta).iterdir()), [])
            boa = b'<a href="premiados-2024">2024</a>'
            self.assertIn("premiados-2024", self.baixar_com([boa], pasta, esperado="premiados-"))
            self.assertIn("premiados-2024", self.baixar_com([], pasta, esperado="premiados-"))   # veio do cache

    def test_cache_antigo_de_pagina_ruim_e_baixado_de_novo(self):
        with tempfile.TemporaryDirectory() as pasta:
            self.baixar_com([b"<h1>Em manutencao</h1>"], pasta)   # sem conferência: fica guardada (como antes)
            boa = b'<a href="premiados-2024">2024</a>'
            self.assertIn("premiados-2024", self.baixar_com([boa], pasta, esperado="premiados-"))


if __name__ == "__main__":
    unittest.main()
