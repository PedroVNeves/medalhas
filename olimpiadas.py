"""Cadastro das olimpíadas suportadas.

Para adicionar uma olimpíada nova:
  1. escreva o coletor em scraper/<sigla>.py com uma função scrape() que devolve registros no mesmo
     formato dos existentes (competicao, ano, nivel, nome, escola, municipio, uf, premio, medalha, fonte…);
  2. cadastre-a abaixo (nome, área, tabela de pontos e regra do IMPA Tech, se houver);
  3. rode `python build_db.py`.
A interface monta os filtros de olimpíada, área e nível a partir dos dados, sem mudar o front-end.
"""
from scraper import imo, obi, obm, obm_internacional, obmep

# Tabela oficial do IMPA Tech — Edital do Processo Seletivo 2026, item 6.1
FONTE_PONTOS = {
    "nome": "Edital do Processo Seletivo 2026 do IMPA Tech, item 6.1",
    "url": "https://impatech.edu.br/wp-content/uploads/2025/10/Edital-IMPA-Tech-2026-versao-final-2025-10-23site.pdf",
}
PONTOS_MATEMATICA = {"Ouro": 18, "Prata": 6, "Bronze": 2}   # OBMEP e OBM no edital
PONTOS_OUTRAS_IMPA = {"Ouro": 9, "Prata": 3, "Bronze": 1}   # OBFEP, OBQ e OBI no mesmo edital

# ---------------------------------------------------------------------------------------------
# "Nossa versão": escala própria que reflete a dificuldade de cada olimpíada.
# Regras (verificadas em _checar_escala ao importar):
#   - ouro OBM = 2 × ouro OBMEP
#   - bronze OBM  > ouro OBMEP
#   - bronze Ibero > prata OBM
#   - bronze IMO  > prata Ibero
#   - olimpíadas de entrada (Canguru e similares) valem bem menos que a OBMEP
#   - olimpíadas brasileiras aceitas pelo IMPA Tech (OBI, OBQ, OBFEP) usam a escala da OBMEP;
#     as brasileiras fora do edital usam a escala de entrada
# As tabelas de olimpíadas que ainda não têm coletor ficam aqui prontas para quando entrarem.
ESCALA_SITE = {
    "ENTRADA": {"Ouro": 20, "Prata": 12, "Bronze": 6},      # Canguru e similares
    "OBMEP": {"Ouro": 100, "Prata": 60, "Bronze": 30},
    "OBM": {"Ouro": 200, "Prata": 150, "Bronze": 110, "Menção Honrosa": 40, "_outros": 110},
    "CONESUL": {"Ouro": 260, "Prata": 190, "Bronze": 140, "Menção Honrosa": 50},
    "IBERO": {"Ouro": 320, "Prata": 240, "Bronze": 170, "Menção Honrosa": 60},
    "IMO": {"Ouro": 600, "Prata": 400, "Bronze": 280, "Menção Honrosa": 100},
}


def _checar_escala() -> None:
    e = ESCALA_SITE
    assert e["OBM"]["Ouro"] == 2 * e["OBMEP"]["Ouro"], "ouro OBM deve ser o dobro do ouro OBMEP"
    assert e["OBM"]["Bronze"] > e["OBMEP"]["Ouro"], "bronze OBM deve valer mais que ouro OBMEP"
    assert e["IBERO"]["Bronze"] > e["OBM"]["Prata"], "bronze Ibero deve valer mais que prata OBM"
    assert e["IMO"]["Bronze"] > e["IBERO"]["Prata"], "bronze IMO deve valer mais que prata Ibero"
    assert e["OBM"]["Ouro"] < e["CONESUL"]["Ouro"] < e["IBERO"]["Ouro"], "Cone Sul fica entre OBM e Ibero"
    assert e["ENTRADA"]["Ouro"] < e["OBMEP"]["Bronze"], "olimpíadas de entrada valem menos que a OBMEP"
    for tabela in e.values():
        assert tabela["Ouro"] > tabela["Prata"] > tabela["Bronze"]


_checar_escala()


def _sem_outros(tabela: dict) -> dict:
    return {k: v for k, v in tabela.items() if not k.startswith("_")}


OLIMPIADAS = {
    "OBMEP": {
        "nome": "Olimpíada Brasileira de Matemática das Escolas Públicas",
        "area": "Matemática",
        "pontos": PONTOS_MATEMATICA,             # tabela IMPA Tech
        "pontos_site": ESCALA_SITE["OBMEP"],
        "impa_niveis": {"3"},          # edital: só Nível 3, premiação nacional
        "scrape": obmep.scrape,
        "site": "https://www.obmep.org.br",
    },
    "OBM": {
        "nome": "Olimpíada Brasileira de Matemática",
        "area": "Matemática",
        "pontos": PONTOS_MATEMATICA,
        # menção honrosa e prêmios antigos ("1º Prêmio"…, 1979–1990) também pontuam
        "pontos_site": ESCALA_SITE["OBM"],
        "impa_niveis": {"3"},          # edital: só Nível 3
        "scrape": obm.scrape,
        "site": "https://www.obm.org.br",
    },
    "OBI": {
        "nome": "Olimpíada Brasileira de Informática",
        "area": "Informática",
        "pontos": PONTOS_OUTRAS_IMPA,
        "pontos_site": ESCALA_SITE["OBMEP"],   # aceita pelo IMPA Tech: mesma escala da OBMEP
        # edital: Modalidade Programação, Níveis 1 e 2
        "impa_niveis": {"Programação Nível 1", "Programação Nível 2"},
        "scrape": obi.scrape,
        "site": "https://olimpiada.ic.unicamp.br",
    },
    "IMO": {
        "nome": "Olimpíada Internacional de Matemática (IMO)",
        "area": "Matemática", "internacional": True,
        "pontos": {}, "pontos_site": ESCALA_SITE["IMO"], "impa_niveis": set(),
        "scrape": imo.scrape,
        "site": "https://www.imo-official.org",
    },
}

