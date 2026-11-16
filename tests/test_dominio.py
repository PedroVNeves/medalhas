"""Regras de negócio: pontuação, escolas, identidade de alunos, ranking e gamificação."""
import unittest

from medalhas.dominio import enderecos, escolas, gamificacao, identidade, pontuacao, ranking, sexo
from medalhas.dominio.texto import capitalizar_nome, normalizar


def premiacao(nome, uf, competicao="OBMEP", ano=2020, medalha="Ouro", nivel="3") -> dict:
    return {"competicao": competicao, "ano": ano, "nivel": nivel, "nome": nome, "escola": None, "rede": None,
            "esfera": None, "municipio": None, "uf": uf, "premio": medalha, "medalha": medalha, "pontos": None,
            "fonte": "https://exemplo"}


class TestTexto(unittest.TestCase):
    def test_normalizar(self):
        self.assertEqual(normalizar("  São  Paulo-SP "), "SAO PAULO SP")
        self.assertEqual(normalizar(None), "")

    def test_capitalizar_nome(self):
        self.assertEqual(capitalizar_nome("JOÃO DA SILVA"), "João da Silva")


class TestPontuacao(unittest.TestCase):
    def test_impa_todos_os_niveis(self):
        self.assertEqual(pontuacao.pontos_impa("OBMEP", "Ouro"), 18)
        self.assertEqual(pontuacao.pontos_impa("OBI", "Prata"), 3)
        self.assertEqual(pontuacao.pontos_impa("OBM", "Menção Honrosa"), 0)
        self.assertEqual(pontuacao.pontos_impa("IMO", "Ouro"), 0)   # fora do edital

    def test_impa_oficial_so_niveis_do_edital(self):
        self.assertEqual(pontuacao.pontos_impa_oficial("OBMEP", "Ouro", "3"), 18)
        self.assertEqual(pontuacao.pontos_impa_oficial("OBMEP", "Ouro", "2"), 0)
        self.assertEqual(pontuacao.pontos_impa_oficial("OBI", "Bronze", "Programação Nível 2"), 1)
        self.assertEqual(pontuacao.pontos_impa_oficial("OBI", "Bronze", "Iniciação Nível 1"), 0)

    def test_nossa_versao(self):
        self.assertEqual(pontuacao.pontos_site("OBM", "Ouro"), 2 * pontuacao.pontos_site("OBMEP", "Ouro"))
        self.assertEqual(pontuacao.pontos_site("OBM", "1º Prêmio"), pontuacao.pontos_site("OBM", "Bronze"))
        self.assertEqual(pontuacao.pontos_site("OIM", "Participação"), 0)
        self.assertEqual(pontuacao.pontos_site("DESCONHECIDA", "Ouro"), 0)

    def test_metodo_desconhecido_usa_o_padrao(self):
        self.assertEqual(pontuacao.resolver_metodo("xyz"), ("impa", "p_impa"))
        self.assertEqual(pontuacao.resolver_metodo("site"), ("site", "p_site"))

    def test_impa3_restringe_niveis(self):
        aceitos = pontuacao.niveis_impa()
        self.assertEqual(pontuacao.restringir_niveis("impa3", None), aceitos)
        self.assertEqual(pontuacao.restringir_niveis("impa3", "1,2"), aceitos)
        self.assertEqual(pontuacao.restringir_niveis("impa3", "3"), "3")
        self.assertEqual(pontuacao.restringir_niveis("impa", "1"), "1")


class TestEscolas(unittest.TestCase):
    def test_sigla_e_nome_completo_tem_a_mesma_chave(self):
        _, curta = escolas.indexar_escola("IFAL Campus Maceió", "Maceió", "AL")
        nome_completo = "Instituto Federal de Educação, Ciência e Tecnologia de Alagoas - Campus Maceió"
        _, longa = escolas.indexar_escola(nome_completo, "MACEIO", "AL")
        self.assertEqual(curta, longa)

    def test_mesma_escola_em_cidades_diferentes_tem_chaves_diferentes(self):
        self.assertNotEqual(escolas.indexar_escola("EE Joao", "Santos", "SP")[1],
                            escolas.indexar_escola("EE Joao", "Campinas", "SP")[1])

    def test_letras_soltas_viram_sigla(self):
        termos, _ = escolas.indexar_escola("E E E F Abel", "X", "PB")
        self.assertIn(" EEEF ", termos)
        self.assertIn(" ESCOLA ", termos)

    def test_escola_renomeada_usa_a_chave_do_nome_atual(self):
        termos, antiga = escolas.indexar_escola("CEFET DO ESPIRITO SANTO", "VITORIA", "ES")
        _, atual = escolas.indexar_escola("Ifes - Campus Vitória", "Vitória", "ES")
        self.assertEqual(antiga, atual)
        self.assertIn(" INSTITUTO ", termos)   # quem busca "instituto federal" também acha o tempo de CEFET
        # o CEFET de outra cidade continua separado
        self.assertNotEqual(escolas.indexar_escola("CEFETES CARIACICA", "CARIACICA", "ES")[1], atual)

    def test_busca_expande_sigla(self):
        self.assertEqual(escolas.palavras_da_busca("etec de sp"),
                         [("ETEC", ["ESCOLA", "TECNICA", "ESTADUAL"]), ("SP", ["SP"])])


