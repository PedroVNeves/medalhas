"""Rankings feitos pelo próprio SQLite: o banco agrupa, ordena, numera as posições e devolve só a página pedida,
só com as colunas pedidas. O servidor nunca monta a lista inteira na memória.

O critério de ordem espelha dominio.ranking.ORDENACOES (e as posições gravadas por ranking.preencher_posicoes):
empate em todo o critério divide a posição, como RANK(); o nome desempata só a ordem de exibição.
"""
from collections.abc import Iterator

from ...dominio import gamificacao, pontuacao
from ...dominio.ranking import ORDEM_PADRAO, ORDENACOES, TIPOS, PaginaDoRanking
from .conexao import Conexao
from .filtros import CHAVES_FILTRO, condicoes

# Critério de cada ordenação (o mesmo de dominio.ranking.ORDENACOES), sobre as colunas da consulta: valores que,
# comparados em ordem e todos do maior para o menor, decidem quem vem antes
_VALORES = {
    "xp": ("xp", "ouro", "prata", "bronze"),
    "medalhas": ("ouro", "prata", "bronze", "xp"),
    "total": ("(ouro + prata + bronze)", "xp"),
}
_CRITERIO = {ordem: ", ".join(f"{v} DESC" for v in valores) for ordem, valores in _VALORES.items()}
assert set(_CRITERIO) == set(ORDENACOES)

# O que cada uso mostra, além de id, posição, pontos e as quatro contagens de medalhas
CAMPOS_DA_TELA = {
    "alunos": ("nome", "uf", "escola", "municipio", "de", "ate"),
    "escolas": ("nome", "municipio", "uf", "rede", "alunos"),
    "cidades": ("nome", "uf", "alunos", "escolas"),
    "estados": ("nome", "alunos", "escolas", "total"),   # o mapa colore os estados também pelo total
}
_COMPLETO = ("total", "p_impa", "p_impa3", "p_site", "de", "ate")   # API pública e exportação
CAMPOS_COMPLETOS = {
    "alunos": ("nome", "uf", "escola", "municipio", *_COMPLETO),
    "escolas": ("nome", "municipio", "uf", "rede", "alunos", *_COMPLETO),
    "cidades": ("nome", "uf", "alunos", "escolas", *_COMPLETO),
    "estados": ("nome", "alunos", "escolas", *_COMPLETO),
}
_MEDALHAS = ("ouro", "prata", "bronze", "mencao")
# Tabelas-resumo (gravadas na geração) e as colunas próprias de cada uma, além de id, nome, uf, pontos e medalhas
_EXTRA_DO_RESUMO = {"alunos": "escola, municipio", "escolas": "municipio, rede, alunos", "cidades": "alunos, escolas"}
# Ordem de exibição entre empatados: alfabética. Em alunos, pelo número do aluno (alunos.n), dado em ordem
# alfabética do id na geração: desempata sem consultar o nome de ninguém
_EXIBICAO = {"alunos": "ordem", "escolas": "nome, id", "cidades": "nome, id", "estados": "nome, id"}
# Como as premiações de um item se juntam: (expressão do item, condição para a premiação contar nele). O aluno
# vai pelo número (premiacoes.aluno_n); os demais, pelo próprio id
_CHAVE = {
    "alunos": ("aluno_n", None),
    "escolas": ("escola_chave", "escola_chave != ''"),
    "cidades": ("municipio_busca || '|' || uf", "municipio_busca != '' AND uf IS NOT NULL"),
    "estados": ("uf", "uf IS NOT NULL"),
}
# Rankings com filtros numerados sem RANK() sobre a lista inteira (_pagina_com_filtros): os de muitos itens. Em
# escolas a numeração completa é barata, e a soma pela visão (que a escola exige) deixaria o caminho novo mais lento
_SEM_NUMERAR_TUDO = ("alunos", "cidades")
# Filtros que dependem das tabelas pequenas juntadas pela visão medalhas (área da olimpíada, escola da grafia)
_SO_NA_VISAO = {"area", "escola_chave"}


