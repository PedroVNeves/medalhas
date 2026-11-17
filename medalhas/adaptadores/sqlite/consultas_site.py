"""Consultas das páginas do site: busca, rankings, perfis de aluno e escola e visão geral.

Recebem os parâmetros da URL como vieram (a API interna é tolerante: valor desconhecido vira o padrão).
"""
from ...dominio import gamificacao, pontuacao
from ...dominio.enderecos import Enderecos, texto_escola
import re

from ...dominio.escolas import palavras_da_busca
from ...dominio.texto import capitalizar_nome
from ...dominio.ranking import (ORDEM_PADRAO, ORDENACOES, TIPOS, RankingOrdenado, com_pontos, com_posicoes, ordenar,
                              posicionar)
from .conexao import Conexao, marcadores
from .filtros import AGREGADOS, CHAVES_FILTRO, condicoes, condicoes_de_texto

MAX_RESULTADOS_BUSCA = 2000
MAX_POR_PAGINA = 200
_TOTAIS = "ouro, prata, bronze, mencao, total, de, ate, " + ", ".join(pontuacao.COLUNAS)
_COLUNAS_RESUMO = {
    "alunos": "id, nome, uf, competicoes, escola, escola_chave, municipio, " + _TOTAIS,
    "escolas": "id, nome, municipio, uf, rede, esfera, alunos, " + _TOTAIS,
}


def _com_metodo(params: dict) -> tuple[dict, str, str]:
    """(parâmetros com os níveis que o método aceita, método, coluna de pontos)."""
    metodo, coluna = pontuacao.resolver_metodo(params.get("metodo"))
    niveis = pontuacao.restringir_niveis(metodo, params.get("nivel"))
    if niveis != params.get("nivel"):
        params = {**params, "nivel": niveis}
    return params, metodo, coluna


def _filtros(params: dict) -> dict:
    """Só as chaves de filtro reconhecidas e preenchidas (também servem de chave do cache)."""
    return {k: params[k] for k in CHAVES_FILTRO if params.get(k)}


# ---------------------------------------------------------------- busca

def busca(con: Conexao, params: dict) -> dict:
    """Premiações que casam com o texto (q, no campo nome, escola ou tudo) e os filtros, com os pontos do método.

    Devolve o total e no máximo MAX_RESULTADOS_BUSCA linhas, ordenadas por escola na busca por escola e por
    nome nas outras. Sem texto e sem recorte (ano, UF, município ou escola), devolve vazio."""
    params, _, coluna = _com_metodo(params)
    campo = params.get("campo") if params.get("campo") in ("nome", "escola", "tudo") else "nome"
    palavras = palavras_da_busca(params.get("q", ""))
    where, args = condicoes(params)
    w, a = condicoes_de_texto(campo, palavras)
    where, args = where + w, args + a
    if not palavras and not any(params.get(k) for k in ("ano", "uf", "municipio", "escola_chave")):
        return {"total": 0, "resultados": []}   # sem texto nem recorte, a busca devolveria a base inteira

    sql_where = " AND ".join(where) or "1"
    ordem = "escola_chave, ano DESC, nome_busca" if campo == "escola" else "nome_busca, ano, competicao"
    total = con.execute(f"SELECT COUNT(*) FROM medalhas WHERE {sql_where}", args).fetchone()[0]
    linhas = con.linhas(
        f"""SELECT competicao, ano, nivel, nome, escola, rede, esfera, municipio, uf, premio, medalha,
                   pontos, fonte, nome_busca, escola_chave, aluno_id, p_impa, p_impa3, p_site
            FROM medalhas WHERE {sql_where} ORDER BY {ordem} LIMIT {MAX_RESULTADOS_BUSCA}""", args)
    return {"total": total, "limite": MAX_RESULTADOS_BUSCA, "resultados": [com_pontos(r, coluna) for r in linhas]}


# ---------------------------------------------------------------- sugestões (enquanto a pessoa digita)

MAX_SUGESTOES = 8
_COLUNAS_SUGESTAO = {
    "alunos": "id, nome, uf, escola, municipio, ouro, prata, bronze, mencao",
    "escolas": "id, nome, municipio, uf, alunos, ouro, prata, bronze, mencao",
}


