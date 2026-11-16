"""Identidade de alunos: decidir quais premiações são da mesma pessoa.

As listas oficiais não têm documento nem data de nascimento, só nome, escola e cidade/UF. As regras
abaixo equilibram dois erros: separar a mesma pessoa (perde medalhas do perfil) e juntar homônimos
(atribui medalhas a quem não ganhou).
"""
from collections.abc import Iterable

from .olimpiadas import area, e_alto_nivel
from .premiacao import Premiacao
from .texto import normalizar

PARTICULAS = {"DE", "DA", "DO", "DAS", "DOS", "E", "D"}
MAX_ANOS_CARREIRA = 12              # do 6º ano do fundamental ao fim da faculdade
LIMITE_HOMONIMOS = 0.3              # nº esperado de pessoas com o nome, abaixo do qual o nome é "raro"
LIMITE_HOMONIMOS_ALTO_NIVEL = 3.0   # mais tolerante quando há OBM/internacional em 2+ UFs


# Grafias erradas nas listas oficiais que partem uma pessoa em dois perfis, corrigidas à mão a pedido
# (correções chegam pelo contato do site). Chave: (nome sem acento, UF) como veio na fonte.
GRAFIAS_CORRIGIDAS: dict[tuple[str, str], str] = {
    # OBMEP 2018 e OBM 2019 escreveram "Gouveia"; nas outras listas, e no nome dele, é Gouvêa
    ("ISAIAS GOUVEIA GONCALVES", "DF"): "Isaías Gouvêa Gonçalves",
    # OBMEP 2018 escreveu "Edigard"; 2019, 2021 e 2022 trazem Edgard (mesma escola, em Cocal dos Alves)
    ("EDIGARD JUNIO DA SILVA VIANA", "PI"): "Edgard Junio da Silva Viana",
}


def corrigir_grafias(premiacoes: list[Premiacao]) -> int:
    """Troca o nome das premiações listadas em GRAFIAS_CORRIGIDAS. Altera a lista; devolve quantas mudaram."""
    corrigidas = 0
    for p in premiacoes:
        certo = GRAFIAS_CORRIGIDAS.get((normalizar(p["nome"]), p.get("uf") or ""))
        if certo:
            p["nome"] = certo
            corrigidas += 1
    return corrigidas


def _subsequencia(curto: list[str], longo: list[str]) -> bool:
    """'ENZO HOLANDA' é subsequência de 'ENZO HOLANDA SAMPAIO': mesma ordem e mesmo primeiro nome."""
    if not curto or curto[0] != longo[0]:
        return False
    restante = iter(longo)
    return all(palavra in restante for palavra in curto)


def _alto_nivel(premiacoes: Iterable[Premiacao]) -> bool:
    return any(e_alto_nivel(p["competicao"]) for p in premiacoes)


def _estimador_de_homonimos(nomes: Iterable[str]):
    """Função nome -> número esperado de pessoas com esse nome, pela frequência de cada palavra entre os
    nomes distintos (nomes já normalizados)."""
    distintos = set(nomes)
    total = len(distintos) or 1
    frequencia: dict[str, int] = {}
    for nome in distintos:
        for palavra in set(nome.split()) - PARTICULAS:
            frequencia[palavra] = frequencia.get(palavra, 0) + 1

    def homonimos_esperados(nome: str) -> float:
        esperado = float(total)
        for palavra in set(nome.split()) - PARTICULAS:
            esperado *= frequencia.get(palavra, 1) / total
        return esperado
    return homonimos_esperados


def _pode_usar_o_nome(p: Premiacao, homonimos_esperados) -> bool:
    """Premiação sem UF pode ir para a única pessoa com o mesmo nome? Em olimpíada de alto nível (IMO…) sim:
    quem chega lá é raro. Nas demais (regionais, com muitos alunos), só se o próprio nome for raro."""
    return e_alto_nivel(p["competicao"]) or homonimos_esperados(normalizar(p["nome"])) < LIMITE_HOMONIMOS


