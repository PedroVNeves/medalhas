"""Regras de negócio: pontuação, escolas, identidade de alunos, ranking e gamificação."""
import unittest

from medalhas.dominio import (
    enderecos,
    escolas,
    gamificacao,
    identidade,
    pontuacao,
    ranking,
    sexo,
)
from medalhas.dominio.texto import (
    capitalizar_nome,
    limpar_escola,
    limpar_nome,
    normalizar,
)


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

    def test_escola_sem_cidade_adota_a_unica_cidade_do_mesmo_nome_no_estado(self):
        ps = [{"escola": "LICEU JARDIM", "municipio": "Santo André", "uf": "SP"},
              {"escola": "COLEGIO ETAPA", "municipio": "São Paulo", "uf": "SP"},
              {"escola": "COLEGIO ETAPA", "municipio": "Valinhos", "uf": "SP"},
              {"escola": "Liceu Jardim", "municipio": None, "uf": "SP"},     # OBQ: só nome e estado
              {"escola": "ETAPA COLÉGIO", "municipio": None, "uf": "SP"},    # duas cidades possíveis
              {"escola": "LICEU JARDIM", "municipio": None, "uf": "RJ"}]     # outro estado
        self.assertEqual(escolas.completar_municipios(ps), 1)
        self.assertEqual([p["municipio"] for p in ps[3:]], ["Santo André", None, None])

    def test_escola_sem_uf_nao_tem_chave(self):
        termos, chave = escolas.indexar_escola("Colégio Kennedy", None, None)
        self.assertEqual(chave, "")
        self.assertIn(" KENNEDY ", termos)   # o nome continua pesquisável

    def test_busca_expande_sigla(self):
        self.assertEqual(escolas.palavras_da_busca("etec de sp"),
                         [("ETEC", ["ESCOLA", "TECNICA", "ESTADUAL"]), ("SP", ["SP"])])


