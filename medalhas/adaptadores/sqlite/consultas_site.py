"""Consultas das páginas do site: busca, rankings, perfis de aluno e escola e visão geral.

Recebem os parâmetros da URL como vieram (a API interna é tolerante: valor desconhecido vira o padrão).
"""

from ...dominio import gamificacao, pontuacao
from ...dominio.escolas import palavras_da_busca
from ...dominio.ranking import com_pontos
from . import consultas_ranking
from .conexao import Conexao, marcadores
from .consultas_enderecos import EnderecosDaBase
from .filtros import AGREGADOS, CHAVES_FILTRO, condicoes, condicoes_de_texto, inteiro

GRUPOS_POR_PAGINA_BUSCA = 30   # cartões (alunos ou escolas) por página da busca; "Mostrar mais" pede os próximos
PREMIACOES_NO_CARTAO = 5       # as mais recentes de cada um; o perfil tem todas
MAX_POR_PAGINA = 200


def _com_metodo(params: dict) -> tuple[dict, str, str]:
    """(parâmetros com os níveis que o método aceita, método, coluna de pontos).

    No IMPA edital entra também so_edital: o nível "3" existe em olimpíadas fora do edital (Itabirana), e as
    medalhas delas não podem contar no quadro de quem está sendo ordenado pelo edital."""
    metodo, coluna = pontuacao.resolver_metodo(params.get("metodo"))
    niveis = pontuacao.restringir_niveis(metodo, params.get("nivel"))
    so_edital = "1" if metodo == "impa3" else None
    if niveis != params.get("nivel") or so_edital != params.get("so_edital"):
        params = {**params, "nivel": niveis, "so_edital": so_edital}
    return params, metodo, coluna


def _filtros(params: dict) -> dict:
    """Só as chaves de filtro reconhecidas e preenchidas (também servem de chave do cache)."""
    return {k: params[k] for k in CHAVES_FILTRO if params.get(k)}


# ---------------------------------------------------------------- busca

def busca(con: Conexao, params: dict) -> dict:
    """Alunos (ou escolas, no campo escola) com premiações que casam com o texto (q) e os filtros, uma página de
    cartões por vez (offset), dos que mais pontuam no método para os que menos.

    Cada cartão traz só o que a tela mostra: nome e lugar (da ficha do aluno ou da escola), as contagens de todas
    as premiações dele no recorte e as PREMIACOES_NO_CARTAO mais recentes, com os campos de cada linha. Sem texto
    e sem recorte (ano, UF, município ou escola), devolve vazio: seria a base inteira."""
    params, _, coluna = _com_metodo(params)
    campo = params.get("campo") if params.get("campo") in ("nome", "escola", "tudo") else "nome"
    offset = inteiro(params.get("offset", 0), "offset", 0, 10**9)
    palavras = palavras_da_busca(params.get("q", ""))
    where, args = condicoes(params)
    w, a = condicoes_de_texto(campo, palavras)
    where, args = where + w, args + a
    vazio = {"total": 0, "total_grupos": 0, "offset": offset, "limite": GRUPOS_POR_PAGINA_BUSCA, "grupos": []}
    if not palavras and not any(params.get(k) for k in ("ano", "uf", "municipio", "escola_chave")):
        return vazio

    sql_where = " AND ".join(where) or "1"
    por_escola = campo == "escola"
    chave = "escola_chave" if por_escola else "aluno_id"
    # escola sem estado (lista sem UF) não tem página: fica de fora do agrupamento por escola
    com_grupo = sql_where + (" AND escola_chave != ''" if por_escola else "")
    total = con.execute(f"SELECT COUNT(*) FROM medalhas WHERE {sql_where}", args).fetchone()[0]
    grupos = con.linhas(
        f"""SELECT {chave} AS id, SUM(medalha='Ouro') AS ouro, SUM(medalha='Prata') AS prata,
                   SUM(medalha='Bronze') AS bronze, SUM(medalha='Menção Honrosa') AS mencao,
                   COUNT(*) AS total, COUNT(*) OVER () AS _grupos
            FROM medalhas WHERE {com_grupo} GROUP BY {chave} || ''
            ORDER BY SUM({coluna}) DESC, total DESC, id LIMIT ? OFFSET ?""", [*args, GRUPOS_POR_PAGINA_BUSCA, offset])
    if not grupos:
        return {**vazio, "total": total}
    total_grupos = grupos[0].pop("_grupos")
    ids = [g["id"] for g in grupos]
    for g in grupos[1:]:
        del g["_grupos"]

    # nome e lugar: os da ficha (o mesmo nome do perfil), uma vez por cartão
    ficha = ("SELECT id, nome, municipio, uf FROM escolas" if por_escola else "SELECT id, nome, uf FROM alunos")
    fichas = {r["id"]: r for r in con.linhas(f"{ficha} WHERE id IN ({marcadores(len(ids))})", ids)}
    # as premiações mais recentes de cada um, só com as colunas que a linha do cartão mostra
    colunas = "nome, aluno_id" if por_escola else "escola, escola_chave, municipio, uf"
    desempate = "nome_busca" if por_escola else "competicao"
    linhas = con.linhas(
        f"""SELECT * FROM (
                SELECT {chave} AS _grupo, id, ano, competicao, medalha, premio, nivel, fonte, {colunas},
                       ROW_NUMBER() OVER (PARTITION BY {chave} ORDER BY ano DESC, {desempate}) AS _ordem
                FROM medalhas WHERE {com_grupo} AND {chave} IN ({marcadores(len(ids))}))
            WHERE _ordem <= ? ORDER BY _ordem""", [*args, *ids, PREMIACOES_NO_CARTAO])
    por_grupo: dict[str, list[dict]] = {}
    for r in linhas:
        grupo = r.pop("_grupo")
        del r["_ordem"]
        if r["premio"] == r["medalha"]:
            del r["premio"]          # o tipo do prêmio só vai quando diz algo além da medalha ("Honra ao Mérito")
        if r.get("escola"):
            del r["municipio"], r["uf"]   # com a escola, a cidade não aparece na linha
        por_grupo.setdefault(grupo, []).append({k: v for k, v in r.items() if v is not None})
    for g in grupos:
        g.update({k: v for k, v in dict(fichas.get(g["id"], {})).items() if k != "id"})
        g["premiacoes"] = por_grupo.get(g["id"], [])
    return {"total": total, "total_grupos": total_grupos, "offset": offset, "limite": GRUPOS_POR_PAGINA_BUSCA,
            "grupos": grupos}


