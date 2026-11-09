"""Regras de gamificação: níveis (tiers) e conquistas de alunos e escolas."""
from collections import Counter

MEDALHAS = ("Ouro", "Prata", "Bronze")
MEDAL_RANK = {"Bronze": 1, "Prata": 2, "Ouro": 3}

# (nome, pontos mínimos, cor de destaque). Calibrado na escala do IMPA Tech (ouro 18, prata 6, bronze 2).
# Nomes de nível evitam "ouro/prata/bronze" para não confundir com as medalhas.
TIERS_ALUNO = [
    ("Estreante", 0, "#8b93a7"),
    ("Promessa", 6, "#4bbf7f"),     # ex.: 1 prata ou 3 bronzes
    ("Talento", 18, "#5ea8ff"),     # ex.: 1 ouro
    ("Destaque", 36, "#b57bff"),    # ex.: 2 ouros
    ("Elite", 72, "#5ee0d0"),       # ~ top 300 do Brasil
    ("Mestre", 120, "#f5c542"),     # ~ top 40
    ("Lenda", 170, "#ff6bd6"),      # ~ top 5
]
TIERS_ESCOLA = [
    ("Estreante", 0, "#8b93a7"),
    ("Promessa", 20, "#4bbf7f"),
    ("Talento", 60, "#5ea8ff"),
    ("Destaque", 150, "#b57bff"),
    ("Elite", 400, "#5ee0d0"),
    ("Mestre", 1200, "#f5c542"),
    ("Lenda", 3000, "#ff6bd6"),
]

import olimpiadas as olp

FONTE_PONTOS = olp.FONTE_PONTOS


def tier(xp: int, escola: bool = False) -> dict:
    tiers = TIERS_ESCOLA if escola else TIERS_ALUNO
    idx = max(i for i, (_, minimo, _) in enumerate(tiers) if xp >= minimo)
    nome, minimo, cor = tiers[idx]
    nxt = tiers[idx + 1] if idx + 1 < len(tiers) else None
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