class TestIdentidade(unittest.TestCase):
    def test_mencao_da_obmep_nao_muda_quem_e_quem(self):
        def mencao(nome, uf, ano, nivel="1", municipio=None):
            p = premiacao(nome, uf, ano=ano, medalha="Menção Honrosa", nivel=nivel)
            p["municipio"] = municipio
            return p
        ouro = premiacao("Ana Clara Raro Nome", "AL", ano=2015, nivel="2")
        imo = {**premiacao("Ana Clara Raro Nome", None, "IMO", 2018), "uf": None}
        cabe = mencao("Ana Clara Raro Nome", "AL", 2014)                 # antes do ouro, nível menor: a mesma
        outro_estado = mencao("Ana Clara Raro Nome", "SP", 2016)         # nome raro em outro estado: não une
        regride = [mencao("Ana Clara Raro Nome", "AL", ano, "1", "Arapiraca") for ano in (2016, 2017, 2018)]
        ps = [ouro, imo, cabe, outro_estado, *regride]
        identidade.completar_identidades(ps)
        self.assertEqual(identidade.atribuir_alunos(ps), 0)              # nenhuma união entre estados
        self.assertEqual(imo["uf"], "AL")                                # a menção de SP não atrapalhou
        self.assertEqual({ouro["aluno_id"], imo["aluno_id"], cabe["aluno_id"]}, {"ANA CLARA RARO NOME|AL"})
        self.assertEqual(outro_estado["aluno_id"], "ANA CLARA RARO NOME|SP")
        # três menções de nível 1 depois do ouro de nível 2 são de outra pessoa, e o medalhista fica com o endereço
        self.assertEqual({r["aluno_id"] for r in regride}, {"ANA CLARA RARO NOME|AL|ARAPIRACA"})

    def test_mencao_entre_dois_homonimos_so_entra_pela_escola(self):
        a = {**premiacao("Joao Silva", "PE", ano=2015, nivel="1"), "municipio": "Recife", "escola": "EE Alfa"}
        b = {**premiacao("Joao Silva", "PE", ano=2015, nivel="1"), "municipio": "Caruaru", "escola": "EE Beta"}
        mencao = {**premiacao("Joao Silva", "PE", ano=2016, medalha="Menção Honrosa", nivel="2"),
                  "municipio": "Caruaru", "escola": "EE Beta"}
        duvida = {**premiacao("Joao Silva", "PE", ano=2017, medalha="Menção Honrosa", nivel="3"), "escola": "EE Gama"}
        ps = [a, b, mencao, duvida]
        identidade.atribuir_alunos(ps)
        self.assertNotEqual(a["aluno_id"], b["aluno_id"])
        self.assertEqual(mencao["aluno_id"], b["aluno_id"])
        self.assertNotIn(duvida["aluno_id"], {a["aluno_id"], b["aluno_id"]})   # na dúvida, não entra em ninguém

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

    def test_sem_uf_em_regional_so_vai_para_nome_raro(self):
        comuns = ([premiacao(f"Maria Silva {i}", "SP") for i in range(40)]
                  + [premiacao(f"Ana Silva {i}", "RJ") for i in range(40)])
        ps = comuns + [premiacao("Maria Silva", "MG"), premiacao("Maria Silva", None, "OITM"),
                       premiacao("Zebedeu Quintanilha", "PI"), premiacao("Zebedeu Quintanilha", None, "OITM")]
        identidade.completar_identidades(ps)
        self.assertIsNone(ps[-3]["uf"])     # nome comum: pode ser outra Maria Silva
        self.assertEqual(ps[-1]["uf"], "PI")   # nome raro: é a mesma pessoa

    def test_sem_uf_vai_para_quem_foi_premiado_na_mesma_escola(self):
        comuns = [premiacao(f"Lucas Oliveira {i}", "SP") for i in range(60)]
        mg = premiacao("Lucas Gabriel de Oliveira", "MG")
        mg["escola"] = "EE MAJ LAGE"
        sem_uf = premiacao("Lucas Gabriel de Oliveira", None, "OITM", 2020)
        sem_uf["escola"] = "Escola Estadual Major Lage"
        outra = premiacao("Lucas Gabriel de Oliveira", None, "OITM", 2021)
        outra["escola"] = "Colégio Kennedy"
        identidade.completar_identidades(comuns + [mg, sem_uf, outra])
        self.assertEqual(sem_uf["uf"], "MG")   # nome comum, mas mesma escola
        self.assertIsNone(outra["uf"])         # nome comum e outra escola: pode ser outra pessoa

    def test_mesma_escola_aceita_abreviacao(self):
        self.assertTrue(identidade.mesma_escola("Escola Estadual Major Lage", "EE MAJ LAGE"))
        self.assertFalse(identidade.mesma_escola("Escola Estadual Major Lage", "EE Mestre Zeca Amancio"))
        self.assertFalse(identidade.mesma_escola("Escola Estadual", "EE Joao Pinto"))   # só palavras genéricas

    def test_grafia_corrigida_a_mao_une_os_perfis(self):
        ps = [premiacao("ISAIAS GOUVEIA GONCALVES", "DF", ano=2018),
              premiacao("Isaias Gouveia Gonçalves", "DF", "OBM", 2019),
              premiacao("Isaías Gouvêa Gonçalves", "PR", "OBM", 2020), premiacao("ISAIAS GOUVEIA GONCALVES", "SP")]
        self.assertEqual(identidade.corrigir_grafias(ps), 2)   # só a grafia errada de DF; a de SP é outra pessoa
        self.assertEqual(ps[0]["nome"], "Isaías Gouvêa Gonçalves")
        ps += [premiacao(f"Pessoa {i} Silva", "SP") for i in range(50)]
        identidade.atribuir_alunos(ps)
        self.assertEqual({p["aluno_id"] for p in ps[:3]}, {"ISAIAS GOUVEA GONCALVES|PR"})