class TestIdentidade(unittest.TestCase):
    def test_nome_raro_em_duas_ufs_e_a_mesma_pessoa(self):
        ps = [premiacao("Zebedeu Quintanilha", "PI", ano=2015), premiacao("Zebedeu Quintanilha", "CE", ano=2017)]
        ps += [premiacao(f"Pessoa {i} Silva", "SP") for i in range(50)]   # base para estimar a raridade
        self.assertEqual(identidade.atribuir_alunos(ps), 1)
        self.assertEqual(ps[0]["aluno_id"], ps[1]["aluno_id"])
        self.assertEqual(ps[0]["aluno_id"], "ZEBEDEU QUINTANILHA|CE")   # UF do registro mais recente

    def test_mesma_edicao_em_duas_ufs_sao_homonimos(self):
        ps = [premiacao("Zebedeu Quintanilha", "PI"), premiacao("Zebedeu Quintanilha", "CE")]
        identidade.atribuir_alunos(ps)
        self.assertNotEqual(ps[0]["aluno_id"], ps[1]["aluno_id"])

    def test_sem_uf_herda_a_uf_conhecida(self):
        ps = [premiacao("Zebedeu Quintanilha", "PI"), premiacao("Zebedeu Quintanilha", None, competicao="IMO")]
        self.assertEqual(identidade.completar_identidades(ps), (1, 0))
        self.assertEqual(ps[1]["uf"], "PI")

    def test_nome_abreviado_e_completado(self):
        ps = [premiacao("Enzo Holanda Sampaio", "CE", competicao="OBM"), premiacao("Enzo Holanda", None, "IMO")]
        self.assertEqual(identidade.completar_identidades(ps), (0, 1))
        self.assertEqual(ps[1]["nome"], "Enzo Holanda Sampaio")

    def test_nome_abreviado_na_informatica_internacional_busca_na_obi(self):
        ps = [premiacao("Talita Ribeiro de Rezende", "SP", competicao="OBI"), premiacao("Talita Rezende", None, "EGOI"),
              premiacao("Talita Ribeiro de Rezende", "SP"), premiacao("Ana Rezende", None, "IMO")]
        self.assertEqual(identidade.completar_identidades(ps), (0, 1))
        self.assertEqual(ps[1]["nome"], "Talita Ribeiro de Rezende")
        self.assertEqual(ps[3]["nome"], "Ana Rezende")   # matemática não procura na OBI

    def test_grafia_corrigida_a_mao_une_os_perfis(self):
        ps = [premiacao("ISAIAS GOUVEIA GONCALVES", "DF", ano=2018), premiacao("Isaias Gouveia Gonçalves", "DF", "OBM", 2019),
              premiacao("Isaías Gouvêa Gonçalves", "PR", "OBM", 2020), premiacao("ISAIAS GOUVEIA GONCALVES", "SP")]
        self.assertEqual(identidade.corrigir_grafias(ps), 2)   # só a grafia errada de DF; a de SP é outra pessoa
        self.assertEqual(ps[0]["nome"], "Isaías Gouvêa Gonçalves")
        ps += [premiacao(f"Pessoa {i} Silva", "SP") for i in range(50)]
        identidade.atribuir_alunos(ps)
        self.assertEqual({p["aluno_id"] for p in ps[:3]}, {"ISAIAS GOUVEA GONCALVES|PR"})


class TestSexo(unittest.TestCase):
    def test_so_classifica_nomes_quase_exclusivos(self):
        self.assertEqual(sexo.classificar(0.99), "F")
        self.assertEqual(sexo.classificar(0.02), "M")
        self.assertIsNone(sexo.classificar(0.5))    # Ariel, Darcy…
        self.assertIsNone(sexo.classificar(None))   # nome fora do Censo

    def test_estima_por_aluno_e_olimpiada_so_de_meninas_decide(self):
        ps = [premiacao("Maria Souza", "SP"), premiacao("Ariel Lima", "RJ"), premiacao("Ariel Lima", "RJ", "EGMO", 2021),
              premiacao("Joao Reis", "CE"), premiacao("Zuleica Neri", "PI")]
        for p in ps:
            p["aluno_id"] = normalizar(p["nome"]) + "|" + p["uf"]
        contagem = sexo.estimar(ps, {"MARIA": 0.995, "ARIEL": 0.4, "JOAO": 0.003})
        self.assertEqual([p["sexo"] for p in ps], ["F", "F", "F", "M", None])
        self.assertEqual(contagem, {"F": 2, "M": 1, None: 1})