def _origem(tipo: str, filtros: dict) -> str:
    """Tabela das premiações a somar. A visão medalhas junta grafia, fonte e área a cada linha, mesmo quando a
    consulta não usa nenhuma delas (o dobro do tempo numa soma da base inteira); premiacoes tem o resto."""
    return "medalhas" if tipo == "escolas" or _SO_NA_VISAO & filtros.keys() else "premiacoes"


def _so_estes(tipo: str, ids: list) -> tuple[list[str], list]:
    """Condições que restringem as premiações às dos itens dados (alunos: pelo número), por um caminho indexado."""
    chave, _ = _CHAVE[tipo]
    marcas = ", ".join("?" * len(ids))
    if tipo != "cidades":
        return [f"{chave} IN ({marcas})"], list(ids)
    municipios = sorted({i.rsplit("|", 1)[0] for i in ids})   # pelo índice de municipio_busca, depois o id inteiro
    return ([f"municipio_busca IN ({', '.join('?' * len(municipios))})", f"{chave} IN ({marcas})"],
            [*municipios, *ids])


def _recorte(params: dict) -> tuple[dict, str, str, dict]:
    """(parâmetros com as restrições do método, método, coluna de pontos, filtros reconhecidos).

    No IMPA edital entram os níveis aceitos e so_edital: o nível "3" também existe fora do edital (Itabirana)."""
    metodo, coluna = pontuacao.resolver_metodo(params.get("metodo"))
    params = {**params, "nivel": pontuacao.restringir_niveis(metodo, params.get("nivel")),
              "so_edital": "1" if metodo == "impa3" else None}
    return params, metodo, coluna, {k: params[k] for k in CHAVES_FILTRO if params.get(k)}


def _base(tipo: str, coluna: str, filtros: dict, carreira: bool, contagens: bool = True,
          ids: list[str] | None = None) -> tuple[str, list]:
    """SELECT de um item por aluno, escola, cidade ou estado, com todas as colunas que algum uso pode pedir.

    Sem filtros, alunos, escolas e cidades vêm das tabelas-resumo (pontos e contagens prontos). Com filtros, as
    premiações do recorte são somadas; nome, UF, escola e cidade vêm do resumo (os do perfil, não os de uma
    premiação qualquer). carreira: acrescenta os pontos da carreira inteira, que decidem o nível (tier) mostrado.
    contagens=False: sem alunos e escolas distintos de cada cidade ou estado (a parte cara), quando só a posição
    importa. ids: só esses itens (os campos de uma página já escolhida)."""
    if tipo in _EXTRA_DO_RESUMO and not filtros:
        ordem = ", n AS ordem" if tipo == "alunos" else ""
        return (f"""SELECT id, nome, uf, {_EXTRA_DO_RESUMO[tipo]}, {coluna} AS xp, {coluna} AS carreira, ouro, prata,
                           bronze, mencao, total, p_impa, p_impa3, p_site, de, ate{ordem} FROM {tipo}""", [])
    where, args = condicoes(filtros)
    if ids is not None:
        w, a = _so_estes(tipo, ids)
        where, args = [*where, *w], [*args, *a]
    soma = f"""SUM(medalha='Ouro') AS ouro, SUM(medalha='Prata') AS prata, SUM(medalha='Bronze') AS bronze,
               SUM(medalha='Menção Honrosa') AS mencao, COUNT(*) AS total, SUM({coluna}) AS xp,
               SUM(p_impa) AS p_impa, SUM(p_impa3) AS p_impa3, SUM(p_site) AS p_site, MIN(ano) AS de, MAX(ano) AS ate"""
    # "GROUP BY x || ''" impede o SQLite de usar o índice de x: quando o recorte cobre quase a base toda, uma
    # varredura sequencial é bem mais rápida que milhares de saltos pelo índice
    if tipo == "alunos":
        car = f", a.{coluna} AS carreira" if carreira else ""
        return (f"""SELECT g.*, a.id, a.nome, a.uf, a.escola, a.municipio, a.n AS ordem{car} FROM (
                        SELECT aluno_n, {soma} FROM medalhas WHERE {' AND '.join(where) or '1'}
                        GROUP BY aluno_n || '') g JOIN alunos a ON a.n = g.aluno_n""", args)
    if tipo == "escolas":
        car = f", e.{coluna} AS carreira" if carreira else ""
        return (f"""SELECT g.*, e.nome, e.municipio, e.uf, e.rede{car} FROM (
                        SELECT escola_chave AS id, COUNT(DISTINCT aluno_n) AS alunos, {soma} FROM medalhas
                        WHERE {' AND '.join([*where, "escola_chave != ''"])} GROUP BY escola_chave || '') g
                    JOIN escolas e ON e.id = g.id""", args)
    if tipo == "cidades":   # id = MUNICIPIO|UF sem acento; o nome de exibição é o do resumo
        distintos = ("COUNT(DISTINCT aluno_n) AS alunos, COUNT(DISTINCT NULLIF(escola_chave, '')) AS escolas,"
                     if contagens else "")
        return (f"""SELECT g.*, c.nome FROM (
                        SELECT municipio_busca || '|' || uf AS id, uf, {distintos} {soma} FROM medalhas
                        WHERE {' AND '.join([*where, "municipio_busca != ''", "uf IS NOT NULL"])}
                        GROUP BY municipio_busca, uf) g JOIN cidades c ON c.id = g.id""", args)
    if not filtros:   # estados sem filtro: quantos alunos e escolas têm o perfil no estado
        return (f"""SELECT g.*, (SELECT COUNT(*) FROM alunos a WHERE a.uf = g.id) AS alunos,
                           (SELECT COUNT(*) FROM escolas e WHERE e.uf = g.id) AS escolas FROM (
                        SELECT uf AS id, uf AS nome, {soma} FROM medalhas WHERE uf IS NOT NULL GROUP BY uf || '') g""",
                [])
    return (f"""SELECT uf AS id, uf AS nome, COUNT(DISTINCT aluno_n) AS alunos,
                       COUNT(DISTINCT NULLIF(escola_chave, '')) AS escolas, {soma}
                FROM medalhas WHERE {' AND '.join([*where, "uf IS NOT NULL"])} GROUP BY uf || ''""", args)