class TestSexo(unittest.TestCase):
    def test_so_quem_foi_premiada_em_olimpiada_para_meninas(self):
        ps = [premiacao("Maria Souza", "SP"), premiacao("Ariel Lima", "RJ"),
              premiacao("Ariel Lima", "RJ", "EGMO", 2021),
              premiacao("Joao Reis", "CE")]
        for p in ps:
            p["aluno_id"] = normalizar(p["nome"]) + "|" + p["uf"]
        self.assertEqual(sexo.marcar_meninas(ps), 1)
        self.assertEqual([p["sexo"] for p in ps], [None, "F", "F", None])   # Maria: não há como saber


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
        self.assertEqual(e.fatia("escola", 0, 10), [oficial])

    def test_enderecos_repetidos_ganham_numero(self):
        e = enderecos.Enderecos([], [("B|X|SP", "USP SP"), ("A|Y|SP", "USP SP")])
        self.assertEqual(e.de("escola", "A|Y|SP"), "usp-sp")       # o id menor fica com o endereço
        self.assertEqual(e.de("escola", "B|X|SP"), "usp-sp-2")

    def test_endereco_da_grafia_corrigida_leva_ao_perfil_certo(self):
        e = enderecos.Enderecos([("JOAO PRIMAKI|PR", "JOAO PRIMAKI|PR"), ("JOAO PIMAKI|SP", "JOAO PIMAKI|SP")], [],
                                antigos_alunos=[("joao-pimaki-pr", "JOAO PRIMAKI|PR"),
                                                ("joao-pimaki-sp", "JOAO PRIMAKI|PR"),   # é de outra pessoa
                                                ("maria-pr", "MARIA|PR")])               # perfil que não existe
        self.assertEqual(e.resolver("aluno", "joao-pimaki-pr"), ("JOAO PRIMAKI|PR", "joao-primaki-pr"))
        self.assertEqual(e.resolver("aluno", "joao-pimaki-sp"), ("JOAO PIMAKI|SP", "joao-pimaki-sp"))
        self.assertIsNone(e.resolver("aluno", "maria-pr"))
        self.assertEqual(e.fatia("aluno", 0, 10), ["joao-pimaki-sp", "joao-primaki-pr"])   # fora do sitemap

    def test_nome_de_exibicao_da_escola(self):
        self.assertEqual(escolas.nome_de_exibicao("MILITAR DE FORTALEZA, COLEGIO"), "Colegio Militar de Fortaleza")
        self.assertEqual(escolas.nome_de_exibicao("EE PROF JOSE DA SILVA"), "EE Prof Jose da Silva")
        self.assertEqual(escolas.nome_de_exibicao("Colégio Etapa"), "Colégio Etapa")   # caixa mista fica igual


