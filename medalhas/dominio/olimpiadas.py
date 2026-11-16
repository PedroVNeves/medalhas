"""Cadastro das olimpíadas suportadas.

Para adicionar uma olimpíada nova:
  1. cadastre-a em CATALOGO (nome, área, escala de pontos e regra do IMPA Tech, se houver);
  2. escreva o coletor em medalhas/adaptadores/coletores/<sigla>.py e registre-o em
     medalhas/adaptadores/coletores/__init__.py;
  3. rode `python build_db.py`.
O site monta os filtros de olimpíada, área e nível a partir dos dados, sem mudar o front-end.
"""
from dataclasses import dataclass

_OBM = "https://www.obm.org.br"


@dataclass(frozen=True)
class Olimpiada:
    sigla: str
    nome: str
    area: str
    site: str                                # página oficial (ou página de resultados do Brasil)
    escala: str                              # degrau na escala da "nossa versão" (pontuacao.ESCALA_SITE)
    tabela_impa: str | None = None           # tabela do edital do IMPA Tech (pontuacao.TABELAS_IMPA)
    niveis_impa: frozenset[str] = frozenset()  # níveis aceitos pelo edital do IMPA Tech
    internacional: bool = False
    pontua_outros_premios: bool = False      # prêmios fora de ouro/prata/bronze/menção valem como bronze


def _internacional(sigla: str, nome: str, escala: str, pagina: str, internacional: bool = True) -> Olimpiada:
    """Competição com resultados do Brasil publicados pela OBM (www.obm.org.br/<pagina>/)."""
    return Olimpiada(sigla, nome, "Matemática", f"{_OBM}/{pagina}/", escala, internacional=internacional)


# A ordem importa: é a ordem de coleta, que define a ordem (e o id) das premiações na base.
CATALOGO: dict[str, Olimpiada] = {o.sigla: o for o in [
    Olimpiada("OBMEP", "Olimpíada Brasileira de Matemática das Escolas Públicas", "Matemática",
              "https://www.obmep.org.br", escala="OBMEP", tabela_impa="matematica",
              niveis_impa=frozenset({"3"})),                        # edital: só Nível 3, premiação nacional
    Olimpiada("OBM", "Olimpíada Brasileira de Matemática", "Matemática", "https://www.obm.org.br",
              escala="OBM", tabela_impa="matematica", niveis_impa=frozenset({"3"}),
              pontua_outros_premios=True),                          # "1º Prêmio" e afins (1979–1990)
    Olimpiada("OBI", "Olimpíada Brasileira de Informática", "Informática", "https://olimpiada.ic.unicamp.br",
              escala="OBMEP",                                       # aceita pelo IMPA: mesma escala da OBMEP
              tabela_impa="outras",                                 # edital: Modalidade Programação, níveis 1 e 2
              niveis_impa=frozenset({"Programação Nível 1", "Programação Nível 2"})),
    Olimpiada("IMO", "Olimpíada Internacional de Matemática (IMO)", "Matemática", "https://www.imo-official.org",
              escala="IMO", internacional=True),
    _internacional("OIM", "Olimpíada Ibero-Americana de Matemática", "IBERO",
                   "resultados-do-brasil-olimpiada-ibero-americana-de-matematica"),
    _internacional("CONESUL", "Olimpíada de Matemática do Cone Sul", "CONESUL",
                   "resultados-olimpiada-de-matematica-do-cone-sul"),
    _internacional("EGMO", "European Girls' Mathematical Olympiad", "IBERO",
                   "resultados-european-girls-mathematical-olympiad"),
    _internacional("APMO", "Asian Pacific Mathematics Olympiad", "IBERO", "resultados-apmo"),
    _internacional("IMC", "International Mathematics Competition for University Students", "IBERO", "resultados-imc"),
    _internacional("PAGMO", "Pan-American Girls' Mathematical Olympiad", "CONESUL", "resultados-pagmo"),
    _internacional("OMCPLP", "Olimpíada de Matemática da Comunidade dos Países de Língua Portuguesa", "OBM",
                   "resultados-omcplp"),
    _internacional("IGO", "Olimpíada Iraniana de Geometria", "OBM", "resultados-olimpiada-iraniana-de-geometria-igo"),
    _internacional("IMSC", "International Mathematical Summer Camp", "OBM",
                   "resultados-international-mathematical-summer-camp"),
    _internacional("OIMU", "Olimpíada Ibero-Americana de Matemática Universitária", "OBM", "resultados-oimu"),
    _internacional("CIIM", "Competição Ibero-Americana Interuniversitária de Matemática", "OBM", "resultados-ciim"),
    _internacional("MAIO", "Olimpíada de Maio", "OBMEP", "resultados-olimpiada-de-maio"),
    _internacional("OMOP", "Olimpíada de Matemática Online em Português", "OBMEP", "resultados-omop"),
    # brasileira, fora do edital do IMPA: escala de entrada
    _internacional("GALOIS", "Concurso Galois-Noether", "ENTRADA", "resultados-concurso-galois-noether",
                   internacional=False),
    # informática e IA, resultados nos sites oficiais; mesmo degrau da EGMO (internacional para meninas).
    # No fim da lista: entraram depois, e a ordem de coleta define o id das premiações
    Olimpiada("EGOI", "European Girls' Olympiad in Informatics", "Informática",
               "https://stats.egoi.org/countries/BRA/results/", escala="IBERO", internacional=True),
    Olimpiada("IOAI", "International Olympiad in Artificial Intelligence", "Informática",
               "https://ioai-official.org", escala="IBERO", internacional=True),
    # aceita pelo IMPA Tech (tabela das "outras": OBFEP, OBQ, OBI); modalidades A e B são a fase nacional
    Olimpiada("OBQ", "Olimpíada Brasileira de Química", "Química", "https://obquimica.org", escala="OBMEP",
              tabela_impa="outras", niveis_impa=frozenset({"Modalidade A", "Modalidade B"})),
]}


def buscar(sigla: str) -> Olimpiada | None:
    return CATALOGO.get(sigla)


def area(sigla: str) -> str | None:
    o = CATALOGO.get(sigla)
    return o.area if o else None


def e_alto_nivel(sigla: str) -> bool:
    """OBM ou competição internacional: quem chega aqui é raro, o que ajuda a reconhecer a mesma pessoa."""
    o = CATALOGO.get(sigla)
    return sigla == "OBM" or bool(o and o.internacional)
