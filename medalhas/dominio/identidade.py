"""Identidade de alunos: decidir quais premiações são da mesma pessoa.

As listas oficiais não têm documento nem data de nascimento, só nome, escola e cidade/UF. As regras
abaixo equilibram dois erros: separar a mesma pessoa (perde medalhas do perfil) e juntar homônimos
(atribui medalhas a quem não ganhou). Juntar homônimos é o erro grave: põe no perfil de alguém uma medalha
que não é dele, sem que quem lê perceba. Na dúvida, as regras separam.

Ordem em que gerar_base as aplica:
1. corrigir_grafias: as correções à mão (GRAFIAS_CORRIGIDAS) vêm antes de tudo;
2. completar_identidades: a UF de quem veio sem ela e os nomes abreviados das listas internacionais;
3. atribuir_alunos: mesmo nome (sem acento) + mesma UF = mesma pessoa, com as travas que separam homônimos
   (_cabe_numa_pessoa) e a união entre estados para nomes raros;
4. juntar_grafias (depois da cidade das escolas): perfis da mesma pessoa com o nome escrito de jeitos
   diferentes ("Almir Sergio R dos Santos Filho" e "Almir Sergio Ramos dos Santos Filho"), só com prova de
   contexto (mesma escola, ou mesma cidade a até 3 anos) e um agrupamento que recusa juntar grupos que não
   cabem numa pessoa.

As regras, em linguagem simples, estão em docs/identidade-regras.md.
"""
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

from .escolas import PARTICULAS, palavras_da_chave
from .olimpiadas import area, e_alto_nivel
from .premiacao import MENCAO, Premiacao
from .texto import normalizar

MAX_ANOS_CARREIRA = 12              # do 6º ano do fundamental ao fim da faculdade
MAX_ANOS_SEM_PREMIO = 8             # intervalo sem premiação que, numa carreira longa demais, separa duas pessoas
# O mesmo nível da OBMEP mais anos depois que isto é outra pessoa. Os níveis 1 e 2 cobrem 2 séries cada. O nível 3
# cobre o ensino médio, que dura 4 anos nas escolas técnicas (IFs, Liberato, ETEs), e há quem recomece o médio ao
# entrar numa delas: com 3 anos, 20 medalhistas reais de escola técnica seriam divididos (ver identidade-regras.md)
MAX_ANOS_MESMO_NIVEL = {"1": 3, "2": 3, "3": 5}
LIMITE_HOMONIMOS = 0.3              # nº esperado de pessoas com o nome, abaixo do qual o nome é "raro"
LIMITE_HOMONIMOS_ALTO_NIVEL = 3.0   # mais tolerante quando há OBM/internacional em 2+ UFs


# Grafias erradas nas listas oficiais que partem uma pessoa em dois perfis, corrigidas à mão a pedido
# (correções chegam pelo contato do site). Chave: (nome sem acento, UF) como veio na fonte; para um nome comum,
# (nome, UF, olimpíada, ano): só aquela premiação muda.
GRAFIAS_CORRIGIDAS: dict[tuple, str] = {
    # OBMEP 2018 e OBM 2019 escreveram "Gouveia"; nas outras listas, e no nome dele, é Gouvêa
    ("ISAIAS GOUVEIA GONCALVES", "DF"): "Isaías Gouvêa Gonçalves",
    # OBMEP 2018 escreveu "Edigard"; 2019, 2021 e 2022 trazem Edgard (mesma escola, em Cocal dos Alves)
    ("EDIGARD JUNIO DA SILVA VIANA", "PI"): "Edgard Junio da Silva Viana",
    # OBMEP 2017 ("Moteiro") e 2019 ("Azevedo"); nas outras listas, Azeredo de Moura Monteiro (Colégio Militar do RJ)
    ("SOFIA AZEREDO DE MOURA MOTEIRO", "RJ"): "Sofia Azeredo de Moura Monteiro",
    ("SOFIA AZEVEDO DE MOURA MONTEIRO", "RJ"): "Sofia Azeredo de Moura Monteiro",
    # OBMEP 2014 escreveu "Pimaki"; 2011 a 2017 trazem Primaki (mesma escola, em Roncador), confirmado por ele
    ("JOAO VINICIUS PIMAKI PRADO", "PR"): "João Vinícius Primaki Prado",
    # IMC 2024 escreveu "Tomás" (lista sem UF, pela FGV Rio); a IMC 2025 e as demais listas trazem Tomaz
    ("JOAO VITOR TOMAS ALVES FERREIRA", ""): "João Vitor Tomaz Alves Ferreira",
    # IMC 2026 abreviou para "João Ferreira" (pela FGV, sem UF): é ele, menção honrosa como em 2024
    ("JOAO FERREIRA", "", "IMC", 2026): "João Vitor Tomaz Alves Ferreira",
    # IMC 2026 escreveu "Aquinos"; a IMC 2024 e a 2025 trazem Aquines (FGV, sem UF)
    ("RAMYRO CORREA AQUINOS", ""): "Ramyro Corrêa Aquines",
    # OBMEP 2023 a 2025 abreviaram o nome de formas diferentes; 2022 e a OMIF 2026 trazem o nome completo (EE Dr.
    # Jorge de Lima, em União dos Palmares, e depois IFAL Murici)
    ("ALMIR SERGIO R DO SANTOS FILHO", "AL"): "Almir Sérgio Ramos dos Santos Filho",
    ("ALMIR SERGIO RAMOS DOS S FILHO", "AL"): "Almir Sérgio Ramos dos Santos Filho",
    ("ALMIR SERGIO R DOS SANTOS FILHO", "AL"): "Almir Sérgio Ramos dos Santos Filho",
}