# ---------------------------------------------------------------- sugestões (enquanto a pessoa digita)

MAX_SUGESTOES = 8
_COLUNAS_SUGESTAO = {
    "alunos": "id, nome, uf, escola, municipio, ouro, prata, bronze, mencao",
    "escolas": "id, nome, municipio, uf, alunos, ouro, prata, bronze, mencao",
}


def _consulta_de_texto(palavras, com_siglas: bool) -> str:
    """Consulta do índice de texto (FTS5): toda palavra digitada casa o início de alguma palavra do nome; em
    escolas, a sigla também casa pela expansão (todas as palavras dela: IFAL -> INSTITUTO FEDERAL ALAGOAS).
    As palavras já vêm normalizadas (só A-Z, 0-9), então as aspas não precisam de escape."""
    partes = []
    for palavra, expansao in palavras:
        termo = f'"{palavra}"*'
        if com_siglas and expansao != [palavra]:
            termo = "(" + termo + " OR (" + " AND ".join(f'"{e}"*' for e in expansao) + "))"
        partes.append(termo)
    return " AND ".join(partes)


def _mais_pontuados(con: Conexao, tipo: str, palavras, coluna: str, limite: int) -> list[dict]:
    """Até `limite` alunos ou escolas que casam com as palavras, dos mais pontuados no método para os menos,
    com pontos e posição nacional. O banco acha os que casam (índice busca_alunos ou busca_escolas) e devolve só
    os primeiros: nenhuma lista de nomes fica na memória."""
    return con.linhas(
        f"""SELECT {", ".join("t." + c for c in _COLUNAS_SUGESTAO[tipo].split(", "))}, t.{coluna} AS pontos,
                   t.{coluna}_pos AS posicao
            FROM busca_{tipo} b JOIN {tipo} t ON t.n = b.rowid WHERE busca_{tipo} MATCH ?
            ORDER BY t.{coluna} DESC, t.total DESC, t.nome LIMIT ?""",
        (_consulta_de_texto(palavras, tipo == "escolas"), limite))


