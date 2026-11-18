"""Esquema da base SQLite.

premiacoes uma linha por premiação, com campos de busca normalizados e os pontos nos três métodos;
          fontes, grafias e olimpiadas guardam uma vez o que se repete (endereço da lista, escola, área)
medalhas  visão que junta tudo, com as colunas que as consultas usam
alunos    resumo por aluno, numerado (n) em ordem alfabética do id; as premiações guardam esse número
          (totais, pontos e posição nacional/estadual em cada método), pré-calculado
escolas   o mesmo, por escola
cidades   o mesmo, por cidade (município + UF), com o nome de exibição
enderecos endereços aceitos além do oficial (que fica na tabela-resumo) -> id
busca_alunos, busca_escolas  índices de texto das sugestões da busca
meta      chave/valor (ex.: atualizado_em)

Tudo o que dá para calcular na geração é gravado aqui: o servidor lê só a linha de que precisa, sem montar
listas da base inteira na memória.
"""
from ...dominio.pontuacao import COLUNAS as PONTOS

# Campos que vêm do coletor, na ordem das colunas da tabela
CAMPOS_ORIGINAIS = ["competicao", "ano", "nivel", "nome", "escola", "rede", "esfera",
                    "municipio", "uf", "premio", "medalha", "pontos", "fonte"]
# Campos derivados ao indexar (aplicacao.gerar_base.indexar)
CAMPOS_DERIVADOS = ["nome_busca", "escola_termos", "escola_chave", "municipio_busca", "aluno_id", *PONTOS, "area",
                    "sexo"]
CAMPOS_PREMIACAO = CAMPOS_ORIGINAIS + CAMPOS_DERIVADOS

# Colunas da tabela premiacoes (o que se repete muito fica em tabelas pequenas, por número): fonte -> fontes,
# escola/termos/chave -> grafias, area -> olimpiadas; premio fica NULL quando é igual à medalha
CAMPOS_FISICOS = ["competicao", "ano", "nivel", "nome", "rede", "esfera", "municipio", "uf", "premio", "medalha",
                  "pontos", "fonte_n", "grafia_n", "nome_busca", "municipio_busca", "aluno_n", *PONTOS, "sexo"]

PREMIACOES = """
CREATE TABLE premiacoes (
    id              INTEGER PRIMARY KEY,
    competicao      TEXT NOT NULL,
    ano             INTEGER,
    nivel           TEXT,
    nome            TEXT NOT NULL,
    rede            TEXT,
    esfera          TEXT,
    municipio       TEXT,
    uf              TEXT,
    premio          TEXT,               -- NULL: igual à medalha (o caso comum); '': a lista não informou
    medalha         TEXT,
    pontos          TEXT,               -- nota na prova, quando publicada
    fonte_n         INTEGER NOT NULL,   -- fontes.n (endereço da lista oficial)
    grafia_n        INTEGER NOT NULL,   -- grafias.n (escola como escrita na lista, termos de busca e chave)
    nome_busca      TEXT NOT NULL,      -- campos *_busca/termos: normalizados (sem acento, maiúsculos)
    municipio_busca TEXT,
    aluno_n         INTEGER NOT NULL,   -- alunos.n: o aluno (dominio.identidade.atribuir_alunos), por número
    p_impa          INTEGER NOT NULL,   -- IMPA, todos os níveis
    p_impa3         INTEGER NOT NULL,   -- IMPA oficial: só o que o edital aceita
    p_site          INTEGER NOT NULL,   -- nossa versão
    sexo            TEXT                -- F (premiada em olimpíada só para meninas, dominio.sexo) ou NULL
);
CREATE TABLE fontes (n INTEGER PRIMARY KEY, url TEXT NOT NULL);
-- escola como veio na lista + termos de busca + chave da escola (dominio.escolas.indexar_escola); a grafia
-- "sem escola" tem escola NULL, termos e chave vazios
CREATE TABLE grafias (n INTEGER PRIMARY KEY, escola TEXT, escola_termos TEXT NOT NULL, escola_chave TEXT NOT NULL);
CREATE TABLE olimpiadas (competicao TEXT PRIMARY KEY, area TEXT) WITHOUT ROWID;
CREATE INDEX idx_aluno  ON premiacoes(aluno_n);
CREATE INDEX idx_grafia ON premiacoes(grafia_n);
CREATE INDEX idx_ano    ON premiacoes(ano);
CREATE INDEX idx_uf     ON premiacoes(uf);
CREATE INDEX idx_cidade ON premiacoes(municipio_busca, uf);
CREATE INDEX idx_chave  ON grafias(escola_chave);
-- as consultas leem esta visão, com as mesmas colunas de quando tudo ficava numa tabela só. Toda premiação tem
-- grafia, mas a junção é LEFT JOIN de propósito: assim o SQLite percorre as premiações e busca a grafia de cada
-- uma, em vez de partir das grafias e saltar pelas premiações (a busca por nome ficava 20 vezes mais lenta).
-- O id do aluno vem da tabela alunos pelo número, só quando a consulta usa a coluna aluno_id: quem agrupa,
-- conta ou filtra por aluno usa aluno_n, um número pequeno, em vez de repetir o id em texto em cada premiação
CREATE VIEW medalhas AS
SELECT p.id, p.competicao, p.ano, p.nivel, p.nome, g.escola, p.rede, p.esfera, p.municipio, p.uf,
       CASE WHEN p.premio IS NULL THEN p.medalha WHEN p.premio = '' THEN NULL ELSE p.premio END AS premio,
       p.medalha, p.pontos, f.url AS fonte, p.nome_busca, g.escola_termos, g.escola_chave, p.municipio_busca,
       (SELECT a.id FROM alunos a WHERE a.n = p.aluno_n) AS aluno_id, p.aluno_n, p.p_impa, p.p_impa3, p.p_site,
       o.area, p.sexo
FROM premiacoes p LEFT JOIN grafias g ON g.n = p.grafia_n LEFT JOIN fontes f ON f.n = p.fonte_n
     LEFT JOIN olimpiadas o ON o.competicao = p.competicao;
CREATE TABLE meta (chave TEXT PRIMARY KEY, valor TEXT);
"""