def corrigir_grafias(premiacoes: list[Premiacao]) -> int:
    """Troca o nome das premiações listadas em GRAFIAS_CORRIGIDAS. Altera a lista; devolve quantas mudaram."""
    corrigidas = 0
    for p in premiacoes:
        chave = (normalizar(p["nome"]), p.get("uf") or "")
        certo = GRAFIAS_CORRIGIDAS.get(chave) or GRAFIAS_CORRIGIDAS.get((*chave, p["competicao"], p["ano"]))
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
    return _palavras_da_escola(p["escola"]) if p.get("escola") else ""


@lru_cache(maxsize=None)
def _palavras_da_escola(escola: str) -> str:
    """As palavras de palavras_da_chave, em ordem. Em cache: a mesma escola aparece em muitas premiações."""
    return " ".join(sorted(palavras_da_chave(escola)))


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


def _nivel_parado(registros: list[Premiacao]) -> bool:
    """O mesmo nível da OBMEP com mais de MAX_ANOS_MESMO_NIVEL anos de distância: é outra pessoa (a "Isabela de
    Lima da Silva" do nível 1 em 2012 não é a do nível 1 em 2022)."""
    anos: dict[str, list[int]] = {}
    for p in registros:
        if p["competicao"] == "OBMEP" and p.get("nivel") in MAX_ANOS_MESMO_NIVEL:
            anos.setdefault(p["nivel"], []).append(p["ano"])
    return any(max(a) - min(a) > MAX_ANOS_MESMO_NIVEL[nivel] for nivel, a in anos.items())


def _cabe_numa_pessoa(registros: list[Premiacao]) -> bool:
    """As premiações podem ser de uma pessoa só: cabem numa carreira escolar, sem a mesma edição em dois lugares,
    sem o nível da OBMEP regredir e sem o mesmo nível da OBMEP anos demais depois (_nivel_parado)."""
    anos = [p["ano"] for p in registros]
    if max(anos) - min(anos) > MAX_ANOS_CARREIRA or _nivel_regride(registros) or _nivel_parado(registros):
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


# ------------------------------------------------------------------------------------------------------------
# Grafias diferentes da mesma pessoa
#
# Depois que as regras acima definem os perfis pelo nome exato, juntar_grafias junta os perfis da mesma pessoa
# escritos de jeitos diferentes nas listas ("Almir Sergio R dos Santos Filho", "Almir Sergio Ramos dos S Filho").
# A regra, em linguagem simples, está em docs/identidade-regras.md; a pesquisa que a escolheu, com os números,
# em docs/identidade-pesquisa.md (é a "r_recomendada" de experimentos/identidade/).

