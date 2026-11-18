"""Repositório de escrita: grava as premiações e pré-calcula tudo o que o site lê: tabelas-resumo de alunos,
escolas e cidades, os endereços das páginas e os índices das sugestões da busca."""
import sqlite3
from pathlib import Path

from ...dominio.enderecos import ALUNO, CIDADE, ESCOLA, Enderecos, slug, texto_escola
from ...dominio.escolas import ESCOLAS_RENOMEADAS
from ...dominio.identidade import GRAFIAS_CORRIGIDAS, de_massa
from ...dominio.premiacao import BRONZE, MENCAO, OURO, PRATA
from ...dominio.ranking import preencher_posicoes
from ...dominio.texto import nome_da_cidade, normalizar
from .esquema import (
    CAMPOS_ALUNO,
    CAMPOS_CIDADE,
    CAMPOS_ESCOLA,
    CAMPOS_FISICOS,
    PONTOS,
    PREMIACOES,
    RESUMOS,
    insert,
)

_CAMPO_MEDALHA = {OURO: "ouro", PRATA: "prata", BRONZE: "bronze", MENCAO: "mencao"}
# Contagens que desempatam a posição em cada método (ranking.preencher_posicoes). No IMPA edital a lista do
# ranking só soma as medalhas que pontuam nele: o resumo guarda essas contagens à parte (não vão para a base).
_MEDALHAS_EDITAL = ("ouro_edital", "prata_edital", "bronze_edital")
_DESEMPATE = {"p_impa3": _MEDALHAS_EDITAL}


class RepositorioSqlite:
    """Implementa aplicacao.portas.RepositorioPremiacoes.

    A base nova é montada num arquivo temporário e só substitui a atual no fim: quem estiver lendo
    nunca vê uma base pela metade.
    """

    def __init__(self, caminho: Path):
        self.caminho = caminho

    def premiacoes_por_olimpiada(self) -> dict[str, int]:
        """Contagem por sigla na base atual; vazio se o arquivo não existe ou não é uma base legível."""
        if not self.caminho.exists():
            return {}
        con = sqlite3.connect(f"file:{self.caminho}?mode=ro", uri=True)
        try:
            return dict(con.execute("SELECT competicao, COUNT(*) FROM medalhas GROUP BY competicao").fetchall())
        except sqlite3.Error:
            return {}
        finally:
            con.close()

    def substituir(self, registros: list[dict], atualizado_em: str) -> None:
        """Grava as premiações (já indexadas), a data da atualização e as tabelas-resumo num arquivo .tmp e
        troca a base por ele. Se algo falhar no meio, a base atual fica intacta."""
        self.caminho.parent.mkdir(exist_ok=True)
        temporario = self.caminho.with_suffix(".tmp")
        temporario.unlink(missing_ok=True)
        con = sqlite3.connect(temporario)
        try:
            con.executescript(PREMIACOES)
            con.executescript(RESUMOS)
            gravar_premiacoes(con, registros)
            con.execute("INSERT INTO meta VALUES ('atualizado_em', ?)", (atualizado_em,))
            # perfis de outra grafia juntados pela identidade (identidade.juntar_grafias): id antigo -> id atual
            absorvidos = {r["aluno_id_absorvido"]: r["aluno_id"] for r in registros if r.get("aluno_id_absorvido")}
            gravar_resumos(con, absorvidos, anterior=self.caminho)
            con.execute("ANALYZE")   # estatísticas para o SQLite escolher o índice certo em cada consulta
            con.commit()
            con.execute("VACUUM")    # sem as páginas soltas que a montagem dos índices deixa: arquivo menor
        finally:
            con.close()
        temporario.replace(self.caminho)   # troca atômica: nunca há um instante sem base