def _indice_de_sugestoes(con: Conexao) -> dict[tuple[str, int], list[tuple[str, str]]]:
    """Por (tipo, método), (texto pesquisável, id) de todos os alunos e escolas, do mais ao menos pontuado.

    Montado uma vez por versão da base. O texto segue as colunas da busca (palavras entre espaços), para que
    "% PALAVRA%" do SQL vire um simples ' PALAVRA' in texto. Alunos e escolas com mais de uma grafia (ou
    escolas que mudaram de nome, como CEFET-ES -> Ifes) guardam todas.
    Já em ordem de pontos, a busca para nas primeiras que casam: nomes comuns respondem sem varrer tudo.
    """
    def montar() -> dict[tuple[str, int], list[tuple[str, str]]]:
        pontos = ", ".join(f"r.{c}" for c in pontuacao.COLUNAS)
        linhas = {
            "alunos": con.execute(
                f"""SELECT ' ' || REPLACE(t.texto, ',', ' '), r.id, {pontos} FROM alunos r
                    JOIN (SELECT aluno_id, GROUP_CONCAT(DISTINCT nome_busca) AS texto
                          FROM medalhas GROUP BY aluno_id) t ON t.aluno_id = r.id""").fetchall(),
            "escolas": con.execute(
                f"""SELECT ' ' || REPLACE(t.texto, ',', ' '), r.id, {pontos} FROM escolas r
                    JOIN (SELECT escola_chave, GROUP_CONCAT(DISTINCT escola_termos) AS texto FROM medalhas
                          WHERE escola_chave != '' GROUP BY escola_chave) t ON t.escola_chave = r.id""").fetchall(),
        }
        return {(tipo, i): [(r[0], r[1]) for r in sorted(rs, key=lambda r: r[2 + i] or 0, reverse=True)]
                for tipo, rs in linhas.items() for i in range(len(pontuacao.COLUNAS))}

    return con.fixo("indice_de_sugestoes", montar)


def _casa(texto: str, palavras, com_siglas: bool) -> bool:
    """Toda palavra digitada começa alguma palavra do texto (ou, em escolas, a sigla casa pela expansão)."""
    for palavra, expansao in palavras:
        if f" {palavra}" in texto:
            continue
        if com_siglas and expansao != [palavra] and all(f" {e}" in texto for e in expansao):
            continue
        return False
    return True


def _mais_pontuados(con: Conexao, tipo: str, palavras, metodo: int, limite: int) -> list[dict]:
    """Até `limite` alunos ou escolas que casam com as palavras, dos mais pontuados no método (índice em
    pontuacao.COLUNAS) para os menos, com pontos e posição nacional."""
    com_siglas = tipo == "escolas"
    ids: list[str] = []
    for texto, ident in _indice_de_sugestoes(con)[(tipo, metodo)]:
        if _casa(texto, palavras, com_siglas):
            ids.append(ident)
            if len(ids) == limite:
                break
    if not ids:
        return []
    coluna = pontuacao.COLUNAS[metodo]
    linhas = con.linhas(f"SELECT {_COLUNAS_SUGESTAO[tipo]}, {coluna} AS pontos, {coluna}_pos AS posicao "
                        f"FROM {tipo} WHERE id IN ({marcadores(len(ids))})", ids)
    por_id = {r["id"]: r for r in linhas}
    return [por_id[i] for i in ids if i in por_id]


def sugestoes(con: Conexao, params: dict) -> dict:
    """Os alunos e escolas mais premiados cujo nome casa com o que foi digitado (lista curta e rápida)."""
    _, coluna = pontuacao.resolver_metodo(params.get("metodo"))
    campo = params.get("campo") if params.get("campo") in ("nome", "escola", "tudo") else "tudo"
    palavras = palavras_da_busca(params.get("q", ""))
    if not palavras or len("".join(p for p, _ in palavras)) < 2:
        return {"alunos": [], "escolas": []}
    i = pontuacao.COLUNAS.index(coluna)
    alunos = _mais_pontuados(con, "alunos", palavras, i, MAX_SUGESTOES) if campo != "escola" else []
    escolas = _mais_pontuados(con, "escolas", palavras, i, MAX_SUGESTOES) if campo != "nome" else []
    if campo == "tudo":   # alunos primeiro, mas sempre com espaço para até 3 escolas
        alunos = alunos[:max(MAX_SUGESTOES - min(3, len(escolas)), 0)]
        escolas = escolas[:MAX_SUGESTOES - len(alunos)]
    return {"alunos": alunos, "escolas": escolas}