def completar_identidades(premiacoes: list[Premiacao]) -> tuple[int, int]:
    """Para quem veio sem UF (IMO, IMC…), descobre a pessoa nos outros registros. Altera a lista.

    1. nome idêntico (sem acento) com uma única UF conhecida -> usa essa UF;
    2. nome abreviado ('Enzo Holanda') que é subsequência de um único nome completo de medalhista de
       alto nível (OBM ou internacionais) -> adota o nome completo (a UF sai em atribuir_alunos). Nas
       internacionais de informática (EGOI, IOAI), os medalhistas da OBI também contam: é de lá que vêm.

    Fora das olimpíadas de alto nível, o passo 1 só vale para nome raro (ver _pode_usar_o_nome).

    Devolve (UFs inferidas pelo nome exato, nomes abreviados completados).
    """
    homonimos_esperados = _estimador_de_homonimos(normalizar(p["nome"]) for p in premiacoes)
    ufs_do_nome: dict[str, set[str]] = {}
    for p in premiacoes:
        if p.get("uf"):
            ufs_do_nome.setdefault(normalizar(p["nome"]), set()).add(p["uf"])
    alto_nivel: dict[str, str] = {}
    for p in premiacoes:
        if p.get("uf") and e_alto_nivel(p["competicao"]):
            alto_nivel.setdefault(normalizar(p["nome"]), p["nome"])
    candidatos = [(normalizado.split(), nome) for normalizado, nome in alto_nivel.items()]
    obi: dict[str, str] = {}
    for p in premiacoes:
        if p.get("uf") and p["competicao"] == "OBI":
            obi.setdefault(normalizar(p["nome"]), p["nome"])
    candidatos_informatica = candidatos + [(n.split(), nome) for n, nome in obi.items() if n not in alto_nivel]

    exatos = abreviados = 0
    for p in premiacoes:
        if p.get("uf"):
            continue
        chave = normalizar(p["nome"])
        if len(ufs_do_nome.get(chave, ())) == 1 and _pode_usar_o_nome(p, homonimos_esperados):
            p["uf"] = next(iter(ufs_do_nome[chave]))
            exatos += 1
            continue
        palavras = chave.split()
        if len(palavras) < 2:
            continue
        lista = candidatos_informatica if area(p["competicao"]) == "Informática" else candidatos
        achados = {nome for c, nome in lista if len(c) > len(palavras) and _subsequencia(palavras, c)}
        if len(achados) == 1:
            p["nome"] = next(iter(achados))
            abreviados += 1
    return exatos, abreviados


def atribuir_alunos(premiacoes: list[Premiacao]) -> int:
    """Preenche `aluno_id` ("NOME NORMALIZADO|UF") em cada premiação. Devolve quantas pessoas foram
    reunidas entre UFs diferentes.

    Por padrão, mesma pessoa = mesmo nome (sem acento) + mesma UF. Como alunos de ponta mudam de estado
    (vão estudar em Fortaleza, por exemplo), o mesmo nome em UFs diferentes é unido quando:
      - não há conflito: o nome premiado na mesma olimpíada e no mesmo ano em duas UFs são homônimos;
      - as premiações cabem numa carreira escolar (≤ MAX_ANOS_CARREIRA anos);
      - o nome é raro: o número esperado de pessoas com esse nome, estimado pela frequência de cada
        palavra entre todos os nomes, fica abaixo de LIMITE_HOMONIMOS.
    Premiações sem UF entram na pessoa quando ela é única (e, fora do alto nível, o nome é raro).
    """
    por_nome: dict[str, list[Premiacao]] = {}
    for p in premiacoes:
        por_nome.setdefault(normalizar(p["nome"]), []).append(p)
    homonimos_esperados = _estimador_de_homonimos(por_nome)

    unidos = 0
    for nome, registros in por_nome.items():
        por_uf: dict[str, list[Premiacao]] = {}
        sem_uf: list[Premiacao] = []
        for p in registros:
            (por_uf.setdefault(p["uf"], []) if p.get("uf") else sem_uf).append(p)
        grupos = list(por_uf.values())

        if len(grupos) > 1:
            dono: dict[tuple, str] = {}
            conflito = False
            for uf, ps in por_uf.items():
                for edicao in {(p["competicao"], p["ano"]) for p in ps}:
                    conflito |= dono.setdefault(edicao, uf) != uf
            anos = [p["ano"] for p in registros if p["ano"]]
            cabe_na_carreira = max(anos) - min(anos) <= MAX_ANOS_CARREIRA
            limite = LIMITE_HOMONIMOS_ALTO_NIVEL if sum(_alto_nivel(g) for g in grupos) >= 2 else LIMITE_HOMONIMOS
            if not conflito and cabe_na_carreira and homonimos_esperados(nome) < limite:
                grupos = [[p for g in grupos for p in g]]
                unidos += 1

        ids = []
        for grupo in grupos:
            # UF principal = a do registro mais recente (aparece no perfil e no ranking por estado)
            principal = max(grupo, key=lambda p: (p["ano"] or 0, p["competicao"] != "OBMEP"))["uf"]
            ident = f"{nome}|{principal}"
            ids.append(ident)
            for p in grupo:
                p["aluno_id"] = ident
        for p in sem_uf:
            unico = len(ids) == 1 and _pode_usar_o_nome(p, homonimos_esperados)
            p["aluno_id"] = ids[0] if unico else f"{nome}|"
    return unidos
