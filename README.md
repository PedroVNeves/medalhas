# medalhas

Base de pesquisa e rankings dos medalhistas brasileiros em olimpíadas: **OBMEP**, **OBM**, **OBI**, **IMO**,
**Ibero**, **Cone Sul** e mais 12 competições internacionais (1979–2026), com busca por pessoa ou escola,
[API pública](#api-pública-v1) e exportação dos dados em CSV e JSON.

## Como usar

Requer apenas Python 3.10+. A única dependência é opcional: o Pillow (`pip install -r requirements.txt`),
que desenha as imagens dos cartões de compartilhamento; sem ele, todo o resto funciona.

```bash
python build_db.py   # baixa as listas oficiais e gera data/medalhas.db (alguns minutos na 1ª vez)
python server.py     # abre a busca em http://localhost:8000
```

- `python build_db.py --refresh` apaga o cache e baixa tudo de novo (use quando sair um ano novo).
- `python server.py --port 9000 --no-browser` para mudar a porta / não abrir o navegador.
- `python server.py --host 0.0.0.0` para aceitar conexões de outras máquinas (API pública); veja os
  [proteções](#proteção-contra-excesso-de-requisições).

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
  olimpíada no mesmo ano em duas UFs (`medalhas/dominio/identidade.py`).
- Cada resultado tem link para a página oficial (`fonte ↗`) para conferência.

Ainda não coletadas: **OBQ** (resultados só em PDFs com formato diferente a cada ano), **OBFEP**
(site fora do ar na coleta), **OBA** (página de resultados não encontrada), **ONHB** (site indisponível)
e **Canguru** (não publica lista pública de premiados).

## O site

Página única servida pelo `server.py` (Alpine.js, ECharts, Lucide e canvas-confetti via CDN). O CSS do
Tailwind é gerado de antemão em `web/css/site.css`, que fica no repositório: para rodar o site basta o
Python. Só quem muda classes no HTML/JS precisa do Node:

```bash
npm install          # uma vez: instala o Tailwind (só para gerar o CSS)
npm run css          # gera web/css/site.css (o `firebase deploy` também roda isso antes de publicar)
npm run css:watch    # regera a cada mudança enquanto você edita
```


- **Busca** por pessoa, escola (com siglas) ou tudo, com link para a fonte oficial de cada premiação.
- **Rankings** de alunos, escolas e estados, filtráveis por UF, olimpíada, período, nível e rede, ordenados
  por pontos, quadro de medalhas (ouro → prata → bronze) ou total de medalhas.
- **Mapa do Brasil** por pontos, ouros, premiações ou alunos.
- **Perfis** de aluno e escola com posição nacional/estadual, nível, conquistas, trajetória e gráfico por ano.
- **Exportar** na busca, nos rankings e nos perfis: baixa o que está na tela em CSV, CSV para Excel ou JSON.
- **API & Dados**: documentação da API com exemplos, teste ao vivo e download da base inteira.

### Endereços e buscadores

Cada aluno e cada escola tem endereço próprio, que o Google indexa: `/aluno/maria-souza-lima-al` (o id
`NOME|UF` em forma de slug) e `/escola/em-benedita-braga-cobra-borda-da-mata-mg` (nome de exibição +
município + UF; ver `dominio/enderecos.py`). As outras telas também: `/ranking/alunos`, `/ranking/escolas`,
`/ranking/estados`, `/estados`, `/dados` (API & Dados), `/sobre` e `/busca?q=...` (esta fora do Google).
Links antigos com `#` (`/#/ranking/alunos`, `#/aluno/NOME%7CUF`, `#/api`) continuam funcionando: o site
troca pelo endereço novo.

- Ao abrir qualquer um desses endereços, o servidor (`adaptadores/http/paginas.py`) entrega o mesmo
  `index.html` com título, descrição, endereço canônico e um resumo em texto (em `<noscript>`, para robôs
  de IA que não rodam JavaScript): o perfil, os 100 primeiros do ranking, ou o texto do Sobre (o trecho
  entre `sobre:inicio` e `sobre:fim` do `index.html`). No site, a troca de página acontece sem recarregar.
  Os títulos de cada tela estão em `paginas.py` (`TELAS`) e em `web/js/app.js` (`TITULOS`).
- Endereço que não existe mostra `web/404.html` (o Firebase Hosting e o servidor Python, com status 404).
- Imagens de compartilhamento (`og:image`, 1200×630, o cartão que aparece ao mandar o link no WhatsApp,
  X, LinkedIn...): `/og/aluno/{endereço}.png` e `/og/escola/{endereço}.png` são desenhadas na hora
  (`adaptadores/http/imagens.py`, com Pillow) com o nome, as medalhas e a posição no ranking (só entre os
  1.000 primeiros); as demais páginas usam `/og/site.png`. Ficam no CDN como as páginas. As fontes (Inter
  e Space Grotesk, licença OFL) estão em `adaptadores/http/fontes/`.
- O site monta os links de escola pelo id (`slug()` em `web/js/util.js`, cópia do Python); o servidor
  redireciona esse endereço para o oficial, e o site troca o da barra quando o perfil carrega.
- `/sitemap.xml` lista todas as páginas (um arquivo a cada 40 mil endereços em `/sitemaps/`).
  `web/robots.txt` libera buscadores e IAs, e `web/llms.txt` explica o site e a API para IAs.
- O endereço canônico usa `https://medalhas.online`; para outro domínio, defina `MEDALHAS_URL`.

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

Escala da nossa versão (`ESCALA_SITE` em `medalhas/dominio/pontuacao.py`, com as regras verificadas ao
importar):
ouro OBM = 2× ouro OBMEP, bronze OBM > ouro OBMEP, bronze Ibero > prata OBM, bronze IMO > prata Ibero,
e olimpíadas de entrada valem menos que um bronze da OBMEP.

| | Ouro | Prata | Bronze | Menção |
|---|---|---|---|---|
| Entrada (Canguru e similares) | 20 | 12 | 6 | – |
| OBMEP | 100 | 60 | 30 | – |
| OBM | 200 | 150 | 110 | 40 |
| Ibero | 320 | 240 | 170 | 60 |
| IMO | 600 | 400 | 280 | 100 |

Os três totais e as posições nacional e estadual em cada método são pré-calculados ao gerar a base.
No ranking por pontos, quem tem zero no método fica de fora. Os níveis (Estreante → Promessa → Talento →
Destaque → Elite → Mestre → Lenda) têm limites próprios por método (`medalhas/dominio/gamificacao.py`), e há conquistas
como *Hat-trick Dourado*, *Dupla Coroa*, *Imparável* e *Grand Slam*.

### Adicionar uma olimpíada

1. Cadastre a olimpíada em `CATALOGO` (`medalhas/dominio/olimpiadas.py`): nome, área (Matemática,
   Astronomia, História…), degrau na escala da nossa versão (`escala`), tabela do IMPA (`tabela_impa`) e
   quais níveis contam para o IMPA Tech (`niveis_impa`, vazio se nenhum).
2. Escreva o coletor em `medalhas/adaptadores/coletores/<sigla>.py`, com uma função `coletar(log)` que
   devolve `Premiacao` (`medalhas/dominio/premiacao.py`), e registre-o em `coletores/__init__.py`.
   O teste `test_toda_olimpiada_do_catalogo_tem_coletor` acusa se faltar.
3. Rode `python build_db.py`.

Os filtros de olimpíada, área e nível da busca e dos rankings são montados a partir dos dados, então
não é preciso mexer no front-end. O filtro de área só aparece quando houver mais de uma área.

### API interna (usada pelas páginas do site)

Pode mudar sem aviso; para integrações use a [API pública](#api-pública-v1).

| Rota | O que retorna |
|---|---|
| `/api/busca?q=&campo=nome\|escola\|tudo&uf=&competicao=&area=&medalha=&ano=&nivel=&rede=&escola_chave=` | premiações que casam com a busca |
| `/api/ranking?tipo=alunos\|escolas\|estados&ordem=xp\|medalhas\|total\|impa&uf=&competicao=&area=&ano_de=&ano_ate=&nivel=&rede=&offset=` | ranking paginado |
| `/api/aluno?id=` / `/api/escola?id=` | perfil completo com conquistas (ou `?endereco=` com o slug da página) |
| `/api/overview` | totais, série histórica, top 10, estados, catálogo de olimpíadas e níveis |

Todas as rotas aceitam `metodo=impa|impa3|site`; o campo `xp` das respostas é sempre a pontuação no
método pedido. `competicao`, `area` e `nivel` aceitam vários valores separados por vírgula (ex.: `nivel=3` para só o
nível 3, ou `nivel=1,2,3,Universitário`).

Rankings sem filtro e perfis leem as tabelas-resumo `alunos` e `escolas`, pré-calculadas ao gerar a
base; rankings filtrados são agregados na hora e ficam em cache na memória.

## API pública (v1)

Acesso livre, sem cadastro e sem chave. Respostas em JSON (UTF-8) e CORS liberado, então a API pode ser
chamada de outro site, de um script ou de uma planilha. A documentação completa, com exemplos em cURL,
Python e JavaScript e um botão para testar cada rota, está na página **API & Dados** do site (`/dados`).
A especificação [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0) fica em `/api/v1/openapi.json`, para
importar no Postman, Insomnia ou Swagger Editor.

| Rota | Para quê |
|---|---|
| `GET /api/v1/alunos?nome=` | buscar alunos pelo nome (com as premiações de cada um) |
| `GET /api/v1/alunos/{id}` | um aluno específico e todas as premiações dele |
| `GET /api/v1/escolas?nome=` | buscar escolas pelo nome ou sigla (IFAL, ETEC…) |
| `GET /api/v1/escolas/{id}` | resumo de uma escola |
| `GET /api/v1/escolas/{id}/medalhistas` | todos os alunos premiados de uma escola (até 500 por página) |
| `GET /api/v1/premiacoes` | todas as premiações, filtradas ou não, paginadas (até 1000 por página) |
| `GET /api/v1/ranking/{alunos\|escolas\|estados}` | rankings com os mesmos critérios do site |
| `GET /api/v1/exportar` | baixar premiações ou rankings em CSV ou JSON, inteiros ou filtrados |
| `GET /api/v1/olimpiadas` | olimpíadas, níveis e valores aceitos nos filtros |
| `GET /api/v1` | índice com rotas, exemplos e limites atuais |

Ids vão no caminho codificados para URL (`encodeURIComponent` no JavaScript, `quote(id, safe="")` no
Python): o aluno `ERICK AKIRA KOGA|SP` vira `/api/v1/alunos/ERICK%20AKIRA%20KOGA%7CSP`.

**Filtros comuns** (valem em todas as consultas e na exportação): `uf`, `municipio`, `competicao`,
`area`, `medalha`, `nivel`, `ano`, `ano_de`, `ano_ate`, `rede`. `competicao` e `nivel` aceitam vários
valores separados por vírgula. Valores inválidos voltam com erro 400 explicando o que corrigir.
`metodo` (`impa`, `impa3`, `site`) muda a ordem dos resultados; os pontos dos três métodos vêm sempre.

### Medalhas de um aluno específico

```bash
# 1. buscar pelo nome: devolve o id e já traz as premiações
curl "http://localhost:8000/api/v1/alunos?nome=erick+akira+koga"

# 2. o mesmo aluno pelo id (estável: homônimos de outros estados têm outro id)
curl "http://localhost:8000/api/v1/alunos/ERICK%20AKIRA%20KOGA%7CSP"

# confirmar uma medalha: total > 0 significa que ela existe
curl "http://localhost:8000/api/v1/alunos?nome=erick+akira+koga&competicao=OBM&ano=2023&premiacoes=0"
```

Cada aluno traz `medalhas`, `pontos` e `posicao` (nacional e estadual) nos três métodos, e cada premiação
traz `olimpiada`, `ano`, `nivel`, `medalha`, `escola`, `municipio`, `uf`, `pontos` e `fonte` (a página
oficial onde ela foi publicada).

### Todos os medalhistas de uma escola

```python
import requests
from urllib.parse import quote

BASE = "http://localhost:8000/api/v1"
escola = requests.get(f"{BASE}/escolas", params={"nome": "ifal maceio"}).json()["escolas"][0]

medalhistas, offset = [], 0
while True:
    pagina = requests.get(f"{BASE}/escolas/{quote(escola['id'], safe='')}/medalhistas",
                          params={"limite": 500, "offset": offset}).json()
    medalhistas += pagina["medalhistas"]
    offset += pagina["limite"]
    if offset >= pagina["total"]:
        break
```

### Todos os dados

```bash
curl --compressed -OJ "http://localhost:8000/api/v1/exportar?formato=csv"            # base inteira (CSV)
curl --compressed -OJ "http://localhost:8000/api/v1/exportar?formato=csv&separador=;" # para o Excel em português
curl --compressed -OJ "http://localhost:8000/api/v1/exportar?formato=json"           # base inteira (JSON)
curl --compressed -OJ "http://localhost:8000/api/v1/exportar?competicao=OBM&uf=SP"   # só um recorte
curl --compressed -OJ "http://localhost:8000/api/v1/exportar?conjunto=escolas&metodo=impa3"  # ranking completo
```

- O CSV é UTF-8 com BOM (o Excel reconhece os acentos); `separador=;` abre direto no Excel em português.
- A base inteira tem ~45 MB em CSV, mas trafega compactada (~7 MB) quando o cliente aceita gzip
  (`curl --compressed`, navegadores, `requests`). O arquivo é gerado uma vez por versão da base e
  reaproveitado (`data/exportar/`).
- Exportações filtradas são geradas num arquivo temporário e a conexão com a base é liberada antes do
  envio, então um cliente lento não segura o servidor.
- No site, a busca, os rankings e os perfis de aluno e de escola têm um botão **Exportar** que baixa o
  que está na tela (CSV, CSV para Excel ou JSON), e a página **API & Dados** baixa a base inteira.

### Proteção contra excesso de requisições

O servidor aceita conexões só da própria máquina por padrão. Para abrir a API para a rede, rode
`python server.py --host 0.0.0.0` e libere a porta no firewall. A proteção (`medalhas/adaptadores/http/limites.py`) funciona
por IP:

| Camada | Padrão | Ao exceder | Opção |
|---|---|---|---|
| Consultas à API pública | 60/min e 2000/dia | 429 + `Retry-After` | `--rate-limit`, `--daily-limit` |
| Exportações (downloads) | 5/hora e 10/dia | 429 + `Retry-After` | `--export-limit` |
| API usada pelo site | 600/min | 429 + `Retry-After` | `--site-rate-limit` |
| Insistir depois do limite | 30 recusas em 60 s | IP bloqueado por 10 min em todo o site | — |
| Conexões abertas por IP | 12 (64 no total) | conexão recusada | `--max-connections-per-ip` |
| Consultas à base ao mesmo tempo | 8 | espera até 10 s, depois 503 | `--max-concurrent` |
| Conexão parada (sem enviar nada) | 20 s | conexão encerrada | — |

- O limite por minuto aceita rajadas curtas e recarrega aos poucos (1 consulta por segundo no padrão).
  `0` remove um limite.
- Toda resposta traz `X-RateLimit-Limit` e `X-RateLimit-Remaining`; a recusa traz `Retry-After` (segundos)
  e `{"erro": "...", "tente_em_segundos": N}`. O teto diário volta à meia-noite.
- Textos de busca têm no máximo 100 caracteres e 8 palavras, e as páginas têm tamanho máximo, para
  nenhuma consulta isolada pesar demais.
- Atrás de um proxy reverso (nginx, Caddy, Cloudflare), rode com `--trust-proxy` para usar o IP real de
  `X-Forwarded-For`. Sem proxy, não use essa opção: qualquer um poderia forjar o cabeçalho e fugir do limite.
- Os contadores ficam na memória e zeram quando o servidor reinicia. Contra ataques grandes de verdade
  (milhares de IPs), a proteção precisa vir antes do servidor, por exemplo com o Cloudflare na frente.

## Publicar na internet (Firebase Hosting + Cloud Run)

```
visitante -> medalhas.online (Firebase Hosting: HTTPS, CDN, arquivos de web/)
                 └── /api/**, /aluno/**, /escola/**, /ranking/**, /estados, /dados, /busca, /sobre,
                     /og/**, /sitemap.xml, /sitemaps/**
                       ->  Cloud Run "medalhas" (server.py + data/medalhas.db dentro da imagem)
```

- `Dockerfile`: imagem do servidor; a base vai dentro dela (só leitura). `.gcloudignore` define o que sobe.
- `firebase.json`: publica `web/` e repassa a API, as telas com endereço próprio e o sitemap ao Cloud Run em
  `southamerica-east1` (São Paulo).
- O servidor roda com `--trust-proxy`: lê o IP do visitante em `X-Forwarded-For` e o domínio em
  `X-Forwarded-Host` (para os links da API apontarem para o seu domínio).

Primeira vez (precisa do [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) e de
`npm install -g firebase-tools`; o Cloud Run exige o plano **Blaze** do Firebase, pago por uso):

```bash
gcloud auth login
firebase login
firebase projects:create SEU-PROJETO     # ou use um projeto existente; ative o Blaze no console
gcloud config set project SEU-PROJETO
firebase use --add SEU-PROJETO           # grava o .firebaserc
```

Publicar (e republicar sempre que mudar o código ou rodar `python build_db.py`):

```bash
gcloud run deploy medalhas --source . --region southamerica-east1 --allow-unauthenticated \
  --memory 1Gi --concurrency 40 --max-instances 3
firebase deploy --only hosting
```

Rode sempre os dois comandos, nessa ordem: `/api/overview` (dados da página inicial) e as páginas de
aluno e escola ficam até um dia no CDN do Firebase Hosting, e é o `firebase deploy` que limpa esse cache.
Sem ele, o site continuaria mostrando os números antigos. As páginas de perfil saem do `index.html` que
está dentro da imagem do Cloud Run: mudou o `index.html`, publique os dois. O `firebase deploy` roda
`npm run css` antes de publicar (`predeploy` no `firebase.json`), então precisa do `npm install` feito.

`--max-instances` limita o custo: cada instância tem seus próprios contadores de limite por IP.
Sem tráfego o Cloud Run desliga (custo zero, primeira visita depois disso demora alguns segundos).

**Domínio próprio:** no console do Firebase, *Hosting → Adicionar domínio personalizado*, e crie no
registrador do domínio (Registro.br, Cloudflare…) os registros `TXT` e `A` que ele mostrar. O
certificado HTTPS é emitido sozinho em algumas horas.

## Como a busca de escolas funciona

- Acentos, pontuação e ordem das palavras são ignorados ("MILITAR DE FORTALEZA, COLEGIO" = "Colégio Militar de Fortaleza").
- Abreviações e siglas são expandidas nos dados **e** no texto digitado
(`medalhas/dominio/escolas.py`):
  `EE` → escola estadual, `EMEF`, `EEEFM`, `ETEC`/`ETE` → escola técnica estadual, `PROFA` → professor,
  `IFAL` → instituto federal de Alagoas (todas as `IF<UF>`, `IFSUL`, `IFBAIANO`, `CEFET`…).
  Assim, "instituto federal de alagoas" traz também as escolas cadastradas como "IFAL".
- Grafias diferentes da mesma escola (mesmo município) são agrupadas em um único cartão.
- Para incluir uma sigla nova, adicione em `SIGLAS` ou `ABREVIACOES` e rode `python build_db.py`.

## Arquitetura

O código segue a **arquitetura hexagonal** (portas e adaptadores): as regras de negócio ficam no centro,
sem saber de banco, rede ou HTTP, e as dependências apontam sempre para dentro.

```
adaptadores (coletores, SQLite, HTTP)  ->  aplicacao (casos de uso, portas)  ->  dominio (regras)
```

```
build_db.py                    ponto de montagem: coletores + SQLite -> gerar_base
server.py                      ponto de montagem: SQLite (leitura) -> servidor HTTP
medalhas/
  config.py                    caminhos no disco (único módulo que os conhece) e endereço do site
  dominio/                     regras puras, sem I/O
    premiacao.py               a premiação (TypedDict), medalhas e UFs
    olimpiadas.py              catálogo das olimpíadas
    pontuacao.py               tabela do IMPA Tech, escala da nossa versão e métodos
    escolas.py                 siglas, abreviações e chave que agrupa grafias da mesma escola
    identidade.py              quais premiações são da mesma pessoa
    ranking.py                 ordenação e posição (empates dividem a posição)
    gamificacao.py             tiers e conquistas
    enderecos.py               endereços legíveis das páginas (/aluno/maria-souza-lima-al)
    texto.py                   normalização de nomes
  aplicacao/
    portas.py                  interfaces: Coletor, RepositorioPremiacoes, FonteDeLeitura, SessaoDeLeitura
    gerar_base.py              caso de uso: coletar -> reconhecer pessoas -> indexar -> gravar
  adaptadores/
    coletores/                 leitura das páginas oficiais (download com cache em cache/)
    sqlite/                    esquema, gravação, tabelas-resumo e consultas (site e API)
    http/                      servidor, site estático, API do site, limites por IP
      paginas.py               páginas de aluno/escola e das telas com título e resumo, e o sitemap
      imagens.py, fontes/      imagens de compartilhamento (og:image) de cada aluno, escola e do site
      api_v1/                  API pública: parâmetros, rotas, apresentação JSON, exportação, OpenAPI
web/
  index.html, styles.css       página única (Alpine.js, ECharts via CDN) e estilos próprios
  404.html                     página de endereço inexistente
  css/site.css                 classes do Tailwind, geradas por `npm run css` (entrada: css/entrada.css)
  js/util.js                   chamada à API, formatação, ícones
  js/graficos.js               gráficos, mapa, confete
  js/documentacao-api.js       conteúdo da página API & Dados
  js/app.js                    componente Alpine: rotas, estado e ações
tests/                         testes (unittest, sem dependências)
```

Decisões:
- **Leitura sem caso de uso intermediário.** As consultas do site e da API são relatórios (agregações,
  rankings, paginação) e passam direto pela porta `SessaoDeLeitura`. Uma camada a mais só repetiria as
  assinaturas. As regras que elas usam (pontuação, ranking, tiers) continuam no domínio.
- **Uma conexão por requisição.** O servidor abre uma `SessaoDeLeitura` por chamada à API e a fecha antes
  de enviar arquivos de exportação, para um cliente lento não ocupar uma vaga de consulta.
- **O HTTP não conhece o SQLite.** O `Servidor` recebe a fonte de leitura pronta (`server.py` faz a
  montagem); trocar o banco é escrever outro adaptador com a mesma porta.
- **Contrato público isolado.** O formato das respostas da API v1 fica só em `api_v1/apresentacao.py`.

## Testes

```bash
python -m unittest discover -s tests -t .
```

- `test_arquitetura.py`: confere a direção das dependências (o domínio não importa adaptadores nem faz I/O;
  o HTTP não importa o SQLite; e assim por diante).
- `test_dominio.py`: pontuação, identidade de alunos e escolas, ranking e gamificação.
- `test_adaptadores.py`: leitura das páginas oficiais, limites por IP e validação dos parâmetros da API.
- `test_integracao.py`: ponta a ponta com uma base pequena: coletor falso, SQLite num diretório temporário
  e servidor HTTP numa porta livre. Não usa a base real nem a internet.

## Padrão de código

- Python 3.10+, só biblioteca padrão. Nomes e comentários em português (o domínio é brasileiro); mensagens
  de commit em inglês ([Conventional Commits](https://www.conventionalcommits.org)).
- Linhas de até 120 caracteres; *type hints* nas funções públicas; docstring em todo módulo dizendo a
  responsabilidade dele.
- Comentários explicam o **porquê** (uma regra do edital, uma armadilha do site oficial), não o quê.
- SQL sempre com parâmetros (`?`); nomes de coluna interpolados vêm só de listas fixas do código.