# ---------------------------------------------------------------- rankings

def _pontos_da_carreira(con: Conexao, tabela: str, ids: list[str], coluna: str) -> dict:
    """Pontos totais (sem filtros) de cada aluno/escola: o tier é sempre o da carreira inteira."""
    if not ids:
        return {}
    return dict(con.execute(f"SELECT id, {coluna} FROM {tabela} WHERE id IN ({marcadores(len(ids))})", ids).fetchall())


def _ultima_escola(con: Conexao, aluno_ids: list[str]) -> dict:
    """id -> escola, chave da escola e município mais recentes de cada aluno (da tabela-resumo)."""
    if not aluno_ids:
        return {}
    return {r["id"]: {"escola": r["escola"], "escola_chave": r["escola_chave"], "municipio": r["municipio"]}
            for r in con.execute(f"SELECT id, escola, escola_chave, municipio FROM alunos "
                                 f"WHERE id IN ({marcadores(len(aluno_ids))})", aluno_ids)}


def agregar(con: Conexao, tipo: str, params: dict) -> list[dict]:
    """Um item por aluno, escola ou estado, somando as premiações que passam nos filtros (em cache).

    Sem filtros, alunos e escolas vêm prontos das tabelas-resumo.
    """
    filtros = _filtros(params)

    def calcular() -> list[dict]:
        if tipo in _COLUNAS_RESUMO and not filtros:
            return con.linhas(f"SELECT {_COLUNAS_RESUMO[tipo]} FROM {tipo}")
        where, args = condicoes(filtros)
        # "GROUP BY x || ''" impede o SQLite de usar o índice de x: uma varredura sequencial só é bem
        # mais rápida que milhares de saltos pelo índice quando o agrupamento cobre a base quase toda
        if tipo == "estados":
            where.append("uf IS NOT NULL")
            if not filtros:
                linhas = con.linhas(f"SELECT uf AS id, uf AS nome, {AGREGADOS} FROM medalhas "
                                    "WHERE uf IS NOT NULL GROUP BY uf || ''")
                alunos = dict(con.execute("SELECT uf, COUNT(*) FROM alunos GROUP BY uf").fetchall())
                escolas = dict(con.execute("SELECT uf, COUNT(*) FROM escolas GROUP BY uf").fetchall())
                for r in linhas:
                    r["alunos"], r["escolas"] = alunos.get(r["id"], 0), escolas.get(r["id"], 0)
                return linhas
            return con.linhas(
                f"""SELECT uf AS id, uf AS nome, COUNT(DISTINCT aluno_id) AS alunos,
                           COUNT(DISTINCT NULLIF(escola_chave, '')) AS escolas, {AGREGADOS}
                    FROM medalhas WHERE {' AND '.join(where)} GROUP BY uf || ''""", args)
        if tipo == "cidades":   # id = MUNICIPIO|UF (sem acento); MAX(municipio) prefere a grafia com acento
            where += ["municipio_busca != ''", "uf IS NOT NULL"]
            linhas = con.linhas(
                f"""SELECT municipio_busca || '|' || uf AS id, uf,
                           COUNT(DISTINCT aluno_id) AS alunos, COUNT(DISTINCT NULLIF(escola_chave, '')) AS escolas,
                           {AGREGADOS}
                    FROM medalhas WHERE {' AND '.join(where)} GROUP BY municipio_busca, uf""", args)
            nomes = _nomes_das_cidades(con)
            for r in linhas:
                r["nome"] = nomes.get(r["id"], r["id"].split("|")[0])
            return linhas
        if tipo == "escolas":
            where.append("escola_chave != ''")
            return con.linhas(
                f"""SELECT escola_chave AS id, MAX(escola) AS nome, MAX(municipio) AS municipio, MAX(uf) AS uf,
                           MAX(rede) AS rede, MAX(esfera) AS esfera, COUNT(DISTINCT aluno_id) AS alunos, {AGREGADOS}
                    FROM medalhas WHERE {' AND '.join(where)} GROUP BY escola_chave || ''""", args)
        return con.linhas(
            f"""SELECT aluno_id AS id, COALESCE(MAX(CASE WHEN competicao = 'OBM' THEN nome END), MAX(nome)) AS nome,
                       MAX(uf) AS uf, GROUP_CONCAT(DISTINCT competicao) AS competicoes, {AGREGADOS}
                FROM medalhas WHERE {' AND '.join(where) or '1'} GROUP BY aluno_id || ''""", args)

    return con.em_cache(("agregado", tipo, tuple(sorted(filtros.items()))), calcular)