def _consulta(tipo: str, ordem: str, coluna: str, filtros: dict, carreira: bool,
              contagens: bool = True) -> tuple[str, list]:
    """A base numerada: posição (RANK pelo critério) e total de itens, em ordem de exibição."""
    criterio = _CRITERIO[ordem]
    if tipo in _EXTRA_DO_RESUMO and not filtros and ordem == "xp":
        # o ranking que todo mundo abre: as posições já estão gravadas no resumo (ranking.preencher_posicoes, mesmo
        # critério) e o índice por pontos entrega a página sem ordenar a tabela inteira
        extra = _EXTRA_DO_RESUMO[tipo] + (", n AS ordem" if tipo == "alunos" else "")
        return (f"""SELECT id, nome, uf, {extra}, {coluna} AS xp, {coluna} AS carreira, ouro, prata, bronze, mencao,
                           total, p_impa, p_impa3, p_site, de, ate, {coluna}_pos AS pos,
                           (SELECT COUNT(*) FROM {tipo} WHERE {coluna} > 0) AS _total
                    FROM {tipo} WHERE {coluna} > 0
                    ORDER BY {coluna} DESC, ouro DESC, prata DESC, bronze DESC, {_EXIBICAO[tipo]}""",
                [])
    base, args = _base(tipo, coluna, filtros, carreira, contagens)
    so_quem_pontua = "WHERE xp > 0" if ordem == "xp" else ""   # no ranking por pontos, quem não pontua fica de fora
    return (f"""SELECT *, RANK() OVER (ORDER BY {criterio}) AS pos, COUNT(*) OVER () AS _total
                FROM ({base}) {so_quem_pontua} ORDER BY {criterio}, {_EXIBICAO[tipo]}""", args)


