"""Regras de gamificação: níveis (tiers) e conquistas de alunos e escolas."""
from collections import Counter

MEDALHAS = ("Ouro", "Prata", "Bronze")
MEDAL_RANK = {"Bronze": 1, "Prata": 2, "Ouro": 3}

import olimpiadas as olp

FONTE_PONTOS = olp.FONTE_PONTOS

# Níveis (tiers). Os nomes evitam "ouro/prata/bronze" para não confundir com as medalhas.
TIER_NOMES = ["Estreante", "Promessa", "Talento", "Destaque", "Elite", "Mestre", "Lenda"]
TIER_CORES = ["#8b93a7", "#4bbf7f", "#5ea8ff", "#b57bff", "#5ee0d0", "#f5c542", "#ff6bd6"]

# Pontos mínimos de cada nível, por método de pontuação. Calibrados na distribuição real
# (Mestre ≈ top 40 do Brasil, Lenda ≈ top 5–10).
LIMITES = {
    "impa": {"aluno": [0, 6, 18, 36, 72, 120, 170], "escola": [0, 20, 60, 150, 400, 1200, 3000]},
    "impa3": {"aluno": [0, 2, 6, 18, 36, 54, 80], "escola": [0, 6, 20, 60, 150, 600, 1300]},
    "site": {"aluno": [0, 60, 150, 300, 600, 1300, 1900], "escola": [0, 150, 500, 1500, 5000, 15000, 40000]},
}


def tiers(metodo: str, escola: bool = False) -> list[tuple]:
    limites = LIMITES.get(metodo, LIMITES[olp.METODO_PADRAO])["escola" if escola else "aluno"]
    return list(zip(TIER_NOMES, limites, TIER_CORES))


def tier(xp: int, escola: bool = False, metodo: str = olp.METODO_PADRAO) -> dict:
    tiers_ = tiers(metodo, escola)
    xp = xp or 0
    idx = max(i for i, (_, minimo, _) in enumerate(tiers_) if xp >= minimo)
    nome, minimo, cor = tiers_[idx]
    nxt = tiers_[idx + 1] if idx + 1 < len(tiers_) else None
    progresso = 1.0 if not nxt else (xp - minimo) / (nxt[1] - minimo)
    return {
        "nome": nome, "cor": cor, "nivel": idx + 1, "min": minimo, "xp": xp,
        "proximo": nxt[0] if nxt else None, "proximo_xp": nxt[1] if nxt else None,
        "falta": (nxt[1] - xp) if nxt else 0, "progresso": round(progresso, 4),
    }


def max_streak(anos: set[int]) -> int:
    """Maior sequência de anos consecutivos (2020 não teve OBMEP, então 2019→2021 conta)."""
    best = cur = 0
    prev = None
    for a in sorted(anos):
        if prev is not None and (a == prev + 1 or (prev == 2019 and a == 2021)):
            cur += 1
        else:
            cur = 1
        best = max(best, cur)
        prev = a
    return best


def _badge(bid, nome, desc, icone, atual, meta, raridade="comum"):
    atual = min(atual, meta)
    return {"id": bid, "nome": nome, "descricao": desc, "icone": icone, "raridade": raridade,
            "desbloqueada": atual >= meta, "atual": atual, "meta": meta}