def ranking_ordenado(con: Conexao, params: dict) -> RankingOrdenado:
    """Ranking completo, ordenado e em cache. Usado pela página, pela API e pela exportação."""
    params, metodo, coluna = _com_metodo(params)
    tipo = params.get("tipo") if params.get("tipo") in TIPOS else "alunos"
    ordem = params.get("ordem") if params.get("ordem") in ORDENACOES else ORDEM_PADRAO
    filtros = tuple(sorted(_filtros(params).items()))
    itens = con.em_cache(("ordenado", tipo, ordem, metodo, filtros),
                         lambda: ordenar(agregar(con, tipo, params), ordem, coluna))
    return RankingOrdenado(tipo, ordem, metodo, coluna, params.get("nivel"), itens)


def ranking(con: Conexao, params: dict) -> dict:
    """Uma página do ranking (limite até MAX_POR_PAGINA, a partir de offset), com posição e tier de cada item.

    Escolas levam o nome da tabela-resumo; alunos sem escola no recorte levam a mais recente. O tier é sempre
    o da carreira inteira, mesmo com filtros. No método IMPA oficial, nivel_forcado traz os níveis que ele
    aceita (o filtro de nível fica restrito a eles)."""
    limite = min(int(params.get("limite", 50)), MAX_POR_PAGINA)
    offset = max(int(params.get("offset", 0)), 0)
    r = ranking_ordenado(con, params)
    pagina = list(com_posicoes(r, offset, limite))

    if r.tipo == "escolas" and pagina:   # rankings filtrados trazem uma grafia qualquer: usa o nome da escola
        ids = [it["id"] for it in pagina]
        nomes = dict(con.execute(f"SELECT id, nome FROM escolas WHERE id IN ({marcadores(len(ids))})", ids).fetchall())
        for it in pagina:
            it["nome"] = nomes.get(it["id"], it["nome"])
    if r.tipo in ("alunos", "escolas"):
        ids = [it["id"] for it in pagina]
        carreira = _pontos_da_carreira(con, r.tipo, ids, r.coluna)
        escolas = _ultima_escola(con, ids) if r.tipo == "alunos" else {}
        for it in pagina:
            # rankings filtrados não trazem a escola: completa com a mais recente do aluno
            it.update({k: v for k, v in escolas.get(it["id"], {}).items() if not it.get(k)})
            it["tier"] = gamificacao.tier(carreira.get(it["id"], it["xp"]), escola=r.tipo == "escolas",
                                          metodo=r.metodo)
    return {"tipo": r.tipo, "metodo": r.metodo, "nivel_forcado": r.niveis if r.metodo == "impa3" else None,
            "total": len(r.itens), "offset": offset, "limite": limite, "itens": pagina}


# ---------------------------------------------------------------- perfis

def _pontuacoes(resumo) -> dict:
    """Pontos e posição nacional nos três métodos (quadro comparativo do perfil)."""
    return {m: {"pts": resumo[i["coluna"]], "pos": resumo[f"{i['coluna']}_pos"] if resumo[i["coluna"]] else None}
            for m, i in pontuacao.METODOS.items()}


def _participantes(con: Conexao, tabela: str, coluna: str, uf: str | None) -> tuple[int, int]:
    """Quantos pontuam no método (no Brasil e na UF): o "de N" da posição."""
    total = con.execute(f"SELECT COUNT(*) FROM {tabela} WHERE {coluna} > 0").fetchone()[0]
    if not uf:
        return total, 0   # sem estado não há posição estadual
    total_uf = con.execute(f"SELECT COUNT(*) FROM {tabela} WHERE uf = ? AND {coluna} > 0", (uf,)).fetchone()[0]
    return total, total_uf