def _estreito(tipo: str, coluna: str, filtros: dict, ids: list[str] | None = None) -> tuple[str, list]:
    """Só o que ordena, uma linha por item do recorte: id, pontos e as quatro contagens de medalhas."""
    chave, so_quem_conta = _CHAVE[tipo]
    where, args = condicoes(filtros)
    if so_quem_conta:
        where.append(so_quem_conta)
    if ids is not None:
        w, a = _so_estes(tipo, ids)
        where, args = [*where, *w], [*args, *a]
    # "GROUP BY x || ''": agrupar ordenando é mais rápido que saltar pelo índice de x quando o recorte é grande
    return (f"""SELECT {chave} AS id, SUM({coluna}) AS xp, SUM(medalha='Ouro') AS ouro, SUM(medalha='Prata') AS prata,
                       SUM(medalha='Bronze') AS bronze, SUM(medalha='Menção Honrosa') AS mencao
                FROM {_origem(tipo, filtros)} WHERE {' AND '.join(where) or '1'} GROUP BY {chave} || ''""", args)


def _contagens(con: Conexao, tipo: str, ordem: str, coluna: str, filtros: dict,
               valores: tuple | None = None) -> tuple[int, int]:
    """(itens no ranking com filtros, quantos vêm estritamente antes de quem tem estes valores do critério), numa
    passada só. A posição de quem tem os valores é esse segundo número + 1, como RANK(); quem vem antes pontua
    mais, então no ranking por pontos também pontua."""
    sql, args = _estreito(tipo, coluna, filtros)
    exprs = _VALORES[ordem]
    antes, vargs = ((f"({', '.join(exprs)}) > ({', '.join('?' * len(exprs))})", list(valores)) if valores
                    else ("0", []))
    total, a_frente = con.execute(f"""SELECT COUNT(*), TOTAL({antes}) FROM ({sql})
                                      {'WHERE xp > 0' if ordem == 'xp' else ''}""", [*vargs, *args]).fetchone()
    return total, int(a_frente)


def _valores(linha, ordem: str) -> tuple:
    """Os valores do critério de uma linha, na ordem de _VALORES."""
    v = {"xp": linha["xp"], "ouro": linha["ouro"], "prata": linha["prata"], "bronze": linha["bronze"]}
    v["(ouro + prata + bronze)"] = v["ouro"] + v["prata"] + v["bronze"]
    return tuple(v[e] for e in _VALORES[ordem])


def _pagina_com_filtros(con: Conexao, tipo: str, ordem: str, coluna: str, filtros: dict, offset: int, limite: int,
                        carreira: bool, contagens: bool) -> tuple[int, list]:
    """(total, linhas da página com posição) sem numerar o ranking inteiro.

    O banco soma só o que ordena e devolve a página (com a linha anterior a ela). As posições saem da ordem: a 1ª
    linha da página divide a posição com a anterior só num empate, e aí conta-se quem vem antes dela; nas demais,
    empate com a de cima repete a posição, senão a posição é o lugar na lista. Os outros campos são somados
    depois, só para os itens da página."""
    sql, args = _estreito(tipo, coluna, filtros)
    # a ordem alfabética entre empatados: o nome da cidade vem do resumo; o aluno já vem pelo número, que a segue
    junta = f"JOIN {tipo} r ON r.id = g.id" if tipo == "cidades" else ""
    nome = "r.nome" if junta else "g.id"
    so_quem_pontua = "WHERE xp > 0" if ordem == "xp" else ""
    antes = 1 if offset > 0 else 0
    linhas = con.execute(f"""SELECT * FROM (SELECT g.*, {nome} AS nome FROM ({sql}) g {junta}) {so_quem_pontua}
                             ORDER BY {_CRITERIO[ordem]}, nome, id LIMIT ? OFFSET ?""",
                         [*args, limite + antes, offset - antes]).fetchall()
    anterior, linhas = (linhas[0] if antes and linhas else None), linhas[antes:]
    # a 1ª linha empatada com a de antes da página: a contagem de quem vem antes sai junto com o total
    empate = bool(linhas) and anterior is not None and _valores(anterior, ordem) == _valores(linhas[0], ordem)
    total, a_frente = _contagens(con, tipo, ordem, coluna, filtros, _valores(linhas[0], ordem) if empate else None)
    if not linhas:
        return total, []
    posicoes = [1 + a_frente if empate else offset + 1]
    for i in range(1, len(linhas)):
        empatada = _valores(linhas[i - 1], ordem) == _valores(linhas[i], ordem)
        posicoes.append(posicoes[-1] if empatada else offset + i + 1)
    chaves = [r["id"] for r in linhas]   # alunos: os números
    campos, cargs = _base(tipo, coluna, filtros, carreira, contagens, ids=chaves)
    de_cada = {r["aluno_n" if tipo == "alunos" else "id"]: dict(r) for r in con.execute(campos, cargs)}
    return total, [{**de_cada[k], "pos": p} for k, p in zip(chaves, posicoes)]


