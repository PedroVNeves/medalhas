"""Regras de pontuação: tabela oficial do IMPA Tech e a escala própria do site ("nossa versão").

Cada premiação recebe pontos nos três métodos ao gerar a base; o usuário escolhe qual deles ordena
rankings e define o nível (tier) de alunos e escolas.
"""
from .olimpiadas import CATALOGO

# Tabela oficial do IMPA Tech: Edital do Processo Seletivo 2026, item 6.1
FONTE_PONTOS = {
    "nome": "Edital do Processo Seletivo 2026 do IMPA Tech, item 6.1",
    "url": "https://impatech.edu.br/wp-content/uploads/2025/10/Edital-IMPA-Tech-2026-versao-final-2025-10-23site.pdf",
}
TABELAS_IMPA = {
    "matematica": {"Ouro": 18, "Prata": 6, "Bronze": 2},   # OBMEP e OBM
    "outras": {"Ouro": 9, "Prata": 3, "Bronze": 1},        # OBFEP, OBQ e OBI
}

# "Nossa versão": escala própria que reflete a dificuldade de cada olimpíada. Regras verificadas em
# _verificar_escala ao importar o módulo:
#   - ouro OBM = 2 × ouro OBMEP;  bronze OBM > ouro OBMEP
#   - bronze Ibero > prata OBM;   bronze IMO > prata Ibero;   Cone Sul entre OBM e Ibero
#   - olimpíadas de entrada (Canguru e similares) valem bem menos que a OBMEP
#   - brasileiras aceitas pelo IMPA Tech (OBI, OBQ, OBFEP) usam a escala da OBMEP; as fora do edital,
#     a escala de entrada
# Degraus sem olimpíada coletada ainda (ENTRADA) ficam prontos para quando entrarem.
ESCALA_SITE = {
    "ENTRADA": {"Ouro": 20, "Prata": 12, "Bronze": 6},
    "OBMEP": {"Ouro": 100, "Prata": 60, "Bronze": 30},
    "OBM": {"Ouro": 200, "Prata": 150, "Bronze": 110, "Menção Honrosa": 40},
    "CONESUL": {"Ouro": 260, "Prata": 190, "Bronze": 140, "Menção Honrosa": 50},
    "IBERO": {"Ouro": 320, "Prata": 240, "Bronze": 170, "Menção Honrosa": 60},
    "IMO": {"Ouro": 600, "Prata": 400, "Bronze": 280, "Menção Honrosa": 100},
}

# Métodos que o usuário escolhe no topo do site. "coluna" é onde os pontos ficam em cada registro.
METODOS = {
    "impa": {
        "nome": "IMPA · todos os níveis",
        "curto": "IMPA",
        "descricao": "Tabela oficial do IMPA Tech (ouro 18, prata 6, bronze 2) aplicada às medalhas de todos os "
                     "níveis.",
        "coluna": "p_impa",
    },
    "impa3": {
        "nome": "IMPA oficial · só Nível 3",
        "curto": "IMPA N3",
        "descricao": "Exatamente o que o edital do IMPA Tech aceita: medalhas do Nível 3 da OBMEP (premiação "
                     "nacional) e da OBM.",
        "coluna": "p_impa3",
    },
    "site": {
        "nome": "Medalhas (nossa versão)",
        "curto": "Nossa",
        "descricao": "Escala por dificuldade: ouro OBMEP 100, bronze OBM 110, ouro OBM 200; Ibero e IMO acima; "
                     "olimpíadas de entrada bem abaixo. Menções e prêmios antigos da OBM pontuam.",
        "coluna": "p_site",
    },
}
METODO_PADRAO = "impa"
COLUNAS = [m["coluna"] for m in METODOS.values()]   # p_impa, p_impa3, p_site