def gravar_premiacoes(con: sqlite3.Connection, registros: list[dict]) -> None:
    """Premiações na tabela premiacoes, na ordem recebida (que dá o id). O que se repete em muitas linhas vai uma
    vez só para uma tabela pequena e a linha guarda o número: o endereço da lista oficial (fontes), a escola com
    os termos de busca e a chave (grafias) e a área da olimpíada (olimpiadas). O prêmio fica NULL quando é igual
    à medalha; a visão medalhas desfaz tudo isso. O aluno vai pelo número (aluno_n), dado em ordem alfabética do
    id; a tabela alunos recebe aqui só número e id, e gravar_resumos a completa."""
    numero = {ident: n for n, ident in enumerate(sorted({r["aluno_id"] for r in registros}), 1)}
    fontes: dict[str, int] = {}
    grafias: dict[tuple, int] = {}
    areas: dict[str, str | None] = {}

    def linhas():
        for r in registros:
            premio = None if r["premio"] == r["medalha"] else (r["premio"] if r["premio"] is not None else "")
            fonte = fontes.setdefault(r["fonte"], len(fontes) + 1)
            grafia = grafias.setdefault((r.get("escola") or None, r["escola_termos"] or "", r["escola_chave"] or ""),
                                        len(grafias) + 1)
            areas.setdefault(r["competicao"], r.get("area"))
            especiais = {"premio": premio, "fonte_n": fonte, "grafia_n": grafia, "aluno_n": numero[r["aluno_id"]]}
            yield [especiais[c] if c in especiais else r[c] for c in CAMPOS_FISICOS]
    con.executemany(insert("premiacoes", CAMPOS_FISICOS), linhas())
    con.executemany("INSERT INTO fontes VALUES (?, ?)", ((n, url) for url, n in fontes.items()))
    con.executemany("INSERT INTO grafias VALUES (?, ?, ?, ?)", ((n, *g) for g, n in grafias.items()))
    con.executemany("INSERT INTO olimpiadas VALUES (?, ?)", areas.items())
    con.executemany("INSERT INTO alunos (n, id) VALUES (?, ?)", ((n, i) for i, n in numero.items()))


def _zerado(base: dict) -> dict:
    """Os campos de `base` com as contagens de medalhas e os pontos em todos os métodos zerados."""
    return {**base, "ouro": 0, "prata": 0, "bronze": 0, "mencao": 0, "total": 0, **{c: 0 for c in PONTOS},
            **{c: 0 for c in _MEDALHAS_EDITAL}}