def _itens(con: Conexao, linhas: list, tipo: str, campos: tuple[str, ...], metodo: str, carreira: bool) -> list[dict]:
    """As linhas da página só com os campos pedidos (e o nível, quando a tela o mostra)."""
    itens = []
    for r in linhas:
        item = {"id": r["id"], "pos": r["pos"], "xp": r["xp"] or 0, **{m: r[m] or 0 for m in _MEDALHAS},
                **{c: r[c] for c in campos}}
        if carreira:   # só o que a tela usa do nível: nome e cor
            nivel = gamificacao.tier(r["carreira"], escola=tipo == "escolas", metodo=metodo)
            item["tier"] = {"nome": nivel["nome"], "cor": nivel["cor"]}
        itens.append(item)
    return itens


def pagina(con: Conexao, params: dict, offset: int = 0, limite: int = 50, campos: dict | None = None,
           extras: tuple[str, ...] = ()) -> PaginaDoRanking:
    """Uma página do ranking: posição e total calculados pelo banco, que só devolve as linhas da página.

    campos: CAMPOS_DA_TELA (padrão) ou CAMPOS_COMPLETOS; extras: colunas a mais (ex.: "competicoes" no início).
    A tela recebe o nível (tier) de alunos e escolas, sempre o da carreira inteira, mesmo com filtros."""
    params, metodo, coluna, filtros = _recorte(params)
    tipo = params.get("tipo") if params.get("tipo") in TIPOS else "alunos"
    ordem = params.get("ordem") if params.get("ordem") in ORDENACOES else ORDEM_PADRAO
    escolhidos = tuple(dict.fromkeys((*(campos or CAMPOS_DA_TELA)[tipo], *extras)))
    carreira = campos is None and tipo in ("alunos", "escolas")

    def calcular() -> tuple[int, list[dict]]:
        if tipo in _SEM_NUMERAR_TUDO and filtros:
            total, linhas = _pagina_com_filtros(con, tipo, ordem, coluna, filtros, offset, limite, carreira, True)
        else:
            sql, args = _consulta(tipo, ordem, coluna, filtros, carreira)
            linhas = con.execute(f"{sql} LIMIT ? OFFSET ?", [*args, limite, offset]).fetchall()
            total = linhas[0]["_total"] if linhas else _contar(con, tipo, ordem, coluna, filtros)
        olimpiadas = "competicoes" in escolhidos and tipo == "alunos"
        itens = _itens(con, linhas, tipo, tuple(c for c in escolhidos if c != "competicoes"), metodo, carreira)
        if olimpiadas and itens:   # só o início mostra: vem do resumo, só para os alunos da página
            ids = [i["id"] for i in itens]
            de_cada = dict(con.execute(f"SELECT id, competicoes FROM alunos WHERE id IN ({', '.join('?' * len(ids))})",
                                       ids).fetchall())
            for i in itens:
                i["competicoes"] = de_cada.get(i["id"])
        return total, itens

    chave = ("ranking", tipo, ordem, metodo, tuple(sorted(filtros.items())), offset, limite, escolhidos)
    total, itens = con.em_cache(chave, calcular)
    return PaginaDoRanking(tipo, ordem, metodo, coluna, params.get("nivel"), total, itens)


def _contar(con: Conexao, tipo: str, ordem: str, coluna: str, filtros: dict) -> int:
    """Quantos itens o ranking tem (para a página vazia, depois do fim)."""
    base, args = _base(tipo, coluna, filtros, carreira=False, contagens=False)
    return con.execute(f"SELECT COUNT(*) FROM ({base}) {'WHERE xp > 0' if ordem == 'xp' else ''}", args).fetchone()[0]


