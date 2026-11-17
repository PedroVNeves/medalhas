"""Gamificação: níveis (tiers) e conquistas de alunos e escolas."""
from collections import Counter

from .pontuacao import METODO_PADRAO
from .premiacao import BRONZE, MEDALHAS, MENCAO, OURO, PRATA

_PESO_MEDALHA = {BRONZE: 1, PRATA: 2, OURO: 3}

# Os nomes evitam "ouro/prata/bronze" para não confundir com as medalhas.
TIER_NOMES = ["Estreante", "Promessa", "Talento", "Destaque", "Elite", "Mestre", "Lenda"]
TIER_CORES = ["#8b93a7", "#4bbf7f", "#5ea8ff", "#b57bff", "#5ee0d0", "#f5c542", "#ff6bd6"]

# Pontos mínimos de cada tier, por método. Calibrados na distribuição real
# (Mestre ≈ top 40 do Brasil, Lenda ≈ top 5–10).
LIMITES_TIER = {
    "impa": {"aluno": [0, 6, 18, 36, 72, 120, 170], "escola": [0, 20, 60, 150, 400, 1200, 3000]},
    "impa3": {"aluno": [0, 2, 6, 18, 36, 54, 80], "escola": [0, 6, 20, 60, 150, 600, 1300]},
    "site": {"aluno": [0, 60, 150, 300, 600, 1300, 1900], "escola": [0, 150, 500, 1500, 5000, 15000, 40000]},
}
_ANO_SEM_OBMEP = 2020   # a sequência 2019 -> 2021 conta como consecutiva


def tiers(metodo: str, escola: bool = False) -> list[tuple[str, int, str]]:
    """[(nome, pontos mínimos, cor)] do método."""
    limites = LIMITES_TIER.get(metodo, LIMITES_TIER[METODO_PADRAO])["escola" if escola else "aluno"]
    return list(zip(TIER_NOMES, limites, TIER_CORES))


def tier(xp: int | None, escola: bool = False, metodo: str = METODO_PADRAO) -> dict:
    """Tier atual, o próximo e o progresso até ele."""
    escada = tiers(metodo, escola)
    xp = xp or 0
    i = max(i for i, (_, minimo, _) in enumerate(escada) if xp >= minimo)
    nome, minimo, cor = escada[i]
    proximo = escada[i + 1] if i + 1 < len(escada) else None
    progresso = 1.0 if not proximo else (xp - minimo) / (proximo[1] - minimo)
    return {
        "nome": nome, "cor": cor, "nivel": i + 1, "min": minimo, "xp": xp,
        "proximo": proximo[0] if proximo else None, "proximo_xp": proximo[1] if proximo else None,
        "falta": (proximo[1] - xp) if proximo else 0, "progresso": round(progresso, 4),
    }


def maior_sequencia(anos: set[int]) -> int:
    """Maior sequência de anos consecutivos premiados."""
    melhor = atual = 0
    anterior = None
    for a in sorted(anos):
        consecutivo = anterior is not None and (a == anterior + 1 or (anterior == _ANO_SEM_OBMEP - 1
                                                                    and a == _ANO_SEM_OBMEP + 1))
        atual = atual + 1 if consecutivo else 1
        melhor = max(melhor, atual)
        anterior = a
    return melhor


def _conquista(cid: str, nome: str, descricao: str, icone: str, atual: int, meta: int,
               raridade: str = "comum") -> dict:
    """Uma conquista com o progresso (atual de meta); desbloqueada quando atual chega à meta."""
    atual = min(atual, meta)
    return {"id": cid, "nome": nome, "descricao": descricao, "icone": icone, "raridade": raridade,
            "desbloqueada": atual >= meta, "atual": atual, "meta": meta}


