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

# Critério de cada ordenação (o mesmo de dominio.ranking.ORDENACOES), sobre as colunas da consulta
_CRITERIO = {
    "xp": "xp DESC, ouro DESC, prata DESC, bronze DESC",
    "medalhas": "ouro DESC, prata DESC, bronze DESC, xp DESC",
    "total": "(ouro + prata + bronze) DESC, xp DESC",
}
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


def _recorte(params: dict) -> tuple[dict, str, str, dict]:
    """(parâmetros com as restrições do método, método, coluna de pontos, filtros reconhecidos).

    No IMPA edital entram os níveis aceitos e so_edital: o nível "3" também existe fora do edital (Itabirana)."""
    metodo, coluna = pontuacao.resolver_metodo(params.get("metodo"))
    params = {**params, "nivel": pontuacao.restringir_niveis(metodo, params.get("nivel")),
              "so_edital": "1" if metodo == "impa3" else None}
    return params, metodo, coluna, {k: params[k] for k in CHAVES_FILTRO if params.get(k)}


def _base(tipo: str, coluna: str, filtros: dict, carreira: bool, contagens: bool = True) -> tuple[str, list]:
    """SELECT de um item por aluno, escola, cidade ou estado, com todas as colunas que algum uso pode pedir.

    Sem filtros, alunos, escolas e cidades vêm das tabelas-resumo (pontos e contagens prontos). Com filtros, as
    premiações do recorte são somadas; nome, UF, escola e cidade vêm do resumo (os do perfil, não os de uma
    premiação qualquer). carreira: acrescenta os pontos da carreira inteira, que decidem o nível (tier) mostrado.
    contagens=False: sem alunos e escolas distintos de cada cidade ou estado (a parte cara), quando só a posição
    importa."""
    if tipo in _EXTRA_DO_RESUMO and not filtros:
        return (f"""SELECT id, nome, uf, {_EXTRA_DO_RESUMO[tipo]}, {coluna} AS xp, {coluna} AS carreira, ouro, prata,
                           bronze, mencao, total, p_impa, p_impa3, p_site, de, ate FROM {tipo}""", [])
    where, args = condicoes(filtros)
    soma = f"""SUM(medalha='Ouro') AS ouro, SUM(medalha='Prata') AS prata, SUM(medalha='Bronze') AS bronze,
               SUM(medalha='Menção Honrosa') AS mencao, COUNT(*) AS total, SUM({coluna}) AS xp,
               SUM(p_impa) AS p_impa, SUM(p_impa3) AS p_impa3, SUM(p_site) AS p_site, MIN(ano) AS de, MAX(ano) AS ate"""
    # "GROUP BY x || ''" impede o SQLite de usar o índice de x: quando o recorte cobre quase a base toda, uma
    # varredura sequencial é bem mais rápida que milhares de saltos pelo índice
    if tipo == "alunos":
        car = f", a.{coluna} AS carreira" if carreira else ""
        return (f"""SELECT g.*, a.nome, a.uf, a.escola, a.municipio{car} FROM (
                        SELECT aluno_id AS id, {soma} FROM medalhas WHERE {' AND '.join(where) or '1'}
                        GROUP BY aluno_id || '') g JOIN alunos a ON a.id = g.id""", args)
    if tipo == "escolas":
        car = f", e.{coluna} AS carreira" if carreira else ""
        return (f"""SELECT g.*, e.nome, e.municipio, e.uf, e.rede{car} FROM (
                        SELECT escola_chave AS id, COUNT(DISTINCT aluno_id) AS alunos, {soma} FROM medalhas
                        WHERE {' AND '.join([*where, "escola_chave != ''"])} GROUP BY escola_chave || '') g
                    JOIN escolas e ON e.id = g.id""", args)
    if tipo == "cidades":   # id = MUNICIPIO|UF sem acento; o nome de exibição é o do resumo
        distintos = ("COUNT(DISTINCT aluno_id) AS alunos, COUNT(DISTINCT NULLIF(escola_chave, '')) AS escolas,"
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
    return (f"""SELECT uf AS id, uf AS nome, COUNT(DISTINCT aluno_id) AS alunos,
                       COUNT(DISTINCT NULLIF(escola_chave, '')) AS escolas, {soma}
                FROM medalhas WHERE {' AND '.join([*where, "uf IS NOT NULL"])} GROUP BY uf || ''""", args)


def _consulta(tipo: str, ordem: str, coluna: str, filtros: dict, carreira: bool,
              contagens: bool = True) -> tuple[str, list]:
    """A base numerada: posição (RANK pelo critério) e total de itens, em ordem de exibição."""
    criterio = _CRITERIO[ordem]
    if tipo in _EXTRA_DO_RESUMO and not filtros and ordem == "xp":
        # o ranking que todo mundo abre: as posições já estão gravadas no resumo (ranking.preencher_posicoes, mesmo
        # critério) e o índice por pontos entrega a página sem ordenar a tabela inteira
        extra = _EXTRA_DO_RESUMO[tipo]
        return (f"""SELECT id, nome, uf, {extra}, {coluna} AS xp, {coluna} AS carreira, ouro, prata, bronze, mencao,
                           total, p_impa, p_impa3, p_site, de, ate, {coluna}_pos AS pos,
                           (SELECT COUNT(*) FROM {tipo} WHERE {coluna} > 0) AS _total
                    FROM {tipo} WHERE {coluna} > 0
                    ORDER BY {coluna} DESC, ouro DESC, prata DESC, bronze DESC, nome, id""",
                [])
    base, args = _base(tipo, coluna, filtros, carreira, contagens)
    so_quem_pontua = "WHERE xp > 0" if ordem == "xp" else ""   # no ranking por pontos, quem não pontua fica de fora
    return (f"""SELECT *, RANK() OVER (ORDER BY {criterio}) AS pos, COUNT(*) OVER () AS _total
                FROM ({base}) {so_quem_pontua} ORDER BY {criterio}, nome, id""", args)


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
        # a posição só depende de pontos e medalhas: sem as contagens de alunos e escolas, e o total vem junto
        sql, args = _consulta(tipo, ordem, coluna, filtros, carreira=False, contagens=False)
        achado = con.execute(f"SELECT pos, _total FROM ({sql}) WHERE id = ?", [*args, ident]).fetchone()
        return (achado[0], achado[1]) if achado else (None, _contar(con, tipo, ordem, coluna, filtros))
    return con.em_cache(("posicao", tipo, ordem, metodo, tuple(sorted(filtros.items())), ident), calcular)


__all__ = ["CAMPOS_COMPLETOS", "CAMPOS_DA_TELA", "pagina", "posicao", "todos"]