def todos(con: Conexao, params: dict) -> tuple[PaginaDoRanking, Iterator[dict]]:
    """O ranking inteiro em fluxo, com os campos completos (exportação): as linhas saem do banco uma a uma."""
    params, metodo, coluna, filtros = _recorte(params)
    tipo = params.get("tipo") if params.get("tipo") in TIPOS else "alunos"
    ordem = params.get("ordem") if params.get("ordem") in ORDENACOES else ORDEM_PADRAO
    campos = CAMPOS_COMPLETOS[tipo]
    sql, args = _consulta(tipo, ordem, coluna, filtros, carreira=False)
    info = PaginaDoRanking(tipo, ordem, metodo, coluna, params.get("nivel"), None, [])

    def linhas() -> Iterator[dict]:
        for r in con.execute(sql, args):
            yield from _itens(con, [r], tipo, campos, metodo, carreira=False)
    return info, linhas()


def posicao(con: Conexao, params: dict, ident: str) -> tuple[int | None, int]:
    """(posição do item no ranking, total de itens): o banco ordena tudo, mas só devolve uma linha.

    Sem filtros de quem pede (só o método e, em cidades, o estado), a posição já está gravada no resumo
    ({coluna}_pos e _pos_uf, mesmo critério): basta ler a linha. Uma cidade tem todas as premiações no estado
    dela, então a posição estadual gravada é a mesma do ranking filtrado por UF."""
    pedidos = {k for k in CHAVES_FILTRO if params.get(k)}
    params, metodo, coluna, filtros = _recorte(params)
    tipo = params.get("tipo") if params.get("tipo") in TIPOS else "alunos"
    ordem = params.get("ordem") if params.get("ordem") in ORDENACOES else ORDEM_PADRAO
    if tipo in _EXTRA_DO_RESUMO and ordem == "xp" and pedidos <= ({"uf"} if tipo == "cidades" else set()):
        uf = filtros.get("uf")
        linha = con.execute(f"SELECT {coluna}, {coluna}_pos, {coluna}_pos_uf, uf FROM {tipo} WHERE id = ?",
                            (ident,)).fetchone()
        so_uf, args = ("AND uf = ?", (uf,)) if uf else ("", ())
        total = con.execute(f"SELECT COUNT(*) FROM {tipo} WHERE {coluna} > 0 {so_uf}", args).fetchone()[0]
        if not linha or not linha[0] or (uf and linha[3] != uf):
            return None, total
        return (linha[2] if uf else linha[1]), total

    def calcular() -> tuple[int | None, int]:
        if tipo in _SEM_NUMERAR_TUDO and filtros:   # os valores do item e quantos vêm antes dele
            chave = ident
            if tipo == "alunos":
                achado = con.execute("SELECT n FROM alunos WHERE id = ?", (ident,)).fetchone()
                chave = achado[0] if achado else None
            sql, args = _estreito(tipo, coluna, filtros, ids=[chave])
            linha = con.execute(sql, args).fetchone()
            if not linha or (ordem == "xp" and not linha["xp"]):
                return None, _contagens(con, tipo, ordem, coluna, filtros)[0]
            total, a_frente = _contagens(con, tipo, ordem, coluna, filtros, _valores(linha, ordem))
            return 1 + a_frente, total
        # a posição só depende de pontos e medalhas: sem as contagens de alunos e escolas, e o total vem junto
        sql, args = _consulta(tipo, ordem, coluna, filtros, carreira=False, contagens=False)
        achado = con.execute(f"SELECT pos, _total FROM ({sql}) WHERE id = ?", [*args, ident]).fetchone()
        return (achado[0], achado[1]) if achado else (None, _contar(con, tipo, ordem, coluna, filtros))
    return con.em_cache(("posicao", tipo, ordem, metodo, tuple(sorted(filtros.items())), ident), calcular)


__all__ = ["CAMPOS_COMPLETOS", "CAMPOS_DA_TELA", "pagina", "posicao", "todos"]