POSICOES = [f"{c}_{k}" for c in PONTOS for k in ("pos", "pos_uf")]   # p_impa_pos, p_impa_pos_uf, ...
CAMPOS_ALUNO = ["id", "endereco", "indexar", "nome", "uf", "competicoes", "escola", "escola_chave", "municipio",
                "ouro", "prata", "bronze", "mencao", "total", "de", "ate", *PONTOS, *POSICOES]
CAMPOS_ESCOLA = ["id", "endereco", "indexar", "nome", "municipio", "uf", "rede", "esfera", "alunos", "ouro",
                 "prata", "bronze", "mencao", "total", "de", "ate", *PONTOS, *POSICOES]
CAMPOS_CIDADE = ["id", "endereco", "nome", "uf", "alunos", "escolas", "ouro", "prata", "bronze", "mencao", "total",
                 "de", "ate", *PONTOS, *POSICOES]
_PONTOS_E_POSICOES = ", ".join(f"{c} INT" for c in PONTOS + POSICOES)

RESUMOS = f"""
-- n: número fixo da linha, para o índice de texto das sugestões apontar para ela (o VACUUM não o muda); em
-- alunos, dado em ordem alfabética do id (o nome sem acento): desempata os rankings sem consultar o nome;
-- indexar: 0 quando todas as premiações são menções da OBMEP (fora do sitemap e com noindex)
CREATE TABLE alunos (
    n INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, endereco TEXT UNIQUE, indexar INT, nome TEXT, uf TEXT,
    competicoes TEXT,
    escola TEXT, escola_chave TEXT,
    municipio TEXT, ouro INT, prata INT, bronze INT, mencao INT, total INT, de INT, ate INT,
    {_PONTOS_E_POSICOES}
);
CREATE TABLE escolas (
    n INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, endereco TEXT UNIQUE, indexar INT, nome TEXT, municipio TEXT,
    uf TEXT,
    rede TEXT, esfera TEXT, alunos INT,
    ouro INT, prata INT, bronze INT, mencao INT, total INT, de INT, ate INT,
    {_PONTOS_E_POSICOES}
);
-- cidade = município + UF das premiações (id MUNICIPIO|UF, sem acento); nome é a grafia de exibição
CREATE TABLE cidades (
    id TEXT PRIMARY KEY, endereco TEXT UNIQUE, nome TEXT, uf TEXT, alunos INT, escolas INT,
    ouro INT, prata INT, bronze INT, mencao INT, total INT, de INT, ate INT,
    {_PONTOS_E_POSICOES}
);
-- endereços aceitos além do oficial (que fica na tabela-resumo): o montado pelo id, quando é outro, e os de
-- perfis com grafia corrigida à mão -> id
CREATE TABLE enderecos (tipo TEXT, endereco TEXT, id TEXT, PRIMARY KEY (tipo, endereco)) WITHOUT ROWID;
-- sugestões enquanto a pessoa digita: as grafias de cada aluno e escola, pesquisáveis por início de palavra.
-- Sem cópia do texto (content=''): o rowid de cada linha é o n do aluno ou da escola na tabela-resumo
CREATE VIRTUAL TABLE busca_alunos USING fts5(texto, content='', prefix='2');
CREATE VIRTUAL TABLE busca_escolas USING fts5(texto, content='', prefix='2');
{"".join(f"CREATE INDEX idx_{t}_{c} ON {t}({c} DESC);" for c in PONTOS for t in ("alunos", "escolas", "cidades"))}
CREATE INDEX idx_alunos_uf ON alunos(uf);
CREATE INDEX idx_escolas_uf ON escolas(uf);
CREATE INDEX idx_cidades_uf ON cidades(uf);
"""


def insert(tabela: str, campos: list[str]) -> str:
    """INSERT com um marcador (?) por campo. Tabela e campos vêm das constantes deste módulo, nunca do usuário."""
    return f"INSERT INTO {tabela} ({', '.join(campos)}) VALUES ({', '.join('?' * len(campos))})"