MAX_ANOS_MESMA_CIDADE = 3           # só a mesma cidade (sem a mesma escola) prova algo com premiações a até 3 anos
LIMITE_PRENOME = 0.6                # palavra que é 1º (ou 2º) nome em 60%+ das vezes é prenome (Lívia, Natan)
HOMONIMOS_MESMA_ESCOLA = 1.0        # diferença só de partículas ou de letra: homônimos esperados abaixo disto,
HOMONIMOS_MESMA_CIDADE = 0.1        # com a mesma escola; e abaixo disto, com só a mesma cidade

# Sufixos de parentesco: precisam ser iguais dos dois lados (o pai e o filho têm o mesmo nome sem eles)
_SUFIXOS = {"FILHO": "FILHO", "FILHA": "FILHA", "JUNIOR": "JUNIOR", "JR": "JUNIOR", "NETO": "NETO", "NETA": "NETA",
            "SOBRINHO": "SOBRINHO", "SEGUNDO": "SEGUNDO", "TERCEIRO": "TERCEIRO"}


@dataclass(eq=False, slots=True)
class _Perfil:
    """Um perfil como as regras de nome exato o deixaram: o id, o nome do id e as premiações."""
    ident: str
    palavras: tuple[str, ...]           # o nome sem partículas, com JR -> JUNIOR (ver _palavras)
    registros: list[Premiacao]
    cidades: dict | None = None         # (UF, cidade) -> anos; calculado na primeira consulta (ver _cidades)

    @property
    def nome(self) -> str:
        return self.ident.split("|")[0]


def _palavras(nome: str) -> tuple[str, ...]:
    """Palavras do nome normalizado sem partículas, com JR -> JUNIOR: "R DO SANTOS" e "R DOS SANTOS" dão o mesmo."""
    return tuple(_SUFIXOS.get(w, w) for w in nome.split() if w not in PARTICULAS)


def _sufixo(palavras: tuple[str, ...]) -> str:
    """O sufixo de parentesco no fim do nome (Filho, Júnior, Neto…), ou ""."""
    return palavras[-1] if palavras and palavras[-1] in _SUFIXOS.values() else ""


def _no_maximo(a: str, b: str, limite: int) -> bool:
    """a e b estão a no máximo `limite` edições: troca, falta ou sobra de uma letra, ou inversão de duas vizinhas
    (distância de Damerau-Levenshtein restrita, que para cedo quando passa do limite)."""
    if abs(len(a) - len(b)) > limite:
        return False
    antes_de_anterior, anterior = [], list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        atual = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            atual[j] = min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                atual[j] = min(atual[j], antes_de_anterior[j - 2] + 1)
        if min(atual) > limite:
            return False
        antes_de_anterior, anterior = anterior, atual
    return anterior[-1] <= limite


@lru_cache(maxsize=200_000)
def _encaixe(a: str, b: str) -> str | None:
    """Como duas palavras se encaixam: "igual"; "inicial" (uma é a inicial, ou abreviação de 2 ou 3 letras, da
    outra: R/RAMOS, MA/MARIA); "grafia" (erro de digitação: 1 letra em palavras de 4+ letras, 2 nas de 8+); None."""
    if a == b:
        return "igual"
    curta, longa = sorted((a, b), key=len)
    if longa.startswith(curta) and (len(curta) == 1 or (len(curta) <= 3 and len(longa) > len(curta) + 1)):
        return "inicial"
    if len(curta) >= 4 and _no_maximo(a, b, 2 if len(curta) >= 8 else 1):
        return "grafia"
    return None


def _cabe_em(curto: tuple[str, ...], longo: tuple[str, ...]) -> bool:
    """Cada palavra de `curto` encaixa (_encaixe) numa palavra de `longo`, na mesma ordem; as de `longo` que
    sobram são palavras omitidas."""
    restante = iter(longo)
    return all(any(_encaixe(p, q) for q in restante) for p in curto)