def conquistas_aluno(rows: list[dict]) -> list[dict]:
    medals = [r for r in rows if r["medalha"] in MEDALHAS]
    ouros = [r for r in rows if r["medalha"] == "Ouro"]
    anos = {r["ano"] for r in rows if r["ano"]}
    comps = {r["competicao"] for r in rows}
    obmep = [r for r in rows if r["competicao"] == "OBMEP"]

    by_year: dict[int, set] = {}
    for r in ouros:
        by_year.setdefault(r["ano"], set()).add(r["competicao"])
    dupla_coroa = any(len(c) >= 2 for c in by_year.values())

    best_by_year = {}
    for r in obmep:
        if r["medalha"] in MEDAL_RANK:
            best_by_year[r["ano"]] = max(best_by_year.get(r["ano"], 0), MEDAL_RANK[r["medalha"]])
    seq = [best_by_year[a] for a in sorted(best_by_year)]
    escalada = any(b > a for a, b in zip(seq, seq[1:]))

    return [
        _badge("primeiro_podio", "Primeiro Pódio", "Conquistou a primeira premiação", "sparkles", len(rows), 1),
        _badge("midas", "Toque de Midas", "Ganhou uma medalha de ouro", "crown", len(ouros), 1, "rara"),
        _badge("hat_trick", "Hat-trick Dourado", "3 medalhas de ouro", "flame", len(ouros), 3, "épica"),
        _badge("colecionador", "Colecionador", "5 medalhas no total", "gem", len(medals), 5, "rara"),
        _badge("veterano", "Veterano", "Premiado em 5 anos diferentes", "shield", len(anos), 5, "épica"),
        _badge("imparavel", "Imparável", "Premiado 3 anos seguidos", "zap", max_streak(anos), 3, "rara"),
        _badge("duas_frentes", "Duas Frentes", "Premiado em duas olimpíadas diferentes", "swords", len(comps), 2, "rara"),
        _badge("dupla_coroa", "Dupla Coroa", "Ouro em duas olimpíadas no mesmo ano", "trophy", int(dupla_coroa), 1, "lendária"),
        _badge("prodigio", "Prodígio", "Medalha já no Nível 1", "rocket",
               int(any(r["nivel"] == "1" for r in medals)), 1),
        _badge("escalada", "Escalada", "Melhorou a medalha de um ano para outro", "trending-up", int(escalada), 1, "rara"),
        _badge("invicto", "Invicto", "2+ medalhas na OBMEP, todas de ouro",
               "star", len(obmep) if obmep and all(r["medalha"] == "Ouro" for r in obmep) else 0, 2, "lendária"),
        _badge("universitario", "Lenda Universitária", "Premiado no nível universitário da OBM", "graduation-cap",
               int(any(r["nivel"] == "Universitário" for r in rows)), 1, "épica"),
    ]


def conquistas_escola(rows: list[dict], rank: int | None, rank_uf: int | None) -> list[dict]:
    ouros = sum(r["medalha"] == "Ouro" for r in rows)
    anos = {r["ano"] for r in rows if r["ano"]}
    alunos = {r["aluno_id"] for r in rows}
    gold_levels: dict[int, set] = {}
    for r in rows:
        if r["medalha"] == "Ouro":
            gold_levels.setdefault(r["ano"], set()).add(r["nivel"])
    grand_slam = any({"1", "2", "3"} <= lv for lv in gold_levels.values())
    return [
        _badge("primeira", "Primeira Medalha", "A escola entrou para o quadro", "sparkles", len(rows), 1),
        _badge("fabrica_ouro", "Fábrica de Ouro", "10 medalhas de ouro", "crown", ouros, 10, "épica"),
        _badge("centenaria", "Centenária", "100 premiações", "medal", len(rows), 100, "épica"),
        _badge("celeiro", "Celeiro de Talentos", "50 alunos diferentes premiados", "users", len(alunos), 50, "rara"),
        _badge("tradicao", "Tradição", "Premiada em 10 anos diferentes", "landmark", len(anos), 10, "rara"),
        _badge("dinastia", "Dinastia", "Premiada 5 anos seguidos", "zap", max_streak(anos), 5, "rara"),
        _badge("grand_slam", "Grand Slam", "Ouro nos 3 níveis no mesmo ano", "trophy", int(grand_slam), 1, "lendária"),
        _badge("top_estado", "Nº 1 do Estado", "Melhor escola do seu estado", "map-pin",
               int(rank_uf == 1), 1, "lendária"),
        _badge("elite", "Elite Nacional", "Top 100 do Brasil", "flag", int(bool(rank and rank <= 100)), 1, "épica"),
    ]


def medal_counts(rows) -> dict:
    c = Counter(r["medalha"] for r in rows)
    return {"ouro": c["Ouro"], "prata": c["Prata"], "bronze": c["Bronze"],
            "mencao": c["Menção Honrosa"], "outros": sum(v for k, v in c.items() if k not in (*MEDALHAS, "Menção Honrosa"))}
