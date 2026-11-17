"""Identidade de alunos: decidir quais premiações são da mesma pessoa.

As listas oficiais não têm documento nem data de nascimento, só nome, escola e cidade/UF. As regras
abaixo equilibram dois erros: separar a mesma pessoa (perde medalhas do perfil) e juntar homônimos
(atribui medalhas a quem não ganhou).
"""
from collections.abc import Iterable
from functools import lru_cache

from .escolas import PARTICULAS, palavras_da_chave
from .olimpiadas import area, e_alto_nivel
from .premiacao import MENCAO, Premiacao
from .texto import normalizar

MAX_ANOS_CARREIRA = 12              # do 6º ano do fundamental ao fim da faculdade
MAX_ANOS_SEM_PREMIO = 8             # intervalo sem premiação que, numa carreira longa demais, separa duas pessoas
LIMITE_HOMONIMOS = 0.3              # nº esperado de pessoas com o nome, abaixo do qual o nome é "raro"
LIMITE_HOMONIMOS_ALTO_NIVEL = 3.0   # mais tolerante quando há OBM/internacional em 2+ UFs


# Grafias erradas nas listas oficiais que partem uma pessoa em dois perfis, corrigidas à mão a pedido
# (correções chegam pelo contato do site). Chave: (nome sem acento, UF) como veio na fonte.
GRAFIAS_CORRIGIDAS: dict[tuple[str, str], str] = {
    # OBMEP 2018 e OBM 2019 escreveram "Gouveia"; nas outras listas, e no nome dele, é Gouvêa
    ("ISAIAS GOUVEIA GONCALVES", "DF"): "Isaías Gouvêa Gonçalves",
    # OBMEP 2018 escreveu "Edigard"; 2019, 2021 e 2022 trazem Edgard (mesma escola, em Cocal dos Alves)
    ("EDIGARD JUNIO DA SILVA VIANA", "PI"): "Edgard Junio da Silva Viana",
    # OBMEP 2017 ("Moteiro") e 2019 ("Azevedo"); nas outras listas, Azeredo de Moura Monteiro (Colégio Militar do RJ)
    ("SOFIA AZEREDO DE MOURA MOTEIRO", "RJ"): "Sofia Azeredo de Moura Monteiro",
    ("SOFIA AZEVEDO DE MOURA MONTEIRO", "RJ"): "Sofia Azeredo de Moura Monteiro",
    # OBMEP 2014 escreveu "Pimaki"; 2011 a 2017 trazem Primaki (mesma escola, em Roncador), confirmado por ele
    ("JOAO VINICIUS PIMAKI PRADO", "PR"): "João Vinícius Primaki Prado",
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
    """Alguma premiação é de OBM ou internacional (quem chega lá é raro e costuma mudar de estado)."""
    return any(e_alto_nivel(p["competicao"]) for p in premiacoes)


# Palavras comuns a muitas escolas: não servem para dizer que duas escolas são a mesma
_PALAVRAS_GENERICAS_DE_ESCOLA = frozenset({
    "ESCOLA", "ESTADUAL", "MUNICIPAL", "COLEGIO", "CENTRO", "EDUCACIONAL", "EDUCACAO", "ENSINO", "FUNDAMENTAL",
    "MEDIO", "INSTITUTO", "FEDERAL", "PROFESSOR", "PROFESSORA", "PROF", "PROFA", "UNIDADE", "CAMPUS", "INTEGRAL",
    "TEMPO", "LTDA", "INFANTIL", "BASICA", "TECNICA", "TECNOLOGIA", "CIENCIA"})


@lru_cache(maxsize=None)
def _palavras_marcantes(escola: str) -> frozenset[str]:
    """Palavras do nome da escola que a distinguem de outras (sem "escola", "estadual"…). Em cache: a mesma
    escola é comparada muitas vezes."""
    return frozenset(palavras_da_chave(escola) - _PALAVRAS_GENERICAS_DE_ESCOLA)


def mesma_escola(a: str | None, b: str | None) -> bool:
    """Os dois nomes parecem a mesma escola? Toda palavra marcante do nome mais curto casa com uma do outro,
    aceitando abreviação ("EE MAJ LAGE" == "Escola Estadual Major Lage")."""
    if not a or not b:
        return False
    menor, maior = sorted((_palavras_marcantes(a), _palavras_marcantes(b)), key=len)
    return bool(menor) and all(any(w.startswith(x) or x.startswith(w) for w in maior if min(len(w), len(x)) >= 3)
                               for x in menor)


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

    1. nome idêntico (sem acento) com uma única UF conhecida -> usa essa UF; ou, se a premiação traz a escola,
       a UF da pessoa de mesmo nome que foi premiada nessa escola (quando só uma UF bate);
    2. nome abreviado ('Enzo Holanda') que é subsequência de um único nome completo de medalhista de
       alto nível (OBM ou internacionais) -> adota o nome completo (a UF sai em atribuir_alunos). Nas
       internacionais de informática (EGOI, IOAI), os medalhistas da OBI também contam: é de lá que vêm.

    Fora das olimpíadas de alto nível, o passo 1 só vale para nome raro (ver _pode_usar_o_nome).

    Devolve (UFs inferidas pelo nome exato, nomes abreviados completados).
    """
    provas = [p for p in premiacoes if not de_massa(p)]   # menções da OBMEP não decidem a UF de ninguém
    homonimos_esperados = _estimador_de_homonimos(normalizar(p["nome"]) for p in provas)
    ufs_do_nome: dict[str, set[str]] = {}
    escolas_do_nome: dict[str, set[tuple[str, str]]] = {}   # nome -> {(UF, escola)}
    for p in provas:
        if p.get("uf"):
            ufs_do_nome.setdefault(normalizar(p["nome"]), set()).add(p["uf"])
            if p.get("escola"):
                escolas_do_nome.setdefault(normalizar(p["nome"]), set()).add((p["uf"], p["escola"]))
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
        pela_escola = {uf for uf, escola in escolas_do_nome.get(chave, ()) if mesma_escola(p.get("escola"), escola)}
        if len(pela_escola) == 1:   # nome comum, mas premiado na mesma escola: é a mesma pessoa
            p["uf"] = next(iter(pela_escola))
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


def de_massa(p: Premiacao) -> bool:
    """Menção honrosa da OBMEP: cerca de 50 mil por edição, quase sempre a única premiação da pessoa.

    Essas premiações entram nos perfis sem mudar quem é quem: não unem estados, não contam para saber se um
    nome é raro, não servem de prova do estado de quem veio sem UF e não decidem qual homônimo fica com o
    endereço "NOME|UF" (ver anexar_de_massa)."""
    return p["competicao"] == "OBMEP" and p["medalha"] == MENCAO


def _chave_da_escola(p: Premiacao) -> str:
    """Palavras que identificam a escola da premiação, em ordem ("" sem escola)."""
    return " ".join(sorted(palavras_da_chave(p.get("escola")))) if p.get("escola") else ""


def _mesma_edicao_em_lugares_diferentes(a: Premiacao, b: Premiacao) -> bool:
    """As duas premiações são da mesma olimpíada no mesmo ano, mas em cidades (ou, na mesma cidade, em escolas)
    diferentes: ninguém estuda em dois lugares ao mesmo tempo, então são homônimos. Na mesma escola pode ser a
    mesma pessoa (a OBI premia iniciação e programação no mesmo ano)."""
    if (a["competicao"], a["ano"]) != (b["competicao"], b["ano"]):
        return False
    cidade_a, cidade_b = normalizar(a.get("municipio")), normalizar(b.get("municipio"))
    if cidade_a and cidade_b and cidade_a != cidade_b:
        return True
    return bool(a.get("escola") and b.get("escola") and _chave_da_escola(a) != _chave_da_escola(b)
                and not mesma_escola(a["escola"], b["escola"]))


def _nivel_regride(registros: list[Premiacao]) -> bool:
    """Na OBMEP o nível só sobe com os anos (1 -> 2 -> 3): um nível menor num ano posterior é de outra pessoa."""
    niveis = sorted((p["ano"], int(p["nivel"])) for p in registros
                    if p["competicao"] == "OBMEP" and p.get("nivel") in ("1", "2", "3"))
    return any(depois[0] > antes[0] and depois[1] < antes[1] for antes, depois in zip(niveis, niveis[1:]))


def _cabe_numa_pessoa(registros: list[Premiacao]) -> bool:
    """As premiações podem ser de uma pessoa só: cabem numa carreira escolar, sem a mesma edição em dois lugares
    e sem o nível da OBMEP regredir."""
    anos = [p["ano"] for p in registros]
    if max(anos) - min(anos) > MAX_ANOS_CARREIRA or _nivel_regride(registros):
        return False
    return not any(_mesma_edicao_em_lugares_diferentes(a, b) for i, a in enumerate(registros) for b in registros[:i])


def _separar_por(registros: list[Premiacao], chave) -> list[list[Premiacao]]:
    """Grupos pelo valor de chave(p); quem não tem valor vai para o grupo com o ano mais próximo."""
    grupos: dict[str, list[Premiacao]] = {}
    sem_valor = []
    for p in registros:
        valor = chave(p)
        (grupos.setdefault(valor, []) if valor else sem_valor).append(p)
    if not grupos:
        return [registros]
    for p in sem_valor:
        min(grupos.values(), key=lambda g: (min(abs(p["ano"] - q["ano"]) for q in g), -len(g))).append(p)
    return list(grupos.values())


def _separar_no_tempo(registros: list[Premiacao]) -> list[list[Premiacao]]:
    """Uma carreira longa demais é cortada nos intervalos de MAX_ANOS_SEM_PREMIO anos ou mais sem premiação."""
    ordenados = sorted(registros, key=lambda p: p["ano"])
    if ordenados[-1]["ano"] - ordenados[0]["ano"] <= MAX_ANOS_CARREIRA:
        return [registros]
    partes = [[ordenados[0]]]
    for p in ordenados[1:]:
        if p["ano"] - partes[-1][-1]["ano"] >= MAX_ANOS_SEM_PREMIO:
            partes.append([])
        partes[-1].append(p)
    return partes


def separar_homonimos(registros: list[Premiacao]) -> list[list[Premiacao]]:
    """Divide as premiações de um mesmo nome numa mesma UF quando elas não cabem numa pessoa só
    (ver _cabe_numa_pessoa). A maior parte dos nomes volta inteira, num grupo só.

    A divisão é por cidade; dentro de uma cidade, por escola quando a mesma edição aparece em duas; e, numa
    carreira longa demais, pelos intervalos sem premiação. Pedaços que cabem juntos numa pessoa (quem mudou de
    cidade) são reunidos, desde que só haja um pedaço com que possam se juntar. O primeiro grupo devolvido é o
    maior: ele fica com o id "NOME|UF" e os outros ganham a cidade no id.
    """
    if _cabe_numa_pessoa(registros):
        return [registros]
    pedacos: list[list[Premiacao]] = []
    for da_cidade in _separar_por(registros, lambda p: normalizar(p.get("municipio"))):
        por_escola = [da_cidade] if _cabe_numa_pessoa(da_cidade) else _separar_por(da_cidade, _chave_da_escola)
        for da_escola in por_escola:
            pedacos += _separar_no_tempo(da_escola)
    pedacos.sort(key=lambda g: (-len(g), -max(p["ano"] for p in g)))
    pessoas: list[list[Premiacao]] = []
    for pedaco in pedacos:
        compativeis = [pessoa for pessoa in pessoas if _cabe_numa_pessoa(pessoa + pedaco)]
        if len(compativeis) == 1:
            compativeis[0].extend(pedaco)
        else:
            pessoas.append(list(pedaco))
    return pessoas


def atribuir_alunos(premiacoes: list[Premiacao]) -> int:
    """Preenche `aluno_id` ("NOME NORMALIZADO|UF") em cada premiação. Devolve quantas pessoas foram
    reunidas entre UFs diferentes.

    As premiações de massa (de_massa) ficam de fora dessas regras: depois que as demais definem quem é quem,
    elas só se juntam aos perfis que já existem ou formam pessoas novas (anexar_de_massa).
    """
    principais = [p for p in premiacoes if not de_massa(p)]
    unidos = _atribuir(principais)
    anexar_de_massa([p for p in premiacoes if de_massa(p)], principais)
    return unidos


def _novo_id(nome: str, uf: str, grupo: list[Premiacao], usados: set[str]) -> str:
    """ "NOME|UF"; se já é de outra pessoa (homônimo da mesma UF), a cidade (e um número, se preciso) distingue."""
    ident = f"{nome}|{uf}"
    if ident in usados:
        cidade = normalizar(max(grupo, key=lambda p: (bool(p.get("municipio")), p["ano"])).get("municipio"))
        base, n = f"{ident}|{cidade}", 1
        ident = base
        while ident in usados:
            n += 1
            ident = f"{base} {n}"
    usados.add(ident)
    return ident


def anexar_de_massa(massa: list[Premiacao], principais: list[Premiacao]) -> None:
    """Dá aluno_id às premiações de massa sem mexer nos perfis que as demais premiações definiram.

    Cada uma entra no perfil de mesmo nome e mesma UF em que cabe (_cabe_numa_pessoa: mesma carreira, sem
    repetir edição, sem o nível regredir); se dois homônimos cabem, só a mesma escola decide, e na dúvida ela não
    entra em nenhum. As que sobram formam pessoas novas, divididas como os homônimos (separar_homonimos); se o
    "NOME|UF" já é de um medalhista, elas levam a cidade no id."""
    pessoas: dict[str, list[Premiacao]] = {}
    for p in principais:
        pessoas.setdefault(p["aluno_id"], []).append(p)
    por_nome_uf: dict[tuple[str, str], list[str]] = {}
    usados: dict[str, set[str]] = {}
    for ident, registros in pessoas.items():
        nome = ident.split("|")[0]
        usados.setdefault(nome, set()).add(ident)
        for uf in {p["uf"] for p in registros if p.get("uf")}:
            por_nome_uf.setdefault((nome, uf), []).append(ident)

    grupos: dict[tuple[str, str], list[Premiacao]] = {}
    for p in massa:
        grupos.setdefault((normalizar(p["nome"]), p.get("uf") or ""), []).append(p)
    for (nome, uf), registros in grupos.items():
        sobra = []
        for p in sorted(registros, key=lambda p: p["ano"]):
            cabem = [i for i in por_nome_uf.get((nome, uf), ()) if _cabe_numa_pessoa(pessoas[i] + [p])]
            if len(cabem) > 1:
                cabem = [i for i in cabem if any(mesma_escola(p.get("escola"), q.get("escola")) for q in pessoas[i])]
            if len(cabem) == 1:
                p["aluno_id"] = cabem[0]
                pessoas[cabem[0]].append(p)
            else:
                sobra.append(p)
        for grupo in separar_homonimos(sobra) if sobra else []:
            ident = _novo_id(nome, uf, grupo, usados.setdefault(nome, set()))
            for p in grupo:
                p["aluno_id"] = ident


def _atribuir(premiacoes: list[Premiacao]) -> int:
    """As regras de atribuir_alunos, para as premiações que não são de massa.

    Por padrão, mesma pessoa = mesmo nome (sem acento) + mesma UF. Como alunos de ponta mudam de estado
    (vão estudar em Fortaleza, por exemplo), o mesmo nome em UFs diferentes é unido quando:
      - não há conflito: o nome premiado na mesma olimpíada e no mesmo ano em duas UFs são homônimos;
      - as premiações cabem numa carreira escolar (≤ MAX_ANOS_CARREIRA anos);
      - o nome é raro: o número esperado de pessoas com esse nome, estimado pela frequência de cada
        palavra entre todos os nomes, fica abaixo de LIMITE_HOMONIMOS.
    Premiações sem UF entram na pessoa quando ela é única (e, fora do alto nível, o nome é raro).

    Dentro de uma UF, o mesmo nome é dividido quando as premiações não cabem numa pessoa só (separar_homonimos):
    a maior parte fica com "NOME|UF" e as outras ganham a cidade no id ("NOME|UF|CIDADE").
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
        reunido = False

        if len(grupos) > 1:
            dono: dict[tuple, str] = {}
            conflito = False
            for uf, ps in por_uf.items():
                for edicao in {(p["competicao"], p["ano"]) for p in ps}:
                    conflito |= dono.setdefault(edicao, uf) != uf
            anos = [p["ano"] for p in registros]
            cabe_na_carreira = max(anos) - min(anos) <= MAX_ANOS_CARREIRA
            limite = LIMITE_HOMONIMOS_ALTO_NIVEL if sum(_alto_nivel(g) for g in grupos) >= 2 else LIMITE_HOMONIMOS
            if not conflito and cabe_na_carreira and homonimos_esperados(nome) < limite:
                grupos = [[p for g in grupos for p in g]]
                unidos += 1
                reunido = True
        if not reunido:   # quem foi reunido entre estados já passou pelas mesmas checagens
            grupos = [pessoa for g in grupos for pessoa in separar_homonimos(g)]

        ids: list[str] = []
        usados: set[str] = set()
        for grupo in grupos:
            # UF principal = a do registro mais recente (aparece no perfil e no ranking por estado)
            principal = max(grupo, key=lambda p: (p["ano"], p["competicao"] != "OBMEP"))["uf"]
            ident = _novo_id(nome, principal, grupo, usados)
            ids.append(ident)
            for p in grupo:
                p["aluno_id"] = ident
        for p in sem_uf:
            unico = len(ids) == 1 and _pode_usar_o_nome(p, homonimos_esperados)
            # o medalhista da IMO de 1985 não é o aluno de mesmo nome premiado em 2015
            anos = [q["ano"] for q in grupos[0]] + [p["ano"]] if unico else []
            cabe_na_carreira = unico and max(anos) - min(anos) <= MAX_ANOS_CARREIRA
            p["aluno_id"] = ids[0] if cabe_na_carreira else f"{nome}|"
    return unidos