def perfil_aluno(con: Conexao, aluno_id: str, params: dict) -> dict:
    """Página do aluno: premiações, escolas, posições nacional e estadual, tier, conquistas e o "próximo alvo"
    (quem está logo acima no ranking nacional). {"erro": …} se o aluno não existe."""
    metodo, coluna = pontuacao.resolver_metodo(params.get("metodo"))
    premiacoes = con.linhas(
        """SELECT competicao, ano, nivel, nome, escola, escola_chave, rede, esfera, municipio, uf,
                  premio, medalha, pontos, fonte, p_impa, p_impa3, p_site, aluno_id
           FROM medalhas WHERE aluno_id = ? ORDER BY ano DESC, competicao""", (aluno_id,))
    if not premiacoes:
        return {"erro": "Aluno não encontrado"}
    premiacoes = [com_pontos(r, coluna) for r in premiacoes]
    resumo = con.execute("SELECT * FROM alunos WHERE id = ?", (aluno_id,)).fetchone()
    xp, uf = resumo[coluna], resumo["uf"]
    total, total_uf = _participantes(con, "alunos", coluna, uf)

    # quem está logo acima no ranking nacional ("próximo alvo")
    alvo = con.execute(f"SELECT id, nome, {coluna} AS xp FROM alunos WHERE {coluna} > ? "
                       f"ORDER BY {coluna}, nome LIMIT 1", (xp,)).fetchone()
    acima = {"id": alvo["id"], "nome": alvo["nome"], "xp": alvo["xp"], "diferenca": alvo["xp"] - xp} if alvo else None

    escolas: list[dict] = []
    for r in premiacoes:
        if r["escola_chave"] and r["escola_chave"] not in {e["escola_chave"] for e in escolas}:
            escolas.append({"escola": r["escola"], "escola_chave": r["escola_chave"], "municipio": r["municipio"]})

    return {
        "id": aluno_id, "nome": resumo["nome"], "uf": uf,
        "municipios": sorted({r["municipio"] for r in premiacoes if r["municipio"]}),
        "escolas": escolas, "xp": xp, "tier": gamificacao.tier(xp, metodo=metodo), "metodo": metodo,
        # sem pontos no método não há posição (todos os zerados empatariam no fim da lista)
        "rank": resumo[f"{coluna}_pos"] if xp else None, "rank_total": total,
        "rank_uf": resumo[f"{coluna}_pos_uf"] if xp else None, "rank_uf_total": total_uf,
        "impa": resumo["p_impa3"], "rank_impa": resumo["p_impa3_pos"] if resumo["p_impa3"] else None,
        "pontuacoes": _pontuacoes(resumo),
        "medalhas": gamificacao.contar_medalhas(premiacoes), "anos": sorted({r["ano"] for r in premiacoes if r["ano"]}),
        "conquistas": gamificacao.conquistas_aluno(premiacoes), "acima": acima, "premiacoes": premiacoes,
    }