def gravar_resumos(con: sqlite3.Connection, absorvidos: dict[str, str] | None = None,
                   anterior: Path | None = None) -> None:
    """Tabelas alunos, escolas e cidades: totais, pontos e posição nacional/estadual em cada método; depois os
    endereços das páginas e os índices das sugestões (gravar_enderecos, gravar_indices_de_busca).

    Lê as premiações da mais recente para a mais antiga, então o "primeiro valor não vazio" de nome, escola,
    município, rede e esfera é sempre o mais recente. A UF do aluno é a do id (a UF principal escolhida pela
    regra de identidade), para o perfil e a posição estadual baterem com ele. O nome exibido é a grafia do id:
    num perfil que juntou grafias diferentes (identidade.juntar_grafias), as outras ficam nas premiações e na
    busca, e o título bate com o endereço.

    absorvidos: {id de perfil que deixou de existir: id do perfil que o recebeu}, para os endereços antigos.
    """
    alunos: dict[str, dict] = {}
    escolas: dict[str, dict] = {}
    cidades: dict[str, dict] = {}
    # as menções da OBMEP (identidade.de_massa) vêm por último: nome, escola, cidade, rede e esfera de quem tem
    # outras premiações saem delas, e a menção só preenche o que ficou vazio (ou a ficha de quem só tem menção)
    cursor = con.execute(f"""SELECT aluno_id, aluno_n, nome, uf, competicao, ano, medalha, escola, escola_chave,
                                    municipio, rede, esfera, municipio_busca, nome_busca, {", ".join(PONTOS)}
                             FROM medalhas
                             ORDER BY (competicao = 'OBMEP' AND medalha = '{MENCAO}'), ano DESC, competicao DESC, id""")
    for linha in cursor:
        (aluno_id, aluno_n, nome, uf, competicao, ano, medalha, escola, chave, municipio, rede, esfera, cidade,
         nome_busca) = linha[:14]
        pontos = dict(zip(PONTOS, linha[14:]))
        massa = de_massa({"competicao": competicao, "medalha": medalha})
        grafia_do_id = nome_busca == aluno_id.split("|")[0]
        a = alunos.get(aluno_id)
        if a is None:
            uf_do_id = aluno_id.split("|")[1] if "|" in aluno_id else ""
            a = alunos[aluno_id] = _zerado({"n": aluno_n, "id": aluno_id, "nome": nome, "uf": uf_do_id or uf,
                                            "comps": set(), "escola": None, "escola_chave": None, "municipio": None,
                                            "de": ano, "ate": ano, "grafia_do_id": grafia_do_id})
        elif grafia_do_id and not a["grafia_do_id"]:
            a["nome"], a["grafia_do_id"] = nome, True   # a premiação mais recente era de outra grafia
        if competicao == "OBM" and a["nome"] != nome and "OBM" not in a["comps"] and (
                grafia_do_id or not a["grafia_do_id"]):
            a["nome"] = nome   # a OBM publica nomes com acento e caixa mista: é a grafia mais fiel
        a["comps"].add(competicao)
        a["uf"] = a["uf"] or uf
        a["escola"] = a["escola"] or escola
        a["escola_chave"] = a["escola_chave"] or (chave or None)
        a["municipio"] = a["municipio"] or municipio
        acumular = [a]
        if chave:
            e = escolas.get(chave)
            if e is None:
                e = escolas[chave] = _zerado({"id": chave, "nomes": {}, "municipio": municipio, "uf": uf,
                                              "rede": rede, "esfera": esfera, "alunos_set": set(),
                                              "de": ano, "ate": ano})
            # a premiação mais recente pode ser de uma lista que não informa rede nem esfera (OBM, OBQ…)
            e["rede"], e["esfera"] = e["rede"] or rede, e["esfera"] or esfera
            e["municipio"] = e["municipio"] or municipio
            grafias = e.setdefault("nomes_massa", {}) if massa else e["nomes"]
            grafias[escola] = grafias.get(escola, 0) + 1
            e["alunos_set"].add(aluno_id)
            acumular.append(e)
        if cidade and uf:   # cidade: o par município (normalizado) + UF, como no ranking de cidades
            cidade_id = f"{cidade}|{uf}"
            c = cidades.get(cidade_id)
            if c is None:
                c = cidades[cidade_id] = _zerado({"id": cidade_id, "uf": uf, "grafias": {}, "alunos_set": set(),
                                                  "escolas_set": set(), "de": ano, "ate": ano})
            c["grafias"][municipio] = c["grafias"].get(municipio, 0) + 1
            c["alunos_set"].add(aluno_id)
            if chave:
                c["escolas_set"].add(chave)
            acumular.append(c)
        for x in acumular:
            x["total"] += 1
            x["indexar"] = x.get("indexar", 0) or int(not massa)   # página no Google só com algo além de menção
            for c in PONTOS:
                x[c] += pontos[c]
            x["de"], x["ate"] = min(x["de"], ano), max(x["ate"], ano)
            if medalha in _CAMPO_MEDALHA:
                x[_CAMPO_MEDALHA[medalha]] += 1
                if pontos["p_impa3"] and medalha != MENCAO:   # menção não pontua no edital
                    x[f"{_CAMPO_MEDALHA[medalha]}_edital"] += 1

    for grupo in (alunos, escolas, cidades):
        itens = list(grupo.values())
        por_uf: dict[str, list[dict]] = {}
        for item in itens:
            if item["uf"]:   # sem estado (listas que não informam a UF) não há posição estadual
                por_uf.setdefault(item["uf"], []).append(item)
        for c in PONTOS:
            desempate = _DESEMPATE.get(c, ("ouro", "prata", "bronze"))
            preencher_posicoes(itens, c, f"{c}_pos", desempate)
            for item in itens:
                item[f"{c}_pos_uf"] = None
            for da_uf in por_uf.values():
                preencher_posicoes(da_uf, c, f"{c}_pos_uf", desempate)

    for a in alunos.values():
        a["competicoes"] = ",".join(sorted(a["comps"], reverse=True))
    for e in escolas.values():
        # a grafia mais frequente; na escola que mudou de nome, a mais recente (as premiações vêm da mais nova
        # para a mais antiga): o nome antigo pode ser mais frequente, mas a página mostra o atual
        renomeada = e["id"] in ESCOLAS_RENOMEADAS.values()
        nomes = e["nomes"] or e["nomes_massa"]   # as grafias das menções só valem para a escola só com menções
        # empate na contagem: a primeira lida (a mais recente; a ordem de leitura termina pelo id, então é fixa)
        e["nome"] = next(iter(nomes)) if renomeada else max(nomes, key=nomes.get)
        e["alunos"] = len(e["alunos_set"])
    for c in cidades.values():
        c["nome"] = nome_da_cidade(c["grafias"]) or c["id"].split("|")[0]
        c["alunos"], c["escolas"] = len(c["alunos_set"]), len(c["escolas_set"])
    gravar_enderecos(con, alunos, escolas, cidades, absorvidos, anterior)
    con.execute("DELETE FROM alunos")   # só número e id, de gravar_premiacoes: agora a ficha completa
    campos_aluno = ["n", *CAMPOS_ALUNO]
    con.executemany(insert("alunos", campos_aluno), ([a[c] for c in campos_aluno] for a in alunos.values()))
    con.executemany(insert("escolas", CAMPOS_ESCOLA), ([e[c] for c in CAMPOS_ESCOLA] for e in escolas.values()))
    con.executemany(insert("cidades", CAMPOS_CIDADE), ([c[k] for k in CAMPOS_CIDADE] for c in cidades.values()))
    gravar_indices_de_busca(con)


