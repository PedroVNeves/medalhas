# medalhas

Base de pesquisa dos premiados da **OBMEP** (2005–2025) e da **OBM** (1979–2025), com busca por pessoa ou escola.

## Como usar

Requer apenas Python 3.10+ (sem dependências externas).

```bash
python build_db.py   # baixa as listas oficiais e gera data/medalhas.db (alguns minutos na 1ª vez)
python server.py     # abre a busca em http://localhost:8000
```

- `python build_db.py --refresh` apaga o cache e baixa tudo de novo (use quando sair um ano novo).
- `python server.py --port 9000 --no-browser` para mudar a porta / não abrir o navegador.

## Fontes

| Olimpíada | Origem | Dados disponíveis |
|-----------|--------|-------------------|
| OBMEP | `premiacao.obmep.org.br/<edição>/verRelatorioPremiados{Ouro,Prata,Bronze}[.privada].do.htm` | nome, escola, esfera (E/M/F), município, UF, nível, medalha, rede (pública/privada) |
| OBM | `www.obm.org.br/premiados-obm-<ano>/` | nome, cidade/UF, nível, pontos, prêmio (inclui menções honrosas) |

As edições são descobertas automaticamente a partir de `obmep.org.br/premiados.htm` e
`obm.org.br/quem-somos/premiados-da-obm/`, então anos novos entram sem mudar código.

Observações:
- A OBMEP não teve edição em 2020; escolas privadas só aparecem a partir de 2017.
- A OBM não publica a escola, só cidade/UF.
- Cada resultado tem link para a página oficial (`fonte ↗`) para conferência.

## O site

Página única servida pelo `server.py`, sem etapa de build (Tailwind, Alpine.js, ECharts, Lucide e
canvas-confetti via CDN):

- **Busca** por pessoa, escola (com siglas) ou tudo, com link para a fonte oficial de cada premiação.
- **Rankings** de alunos, escolas e estados, filtráveis por UF, olimpíada, período, nível e rede, ordenados
  por pontos, quadro de medalhas (ouro → prata → bronze) ou total de medalhas.
- **Mapa do Brasil** por pontos, ouros, premiações ou alunos.
- **Perfis** de aluno e escola com posição nacional/estadual, nível, conquistas, trajetória e gráfico por ano.

### Pontos e gamificação

Os pontos seguem a tabela oficial do IMPA para as olimpíadas de matemática
([Edital do Processo Seletivo 2026 do IMPA Tech, item 6.1](https://impatech.edu.br/wp-content/uploads/2025/10/Edital-IMPA-Tech-2026-versao-final-2025-10-23site.pdf)):

| Medalha | OBMEP | OBM |
|---|---|---|
| Ouro | 18 | 18 |
| Prata | 6 | 6 |
| Bronze | 2 | 2 |

Menção honrosa não pontua. Há duas somas:

- **Pontos**: a tabela aplicada a todas as medalhas, de qualquer nível (trajetória completa).
- **Pontuação IMPA Tech**: só o que o edital aceita, ou seja, medalhas do Nível 3 da OBMEP (premiação nacional) e da OBM.

Os pontos definem níveis (Estreante → Promessa → Talento → Destaque → Elite → Mestre → Lenda, com
limites diferentes para alunos e escolas) e há conquistas como *Hat-trick Dourado*, *Dupla Coroa*,
*Imparável* e *Grand Slam* (`gamificacao.py`).

### Adicionar uma olimpíada

1. Escreva o coletor em `scraper/<sigla>.py` com uma função `scrape()` que devolve registros no mesmo
   formato dos existentes (`competicao, ano, nivel, nome, escola, municipio, uf, premio, medalha, fonte…`).
2. Cadastre a olimpíada em `olimpiadas.py`: nome, área (Matemática, Astronomia, História…), tabela de
   pontos e quais níveis contam para o IMPA Tech (se algum).
3. Rode `python build_db.py`.

Os filtros de olimpíada, área e nível da busca e dos rankings são montados a partir dos dados, então
não é preciso mexer no front-end. O filtro de área só aparece quando houver mais de uma área.

### API

| Rota | O que retorna |
|---|---|
| `/api/busca?q=&campo=nome\|escola\|tudo&uf=&competicao=&area=&medalha=&ano=&nivel=&rede=&escola_chave=` | premiações que casam com a busca |
| `/api/ranking?tipo=alunos\|escolas\|estados&ordem=xp\|medalhas\|total\|impa&uf=&competicao=&area=&ano_de=&ano_ate=&nivel=&rede=&offset=` | ranking paginado |
| `/api/aluno?id=` / `/api/escola?id=` | perfil completo com conquistas |
| `/api/overview` | totais, série histórica, top 10, estados, catálogo de olimpíadas e níveis |

`competicao`, `area` e `nivel` aceitam vários valores separados por vírgula (ex.: `nivel=3` para só o
nível 3, ou `nivel=1,2,3,Universitário`).

Rankings sem filtro e perfis leem as tabelas-resumo `alunos` e `escolas`, pré-calculadas pelo
`build_db.py`; rankings filtrados são agregados na hora e ficam em cache na memória.

## Como a busca de escolas funciona

- Acentos, pontuação e ordem das palavras são ignorados ("MILITAR DE FORTALEZA, COLEGIO" = "Colégio Militar de Fortaleza").
- Abreviações e siglas são expandidas nos dados **e** no texto digitado (`scraper/escolas.py`):
  `EE` → escola estadual, `EMEF`, `EEEFM`, `ETEC`/`ETE` → escola técnica estadual, `PROFA` → professor,
  `IFAL` → instituto federal de Alagoas (todas as `IF<UF>`, `IFSUL`, `IFBAIANO`, `CEFET`…).
  Assim, "instituto federal de alagoas" traz também as escolas cadastradas como "IFAL".
- Grafias diferentes da mesma escola (mesmo município) são agrupadas em um único cartão.
- Para incluir uma sigla nova, adicione em `SIGLAS` ou `ABREVIACOES` e rode `python build_db.py`.

## Estrutura

```
scraper/common.py   download com cache + normalização de texto
scraper/obmep.py    coleta OBMEP
scraper/obm.py      coleta OBM
olimpiadas.py       cadastro das olimpíadas (área, pontos, regra IMPA Tech, coletor)
build_db.py         gera o SQLite (data/medalhas.db) com tabelas-resumo de alunos e escolas
gamificacao.py      pontos, níveis e conquistas
server.py           servidor local + API
web/                interface (index.html, app.js, styles.css)
```