def perfil_escola(con: Conexao, escola_id: str, params: dict) -> dict:
    """Página da escola: outras grafias do nome, posições, medalhas por ano, os 15 alunos que mais pontuaram,
    conquistas e as 60 premiações mais recentes. {"erro": …} se a escola não existe."""
    metodo, coluna = pontuacao.resolver_metodo(params.get("metodo"))
    premiacoes = con.linhas(
        """SELECT competicao, ano, nivel, nome, escola, rede, esfera, municipio, uf, premio, medalha,
                  fonte, p_impa, p_impa3, p_site, aluno_id
           FROM medalhas WHERE escola_chave = ? ORDER BY ano DESC, nome""", (escola_id,))
    if not premiacoes:
        return {"erro": "Escola não encontrada"}
    premiacoes = [com_pontos(r, coluna) for r in premiacoes]
    resumo = con.execute("SELECT * FROM escolas WHERE id = ?", (escola_id,)).fetchone()
    xp, uf = resumo[coluna], resumo["uf"]
    posicao = resumo[f"{coluna}_pos"] if xp else None
    posicao_uf = resumo[f"{coluna}_pos_uf"] if xp else None
    total, total_uf = _participantes(con, "escolas", coluna, uf)

    grafias: dict[str, int] = {}
    for r in premiacoes:
        grafias[r["escola"]] = grafias.get(r["escola"], 0) + 1
    nomes = sorted(grafias, key=lambda k: -grafias[k])

    por_ano: dict[int, dict] = {}
    for r in premiacoes:
        s = por_ano.setdefault(r["ano"], {"ano": r["ano"], "Ouro": 0, "Prata": 0, "Bronze": 0})
        if r["medalha"] in s:
            s[r["medalha"]] += 1

    alunos: dict[str, dict] = {}
    for r in premiacoes:
        a = alunos.setdefault(r["aluno_id"], {"id": r["aluno_id"], "nome": r["nome"], "xp": 0,
                                              "ouro": 0, "prata": 0, "bronze": 0, "anos": set()})
        a["xp"] += r["xp"]
        a["anos"].add(r["ano"])
        campo = {"Ouro": "ouro", "Prata": "prata", "Bronze": "bronze"}.get(r["medalha"])
        if campo:
            a[campo] += 1
    destaques = sorted(alunos.values(), key=lambda a: (-a["xp"], a["nome"]))[:15]
    for a in destaques:
        a["anos"] = sorted(a["anos"])

    return {
        "id": escola_id, "nome": resumo["nome"], "variantes": [n for n in nomes if n != resumo["nome"]], "municipio": premiacoes[0]["municipio"], "uf": uf,
        "rede": premiacoes[0]["rede"], "esfera": premiacoes[0]["esfera"], "xp": xp, "metodo": metodo,
        "tier": gamificacao.tier(xp, escola=True, metodo=metodo),
        "rank": posicao, "rank_total": total, "rank_uf": posicao_uf, "rank_uf_total": total_uf,
        "impa": resumo["p_impa3"], "pontuacoes": _pontuacoes(resumo),
        "medalhas": gamificacao.contar_medalhas(premiacoes), "alunos": len(alunos),
        "anos": sorted({r["ano"] for r in premiacoes}), "serie": [por_ano[a] for a in sorted(por_ano)],
        "top_alunos": destaques, "conquistas": gamificacao.conquistas_escola(premiacoes, posicao, posicao_uf),
        "recentes": premiacoes[:60],
    }


# ---------------------------------------------------------------- cidades

def _posicao(r: RankingOrdenado, ident: str) -> tuple[dict | None, int | None]:
    """(item, posição) de um id no ranking; (None, None) se ele não está (sem pontos no método)."""
    for posicao, item in posicionar(r.itens, r.chave):
        if item["id"] == ident:
            return item, posicao
    return None, None


def nome_da_cidade(grafias: dict[str, int]) -> str:
    """Nome de exibição a partir das grafias vistas nas listas e quantas vezes cada uma apareceu.

    Prefere a grafia com acento mais comum ("São Paulo", não "SAO PAULO"), tira pontuação solta ('São Paulo"')
    e padroniza as maiúsculas ("Rio de janeiro" -> "Rio de Janeiro").

    >>> nome_da_cidade({"SAO PAULO": 90, 'São Paulo"': 3, "São Paulo": 2})
    'São Paulo'
    >>> nome_da_cidade({'SANTA BÁRBARA D"OESTE': 4})
    "Santa Bárbara d'Oeste"
    """
    limpas: dict[str, int] = {}
    for g, n in grafias.items():
        g = re.sub(r"[\"´`’]", "'", g or "")   # aspas e acentos soltos no lugar do apóstrofo
        g = re.sub(r"\s+", " ", re.sub(r"^[^\w]+|[^\w]+$", "", g)).strip()
        if g:
            limpas[g.upper()] = limpas.get(g.upper(), 0) + n
    if not limpas:
        return ""
    com_acento = {g: n for g, n in limpas.items() if not g.isascii()} or limpas
    nome = capitalizar_nome(max(com_acento, key=lambda g: (com_acento[g], g)))
    return re.sub(r"\bD'(\w)", lambda m: "d'" + m.group(1).upper(), nome)   # Santa Bárbara d'Oeste