class TestRanking(unittest.TestCase):
    def itens(self):
        return [{"nome": n, "p": p, "ouro": o, "prata": 0, "bronze": 0} for n, p, o in
                [("A", 10, 1), ("B", 30, 1), ("C", 30, 1), ("D", 0, 0), ("E", 5, 0)]]

    def test_empate_divide_a_posicao(self):
        ordenados = ranking.ordenar(self.itens(), "xp", "p")
        posicoes = [(p, i["nome"]) for p, i in ranking.posicionar(ordenados, ranking.chave_de_ordenacao("xp", "p"))]
        self.assertEqual(posicoes, [(1, "B"), (1, "C"), (3, "A"), (4, "E")])   # D não pontua: fica de fora

    def test_paginacao_mantem_a_posicao(self):
        ordenados = ranking.ordenar(self.itens(), "xp", "p")
        pagina = list(ranking.posicionar(ordenados, ranking.chave_de_ordenacao("xp", "p"), offset=1, limite=2))
        self.assertEqual([p for p, _ in pagina], [1, 3])

    def test_preencher_posicoes(self):
        itens = self.itens()
        ranking.preencher_posicoes(itens, "p", "pos")
        self.assertEqual({i["nome"]: i["pos"] for i in itens}, {"B": 1, "C": 1, "A": 3, "E": 4, "D": 5})


class TestGamificacao(unittest.TestCase):
    def test_tier(self):
        self.assertEqual(gamificacao.tier(0)["nome"], "Estreante")
        t = gamificacao.tier(10, metodo="impa")
        self.assertEqual((t["nome"], t["proximo"], t["falta"]), ("Promessa", "Talento", 8))
        self.assertEqual(gamificacao.tier(10**6)["progresso"], 1.0)

    def test_sequencia_pula_2020(self):
        self.assertEqual(gamificacao.maior_sequencia({2018, 2019, 2021, 2022, 2024}), 4)

    def test_conquistas(self):
        ps = [premiacao("A", "SP", ano=a) for a in (2017, 2018, 2019)]
        desbloqueadas = {c["id"] for c in gamificacao.conquistas_aluno(ps) if c["desbloqueada"]}
        self.assertTrue({"primeiro_podio", "midas", "hat_trick", "imparavel", "invicto"} <= desbloqueadas)
        self.assertNotIn("veterano", desbloqueadas)


class TestEnderecos(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(enderecos.slug("MARIA SOUZA LIMA|AL"), "maria-souza-lima-al")
        self.assertEqual(enderecos.slug("Colégio  São Luís (SP)"), "colegio-sao-luis-sp")
        self.assertEqual(enderecos.slug(None), "")

    def test_escola_usa_o_nome_de_exibicao_e_aceita_o_slug_do_id(self):
        e = enderecos.Enderecos([("ANA|SP", "ANA|SP")],
                                [("BENEDITA ESCOLA MUNICIPAL|BORDA|MG", "EM BENEDITA BORDA MG")])
        oficial = "em-benedita-borda-mg"
        self.assertEqual(e.de("escola", "BENEDITA ESCOLA MUNICIPAL|BORDA|MG"), oficial)
        self.assertEqual(e.resolver("escola", oficial), ("BENEDITA ESCOLA MUNICIPAL|BORDA|MG", oficial))
        # o site monta o link pelo id; o servidor acha a escola e manda para o endereço oficial
        self.assertEqual(e.resolver("escola", "benedita-escola-municipal-borda-mg")[1], oficial)
        self.assertEqual(e.resolver("aluno", "ana-sp"), ("ANA|SP", "ana-sp"))
        self.assertIsNone(e.resolver("aluno", "ninguem"))
        self.assertEqual(e.todos("escola"), [oficial])

    def test_enderecos_repetidos_ganham_numero(self):
        e = enderecos.Enderecos([], [("B|X|SP", "USP SP"), ("A|Y|SP", "USP SP")])
        self.assertEqual(e.de("escola", "A|Y|SP"), "usp-sp")       # o id menor fica com o endereço
        self.assertEqual(e.de("escola", "B|X|SP"), "usp-sp-2")

    def test_nome_de_exibicao_da_escola(self):
        self.assertEqual(escolas.nome_de_exibicao("MILITAR DE FORTALEZA, COLEGIO"), "Colegio Militar de Fortaleza")
        self.assertEqual(escolas.nome_de_exibicao("EE PROF JOSE DA SILVA"), "EE Prof Jose da Silva")
        self.assertEqual(escolas.nome_de_exibicao("Colégio Etapa"), "Colégio Etapa")   # caixa mista fica igual


if __name__ == "__main__":
    unittest.main()