def sugestoes(con: Conexao, params: dict) -> dict:
    """Os alunos e escolas mais premiados cujo nome casa com o que foi digitado (lista curta e rápida)."""
    _, coluna = pontuacao.resolver_metodo(params.get("metodo"))
    campo = params.get("campo") if params.get("campo") in ("nome", "escola", "tudo") else "tudo"
    palavras = palavras_da_busca(params.get("q", ""))
    if not palavras or len("".join(p for p, _ in palavras)) < 2:
        return {"alunos": [], "escolas": []}
    alunos = _mais_pontuados(con, "alunos", palavras, coluna, MAX_SUGESTOES) if campo != "escola" else []
    escolas = _mais_pontuados(con, "escolas", palavras, coluna, MAX_SUGESTOES) if campo != "nome" else []
    if campo == "tudo":   # alunos primeiro, mas sempre com espaço para até 3 escolas
        alunos = alunos[:max(MAX_SUGESTOES - min(3, len(escolas)), 0)]
        escolas = escolas[:MAX_SUGESTOES - len(alunos)]
    return {"alunos": alunos, "escolas": escolas}


# ---------------------------------------------------------------- rankings

def ranking(con: Conexao, params: dict, extras: tuple[str, ...] = ()) -> dict:
    """Uma página do ranking (limite até MAX_POR_PAGINA, a partir de offset), só com o que a tela mostra:
    posição, nome, lugar, medalhas, pontos e o nível (tier) da carreira inteira. Ordem e posições são calculadas
    pelo banco (consultas_ranking), que devolve só as linhas da página. No método IMPA oficial, nivel_forcado
    traz os níveis que ele aceita (o filtro de nível fica restrito a eles)."""
    limite = inteiro(params.get("limite", 50), "limite", 0, MAX_POR_PAGINA)
    offset = inteiro(params.get("offset", 0), "offset", 0, 10**9)
    r = consultas_ranking.pagina(con, params, offset, limite, extras=extras)
    return {"tipo": r.tipo, "metodo": r.metodo, "nivel_forcado": r.niveis if r.metodo == "impa3" else None,
            "total": r.total, "offset": offset, "limite": limite, "itens": r.itens}


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
    (quem está logo acima no ranking nacional). {"erro": …} se o aluno não existe.

    Cada premiação vai só com o que a linha da tela mostra: ano, olimpíada, medalha (e o prêmio, quando diz mais
    que ela), nível, escola, nota na prova, pontos no método, se conta no IMPA Tech e a fonte."""
    metodo, coluna = pontuacao.resolver_metodo(params.get("metodo"))
    linhas = con.linhas(
        f"""SELECT id, ano, competicao, medalha, premio, nivel, escola, escola_chave, municipio, pontos, fonte,
                   {coluna} AS xp, p_impa3 > 0 AS impa
            FROM medalhas WHERE aluno_id = ? ORDER BY ano DESC, competicao""", (aluno_id,))
    if not linhas:
        return {"erro": "Aluno não encontrado"}
    resumo = con.execute("SELECT * FROM alunos WHERE id = ?", (aluno_id,)).fetchone()
    xp, uf = resumo[coluna], resumo["uf"]
    total, total_uf = _participantes(con, "alunos", coluna, uf)

    # quem está logo acima no ranking nacional ("próximo alvo")
    alvo = con.execute(f"SELECT id, nome, {coluna} AS xp FROM alunos WHERE {coluna} > ? "
                       f"ORDER BY {coluna}, nome LIMIT 1", (xp,)).fetchone()
    acima = {"id": alvo["id"], "nome": alvo["nome"], "xp": alvo["xp"], "diferenca": alvo["xp"] - xp} if alvo else None

    escolas: list[dict] = []
    for r in linhas:
        if r["escola_chave"] and r["escola_chave"] not in {e["escola_chave"] for e in escolas}:
            escolas.append({"escola": r["escola"], "escola_chave": r["escola_chave"], "municipio": r["municipio"]})
    municipios = sorted({r["municipio"] for r in linhas if r["municipio"]})
    conquistas = gamificacao.conquistas_aluno(linhas)
    premiacoes = []
    for r in linhas:
        r = {k: v for k, v in r.items() if k not in ("escola_chave", "municipio") and v is not None}
        if r.get("premio") == r["medalha"]:
            del r["premio"]          # só vai quando diz algo além da medalha ("Honra ao Mérito")
        if not r["impa"]:
            del r["impa"]
        premiacoes.append(r)

    return {
        "id": aluno_id, "nome": resumo["nome"], "uf": uf, "municipios": municipios, "indexar": bool(resumo["indexar"]),
        "escolas": escolas, "xp": xp, "tier": gamificacao.tier(xp, metodo=metodo), "metodo": metodo,
        # sem pontos no método não há posição (todos os zerados empatariam no fim da lista)
        "rank": resumo[f"{coluna}_pos"] if xp else None, "rank_total": total,
        "rank_uf": resumo[f"{coluna}_pos_uf"] if xp else None, "rank_uf_total": total_uf,
        "pontuacoes": _pontuacoes(resumo),
        "medalhas": gamificacao.contar_medalhas(linhas), "anos": sorted({r["ano"] for r in linhas if r["ano"]}),
        "conquistas": conquistas, "acima": acima, "premiacoes": premiacoes,
    }


MAX_DESTAQUES_ESCOLA = 15


def perfil_escola(con: Conexao, escola_id: str, params: dict) -> dict:
    """Página da escola: outras grafias do nome, posições, medalhas por ano, os MAX_DESTAQUES_ESCOLA alunos que mais
    pontuaram e as conquistas. {"erro": …} se a escola não existe.

    Tudo somado pelo banco: nenhuma premiação é lida uma a uma (uma escola grande tem mais de mil). As premiações
    recentes, que só a página para buscadores mostra, saem de premiacoes_recentes_da_escola."""
    metodo, coluna = pontuacao.resolver_metodo(params.get("metodo"))
    resumo = con.execute("SELECT * FROM escolas WHERE id = ?", (escola_id,)).fetchone() if escola_id else None
    if not resumo:
        return {"erro": "Escola não encontrada"}
    xp, uf = resumo[coluna], resumo["uf"]
    posicao = resumo[f"{coluna}_pos"] if xp else None
    posicao_uf = resumo[f"{coluna}_pos_uf"] if xp else None
    total, total_uf = _participantes(con, "escolas", coluna, uf)

    onde = "escola_chave = ?"
    totais = con.execute(f"""SELECT COUNT(*) AS total, COUNT(DISTINCT aluno_id) AS alunos, SUM(medalha='Ouro') AS ouro,
                                    SUM(medalha='Prata') AS prata, SUM(medalha='Bronze') AS bronze,
                                    SUM(medalha='Menção Honrosa') AS mencao
                             FROM medalhas WHERE {onde}""", (escola_id,)).fetchone()
    medalhas = {m: totais[m] or 0 for m in ("ouro", "prata", "bronze", "mencao")}
    medalhas["outros"] = totais["total"] - sum(medalhas.values())
    grafias = [r[0] for r in con.execute(
        f"SELECT escola FROM medalhas WHERE {onde} GROUP BY escola ORDER BY COUNT(*) DESC", (escola_id,))]
    serie = [{"ano": r[0], "Ouro": r[1], "Prata": r[2], "Bronze": r[3], "Menção Honrosa": r[4]} for r in con.execute(
        f"""SELECT ano, SUM(medalha='Ouro'), SUM(medalha='Prata'), SUM(medalha='Bronze'),
                   SUM(medalha='Menção Honrosa') FROM medalhas WHERE {onde} AND ano IS NOT NULL
            GROUP BY ano ORDER BY ano""", (escola_id,))]
    olimpiadas = [{"sigla": r[0], "total": r[1]} for r in con.execute(
        f"SELECT competicao, COUNT(*) AS n FROM medalhas WHERE {onde} GROUP BY competicao ORDER BY n DESC, competicao",
        (escola_id,))]
    destaques = [{**r, "anos": sorted(int(a) for a in r["anos"].split(","))} for r in con.linhas(
        f"""SELECT m.aluno_id AS id, a.nome, SUM(m.{coluna}) AS xp, SUM(m.medalha='Ouro') AS ouro,
                   SUM(m.medalha='Prata') AS prata, SUM(m.medalha='Bronze') AS bronze,
                   SUM(m.medalha='Menção Honrosa') AS mencao, GROUP_CONCAT(DISTINCT m.ano) AS anos
            FROM medalhas m JOIN alunos a ON a.id = m.aluno_id WHERE m.{onde}
            GROUP BY m.aluno_id ORDER BY xp DESC, a.nome LIMIT ?""", (escola_id, MAX_DESTAQUES_ESCOLA))]
    grand_slam = con.execute(
        f"""SELECT 1 FROM medalhas WHERE {onde} AND medalha = 'Ouro' AND nivel IN ('1', '2', '3')
            GROUP BY ano HAVING COUNT(DISTINCT nivel) = 3 LIMIT 1""", (escola_id,)).fetchone() is not None
    anos = [r["ano"] for r in serie]

    return {
        "id": escola_id, "nome": resumo["nome"], "variantes": [n for n in grafias if n != resumo["nome"]],
        "indexar": bool(resumo["indexar"]),
        "municipio": resumo["municipio"], "uf": uf,
        "rede": resumo["rede"], "esfera": resumo["esfera"], "xp": xp, "metodo": metodo,
        "tier": gamificacao.tier(xp, escola=True, metodo=metodo),
        "rank": posicao, "rank_total": total, "rank_uf": posicao_uf, "rank_uf_total": total_uf,
        "pontuacoes": _pontuacoes(resumo), "medalhas": medalhas, "alunos": totais["alunos"],
        "anos": anos, "serie": serie, "olimpiadas": olimpiadas, "top_alunos": destaques,
        "conquistas": gamificacao.conquistas_escola_por_totais(totais["total"], medalhas["ouro"], totais["alunos"],
                                                               set(anos), grand_slam, posicao, posicao_uf),
    }


def premiacoes_recentes_da_escola(con: Conexao, escola_id: str, limite: int) -> list[dict]:
    """As premiações mais recentes da escola (ano, olimpíada, prêmio, nível, aluno), para a página que os
    buscadores leem."""
    return con.linhas("""SELECT ano, competicao, premio, medalha, nivel, nome FROM medalhas WHERE escola_chave = ?
                         ORDER BY ano DESC, nome LIMIT ?""", (escola_id, limite))


# ---------------------------------------------------------------- cidades

def perfil_cidade(con: Conexao, cidade_id: str, params: dict) -> dict:
    """Resumo de uma cidade (id MUNICIPIO|UF): premiações conquistadas por alunos de escolas de lá.

    Totais, nome e posições vêm da tabela-resumo cidades; o banco só soma, na hora, as medalhas por ano e por
    olimpíada da cidade. Nenhuma premiação é lida uma a uma."""
    metodo, coluna = pontuacao.resolver_metodo(params.get("metodo"))
    resumo = con.execute("SELECT * FROM cidades WHERE id = ?", (cidade_id,)).fetchone()
    if not resumo:
        return {"erro": "Cidade não encontrada"}
    municipio, _, uf = cidade_id.rpartition("|")
    onde, args = "municipio_busca = ? AND uf = ?", (municipio, uf)
    serie = [{"ano": r[0], "Ouro": r[1], "Prata": r[2], "Bronze": r[3], "Menção Honrosa": r[4]} for r in con.execute(
        f"""SELECT ano, SUM(medalha='Ouro'), SUM(medalha='Prata'), SUM(medalha='Bronze'),
                   SUM(medalha='Menção Honrosa') FROM medalhas WHERE {onde} AND ano IS NOT NULL
            GROUP BY ano ORDER BY ano""", args)]
    olimpiadas = [{"sigla": r[0], "total": r[1]} for r in con.execute(
        f"SELECT competicao, COUNT(*) AS n FROM medalhas WHERE {onde} GROUP BY competicao ORDER BY n DESC, competicao",
        args)]
    posicao, total_nacional = consultas_ranking.posicao(con, {"tipo": "cidades", "metodo": metodo}, cidade_id)
    posicao_uf, total_uf = consultas_ranking.posicao(con, {"tipo": "cidades", "metodo": metodo, "uf": uf}, cidade_id)
    medalhas = {m: resumo[m] or 0 for m in ("ouro", "prata", "bronze", "mencao")}
    medalhas["outros"] = resumo["total"] - sum(medalhas.values())
    recorte = {"municipio": municipio, "uf": uf, "metodo": metodo, "limite": 10}
    return {
        "id": cidade_id, "nome": resumo["nome"], "uf": uf, "metodo": metodo, "xp": resumo[coluna] or 0,
        "pontuacoes": {m: resumo[c["coluna"]] or 0 for m, c in pontuacao.METODOS.items()},
        "rank": posicao, "rank_total": total_nacional, "rank_uf": posicao_uf, "rank_uf_total": total_uf,
        "medalhas": medalhas, "total": resumo["total"], "alunos": resumo["alunos"], "escolas": resumo["escolas"],
        "anos": [r["ano"] for r in serie], "serie": serie, "olimpiadas": olimpiadas,
        "top_escolas": ranking(con, {**recorte, "tipo": "escolas"})["itens"],
        "top_alunos": ranking(con, {**recorte, "tipo": "alunos"})["itens"],
    }


# ---------------------------------------------------------------- endereços das páginas

def enderecos(con: Conexao) -> EnderecosDaBase:
    """Endereços legíveis das páginas de aluno, escola e cidade, consultados na base um por vez (calculados na
    geração: gravacao.gravar_enderecos)."""
    return EnderecosDaBase(con)


# ---------------------------------------------------------------- visão geral (página inicial)

_ORDEM_NIVEL = {"1": 1, "2": 2, "3": 3, "Universitário": 9}


def _visao_geral_fixa(con: Conexao) -> dict:
    """Parte da visão geral que não depende do método escolhido."""
    totais = dict(con.execute(f"SELECT {AGREGADOS} FROM medalhas").fetchone())
    totais["alunos"] = con.execute("SELECT COUNT(*) FROM alunos").fetchone()[0]
    totais["escolas"] = con.execute("SELECT COUNT(*) FROM escolas").fetchone()[0]
    # gráfico "Medalhas por ano": [ano, olimpíada, ouro, prata, bronze, menção] por linha, sem repetir os nomes dos
    # campos (é a maior parte da resposta); sem as linhas só de prêmios fora dessas quatro categorias
    serie = [list(r) for r in con.execute(
        """SELECT ano, competicao, SUM(medalha='Ouro'), SUM(medalha='Prata'), SUM(medalha='Bronze'),
                  SUM(medalha='Menção Honrosa') AS mencao FROM medalhas GROUP BY ano, competicao
           HAVING SUM(medalha IN ('Ouro', 'Prata', 'Bronze', 'Menção Honrosa')) > 0 ORDER BY ano""")]
    # do catálogo, só o que as telas usam: filtros, tabela de pontos (Sobre) e níveis do edital
    usados = ("sigla", "nome", "area", "pontos", "pontos_site", "pontos_site_outros", "impa_niveis")
    olimpiadas = [{k: o[k] for k in usados} for o in pontuacao.catalogo()]
    niveis = [{"id": r[0], "n": r[1], "competicoes": r[2].split(",")} for r in con.execute(
        """SELECT nivel, COUNT(*), GROUP_CONCAT(DISTINCT competicao) FROM medalhas
           WHERE nivel IS NOT NULL GROUP BY nivel""")]
    niveis.sort(key=lambda n: (_ORDEM_NIVEL.get(n["id"], 5), n["id"]))
    meta = dict(con.execute("SELECT chave, valor FROM meta").fetchall())
    return {
        "totais": totais, "serie": serie,
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
    """Página inicial: a parte fixa mais os totais em pontos e os destaques (10 alunos, 10 escolas, estados)
    no método pedido. Tudo calculado uma vez por versão da base, fora do limite do cache."""
    metodo, coluna = pontuacao.resolver_metodo(params.get("metodo"))
    dados = dict(con.fixo("visao_geral", lambda: _visao_geral_fixa(con)))
    dados["totais"] = com_pontos(dict(dados["totais"]), coluna)
    dados["metodo"] = metodo
    p = {"metodo": metodo}
    destaques = (("top_alunos", "alunos", 10), ("top_escolas", "escolas", 10), ("estados", "estados", 30))
    for chave, tipo, limite in destaques:
        extras = ("competicoes",) if tipo == "alunos" else ()   # o início mostra as olimpíadas de cada aluno
        dados[chave] = con.fixo((chave, metodo), lambda t=tipo, n=limite, e=extras:
                                ranking(con, {**p, "tipo": t, "limite": n}, e)["itens"])
    return dados