def conquistas_aluno(premiacoes: list[dict]) -> list[dict]:
    """Conquistas do aluno a partir das premiações dele. Sem premiações, a lista serve de vitrine (tudo
    bloqueado) na página Sobre."""
    medalhas = [r for r in premiacoes if r["medalha"] in MEDALHAS]
    ouros = [r for r in premiacoes if r["medalha"] == OURO]
    anos = {r["ano"] for r in premiacoes if r["ano"]}
    competicoes = {r["competicao"] for r in premiacoes}
    obmep = [r for r in premiacoes if r["competicao"] == "OBMEP"]

    ouros_por_ano: dict[int, set] = {}
    for r in ouros:
        ouros_por_ano.setdefault(r["ano"], set()).add(r["competicao"])
    dupla_coroa = any(len(c) >= 2 for c in ouros_por_ano.values())

    melhor_por_ano: dict[int, int] = {}
    for r in obmep:
        if r["medalha"] in _PESO_MEDALHA:
            melhor_por_ano[r["ano"]] = max(melhor_por_ano.get(r["ano"], 0), _PESO_MEDALHA[r["medalha"]])
    sequencia = [melhor_por_ano[a] for a in sorted(melhor_por_ano)]
    escalada = any(b > a for a, b in zip(sequencia, sequencia[1:]))
    invicto = len(obmep) if obmep and all(r["medalha"] == OURO for r in obmep) else 0

    return [
        _conquista("primeiro_podio", "Primeiro Pódio", "Conquistou a primeira premiação", "sparkles",
                   len(premiacoes), 1),
        _conquista("midas", "Toque de Midas", "Ganhou uma medalha de ouro", "crown", len(ouros), 1, "rara"),
        _conquista("hat_trick", "Hat-trick Dourado", "3 medalhas de ouro", "flame", len(ouros), 3, "épica"),
        _conquista("colecionador", "Colecionador", "5 medalhas no total", "gem", len(medalhas), 5, "rara"),
        _conquista("veterano", "Veterano", "Premiado em 5 anos diferentes", "shield", len(anos), 5, "épica"),
        _conquista("imparavel", "Imparável", "Premiado 3 anos seguidos", "zap", maior_sequencia(anos), 3, "rara"),
        _conquista("duas_frentes", "Duas Frentes", "Premiado em duas olimpíadas diferentes", "swords",
                   len(competicoes), 2, "rara"),
        _conquista("dupla_coroa", "Dupla Coroa", "Ouro em duas olimpíadas no mesmo ano", "trophy",
                   int(dupla_coroa), 1, "lendária"),
        _conquista("prodigio", "Prodígio", "Medalha já no Nível 1", "rocket",
                   int(any(r["nivel"] == "1" for r in medalhas)), 1),
        _conquista("escalada", "Escalada", "Melhorou a medalha de um ano para outro", "trending-up",
                   int(escalada), 1, "rara"),
        _conquista("invicto", "Invicto", "2+ medalhas na OBMEP, todas de ouro", "star", invicto, 2, "lendária"),
        _conquista("universitario", "Lenda Universitária", "Premiado no nível universitário da OBM",
                   "graduation-cap", int(any(r["nivel"] == "Universitário" for r in premiacoes)), 1, "épica"),
    ]


def conquistas_escola(premiacoes: list[dict], posicao: int | None, posicao_uf: int | None) -> list[dict]:
    """Conquistas da escola a partir das premiações e da posição nacional e estadual dela."""
    niveis_com_ouro: dict[int, set] = {}
    for r in premiacoes:
        if r["medalha"] == OURO:
            niveis_com_ouro.setdefault(r["ano"], set()).add(r["nivel"])
    return conquistas_escola_por_totais(
        len(premiacoes), sum(r["medalha"] == OURO for r in premiacoes), len({r["aluno_id"] for r in premiacoes}),
        {r["ano"] for r in premiacoes if r["ano"]},
        any({"1", "2", "3"} <= niveis for niveis in niveis_com_ouro.values()), posicao, posicao_uf)


def conquistas_escola_por_totais(premiacoes: int, ouros: int, alunos: int, anos: set[int], grand_slam: bool,
                                 posicao: int | None, posicao_uf: int | None) -> list[dict]:
    """As mesmas conquistas, a partir dos totais (quem tem a base soma no banco, sem ler premiação por premiação):
    nº de premiações, de ouros e de alunos, anos premiados e se houve ouro nos níveis 1, 2 e 3 no mesmo ano."""
    return [
        _conquista("primeira", "Primeira Medalha", "A escola entrou para o quadro", "sparkles", premiacoes, 1),
        _conquista("fabrica_ouro", "Fábrica de Ouro", "10 medalhas de ouro", "crown", ouros, 10, "épica"),
        _conquista("centenaria", "Centenária", "100 premiações", "medal", premiacoes, 100, "épica"),
        _conquista("celeiro", "Celeiro de Talentos", "50 alunos diferentes premiados", "users",
                   alunos, 50, "rara"),
        _conquista("tradicao", "Tradição", "Premiada em 10 anos diferentes", "landmark", len(anos), 10, "rara"),
        _conquista("dinastia", "Dinastia", "Premiada 5 anos seguidos", "zap", maior_sequencia(anos), 5, "rara"),
        _conquista("grand_slam", "Grand Slam", "Ouro nos 3 níveis no mesmo ano", "trophy",
                   int(grand_slam), 1, "lendária"),
        _conquista("top_estado", "Nº 1 do Estado", "Melhor escola do seu estado", "map-pin",
                   int(posicao_uf == 1), 1, "lendária"),
        _conquista("elite", "Elite Nacional", "Top 100 do Brasil", "flag",
                   int(bool(posicao and posicao <= 100)), 1, "épica"),
    ]


def contar_medalhas(premiacoes: list[dict]) -> dict:
    """Quantas de cada categoria; "outros" são prêmios fora de ouro/prata/bronze/menção ("1º Prêmio" da OBM,
    "Elas em Destaque" da Itabirana)."""
    c = Counter(r["medalha"] for r in premiacoes)
    return {"ouro": c[OURO], "prata": c[PRATA], "bronze": c[BRONZE], "mencao": c[MENCAO],
            "outros": sum(v for k, v in c.items() if k not in (*MEDALHAS, MENCAO))}