def gravar_enderecos(con: sqlite3.Connection, alunos: dict, escolas: dict, cidades: dict,
                     absorvidos: dict[str, str] | None = None, anterior: Path | None = None) -> None:
    """Endereço oficial de cada aluno, escola e cidade (no campo endereco de cada item) e a tabela enderecos com
    todo endereço aceito: o oficial, o montado pelo id (o que o site usa nos links) e os perfis que deixaram de
    existir, que levam ao perfil certo: as grafias corrigidas à mão e os perfis absorvidos (id antigo -> id que
    ficou, de identidade.juntar_grafias) e qualquer outro perfil da base anterior que sumiu, que leva ao perfil
    que ficou com as premiações dele (_perfis_que_sumiram). Escolas vão da mais premiada para a menos: quando o
    endereço montado pelo id de duas coincide ("A B|C|UF" e "A B C||UF"), ele leva à maior."""
    por_tamanho = sorted(escolas.values(), key=lambda e: (-e["total"], e["id"]))
    antigos = _enderecos_antigos(con) + [(slug(antigo), ident) for antigo, ident in sorted((absorvidos or {}).items())]
    ja_aceitos = {endereco for endereco, _ in antigos}
    antigos += [(e, i) for e, i in _perfis_que_sumiram(con, anterior, alunos) if e not in ja_aceitos]
    enderecos = Enderecos([(i, i) for i in alunos],
                          [(e["id"], texto_escola(e["nome"], e["municipio"], e["uf"])) for e in por_tamanho],
                          [(i, i) for i in cidades], antigos)
    for tipo, grupo in ((ALUNO, alunos), (ESCOLA, escolas), (CIDADE, cidades)):
        for item in grupo.values():
            item["endereco"] = enderecos.de(tipo, item["id"])
    # o oficial já está na tabela-resumo (com índice): aqui vão só os outros endereços aceitos
    con.executemany("INSERT INTO enderecos VALUES (?, ?, ?)",
                    ((tipo, endereco, ident) for tipo in (ALUNO, ESCOLA, CIDADE)
                     for endereco, ident in enderecos.aceitos(tipo) if endereco != enderecos.de(tipo, ident)))