def _nomes_das_cidades(con: Conexao) -> dict[str, str]:
    """id (MUNICIPIO|UF) -> nome de exibição, de todas as cidades (uma vez por versão da base)."""
    def montar() -> dict[str, str]:
        grafias: dict[str, dict[str, int]] = {}
        for ident, municipio, n in con.execute(
                """SELECT municipio_busca || '|' || uf, municipio, COUNT(*) FROM medalhas
                   WHERE municipio_busca != '' AND uf IS NOT NULL GROUP BY 1, 2"""):
            grafias.setdefault(ident, {})[municipio] = n
        return {ident: nome_da_cidade(g) for ident, g in grafias.items()}
    return con.fixo("nomes_das_cidades", montar)


def perfil_cidade(con: Conexao, cidade_id: str, params: dict) -> dict:
    """Resumo de uma cidade (id MUNICIPIO|UF): premiações conquistadas por alunos de escolas de lá."""
    metodo, coluna = pontuacao.resolver_metodo(params.get("metodo"))
    municipio, _, uf = cidade_id.rpartition("|")
    premiacoes = con.linhas(
        """SELECT competicao, ano, nivel, nome, escola, escola_chave, municipio, uf, medalha, aluno_id, fonte,
                  p_impa, p_impa3, p_site
           FROM medalhas WHERE municipio_busca = ? AND uf = ? ORDER BY ano DESC, nome""", (municipio, uf))
    if not municipio or not premiacoes:
        return {"erro": "Cidade não encontrada"}
    nacional = ranking_ordenado(con, {"tipo": "cidades", "metodo": metodo})
    estadual = ranking_ordenado(con, {"tipo": "cidades", "metodo": metodo, "uf": uf})
    _, posicao = _posicao(nacional, cidade_id)
    _, posicao_uf = _posicao(estadual, cidade_id)

    por_ano: dict[int, dict] = {}
    por_olimpiada: dict[str, int] = {}
    for r in premiacoes:
        s = por_ano.setdefault(r["ano"], {"ano": r["ano"], "Ouro": 0, "Prata": 0, "Bronze": 0})
        if r["medalha"] in s:
            s[r["medalha"]] += 1
        por_olimpiada[r["competicao"]] = por_olimpiada.get(r["competicao"], 0) + 1
    recorte = {"municipio": municipio, "uf": uf, "metodo": metodo, "limite": 10}
    return {
        "id": cidade_id, "nome": _nomes_das_cidades(con).get(cidade_id, municipio), "uf": uf, "metodo": metodo,
        "xp": sum(r[coluna] or 0 for r in premiacoes),
        "pontuacoes": {m: sum(r[c["coluna"]] or 0 for r in premiacoes) for m, c in pontuacao.METODOS.items()},
        "rank": posicao, "rank_total": len(nacional.itens), "rank_uf": posicao_uf, "rank_uf_total": len(estadual.itens),
        "medalhas": gamificacao.contar_medalhas(premiacoes), "total": len(premiacoes),
        "alunos": len({r["aluno_id"] for r in premiacoes}),
        "escolas": len({r["escola_chave"] for r in premiacoes if r["escola_chave"]}),
        "anos": sorted({r["ano"] for r in premiacoes if r["ano"]}), "serie": [por_ano[a] for a in sorted(por_ano)],
        "olimpiadas": sorted(({"sigla": k, "total": v} for k, v in por_olimpiada.items()), key=lambda o: -o["total"]),
        "top_escolas": ranking(con, {**recorte, "tipo": "escolas"})["itens"],
        "top_alunos": ranking(con, {**recorte, "tipo": "alunos"})["itens"],
    }


# ---------------------------------------------------------------- endereços das páginas

def enderecos(con: Conexao) -> Enderecos:
    """Endereços legíveis de todos os alunos, escolas (nome, cidade e UF) e cidades. Um cálculo por versão da base."""
    def montar() -> Enderecos:
        alunos = [(r[0], r[0]) for r in con.execute("SELECT id FROM alunos")]
        escolas = [(r[0], texto_escola(r[1], r[2], r[3])) for r in con.execute("SELECT id, nome, municipio, uf FROM escolas")]
        cidades = [(r[0], r[0]) for r in con.execute(
            "SELECT DISTINCT municipio_busca || '|' || uf FROM medalhas WHERE municipio_busca != '' AND uf IS NOT NULL")]
        return Enderecos(alunos, escolas, cidades)
    return con.fixo("enderecos", montar)


