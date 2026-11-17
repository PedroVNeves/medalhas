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
            gravar_premiacoes(con, registros)
            con.execute("INSERT INTO meta VALUES ('atualizado_em', ?)", (atualizado_em,))
            gravar_resumos(con)
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
    à medalha; a visão medalhas desfaz tudo isso."""
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
            yield [premio if c == "premio" else fonte if c == "fonte_n" else grafia if c == "grafia_n" else r[c]
                   for c in CAMPOS_FISICOS]
    con.executemany(insert("premiacoes", CAMPOS_FISICOS), linhas())
    con.executemany("INSERT INTO fontes VALUES (?, ?)", ((n, url) for url, n in fontes.items()))
    con.executemany("INSERT INTO grafias VALUES (?, ?, ?, ?)", ((n, *g) for g, n in grafias.items()))
    con.executemany("INSERT INTO olimpiadas VALUES (?, ?)", areas.items())


def _zerado(base: dict) -> dict:
    """Os campos de `base` com as contagens de medalhas e os pontos em todos os métodos zerados."""
    return {**base, "ouro": 0, "prata": 0, "bronze": 0, "mencao": 0, "total": 0, **{c: 0 for c in PONTOS},
            **{c: 0 for c in _MEDALHAS_EDITAL}}


def gravar_resumos(con: sqlite3.Connection) -> None:
    """Tabelas alunos, escolas e cidades: totais, pontos e posição nacional/estadual em cada método; depois os
    endereços das páginas e os índices das sugestões (gravar_enderecos, gravar_indices_de_busca).

    Lê as premiações da mais recente para a mais antiga, então o "primeiro valor não vazio" de nome, escola,
    município, rede e esfera é sempre o mais recente. A UF do aluno é a do id (a UF principal escolhida pela
    regra de identidade), para o perfil e a posição estadual baterem com ele.
    """
    con.executescript(RESUMOS)
    alunos: dict[str, dict] = {}
    escolas: dict[str, dict] = {}
    cidades: dict[str, dict] = {}
    # as menções da OBMEP (identidade.de_massa) vêm por último: nome, escola, cidade, rede e esfera de quem tem
    # outras premiações saem delas, e a menção só preenche o que ficou vazio (ou a ficha de quem só tem menção)
    cursor = con.execute(f"""SELECT aluno_id, nome, uf, competicao, ano, medalha, escola, escola_chave, municipio,
                                    rede, esfera, municipio_busca, {", ".join(PONTOS)}
                             FROM medalhas
                             ORDER BY (competicao = 'OBMEP' AND medalha = '{MENCAO}'), ano DESC, competicao DESC, id""")
    for linha in cursor:
        aluno_id, nome, uf, competicao, ano, medalha, escola, chave, municipio, rede, esfera, cidade = linha[:12]
        pontos = dict(zip(PONTOS, linha[12:]))
        massa = de_massa({"competicao": competicao, "medalha": medalha})
        a = alunos.get(aluno_id)
        if a is None:
            uf_do_id = aluno_id.split("|")[1] if "|" in aluno_id else ""
            a = alunos[aluno_id] = _zerado({"id": aluno_id, "nome": nome, "uf": uf_do_id or uf, "comps": set(),
                                            "escola": None, "escola_chave": None, "municipio": None,
                                            "de": ano, "ate": ano})
        if competicao == "OBM" and a["nome"] != nome and "OBM" not in a["comps"]:
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
    gravar_enderecos(con, alunos, escolas, cidades)
    con.executemany(insert("alunos", CAMPOS_ALUNO), ([a[c] for c in CAMPOS_ALUNO] for a in alunos.values()))
    con.executemany(insert("escolas", CAMPOS_ESCOLA), ([e[c] for c in CAMPOS_ESCOLA] for e in escolas.values()))
    con.executemany(insert("cidades", CAMPOS_CIDADE), ([c[k] for k in CAMPOS_CIDADE] for c in cidades.values()))
    gravar_indices_de_busca(con)


def gravar_enderecos(con: sqlite3.Connection, alunos: dict, escolas: dict, cidades: dict) -> None:
    """Endereço oficial de cada aluno, escola e cidade (no campo endereco de cada item) e a tabela enderecos com
    todo endereço aceito: o oficial, o montado pelo id (o que o site usa nos links) e os perfis de grafias
    corrigidas à mão, que levam ao perfil certo. Escolas vão da mais premiada para a menos: quando o endereço
    montado pelo id de duas coincide ("A B|C|UF" e "A B C||UF"), ele leva à maior."""
    por_tamanho = sorted(escolas.values(), key=lambda e: (-e["total"], e["id"]))
    enderecos = Enderecos([(i, i) for i in alunos],
                          [(e["id"], texto_escola(e["nome"], e["municipio"], e["uf"])) for e in por_tamanho],
                          [(i, i) for i in cidades], _enderecos_antigos(con))
    for tipo, grupo in ((ALUNO, alunos), (ESCOLA, escolas), (CIDADE, cidades)):
        for item in grupo.values():
            item["endereco"] = enderecos.de(tipo, item["id"])
    # o oficial já está na tabela-resumo (com índice): aqui vão só os outros endereços aceitos
    con.executemany("INSERT INTO enderecos VALUES (?, ?, ?)",
                    ((tipo, endereco, ident) for tipo in (ALUNO, ESCOLA, CIDADE)
                     for endereco, ident in enderecos.aceitos(tipo) if endereco != enderecos.de(tipo, ident)))


def _enderecos_antigos(con: sqlite3.Connection) -> list[tuple[str, str]]:
    """(endereço do perfil com a grafia errada, id do perfil certo) de cada grafia corrigida à mão.

    O perfil certo é o das premiações que receberam o nome corrigido, nesse estado: a identidade dos alunos
    pode tê-lo juntado a premiações de outro estado, então o id nem sempre é NOME CERTO|UF."""
    antigos = []
    for (errado, uf), certo in GRAFIAS_CORRIGIDAS.items():
        achado = con.execute("SELECT aluno_id FROM medalhas WHERE nome_busca = ? AND uf = ? LIMIT 1",
                             (normalizar(certo), uf)).fetchone()
        if achado:
            antigos.append((slug(f"{errado}|{uf}"), achado[0]))
    return antigos


def gravar_indices_de_busca(con: sqlite3.Connection) -> None:
    """Índices de texto das sugestões: todas as grafias de cada aluno (nome_busca) e de cada escola (os termos de
    busca, que já trazem as siglas por extenso). A busca casa o início das palavras, como a busca completa."""
    con.execute("""INSERT INTO busca_alunos (rowid, texto)
                   SELECT a.n, t.texto FROM alunos a JOIN (
                       SELECT aluno_id, GROUP_CONCAT(DISTINCT nome_busca) AS texto FROM medalhas GROUP BY aluno_id
                   ) t ON t.aluno_id = a.id""")
    con.execute("""INSERT INTO busca_escolas (rowid, texto)
                   SELECT e.n, t.texto FROM escolas e JOIN (
                       SELECT escola_chave, GROUP_CONCAT(DISTINCT escola_termos) AS texto FROM medalhas
                       WHERE escola_chave != '' GROUP BY escola_chave
                   ) t ON t.escola_chave = e.id""")
    con.execute("INSERT INTO busca_alunos (busca_alunos) VALUES ('optimize')")
    con.execute("INSERT INTO busca_escolas (busca_escolas) VALUES ('optimize')")