# O que identifica uma premiação entre duas gerações da base (o id e o aluno mudam; isto não)
_CHAVE_DA_PREMIACAO = "competicao, ano, nivel, medalha, uf, municipio_busca, nome_busca"


def _perfis_que_sumiram(con: sqlite3.Connection, anterior: Path | None, alunos: dict) -> list[tuple[str, str]]:
    """(endereço de um perfil da base anterior que não existe mais, id do perfil que ficou com a maior parte das
    premiações dele). Uma mudança nas regras de identidade (juntar grafias, separar homônimos) pode apagar um
    perfil ou trocar o id dele; quem guardou o link continua chegando às premiações. Sem base anterior legível
    (primeira geração, arquivo corrompido), não há o que redirecionar."""
    if not anterior or not anterior.exists():
        return []
    try:
        velha = sqlite3.connect(f"file:{anterior}?mode=ro", uri=True)
        try:
            enderecos = {i: e for i, e in velha.execute("SELECT id, endereco FROM alunos") if i not in alunos}
            if not enderecos:
                return []
            # premiações dos perfis que sumiram, pela chave que não muda (só elas ficam na memória)
            do_sumido: dict[tuple, list[str]] = {}
            for linha in velha.execute(f"SELECT aluno_id, {_CHAVE_DA_PREMIACAO} FROM medalhas"):
                if linha[0] in enderecos:
                    do_sumido.setdefault(linha[1:], []).append(linha[0])
        finally:
            velha.close()
    except sqlite3.Error:
        return []
    votos: dict[str, dict[str, int]] = {}
    for linha in con.execute(f"""SELECT a.id, {', '.join('p.' + c for c in _CHAVE_DA_PREMIACAO.split(', '))}
                                 FROM premiacoes p JOIN alunos a ON a.n = p.aluno_n"""):
        for sumido in do_sumido.get(linha[1:], ()):
            votos.setdefault(sumido, {}).setdefault(linha[0], 0)
            votos[sumido][linha[0]] += 1
    return [(enderecos[sumido] or slug(sumido), max(sorted(v), key=v.get)) for sumido, v in sorted(votos.items())]


def _enderecos_antigos(con: sqlite3.Connection) -> list[tuple[str, str]]:
    """(endereço do perfil com a grafia errada, id do perfil certo) de cada grafia corrigida à mão.

    O perfil certo é o das premiações que receberam o nome corrigido, nesse estado: a identidade dos alunos
    pode tê-lo juntado a premiações de outro estado, então o id nem sempre é NOME CERTO|UF."""
    antigos = []
    for (errado, uf, *_), certo in GRAFIAS_CORRIGIDAS.items():
        # UF vazia: a lista não informava o estado (a premiação ficou com uf NULL)
        achado = con.execute("SELECT aluno_id FROM medalhas WHERE nome_busca = ? AND uf IS ? LIMIT 1",
                             (normalizar(certo), uf or None)).fetchone()
        if achado:
            antigos.append((slug(f"{errado}|{uf}"), achado[0]))
    return antigos


def gravar_indices_de_busca(con: sqlite3.Connection) -> None:
    """Índices de texto das sugestões: todas as grafias de cada aluno (nome_busca) e de cada escola (os termos de
    busca, que já trazem as siglas por extenso). A busca casa o início das palavras, como a busca completa."""
    con.execute("""INSERT INTO busca_alunos (rowid, texto)
                   SELECT aluno_n, GROUP_CONCAT(DISTINCT nome_busca) FROM premiacoes GROUP BY aluno_n""")
    con.execute("""INSERT INTO busca_escolas (rowid, texto)
                   SELECT e.n, t.texto FROM escolas e JOIN (
                       SELECT escola_chave, GROUP_CONCAT(DISTINCT escola_termos) AS texto FROM medalhas
                       WHERE escola_chave != '' GROUP BY escola_chave
                   ) t ON t.escola_chave = e.id""")
    con.execute("INSERT INTO busca_alunos (busca_alunos) VALUES ('optimize')")
    con.execute("INSERT INTO busca_escolas (busca_escolas) VALUES ('optimize')")