# ---------------------------------------------------------------- visão geral (página inicial)

_ORDEM_NIVEL = {"1": 1, "2": 2, "3": 3, "Universitário": 9}


def _visao_geral_fixa(con: Conexao) -> dict:
    """Parte da visão geral que não depende do método escolhido."""
    totais = dict(con.execute(f"SELECT {AGREGADOS} FROM medalhas").fetchone())
    totais["alunos"] = con.execute("SELECT COUNT(*) FROM alunos").fetchone()[0]
    totais["escolas"] = con.execute("SELECT COUNT(*) FROM escolas").fetchone()[0]
    serie = con.linhas("""SELECT ano, competicao, SUM(medalha='Ouro') AS ouro, SUM(medalha='Prata') AS prata,
                                 SUM(medalha='Bronze') AS bronze, COUNT(*) AS total
                          FROM medalhas GROUP BY ano, competicao ORDER BY ano""")
    competicoes = con.linhas("SELECT competicao, COUNT(*) AS n, MIN(ano) AS de, MAX(ano) AS ate "
                             "FROM medalhas GROUP BY competicao")
    por_sigla = {c["competicao"]: c for c in competicoes}
    olimpiadas = [dict(o, **{k: por_sigla.get(o["sigla"], {}).get(k) for k in ("n", "de", "ate")})
                  for o in pontuacao.catalogo()]
    niveis = [{"id": r[0], "n": r[1], "competicoes": r[2].split(",")} for r in con.execute(
        """SELECT nivel, COUNT(*), GROUP_CONCAT(DISTINCT competicao) FROM medalhas
           WHERE nivel IS NOT NULL GROUP BY nivel""")]
    niveis.sort(key=lambda n: (_ORDEM_NIVEL.get(n["id"], 5), n["id"]))
    meta = dict(con.execute("SELECT chave, valor FROM meta").fetchall())
    return {
        "totais": totais, "serie": serie, "competicoes": competicoes,
        "ufs": [r[0] for r in con.execute("SELECT DISTINCT uf FROM medalhas WHERE uf IS NOT NULL ORDER BY uf")],
        "anos": [r[0] for r in con.execute("SELECT DISTINCT ano FROM medalhas ORDER BY ano DESC")],
        "olimpiadas": olimpiadas, "areas": sorted({o["area"] for o in olimpiadas}), "niveis": niveis,
        "fonte_pontos": pontuacao.FONTE_PONTOS, "metodos": pontuacao.metodos(),
        "metodo_padrao": pontuacao.METODO_PADRAO, "niveis_impa": pontuacao.niveis_impa(),
        "escala_site": [{"grupo": g, **tabela} for g, tabela in pontuacao.ESCALA_SITE.items()],
        "tiers": {m: {"aluno": [{"nome": n, "min": mi, "cor": c} for n, mi, c in gamificacao.tiers(m)],
                      "escola": [{"nome": n, "min": mi, "cor": c} for n, mi, c in gamificacao.tiers(m, True)]}
                  for m in pontuacao.METODOS},
        "conquistas_aluno": gamificacao.conquistas_aluno([]),
        "conquistas_escola": gamificacao.conquistas_escola([], None, None), **meta,
    }


def visao_geral(con: Conexao, params: dict) -> dict:
    """Página inicial: a parte fixa (em cache) mais os totais em pontos e os destaques (10 alunos, 10 escolas,
    estados) no método pedido, cada destaque em cache por método."""
    metodo, coluna = pontuacao.resolver_metodo(params.get("metodo"))
    dados = dict(con.em_cache("visao_geral", lambda: _visao_geral_fixa(con)))
    dados["totais"] = com_pontos(dict(dados["totais"]), coluna)
    dados["metodo"] = metodo
    p = {"metodo": metodo}
    destaques = (("top_alunos", "alunos", 10), ("top_escolas", "escolas", 10), ("estados", "estados", 30))
    for chave, tipo, limite in destaques:
        dados[chave] = con.em_cache((chave, metodo),
                                    lambda t=tipo, n=limite: ranking(con, {**p, "tipo": t, "limite": n})["itens"])
    return dados