def _verificar_escala() -> None:
    e = ESCALA_SITE
    assert e["OBM"]["Ouro"] == 2 * e["OBMEP"]["Ouro"], "ouro OBM deve ser o dobro do ouro OBMEP"
    assert e["OBM"]["Bronze"] > e["OBMEP"]["Ouro"], "bronze OBM deve valer mais que ouro OBMEP"
    assert e["IBERO"]["Bronze"] > e["OBM"]["Prata"], "bronze Ibero deve valer mais que prata OBM"
    assert e["IMO"]["Bronze"] > e["IBERO"]["Prata"], "bronze IMO deve valer mais que prata Ibero"
    assert e["OBM"]["Ouro"] < e["CONESUL"]["Ouro"] < e["IBERO"]["Ouro"], "Cone Sul fica entre OBM e Ibero"
    assert e["ENTRADA"]["Ouro"] < e["OBMEP"]["Bronze"], "olimpíadas de entrada valem menos que a OBMEP"
    for tabela in e.values():
        assert tabela["Ouro"] > tabela["Prata"] > tabela["Bronze"]
    for o in CATALOGO.values():
        assert o.escala in e, f"{o.sigla}: escala desconhecida {o.escala!r}"
        assert o.tabela_impa in (None, *TABELAS_IMPA), f"{o.sigla}: tabela do IMPA desconhecida"


_verificar_escala()


# ---------------------------------------------------------------- pontos de uma premiação

def pontos_impa(competicao: str, medalha: str) -> int:
    """IMPA (todos os níveis): a tabela do edital aplicada a qualquer nível. Menção honrosa não pontua."""
    o = CATALOGO.get(competicao)
    return TABELAS_IMPA[o.tabela_impa].get(medalha, 0) if o and o.tabela_impa else 0


def pontos_impa_oficial(competicao: str, medalha: str, nivel: str | None) -> int:
    """IMPA oficial: só o que o edital aceita (olimpíada e nível); 0 no resto."""
    o = CATALOGO.get(competicao)
    return pontos_impa(competicao, medalha) if o and nivel in o.niveis_impa else 0


def pontos_site(competicao: str, medalha: str) -> int:
    """Nossa versão. Prêmios antigos da OBM ("1º Prêmio"…) valem como bronze."""
    o = CATALOGO.get(competicao)
    if not o:
        return 0
    escala = ESCALA_SITE[o.escala]
    return escala.get(medalha, escala["Bronze"] if o.pontua_outros_premios else 0)


def pontuar(competicao: str, medalha: str, nivel: str | None) -> dict[str, int]:
    """Pontos da premiação nos três métodos, indexados pela coluna de cada método."""
    return {"p_impa": pontos_impa(competicao, medalha),
            "p_impa3": pontos_impa_oficial(competicao, medalha, nivel),
            "p_site": pontos_site(competicao, medalha)}


# ---------------------------------------------------------------- escolha do método

def resolver_metodo(valor: str | None) -> tuple[str, str]:
    """(id do método, coluna de pontos). Valor desconhecido ou vazio cai no método padrão."""
    metodo = valor if valor in METODOS else METODO_PADRAO
    return metodo, METODOS[metodo]["coluna"]


def niveis_impa() -> str:
    """Níveis aceitos pelo IMPA Tech em alguma olimpíada, no formato do filtro ("3,Programação Nível 1,…")."""
    return ",".join(sorted({n for o in CATALOGO.values() for n in o.niveis_impa}))


def restringir_niveis(metodo: str, niveis: str | None) -> str | None:
    """No método IMPA N3 só contam os níveis do edital: o filtro de nível fica limitado a eles.

    Se o usuário já escolheu níveis aceitos (ex.: só "Programação Nível 2"), a escolha é respeitada.
    """
    if metodo != "impa3":
        return niveis
    aceitos = niveis_impa().split(",")
    escolhidos = [n for n in (niveis or "").split(",") if n in aceitos]
    return ",".join(escolhidos or aceitos)


# ---------------------------------------------------------------- versões serializáveis (site e API)

def catalogo() -> list[dict]:
    return [{"sigla": o.sigla, "nome": o.nome, "area": o.area,
             "pontos": TABELAS_IMPA.get(o.tabela_impa or "", {}),
             "pontos_site": ESCALA_SITE[o.escala],
             "pontos_site_outros": ESCALA_SITE[o.escala]["Bronze"] if o.pontua_outros_premios else 0,
             "impa_niveis": sorted(o.niveis_impa), "site": o.site, "escala": o.escala,
             "internacional": o.internacional} for o in CATALOGO.values()]


def metodos() -> list[dict]:
    return [{"id": k, **{c: v for c, v in m.items() if c != "coluna"}} for k, m in METODOS.items()]
