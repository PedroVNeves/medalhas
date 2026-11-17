"""Esquema da base SQLite.

medalhas  uma linha por premiação, com campos de busca normalizados e os pontos nos três métodos
alunos    resumo por aluno (totais, pontos e posição nacional/estadual em cada método), pré-calculado
escolas   o mesmo, por escola
meta      chave/valor (ex.: atualizado_em)
"""
from ...dominio.pontuacao import COLUNAS as PONTOS

# Campos que vêm do coletor, na ordem das colunas da tabela
CAMPOS_ORIGINAIS = ["competicao", "ano", "nivel", "nome", "escola", "rede", "esfera",
                    "municipio", "uf", "premio", "medalha", "pontos", "fonte"]
# Campos derivados ao indexar (aplicacao.gerar_base.indexar)
CAMPOS_DERIVADOS = ["nome_busca", "escola_busca", "escola_termos", "escola_chave", "municipio_busca",
                    "aluno_id", *PONTOS, "area", "sexo"]
CAMPOS_PREMIACAO = CAMPOS_ORIGINAIS + CAMPOS_DERIVADOS

PREMIACOES = """
CREATE TABLE medalhas (
    id              INTEGER PRIMARY KEY,
    competicao      TEXT NOT NULL,
    ano             INTEGER,
    nivel           TEXT,
    nome            TEXT NOT NULL,
    escola          TEXT,
    rede            TEXT,
    esfera          TEXT,
    municipio       TEXT,
    uf              TEXT,
    premio          TEXT,
    medalha         TEXT,
    pontos          TEXT,               -- nota na prova, quando publicada
    fonte           TEXT,
    nome_busca      TEXT NOT NULL,      -- campos *_busca/termos: normalizados (sem acento, maiúsculos)
    escola_busca    TEXT,
    escola_termos   TEXT,
    escola_chave    TEXT,               -- identidade da escola (dominio.escolas.indexar_escola)
    municipio_busca TEXT,
    aluno_id        TEXT NOT NULL,      -- identidade do aluno (dominio.identidade.atribuir_alunos)
    p_impa          INTEGER NOT NULL,   -- IMPA, todos os níveis
    p_impa3         INTEGER NOT NULL,   -- IMPA oficial: só o que o edital aceita
    p_site          INTEGER NOT NULL,   -- nossa versão
    area            TEXT,
    sexo            TEXT                -- F (premiada em olimpíada só para meninas, dominio.sexo) ou NULL
);
CREATE INDEX idx_aluno  ON medalhas(aluno_id);
CREATE INDEX idx_chave  ON medalhas(escola_chave);
CREATE INDEX idx_nome   ON medalhas(nome_busca);
CREATE INDEX idx_escola ON medalhas(escola_busca);
CREATE INDEX idx_ano    ON medalhas(ano);
CREATE INDEX idx_uf     ON medalhas(uf);
CREATE TABLE meta (chave TEXT PRIMARY KEY, valor TEXT);
"""

POSICOES = [f"{c}_{k}" for c in PONTOS for k in ("pos", "pos_uf")]   # p_impa_pos, p_impa_pos_uf, ...
CAMPOS_ALUNO = ["id", "nome", "uf", "competicoes", "escola", "escola_chave", "municipio", "ouro", "prata",
                "bronze", "mencao", "total", "de", "ate", *PONTOS, *POSICOES]
CAMPOS_ESCOLA = ["id", "nome", "municipio", "uf", "rede", "esfera", "alunos", "ouro", "prata", "bronze",
                 "mencao", "total", "de", "ate", *PONTOS, *POSICOES]
_PONTOS_E_POSICOES = ", ".join(f"{c} INT" for c in PONTOS + POSICOES)

RESUMOS = f"""
CREATE TABLE alunos (
    id TEXT PRIMARY KEY, nome TEXT, uf TEXT, competicoes TEXT, escola TEXT, escola_chave TEXT,
    municipio TEXT, ouro INT, prata INT, bronze INT, mencao INT, total INT, de INT, ate INT,
    {_PONTOS_E_POSICOES}
);
CREATE TABLE escolas (
    id TEXT PRIMARY KEY, nome TEXT, municipio TEXT, uf TEXT, rede TEXT, esfera TEXT, alunos INT,
    ouro INT, prata INT, bronze INT, mencao INT, total INT, de INT, ate INT,
    {_PONTOS_E_POSICOES}
);
{"".join(f"CREATE INDEX idx_alunos_{c} ON alunos({c} DESC); CREATE INDEX idx_escolas_{c} ON escolas({c} DESC);"
         for c in PONTOS)}
CREATE INDEX idx_alunos_uf ON alunos(uf);
CREATE INDEX idx_escolas_uf ON escolas(uf);
"""


def insert(tabela: str, campos: list[str]) -> str:
    """INSERT com um marcador (?) por campo. Tabela e campos vêm das constantes deste módulo, nunca do usuário."""
    return f"INSERT INTO {tabela} ({', '.join(campos)}) VALUES ({', '.join('?' * len(campos))})"