class TestRevisao(unittest.TestCase):
    """Regras que entraram com a revisão do back-end."""

    def test_mencao_honrosa_pontua_menos_que_o_bronze_em_todo_degrau(self):
        for degrau, tabela in pontuacao.ESCALA_SITE.items():
            with self.subTest(degrau=degrau):
                self.assertGreater(tabela["Menção Honrosa"], 0)
                self.assertLess(tabela["Menção Honrosa"], tabela["Bronze"])
        self.assertEqual(pontuacao.pontos_site("OBI", "Menção Honrosa"), 10)
        self.assertEqual(pontuacao.pontos_site("OITM", "Menção Honrosa"), 8)
        self.assertEqual(pontuacao.pontos_site("OITM", "Elas em Destaque"), pontuacao.pontos_site("OITM", "Bronze"))
        self.assertEqual(pontuacao.pontos_impa("OBI", "Menção Honrosa"), 0)   # a tabela do edital não muda

    def test_limpar_nome(self):
        for sujo, limpo in (("Adenilson Arcanjo de Moura Júnior/td>", "Adenilson Arcanjo de Moura Júnior"),
                            ("Camilo Marcantonio Junior/B>", "Camilo Marcantonio Junior"),
                            ("Sofia Nunes Pinto de Oliveira 7ºB", "Sofia Nunes Pinto de Oliveira"),
                            ("Giulia Di Credico Paranhos 7c", "Giulia Di Credico Paranhos"),
                            ("Maria Larysse Yasmin Lira Pereira3", "Maria Larysse Yasmin Lira Pereira"),
                            ("Marcelo Kenzo Matsumura fulano.123@gmail.com", "Marcelo Kenzo Matsumura"),
                            ("Marianny Rocha Marques ;", "Marianny Rocha Marques"),
                            ("Fábio Franco C. de Alencar", "Fábio Franco C. de Alencar"),
                            ("Pedro II", "Pedro II")):
            with self.subTest(nome=sujo):
                self.assertEqual(limpar_nome(sujo), limpo)
        self.assertEqual(limpar_escola("EMEF> JOAO JAIME GADELHA"), "EMEF JOAO JAIME GADELHA")
        self.assertIsNone(limpar_escola(" "))

    def test_homonimos_da_mesma_uf_sao_separados(self):
        def p(ano, municipio, nivel="3", competicao="OBMEP", escola=None):
            return {**premiacao("JOAO DA SILVA", "SP", competicao, ano, nivel=nivel), "municipio": municipio,
                    "escola": escola}
        # mesma edição em duas cidades: duas pessoas; a maior parte fica com o id sem cidade
        ps = [p(2021, "Cubatão"), p(2020, "Cubatão", "2"), p(2021, "Barueri", "2")]
        identidade.atribuir_alunos(ps)
        self.assertEqual([x["aluno_id"] for x in ps],
                         ["JOAO DA SILVA|SP", "JOAO DA SILVA|SP", "JOAO DA SILVA|SP|BARUERI"])
        # nível da OBMEP regredindo e carreira de mais de 12 anos: também
        ps = [p(2014, "Joinville"), p(2019, "Mafra", "1"), p(2021, "Mafra", "2")]
        identidade.atribuir_alunos(ps)
        self.assertEqual(len({x["aluno_id"] for x in ps}), 2)
        ps = [p(2007, "Itu", "1"), p(2008, "Itu", "2"), p(2025, "Itu", "1")]
        identidade.atribuir_alunos(ps)
        self.assertEqual(len({x["aluno_id"] for x in ps}), 2)
        # quem só mudou de cidade continua uma pessoa; e a OBI premia duas modalidades no mesmo ano
        ps = [p(2018, "Itu", "1"), p(2019, "Itu", "2"), p(2021, "Campinas"),
              p(2021, "Campinas", "Programação Nível 1", "OBI", "Colégio X"),
              p(2021, "Campinas", "Iniciação Nível 2", "OBI", "Colégio X")]
        identidade.atribuir_alunos(ps)
        self.assertEqual({x["aluno_id"] for x in ps}, {"JOAO DA SILVA|SP"})

    def test_premiacao_sem_uf_fora_da_carreira_nao_entra_no_perfil(self):
        ps = [premiacao("ZULMIRA QUARESMA", "CE", ano=2015), premiacao("ZULMIRA QUARESMA", None, "IMO", 1985)]
        identidade.atribuir_alunos(ps)
        self.assertEqual([x["aluno_id"] for x in ps], ["ZULMIRA QUARESMA|CE", "ZULMIRA QUARESMA|"])

    def test_posicao_do_resumo_segue_o_criterio_do_ranking(self):
        itens = [{"nome": "A", "p": 18, "ouro": 0, "prata": 3, "bronze": 0},
                 {"nome": "B", "p": 18, "ouro": 1, "prata": 0, "bronze": 0},
                 {"nome": "C", "p": 18, "ouro": 1, "prata": 0, "bronze": 0}]
        ranking.preencher_posicoes(itens, "p", "pos")
        ordenados = ranking.ordenar(itens, "xp", "p")
        na_lista = {i["nome"]: pos for pos, i in ranking.posicionar(ordenados, ranking.chave_de_ordenacao("xp", "p"))}
        self.assertEqual({i["nome"]: i["pos"] for i in itens}, na_lista)
        self.assertEqual(na_lista, {"B": 1, "C": 1, "A": 3})

    def test_cidade_da_escola_depois_do_hifen(self):
        ps = [{**premiacao("ANA", "BA"), "escola": "Colégio Y", "municipio": "Salvador"},
              {**premiacao("BIA", "BA", "OBQ"), "escola": "IFBA - SALVADOR"}]
        self.assertEqual(escolas.completar_municipios(ps), 1)
        self.assertEqual(ps[1]["municipio"], "Salvador")

    def test_endereco_pelo_id_vai_para_o_primeiro_da_lista(self):
        grande, pequena = "A B|C|UF", "A B C||UF"
        e = enderecos.Enderecos([], [(grande, "Escola Grande C UF"), (pequena, "Escola Pequena UF")])
        self.assertEqual(e.resolver("escola", enderecos.slug(grande))[0], grande)


if __name__ == "__main__":
    unittest.main()
