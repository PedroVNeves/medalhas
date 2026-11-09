# medalhas

Base de pesquisa e rankings dos medalhistas brasileiros em olimpíadas: **OBMEP**, **OBM**, **OBI**, **IMO**,
**Ibero**, **Cone Sul** e mais 12 competições internacionais (1979–2026), com busca por pessoa ou escola.

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
| OBI | `olimpiada.ic.unicamp.br/passadas/OBI<ano>/qmerito/<modalidade>/` (2005–2025) | nome, escola, cidade, UF, modalidade/nível, medalha, honra ao mérito |
| IMO | `imo-official.org/results/team/year/<ano>/country/BRA/` (1981–2026) | nome, pontos, medalha, menção honrosa |
| Internacionais (OBM) | `www.obm.org.br/resultados-…/` | nome, cidade/UF, prêmio: Ibero (OIM), Cone Sul, EGMO, APMO, IMC, PAGMO, OMCPLP, IGO, IMSC, OIMU, CIIM, Olimpíada de Maio, OMOP, Galois-Noether |

As edições são descobertas automaticamente nas páginas de índice de cada fonte, então anos novos entram
sem mudar código. Uma fonte fora do ar não derruba a geração da base: ela avisa no fim e as outras entram.

Observações:
- A OBMEP não teve edição em 2020; escolas privadas só aparecem a partir de 2017.
- A OBM e as competições internacionais não publicam a escola, só cidade/UF.
- A IMO não publica a UF: ela é inferida pelo nome em outras olimpíadas, e nomes abreviados
  ("Enzo Holanda") são completados quando há um único medalhista compatível.
- **Mesma pessoa:** mesmo nome (sem acento) e mesma UF. Como alunos de ponta mudam de estado, o mesmo
  nome em UFs diferentes é unido quando o nome é raro, as premiações cabem em 12 anos e não há a mesma
  olimpíada no mesmo ano em duas UFs (`atribuir_alunos` em `build_db.py`).
- Cada resultado tem link para a página oficial (`fonte ↗`) para conferência.

Ainda não coletadas: **OBQ** (resultados só em PDFs com formato diferente a cada ano), **OBFEP**
(site fora do ar na coleta), **OBA** (página de resultados não encontrada), **ONHB** (site indisponível)
e **Canguru** (não publica lista pública de premiados).

## O site

Página única servida pelo `server.py`, sem etapa de build (Tailwind, Alpine.js, ECharts, Lucide e
canvas-confetti via CDN):

- **Busca** por pessoa, escola (com siglas) ou tudo, com link para a fonte oficial de cada premiação.
- **Rankings** de alunos, escolas e estados, filtráveis por UF, olimpíada, período, nível e rede, ordenados
  por pontos, quadro de medalhas (ouro → prata → bronze) ou total de medalhas.
- **Mapa do Brasil** por pontos, ouros, premiações ou alunos.
- **Perfis** de aluno e escola com posição nacional/estadual, nível, conquistas, trajetória e gráfico por ano.

### Métodos de pontuação

No topo do site há um seletor global (também aceito na URL como `?metodo=`) com três métodos. A escolha
vale para rankings, mapa, perfis e níveis:

| Método | `metodo` | Como conta |
|---|---|---|
| IMPA · todos os níveis | `impa` (padrão) | Tabela oficial do IMPA Tech (ouro 18, prata 6, bronze 2) em medalhas de qualquer nível |
| IMPA oficial · só Nível 3 | `impa3` | Exatamente o que o [edital do IMPA Tech 2026 (item 6.1)](https://impatech.edu.br/wp-content/uploads/2025/10/Edital-IMPA-Tech-2026-versao-final-2025-10-23site.pdf) aceita: Nível 3 da OBMEP (premiação nacional) e da OBM |
| Medalhas (nossa versão) | `site` | Escala por dificuldade (tabela abaixo); menções honrosas e prêmios antigos da OBM pontuam |

No método **IMPA N3** o filtro de nível fica travado no Nível 3 (o servidor força `nivel=3` em busca e
rankings); tentar mudar mostra um aviso com a opção de trocar de método.

Escala da nossa versão (`ESCALA_SITE` em `olimpiadas.py`, com as regras verificadas ao importar):
ouro OBM = 2× ouro OBMEP, bronze OBM > ouro OBMEP, bronze Ibero > prata OBM, bronze IMO > prata Ibero,
e olimpíadas de entrada valem menos que um bronze da OBMEP.

| | Ouro | Prata | Bronze | Menção |
|---|---|---|---|---|
| Entrada (Canguru e similares) | 20 | 12 | 6 | – |
| OBMEP | 100 | 60 | 30 | – |
| OBM | 200 | 150 | 110 | 40 |
| Ibero | 320 | 240 | 170 | 60 |
| IMO | 600 | 400 | 280 | 100 |

Os três totais e as posições nacional e estadual em cada método são pré-calculados no `build_db.py`.
No ranking por pontos, quem tem zero no método fica de fora. Os níveis (Estreante → Promessa → Talento →
Destaque → Elite → Mestre → Lenda) têm limites próprios por método (`gamificacao.py`), e há conquistas
como *Hat-trick Dourado*, *Dupla Coroa*, *Imparável* e *Grand Slam*.

### Adicionar uma olimpíada

1. Escreva o coletor em `scraper/<sigla>.py` com uma função `scrape()` que devolve registros no mesmo
   formato dos existentes (`competicao, ano, nivel, nome, escola, municipio, uf, premio, medalha, fonte…`).
2. Cadastre a olimpíada em `olimpiadas.py`: nome, área (Matemática, Astronomia, História…), tabela de
   pontos do IMPA (`pontos`), tabela da nossa versão (`pontos_site`) e quais níveis contam para o
   IMPA Tech (`impa_niveis`, vazio se nenhum).
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

Todas as rotas aceitam `metodo=impa|impa3|site`; o campo `xp` das respostas é sempre a pontuação no
método pedido. `competicao`, `area` e `nivel` aceitam vários valores separados por vírgula (ex.: `nivel=3` para só o
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