# Competições internacionais com resultados do Brasil publicados pela OBM: (nome, escala da nossa versão)
_INTERNACIONAIS = {
    "OIM": ("Olimpíada Ibero-Americana de Matemática", "IBERO"),
    "CONESUL": ("Olimpíada de Matemática do Cone Sul", "CONESUL"),
    "EGMO": ("European Girls' Mathematical Olympiad", "IBERO"),
    "APMO": ("Asian Pacific Mathematics Olympiad", "IBERO"),
    "IMC": ("International Mathematics Competition for University Students", "IBERO"),
    "PAGMO": ("Pan-American Girls' Mathematical Olympiad", "CONESUL"),
    "OMCPLP": ("Olimpíada de Matemática da Comunidade dos Países de Língua Portuguesa", "OBM"),
    "IGO": ("Olimpíada Iraniana de Geometria", "OBM"),
    "IMSC": ("International Mathematical Summer Camp", "OBM"),
    "OIMU": ("Olimpíada Ibero-Americana de Matemática Universitária", "OBM"),
    "CIIM": ("Competição Ibero-Americana Interuniversitária de Matemática", "OBM"),
    "MAIO": ("Olimpíada de Maio", "OBMEP"),
    "OMOP": ("Olimpíada de Matemática Online em Português", "OBMEP"),
    "GALOIS": ("Concurso Galois-Noether", "ENTRADA"),  # brasileira, fora do edital do IMPA
}
for _sigla, (_nome, _escala) in _INTERNACIONAIS.items():
    OLIMPIADAS[_sigla] = {
        "nome": _nome, "area": "Matemática", "internacional": _sigla != "GALOIS",
        # sem "_outros": certificados de participação não pontuam (o "_outros" é só da OBM antiga)
        "pontos": {}, "pontos_site": _sem_outros(ESCALA_SITE[_escala]), "impa_niveis": set(),
        "scrape": obm_internacional.scraper_for(_sigla),
        "site": f"{obm_internacional.BASE}/{obm_internacional.COMPETICOES[_sigla][0]}/",
    }

# Métodos de pontuação que o usuário escolhe no topo do site. "coluna" é a coluna na base.
METODOS = {
    "impa": {
        "nome": "IMPA · todos os níveis",
        "curto": "IMPA",
        "descricao": "Tabela oficial do IMPA Tech (ouro 18, prata 6, bronze 2) aplicada às medalhas de todos os níveis.",
        "coluna": "p_impa",
    },
    "impa3": {
        "nome": "IMPA oficial · só Nível 3",
        "curto": "IMPA N3",
        "descricao": "Exatamente o que o edital do IMPA Tech aceita: medalhas do Nível 3 da OBMEP (premiação nacional) e da OBM.",
        "coluna": "p_impa3",
    },
    "site": {
        "nome": "Medalhas (nossa versão)",
        "curto": "Nossa",
        "descricao": "Escala por dificuldade: ouro OBMEP 100, bronze OBM 110, ouro OBM 200; Ibero e IMO acima; olimpíadas de entrada bem abaixo. Menções e prêmios antigos da OBM pontuam.",
        "coluna": "p_site",
    },
}
METODO_PADRAO = "impa"


def escala_de(competicao: str) -> str | None:
    tabela = _sem_outros(OLIMPIADAS.get(competicao, {}).get("pontos_site") or {})
    return next((k for k, v in ESCALA_SITE.items() if _sem_outros(v) == tabela), None)


def niveis_impa() -> str:
    """Níveis aceitos pelo IMPA Tech em alguma olimpíada (hoje só "3"), no formato do filtro."""
    return ",".join(sorted({n for o in OLIMPIADAS.values() for n in o["impa_niveis"]}))


def pontos(competicao: str, medalha: str) -> int:
    """IMPA (todos os níveis): tabela IMPA aplicada a qualquer nível (menção honrosa não pontua)."""
    return OLIMPIADAS.get(competicao, {}).get("pontos", {}).get(medalha, 0)


def pontos_impa(competicao: str, medalha: str, nivel: str | None) -> int:
    """IMPA oficial: pontos aceitos no processo seletivo do IMPA Tech (0 se a olimpíada/nível não conta)."""
    info = OLIMPIADAS.get(competicao, {})
    if nivel in info.get("impa_niveis", set()):
        return info["pontos"].get(medalha, 0)
    return 0


def pontos_site(competicao: str, medalha: str) -> int:
    """Nossa versão (pesos próprios do site)."""
    tabela = OLIMPIADAS.get(competicao, {}).get("pontos_site", {})
    return tabela.get(medalha, tabela.get("_outros", 0))


def area(competicao: str) -> str | None:
    return OLIMPIADAS.get(competicao, {}).get("area")


def catalogo() -> list[dict]:
    """Versão serializável (para a API/front-end)."""
    return [{"sigla": s, "nome": o["nome"], "area": o["area"], "pontos": o["pontos"],
             "pontos_site": {k: v for k, v in o["pontos_site"].items() if not k.startswith("_")},
             "pontos_site_outros": o["pontos_site"].get("_outros", 0),
             "impa_niveis": sorted(o["impa_niveis"]), "site": o["site"], "escala": escala_de(s),
             "internacional": o.get("internacional", False)} for s, o in OLIMPIADAS.items()]


def metodos() -> list[dict]:
    return [{"id": k, **{c: v for c, v in m.items() if c != "coluna"}} for k, m in METODOS.items()]