def _encaixam(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """Os dois nomes podem ser a mesma pessoa pela escrita, admitindo palavras omitidas de um lado: a 1ª palavra
    igual (ou com erro de digitação), o mesmo sufixo e as outras encaixando na ordem. Serve para achar as outras
    leituras de uma abreviação (ver _OutrasLeituras); a junção em si não aceita omissões (ver _diferencas)."""
    if not a or not b or _sufixo(a) != _sufixo(b) or _encaixe(a[0], b[0]) not in ("igual", "grafia"):
        return False
    return _cabe_em(a[1:], b[1:]) or _cabe_em(b[1:], a[1:])


def _diferencas(a: tuple[str, ...], b: tuple[str, ...], prenomes: frozenset[str]) -> int | None:
    """Quantas palavras diferem entre dois nomes que encaixam palavra a palavra, sem omissão, com a 1ª palavra e
    o sufixo iguais; None se não encaixam assim. Cada diferença é uma inicial ou abreviação (vale 1) ou um erro de
    digitação em sobrenome (vale 2). Erro em prenome não junta: Natan/Natani, Lígia/Lívia e Gabriel/Gabriela na
    mesma escola são, quase sempre, irmãos."""
    if len(a) != len(b) or a[0] != b[0] or _sufixo(a) != _sufixo(b):
        return None
    custo = 0
    for x, y in zip(a[1:], b[1:]):
        tipo = _encaixe(x, y)
        if tipo is None or (tipo == "grafia" and (x in prenomes or y in prenomes)):
            return None
        custo += {"igual": 0, "inicial": 1, "grafia": 2}[tipo]
    return custo


def _prenomes(perfis: list[_Perfil]) -> frozenset[str]:
    """Palavras que são quase sempre prenome: aparecem como 1ª palavra (ou 2ª, em nomes de 3+ palavras) em
    LIMITE_PRENOME das vezes ou mais. Sobrenomes (Gouveia, Camargo, Azevedo) raramente são a 2ª palavra."""
    total: dict[str, int] = {}
    prenome: dict[str, int] = {}
    for perfil in perfis:
        palavras = perfil.palavras
        for w in set(palavras):
            total[w] = total.get(w, 0) + 1
        for w in palavras[:2] if len(palavras) > 2 else palavras[:1]:
            prenome[w] = prenome.get(w, 0) + 1
    return frozenset(w for w, n in total.items() if prenome.get(w, 0) / n >= LIMITE_PRENOME)


def _frequencias(perfis: list[_Perfil]) -> dict[str, int]:
    """Palavra -> em quantos perfis ela aparece."""
    frequencia: dict[str, int] = {}
    for perfil in perfis:
        for w in set(perfil.palavras):
            frequencia[w] = frequencia.get(w, 0) + 1
    return frequencia


def _estimador_de_raridade(perfis: list[_Perfil], frequencia: dict[str, int]):
    """Função palavras -> número esperado de perfis com aquele nome, pela frequência de cada palavra entre os
    perfis (como _estimador_de_homonimos); uma inicial vale a fração das palavras que começam com a letra."""
    total = len(perfis) or 1
    por_letra: dict[str, int] = {}
    for w, n in frequencia.items():
        por_letra[w[0]] = por_letra.get(w[0], 0) + n
    soma = sum(por_letra.values()) or 1
    letra = {k: n / soma for k, n in por_letra.items()}

    def esperado(palavras: tuple[str, ...]) -> float:
        valor = float(total)
        for w in set(palavras):
            valor *= letra.get(w, 0.05) if len(w) == 1 else frequencia.get(w, 1) / total
        return valor
    return esperado


def _cidades(perfil: _Perfil) -> dict[tuple[str, str], list[int]]:
    """(UF, cidade) -> anos das premiações do perfil naquela cidade."""
    if perfil.cidades is None:
        perfil.cidades = {}
        for p in perfil.registros:
            cidade = normalizar(p.get("municipio"))
            if cidade:
                perfil.cidades.setdefault((p.get("uf") or "", cidade), []).append(p["ano"])
    return perfil.cidades


def _na_mesma_escola(a: Premiacao, b: Premiacao) -> bool:
    """As duas premiações são da mesma escola: mesmo estado, mesma cidade (ou nenhuma) e o mesmo nome de escola
    pela chave ou por mesma_escola (que aceita abreviações)."""
    if not a.get("escola") or not b.get("escola") or (a.get("uf") or "") != (b.get("uf") or ""):
        return False
    if normalizar(a.get("municipio")) != normalizar(b.get("municipio")):
        return False
    return _chave_da_escola(a) == _chave_da_escola(b) or mesma_escola(a["escola"], b["escola"])


def _mesma_escola_par(x: _Perfil, y: _Perfil) -> bool:
    """Alguma premiação de um e alguma do outro na mesma escola."""
    return any(_na_mesma_escola(a, b) for a in x.registros for b in y.registros)


def _mesma_cidade_perto(x: _Perfil, y: _Perfil) -> bool:
    """Alguma premiação de um e alguma do outro na mesma cidade, a até MAX_ANOS_MESMA_CIDADE anos uma da outra."""
    cidades_y = _cidades(y)
    return any(abs(ano - outro) <= MAX_ANOS_MESMA_CIDADE for lugar, anos in _cidades(x).items()
               for ano in anos for outro in cidades_y.get(lugar, ()))


def _edicao_em_comum(x: _Perfil, y: _Perfil) -> bool:
    """Os dois aparecem na mesma edição (olimpíada e ano): são duas pessoas. A exceção é a OBI na mesma escola,
    que premia modalidades diferentes no mesmo ano."""
    edicoes: dict[tuple, list[Premiacao]] = {}
    for a in x.registros:
        edicoes.setdefault((a["competicao"], a["ano"]), []).append(a)
    return any(b["competicao"] != "OBI" or not _na_mesma_escola(a, b)
               for b in y.registros for a in edicoes.get((b["competicao"], b["ano"]), ()))


def _pares_pelo_nome(perfis: list[_Perfil], prenomes: frozenset[str]):
    """(custo, x, y) para cada par de perfis da mesma UF cujos nomes encaixam sem omissão (_diferencas).

    Só se comparam nomes com o mesmo número de palavras, a mesma 1ª palavra e as mesmas iniciais de cada palavra
    (uma inicial, uma abreviação e quase todo erro de digitação mantêm a primeira letra), e que dividem, além da
    1ª, a 2ª ou a última palavra, como os blocos da pesquisa. Premiações sem UF formam um bloco à parte."""
    por_uf: dict[str, list[_Perfil]] = {}
    for perfil in perfis:
        if len(perfil.palavras) >= 2:
            for uf in {p.get("uf") or "" for p in perfil.registros}:
                por_uf.setdefault(uf, []).append(perfil)
    vistos: set[tuple[str, str]] = set()
    for da_uf in por_uf.values():
        blocos: dict[tuple, list[_Perfil]] = {}
        for perfil in da_uf:
            palavras = perfil.palavras
            blocos.setdefault((palavras[0], "".join(w[0] for w in palavras)), []).append(perfil)
        for membros in blocos.values():
            for i, x in enumerate(membros):
                for y in membros[:i]:
                    if x.nome == y.nome:
                        continue   # o mesmo nome em dois perfis: homônimos que as regras acima separaram
                    if x.palavras[1] != y.palavras[1] and x.palavras[-1] != y.palavras[-1]:
                        continue
                    custo = _diferencas(x.palavras, y.palavras, prenomes)
                    par = (x.ident, y.ident) if x.ident < y.ident else (y.ident, x.ident)
                    if custo is not None and par not in vistos:
                        vistos.add(par)
                        yield custo, x, y


def _par_aceito(x: _Perfil, y: _Perfil, custo: int, raridade) -> tuple | None:
    """Ordem do par no agrupamento (a mais forte primeiro) se ele passa nas provas e travas; senão None.

    - prova de contexto: a mesma escola, ou a mesma cidade com premiações a até MAX_ANOS_MESMA_CIDADE anos;
    - travas: nenhuma edição em comum e as premiações cabendo numa pessoa (_cabe_numa_pessoa);
    - sem inicial (só partículas ou erro de letra): o nome precisa ser pouco comum, porque "Gabriel de Oliveira
      Santos" e "Gabriel Oliveira dos Santos" na mesma cidade são, muitas vezes, duas pessoas.
    A outra trava, a abreviação sem outra leitura na cidade, fica para _OutrasLeituras (é a mais cara)."""
    escola = _mesma_escola_par(x, y)
    if not escola and not _mesma_cidade_perto(x, y):
        return None
    if _edicao_em_comum(x, y) or not _cabe_numa_pessoa(x.registros + y.registros):
        return None
    tem_inicial = any(_encaixe(a, b) == "inicial" for a, b in zip(x.palavras, y.palavras))
    limite = HOMONIMOS_MESMA_ESCOLA if escola else HOMONIMOS_MESMA_CIDADE
    if not tem_inicial and max(raridade(x.palavras), raridade(y.palavras)) >= limite:
        return None
    return (not escola, custo, *sorted((x.ident, y.ident)))


def _chaves_de_leitura(palavras: tuple[str, ...]) -> list[tuple]:
    """Por onde procurar as outras leituras de um nome: a 1ª palavra; e a 2ª com a última (para pegar quem tem
    um erro de digitação na 1ª palavra)."""
    chaves = [("1", palavras[0])]
    if len(palavras) >= 3:
        chaves.append(("2U", palavras[1], palavras[-1]))
    return chaves


class _OutrasLeituras:
    """Uma abreviação ou grafia é ambígua quando, na mesma cidade, outro nome encaixa num dos lados do par e não
    no outro: "Ana Carolina B da Silva" encaixa em Batista e em Barbosa. Se há uma Ana Carolina Barbosa da Silva
    na cidade, o par com a Batista não se junta.

    O índice só guarda as cidades e chaves (_chaves_de_leitura) dos pares a conferir, para não ocupar memória
    com a base inteira."""

    def __init__(self, perfis: list[_Perfil], pares: list[tuple[_Perfil, _Perfil]]):
        procurados = {(lugar, chave) for x, y in pares for lugar in {*_cidades(x), *_cidades(y)}
                      for chave in {*_chaves_de_leitura(x.palavras), *_chaves_de_leitura(y.palavras)}}
        self.indice: dict[tuple, list[_Perfil]] = {}
        for r in perfis:
            if len(r.palavras) < 2:
                continue
            lugares = {(p.get("uf") or "", normalizar(p.get("municipio"))) for p in r.registros}
            for lugar in lugares:
                for chave in _chaves_de_leitura(r.palavras):
                    if (lugar, chave) in procurados:
                        self.indice.setdefault((lugar, chave), []).append(r)

    def tem(self, x: _Perfil, y: _Perfil) -> bool:
        """Algum outro nome da cidade de x ou de y encaixa num dos dois e não no outro?"""
        for lugar in {*_cidades(x), *_cidades(y)}:
            for chave in {*_chaves_de_leitura(x.palavras), *_chaves_de_leitura(y.palavras)}:
                for r in self.indice.get((lugar, chave), ()):
                    if r.nome not in (x.nome, y.nome) and (
                            _encaixam(r.palavras, x.palavras) != _encaixam(r.palavras, y.palavras)):
                        return True
        return False


def _podem_juntar(a: list[_Perfil], b: list[_Perfil]) -> bool:
    """Dois grupos podem virar uma pessoa: nenhum homônimo que as regras de nome exato separaram (o mesmo nome
    em perfis diferentes), nenhuma edição em comum e todas as premiações cabendo numa pessoa."""
    nomes = {p.nome for p in a}
    if any(p.nome in nomes for p in b) or any(_edicao_em_comum(x, y) for x in a for y in b):
        return False
    return _cabe_numa_pessoa([r for p in a + b for r in p.registros])


def _agrupar(arestas: list[tuple[_Perfil, _Perfil]]) -> list[list[_Perfil]]:
    """Agrupamento com restrições (correlation clustering guloso com "cannot-link"): as arestas entram na ordem
    recebida (a mais forte primeiro) e uma aresta é recusada se juntaria dois grupos que não podem ser uma
    pessoa (_podem_juntar). Nunca o fechamento transitivo simples: com ele, uma abreviação que encaixa em dois
    homônimos viraria uma ponte entre eles. Devolve os grupos de 2+ perfis."""
    grupo_de: dict[str, list[_Perfil]] = {}
    for x, y in arestas:
        gx, gy = grupo_de.get(x.ident, [x]), grupo_de.get(y.ident, [y])
        if gx is gy or not _podem_juntar(gx, gy):
            continue
        gx.extend(gy)
        for perfil in gx:
            grupo_de[perfil.ident] = gx
    unicos = {id(g): g for g in grupo_de.values()}
    return list(unicos.values())


def _quem_fica(grupo: list[_Perfil], frequencia: dict[str, int]) -> _Perfil:
    """O perfil que dá o id ao grupo: o de nome mais completo (menos palavras de até 3 letras: iniciais e
    abreviações); no empate, o de grafia mais usual (a palavra mais rara do nome é mais frequente na base:
    Cavalcanti, não Cacalcanti), o de mais premiações além das menções da OBMEP, o de mais premiações, o mais
    recente e, por fim, o id em ordem alfabética (o resultado não depende da ordem das listas)."""
    return min(grupo, key=lambda p: (sum(len(w) <= 3 for w in p.palavras),
                                     -min(frequencia.get(w, 0) for w in p.palavras),
                                     -sum(not de_massa(r) for r in p.registros), -len(p.registros),
                                     -max(r["ano"] for r in p.registros), p.ident))


def juntar_grafias(premiacoes: list[Premiacao]) -> dict[str, str]:
    """Junta perfis da mesma pessoa com o nome escrito de jeitos diferentes. Roda depois de atribuir_alunos (e da
    cidade das escolas: a cidade é prova de contexto) e altera o aluno_id das premiações dos perfis absorvidos,
    guardando o id antigo em aluno_id_absorvido. Devolve {id absorvido: id do perfil que ficou}.

    Dois perfis da mesma UF viram um quando:
      - o nome encaixa palavra a palavra, na ordem, sem palavra omitida, com a 1ª palavra e o sufixo (Filho,
        Júnior, Neto) iguais; as diferenças aceitas são partículas, iniciais e abreviações de até 3 letras (dos
        dois lados) e erro de 1 letra (2 em palavras de 8+) só em sobrenome (_diferencas);
      - há prova de contexto: a mesma escola, ou a mesma cidade com premiações a até 3 anos;
      - nenhuma edição em comum e as premiações cabem numa pessoa (as travas de sempre);
      - diferença só de partículas ou de uma letra exige nome pouco comum (_par_aceito);
      - a abreviação não tem outra leitura entre os nomes da mesma cidade (_OutrasLeituras).
    Os pares aceitos são agrupados com restrições (_agrupar): mais de dois perfis só se juntam se todos cabem
    numa pessoa. O perfil de nome mais completo fica com o id (_quem_fica); os endereços dos outros continuam
    valendo e levam a ele.

    As menções da OBMEP contam aqui como as outras premiações: duas das quatro grafias do Almir só têm menções.
    """
    perfis_por_id: dict[str, _Perfil] = {}
    for p in premiacoes:
        perfil = perfis_por_id.get(p["aluno_id"])
        if perfil is None:
            perfil = perfis_por_id[p["aluno_id"]] = _Perfil(p["aluno_id"], _palavras(p["aluno_id"].split("|")[0]), [])
        perfil.registros.append(p)
    perfis = list(perfis_por_id.values())
    del perfis_por_id
    try:
        frequencia = _frequencias(perfis)
        prenomes, raridade = _prenomes(perfis), _estimador_de_raridade(perfis, frequencia)
        candidatos = []
        for custo, x, y in _pares_pelo_nome(perfis, prenomes):
            ordem = _par_aceito(x, y, custo, raridade)
            if ordem is not None:
                candidatos.append((ordem, x, y))
        candidatos.sort(key=lambda c: c[0])
        leituras = _OutrasLeituras(perfis, [(x, y) for _, x, y in candidatos])
        arestas = [(x, y) for _, x, y in candidatos if not leituras.tem(x, y)]
        absorvidos: dict[str, str] = {}
        for grupo in _agrupar(arestas):
            fica = _quem_fica(grupo, frequencia)
            for perfil in grupo:
                if perfil is not fica:
                    absorvidos[perfil.ident] = fica.ident
                    for p in perfil.registros:
                        p["aluno_id_absorvido"], p["aluno_id"] = p["aluno_id"], fica.ident
        return absorvidos
    finally:
        _encaixe.cache_clear()   # os caches não ficam ocupando memória durante a gravação da base
        _palavras_da_escola.cache_clear()
