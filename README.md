# Medalhas

**[medalhas.online](https://medalhas.online)**: os medalhistas brasileiros das olimpíadas de conhecimento
reunidos em um só lugar, com busca, rankings, páginas de aluno, escola e cidade, API pública e dados abertos.

![Medalhas: quem brilhou nas olimpíadas do Brasil](https://medalhas.online/og/site.png)

Os resultados das olimpíadas científicas são públicos, mas ficam espalhados em dezenas de sites, PDFs e
tabelas, cada um num formato, muitos difíceis de achar. O Medalhas coleta essas listas oficiais, reconhece
quando duas premiações são da mesma pessoa ou da mesma escola, e deixa tudo pesquisável. Cada premiação
mantém o link da página oficial de onde veio, para conferência.

Hoje são **23 olimpíadas**, de **1979 a 2026**: cerca de **135 mil premiações** de **84 mil alunos**,
**23 mil escolas** e **4.300 cidades**.

> Projeto pessoal e independente, feito por **Pedro Neves**. Não tem vínculo com as olimpíadas, a SBM, o
> IMPA nem qualquer órgão público. Correções, remoção de dados e contato:
> **pedro.vasconcelosneves@gmail.com**.

## Sumário

- [Para que serve](#para-que-serve)
- [Rodar no seu computador](#rodar-no-seu-computador)
- [Fontes de dados](#fontes-de-dados)
- [Como os dados são tratados](#como-os-dados-são-tratados)
- [Pontuação](#pontuação)
- [O site](#o-site)
- [API pública (v1)](#api-pública-v1)
- [Publicar na internet](#publicar-na-internet-firebase-hosting--cloud-run)
- [Arquitetura](#arquitetura)
- [Testes](#testes)
- [Como contribuir](#como-contribuir)
- [Licença](#licença)

## Para que serve

| Quem | O que faz no Medalhas |
|---|---|
| **Aluno ou ex-aluno** | Procura o próprio nome e vê todas as medalhas num perfil só, com posição no ranking, nível, conquistas e imagem pronta para o story do Instagram. |
| **Família e escola** | Vê os medalhistas de uma escola ao longo dos anos, a posição dela no estado e no país, e exporta a lista. |
| **Professor e treinador** | Acompanha quem se destacou em cada olimpíada e nível, por estado, cidade ou escola. |
| **Candidato ao IMPA Tech** | Confere a pontuação das medalhas pela tabela oficial do edital (método *IMPA oficial*). |
| **Jornalista e gestor público** | Compara estados, cidades, redes pública e privada, e a evolução por ano. |
| **Pesquisador** | Baixa a base inteira ou um recorte em CSV/JSON, com a fonte oficial de cada registro. |
| **Programador** | Usa a [API pública](#api-pública-v1), sem cadastro nem chave, com especificação OpenAPI. |
| **IAs e buscadores** | Leem um resumo em texto de cada página (sem JavaScript), o `sitemap.xml` e o [`llms.txt`](https://medalhas.online/llms.txt). |

## Rodar no seu computador

> Pela [licença](#licença), rodar o projeto é permitido para desenvolver e testar contribuições. Publicar o
> site ou a API exige autorização do autor.

Requer só **Python 3.10+**. As dependências são opcionais:

| Para | Instale | Sem ela |
|---|---|---|
| Imagens de compartilhamento (cartão do link e story) | `pip install -r requirements.txt` (Pillow) | o resto funciona; as imagens dão 404 |
| Ler os PDFs da OBQ, OMIF e Itabirana ao gerar a base | `pip install pypdf` | essas três olimpíadas ficam de fora (as outras entram) |
| Mudar classes de CSS do site | `npm install` (Tailwind) | o CSS já gerado (`web/css/site.css`) continua valendo |

```bash
python build_db.py   # baixa as listas oficiais e gera data/medalhas.db (alguns minutos na 1ª vez)
python server.py     # abre o site em http://localhost:8000
```

- `python build_db.py --refresh` apaga o cache e baixa tudo de novo (use quando sair um ano novo). Sem
  `--refresh`, as páginas já baixadas ficam em `cache/` e a base é regerada em segundos.
- `python server.py --port 9000 --no-browser` muda a porta e não abre o navegador.
- `python server.py --host 0.0.0.0` aceita conexões de outras máquinas; veja a
  [proteção contra excesso de requisições](#proteção-contra-excesso-de-requisições).

## Fontes de dados

Cada coletor lê a página ou o PDF oficial e devolve as premiações num formato único. As edições são
descobertas nas páginas de índice de cada fonte, então anos novos entram sem mudar código. Uma fonte fora do
ar não derruba a geração da base: ela é avisada no fim e as outras entram.

| Olimpíada | Anos | Origem | O que a lista informa |
|---|---|---|---|
| **OBMEP** | 2005–2025 (sem 2020) | `premiacao.obmep.org.br` | nome, escola, município, UF, nível, medalha, rede e esfera; escolas privadas desde 2017 |
| **OBM** | 1979–2025 | `www.obm.org.br/premiados-obm-<ano>/` | nome, cidade/UF, nível, nota, prêmio (inclui menção honrosa e os prêmios antigos, como "1º Prêmio") |
| **OBI** | 2005–2025 | `olimpiada.ic.unicamp.br/passadas/OBI<ano>/qmerito/…` | nome, escola, cidade, UF, modalidade/nível, medalha, honra ao mérito |
| **OBQ** | 2025–2026 | `obquimica.org/noticias/resultado[-final]-obq-<ano>` → PDF por modalidade | estado, nome, série, escola, nota e faixa (ouro… menção) |
| **OMIF** | 2018, 2020–2026 | `omif.com.br/imprensa/<ano>` → PDFs | nome, instituição (instituto + campus) e medalha |
| **Itabirana (OITM)** | 2018–2025 (sem 2023) | `olimpiadaitabirana.com.br/noticias/premiados<ano>/` → PDFs | nome, nível, escola, faixa e a etapa "Elas em Destaque"; cidade só em 2018–2019 |
| **IMO** | 1981–2026 | `imo-official.org/results/team/year/<ano>/country/BRA/` | nome, nota, medalha, menção honrosa |
| **Internacionais pela OBM** | vários | `www.obm.org.br/resultados-…/` | nome, cidade/UF e prêmio: Ibero (OIM), Cone Sul, EGMO, APMO, IMC, PAGMO, OMCPLP, IGO, IMSC, OIMU, CIIM, Olimpíada de Maio, OMOP e Concurso Galois-Noether |
| **EGOI** (meninas, informática) | 2021–2026 | `stats.egoi.org/countries/BRA/results/` | nome, nota e medalha (lida pela cor da linha) |
| **IOAI** (inteligência artificial) | 2025–2026 | `ioai-official.org/…/results-<ano>/` | nome, nota, medalha e menção honrosa |

Os PDFs (OBQ, OMIF, Itabirana) são lidos pela **posição de cada texto na página** (`coletores/pdf.py`),
porque a ordem do texto extraído nem sempre é a ordem visual: rótulos de faixa (OURO, PRATA…) saem fora do
lugar, colunas vêm grudadas e nomes de escola quebram de linha. Cada coletor documenta as armadilhas do
seu formato no início do arquivo.

### O que não dá para coletar (ainda)

| Olimpíada | Por quê |
|---|---|
| **ONC** (Ciências) | O resultado só aparece pesquisando escola por escola, pelo código INEP; não há lista completa publicada. |
| **OBA** (Astronomia) | Só consulta individual, digitando o nome como está no cadastro; não há lista publicada. |
| **OBR** (Robótica) | Não há lista de premiados individuais; a prova prática é por equipe. |
| **OBFEP**, **ONHB**, **Canguru** | Site fora do ar na coleta ou sem lista pública de premiados. |
| **Olimpíadas estaduais** | A maioria não publica lista. A Olimpíada Alagoana de Matemática (OAM), por exemplo, só divulga números e alguns nomes. São Paulo (OMASP/OMESP) publica PDFs, ainda não coletados. |
| **OBQ antes de 2025** | O link do resultado nacional de 2024 está quebrado no site da OBQ e os anos anteriores não estão mais publicados; os sites estaduais trazem só os premiados de cada estado. |
| **Itabirana 2023** | O PDF é uma imagem escaneada, sem texto. |
| **OMIF 2019** e **2024** | 2019 só publicou os classificados; não houve edição em 2024 (a de 2023 terminou em 2024). |
| **IOAI 2024** | Nenhum brasileiro premiado nos certificados publicados. |

Se você organiza uma olimpíada ou tem a lista de premiados de uma delas, [entre em contato](#como-contribuir).

## Como os dados são tratados

As listas oficiais não têm CPF, data de nascimento nem código de escola: só nomes escritos de jeitos
diferentes. Esta seção explica como o Medalhas decide o que é a mesma pessoa, a mesma escola e a mesma cidade.
As regras ficam em `medalhas/dominio/` e são aplicadas ao gerar a base (`aplicacao/gerar_base.py`), nesta
ordem: correções à mão → identidade dos alunos → cidade das escolas → filtro de meninas → indexação.

### Alunos: quem é a mesma pessoa

O aluno é identificado por **nome (sem acento) + estado**: o id `MARIA SOUZA LIMA|AL` vira o endereço
`/aluno/maria-souza-lima-al`. Por cima disso (`dominio/identidade.py`):

- **Mesmo nome em estados diferentes** vira uma pessoa só quando: o nome é raro (o número esperado de
  homônimos, estimado pela frequência de cada palavra entre todos os nomes, é baixo); as premiações cabem
  numa carreira escolar (até 12 anos); e não há a mesma olimpíada no mesmo ano nos dois estados (aí são
  homônimos). Alunos de ponta mudam de estado (vão estudar em Fortaleza, por exemplo), e essa regra os junta.
- **Premiações sem estado** (IMO, EGOI, IOAI, Itabirana de 2020 em diante) vão para a pessoa de mesmo nome:
  - em olimpíada de alto nível (OBM e internacionais), quando só existe uma pessoa com aquele nome;
  - nas demais, só quando o nome é raro **ou** quando a pessoa de mesmo nome foi premiada **na mesma
    escola** (a comparação aceita abreviações como "EE MAJ LAGE" = "Escola Estadual Major Lage" e ignora
    palavras genéricas como "escola" e "estadual");
  - sem isso, viram um perfil "sem estado". Melhor um perfil a mais do que dar a medalha para outra pessoa.
- **Nomes abreviados** em listas internacionais ("Enzo Holanda") são completados quando há um único
  medalhista compatível ("Enzo Holanda Sampaio"). Nas internacionais de informática (EGOI, IOAI), os
  medalhistas da OBI também contam, porque é de lá que essas alunas e alunos vêm.
- O estado do perfil é o da premiação **mais recente**; se a pessoa ganha uma medalha nova em outro estado,
  o endereço do perfil muda.
- O nome exibido prefere a grafia da OBM, que publica com acentos e maiúsculas certas.

### Escolas

Cada escola tem uma **chave**: palavras do nome + cidade + estado (`dominio/escolas.py`).

- As palavras são normalizadas: sem acento, sem pontuação e em qualquer ordem ("MILITAR DE FORTALEZA,
  COLEGIO" = "Colégio Militar de Fortaleza").
- Siglas e abreviações são expandidas nos dados e no texto digitado: `EE` → escola estadual, `EMEF`,
  `EEEFM`, `ETEC`/`ETE`, `PROFA` → professor, `IFAL` → instituto federal de Alagoas (todas as `IF<UF>`,
  `IFSUL`, `IFBAIANO`, `CEFET`…). Assim, "instituto federal de alagoas" encontra também "IFAL".
- Cidade e estado entram na chave porque nomes se repetem muito ("Escola Estadual Tiradentes" existe em
  dezenas de cidades).
- O nome exibido é a grafia mais frequente. Numa escola que mudou de nome, é a mais recente.

Nem toda lista traz escola, cidade e estado:

| Situação | Olimpíadas | Como é tratada |
|---|---|---|
| Escola, cidade e estado | OBMEP, OBI, Itabirana 2018–2019 | chave completa e página de escola normal |
| Sem escola | OBM, IMO e internacionais | a premiação não conta para nenhuma escola (conta para o aluno, a cidade e o estado, quando há) |
| Escola e estado, sem cidade | OBQ, OMIF, parte da IMC | o site procura a cidade (abaixo); se não achar, a escola fica com estado e sem cidade |
| Escola sem estado | Itabirana 2020–2025 | não cria página de escola: o mesmo nome em estados diferentes é outra escola. O nome continua na premiação e na busca, sem link. Se o aluno for identificado, a premiação herda o estado dele |

Para achar a cidade de uma escola que veio sem ela:
1. se o mesmo nome de escola aparece numa **única cidade daquele estado** nas outras listas, usa essa cidade
   ("Liceu Jardim", SP → Santo André); com duas ou mais cidades possíveis ("Colégio Etapa"), não chuta;
2. senão, se o nome traz o campus e ele é uma cidade conhecida do estado, usa essa cidade
   ("IFES – CAMPUS VITORIA" → Vitória).

### Cidades

A cidade é o par município + estado, como aparece nas listas (`/cidade/vitoria-es`). O nome exibido prefere a
grafia com acento e limpa pontuação solta ("São Paulo\"" → "São Paulo"). O ranking de cidades soma as
premiações com cidade conhecida; os "melhores alunos da cidade" contam só as medalhas ganhas lá.

### Filtro de meninas

As listas oficiais não informam o sexo, e adivinhar pelo nome erra. Por isso o filtro "Meninas"
(`sexo=F` na API) inclui só quem **certamente** é menina (`dominio/sexo.py`):

- premiadas em olimpíada exclusiva para meninas: **EGMO**, **PAGMO** e **EGOI**;
- premiadas na etapa **"Elas em Destaque"** da Olimpíada Itabirana;
- alunas que pediram para entrar (lista `MENINAS_CONFIRMADAS`).

Para essas alunas, **todas** as premiações contam (OBMEP, OBM, OBI…). Outras meninas medalhistas ficam fora
do filtro, mas aparecem normalmente no ranking geral. O sexo não é publicado por pessoa: ele não aparece nos
perfis, nas respostas da API nem nos arquivos exportados.

### Correções à mão

Erros das listas oficiais que nenhuma regra resolve são corrigidos em três listas, sempre com um comentário
dizendo a origem do erro:

| Lista | Arquivo | Para |
|---|---|---|
| `GRAFIAS_CORRIGIDAS` | `dominio/identidade.py` | nome escrito errado numa lista, que separava a pessoa em dois perfis (ex.: "Sofia Azeredo de Moura Moteiro" na OBMEP 2017) |
| `ESCOLAS_RENOMEADAS` | `dominio/escolas.py` | escola que mudou de nome (CEFET-ES → Ifes Vitória; Instituto de Tecnologia ORT → Escola ORT) |
| `MENINAS_CONFIRMADAS` | `dominio/sexo.py` | alunas que pediram para entrar no filtro de meninas |

Depois de uma correção em `GRAFIAS_CORRIGIDAS`, o endereço do perfil com o nome errado continua valendo:
redireciona (301) para o perfil certo, então links já compartilhados não quebram.

Achou um erro? Veja [como contribuir](#como-contribuir).

## Pontuação

No topo do site há um seletor global (também aceito na URL e na API como `?metodo=`) com três métodos. A
escolha vale para rankings, mapa, perfis e níveis.

| Método | `metodo` | Como conta |
|---|---|---|
| IMPA · todos os níveis | `impa` (padrão) | Tabela do IMPA Tech aplicada às medalhas de qualquer nível das olimpíadas que o edital aceita |
| IMPA oficial | `impa3` | Exatamente o que o [edital do IMPA Tech 2027, item 6.1](https://impatech.edu.br/wp-content/uploads/2026/10/Edital-IMPA_Tech_RJ-NE_2027_vs-1.0_-aprovada_site.pdf) aceita |
| Medalhas (nossa versão) | `site` | Escala própria por dificuldade (abaixo); vale para todas as 23 olimpíadas |

Tabela do edital do IMPA Tech 2027 (igual à de 2026):

| Olimpíada | Nível aceito | Ouro | Prata | Bronze |
|---|---|---|---|---|
| OBMEP | Nível 3, premiação nacional | 18 | 6 | 2 |
| OBM | Nível 3 | 18 | 6 | 2 |
| OBFEP | Níveis B e/ou C (não coletada) | 9 | 3 | 1 |
| OBQ | Modalidades A e/ou B | 9 | 3 | 1 |
| OBI | Programação, níveis 1 e/ou 2 | 9 | 3 | 1 |

No método *IMPA oficial*, o filtro de nível fica travado nos níveis do edital. Olimpíadas fora do edital
(IMO, OMIF, Itabirana…) valem zero nos dois métodos do IMPA; no ranking por pontos, quem tem zero fica de fora.
Para vê-las, use "Nossa versão" ou ordene por "Quadro de medalhas".

Escala da nossa versão (`ESCALA_SITE` em `dominio/pontuacao.py`; as relações entre os degraus são
conferidas ao importar o módulo):

| Degrau | Olimpíadas | Ouro | Prata | Bronze | Menção |
|---|---|---|---|---|---|
| Entrada | Galois-Noether | 20 | 12 | 6 | – |
| Regional | Itabirana ("Elas em Destaque" vale bronze) | 80 | 48 | 24 | – |
| OBMEP | OBMEP, OBI, OBQ, OMIF, Maio, OMOP | 100 | 60 | 30 | – |
| OBM | OBM, OMCPLP, IGO, IMSC, OIMU, CIIM | 200 | 150 | 110 | 40 |
| Cone Sul | Cone Sul, PAGMO | 260 | 190 | 140 | 50 |
| Ibero | Ibero, EGMO, APMO, IMC, EGOI, IOAI | 320 | 240 | 170 | 60 |
| IMO | IMO | 600 | 400 | 280 | 100 |

Regras da escala: ouro OBM = 2× ouro OBMEP; bronze OBM > ouro OBMEP; bronze Ibero > prata OBM; bronze IMO >
prata Ibero; Cone Sul entre OBM e Ibero; regionais entre a entrada e a OBMEP. Os prêmios antigos da OBM
("1º Prêmio"…) valem como bronze.

Os totais e as posições nacional e estadual em cada método são pré-calculados ao gerar a base. Os níveis
(Estreante → Promessa → Talento → Destaque → Elite → Mestre → Lenda) têm limites próprios por método
(`dominio/gamificacao.py`), e há conquistas como *Hat-trick Dourado*, *Dupla Coroa* e *Grand Slam*.

## O site

Página única (Alpine.js, ECharts, Lucide e canvas-confetti via CDN) servida pelo `server.py`.

- **Busca** por pessoa, escola (com siglas) ou tudo. Enquanto você digita, aparecem os alunos e escolas mais
  premiados que casam com o texto (`/api/sugestoes`); a página `/busca` mostra todas as premiações, com
  filtros.
- **Rankings** de alunos, escolas, estados e cidades, filtráveis por estado, olimpíada, área, período,
  nível, rede e meninas, ordenados por pontos, quadro de medalhas (ouro → prata → bronze) ou total.
- **Mapa do Brasil** por pontos, ouros, premiações ou alunos.
- **Perfis** de aluno e escola com posição nacional e estadual, nível, conquistas e gráfico por ano;
  **páginas de cidade** com medalhas, posições e as escolas e alunos com mais medalhas de lá.
- **Exportar** na busca, nos rankings e nos perfis (CSV, CSV para Excel ou JSON); a página **API & Dados**
  (`/dados`) documenta a API, testa cada rota ao vivo e baixa a base inteira.
- **Story do Instagram:** o botão *Story* dos perfis gera uma imagem vertical com o link do perfil.

O CSS do Tailwind é gerado de antemão em `web/css/site.css`, que fica no repositório: para rodar o site basta
o Python. Só quem muda classes no HTML/JS precisa do Node (`npm install`, depois `npm run css` ou
`npm run css:watch`).

### Endereços e buscadores

Cada aluno, escola e cidade tem endereço próprio, que o Google indexa: `/aluno/maria-souza-lima-al`,
`/escola/em-benedita-braga-cobra-borda-da-mata-mg` (nome + município + UF) e `/cidade/sao-paulo-sp`. As
telas também: `/ranking/alunos`, `/ranking/escolas`, `/ranking/estados`, `/ranking/cidades`, `/estados`,
`/dados`, `/sobre` e `/busca?q=...` (esta fora do Google). Links antigos com `#` continuam funcionando.

- Ao abrir qualquer endereço, o servidor (`adaptadores/http/paginas.py`) entrega o `index.html` com título,
  descrição, endereço canônico, dados estruturados (JSON-LD) e um resumo em texto dentro de `<noscript>`,
  para robôs de IA que não rodam JavaScript. No site, a troca de página acontece sem recarregar. Os títulos
  das telas estão em `paginas.py` (`TELAS`) e em `web/js/app.js` (`TITULOS`); um teste confere que batem.
- Endereço inexistente mostra `web/404.html` com status 404. Se uma página não puder ser montada (limite de
  acessos, servidor ocupado ou erro interno), o servidor responde com `web/erro.html` preenchida com o código e
  a explicação; a API continua respondendo em JSON.
- Imagens de compartilhamento (`og:image`, 1200×630) de cada aluno e escola são desenhadas na hora
  (`adaptadores/http/imagens.py`, com Pillow); as demais páginas usam `/og/site.png`. Fontes: Inter e
  Space Grotesk (licença OFL), em `adaptadores/http/fontes/`.
- `/sitemap.xml` lista todas as páginas (um arquivo a cada 40 mil endereços em `/sitemaps/`). `web/robots.txt`
  libera buscadores e IAs, e `web/llms.txt` explica o site e a API para IAs.
- O endereço canônico usa `https://medalhas.online`; para outro domínio, defina `MEDALHAS_URL`.
- O mapa usa os contornos dos estados do projeto [Click That 'Hood](https://github.com/codeforgermany/click_that_hood)
  (`brazil-states.geojson`, licença MIT), simplificados e salvos em `web/brasil-uf.json`.

### API interna (usada pelas páginas do site)

Pode mudar sem aviso; para integrações use a [API pública](#api-pública-v1).

| Rota | O que retorna |
|---|---|
| `/api/busca?q=&campo=nome\|escola\|tudo&…filtros` | premiações que casam com a busca |
| `/api/sugestoes?q=&campo=` | até 8 alunos e escolas mais premiados que casam com o texto (lista enquanto digita) |
| `/api/ranking?tipo=alunos\|escolas\|estados\|cidades&ordem=xp\|medalhas\|total&…filtros&offset=` | ranking paginado |
| `/api/aluno`, `/api/escola`, `/api/cidade` com `?endereco=` (ou `?id=`) | perfil completo |
| `/api/overview` | totais, série histórica, destaques, estados, catálogo de olimpíadas e níveis |

Todas aceitam `metodo=impa|impa3|site`; o campo `xp` das respostas é a pontuação no método pedido.

## API pública (v1)

Acesso livre, sem cadastro e sem chave. Respostas em JSON (UTF-8) e CORS liberado. A documentação completa,
com exemplos em cURL, Python e JavaScript e um botão para testar cada rota, está em
[medalhas.online/dados](https://medalhas.online/dados). A especificação
[OpenAPI 3.1](https://medalhas.online/api/v1/openapi.json) importa no Postman, Insomnia ou Swagger Editor.

| Rota | Para quê |
|---|---|
| `GET /api/v1/alunos?nome=` | buscar alunos pelo nome (com as premiações de cada um) |
| `GET /api/v1/alunos/{id}` | um aluno e todas as premiações dele |
| `GET /api/v1/escolas?nome=` | buscar escolas pelo nome ou sigla (IFAL, ETEC…) |
| `GET /api/v1/escolas/{id}` | resumo de uma escola |
| `GET /api/v1/escolas/{id}/medalhistas` | todos os alunos premiados de uma escola (até 500 por página) |
| `GET /api/v1/premiacoes` | todas as premiações, filtradas ou não, paginadas (até 1000 por página) |
| `GET /api/v1/ranking/{alunos\|escolas\|estados\|cidades}` | rankings com os mesmos critérios do site |
| `GET /api/v1/exportar` | baixar premiações ou rankings em CSV ou JSON, inteiros ou filtrados |
| `GET /api/v1/olimpiadas` | olimpíadas, níveis e valores aceitos nos filtros |
| `GET /api/v1` | índice com rotas, exemplos e limites atuais |

Ids vão no caminho codificados para URL: o aluno `ERICK AKIRA KOGA|SP` vira
`/api/v1/alunos/ERICK%20AKIRA%20KOGA%7CSP` (`encodeURIComponent` no JavaScript, `quote(id, safe="")` no Python).

**Filtros comuns** (valem em todas as consultas e na exportação): `uf`, `municipio`, `competicao`, `area`,
`medalha`, `nivel`, `ano`, `ano_de`, `ano_ate`, `rede` e `sexo` (`F`: ver [filtro de meninas](#filtro-de-meninas)).
`competicao` e `nivel` aceitam vários valores separados por vírgula. Valor inválido volta com erro 400
explicando o que corrigir. `metodo` muda a ordem; os pontos dos três métodos vêm sempre.

### Exemplos

```bash
# medalhas de um aluno: buscar pelo nome devolve o id e as premiações
curl "https://medalhas.online/api/v1/alunos?nome=erick+akira+koga"

# confirmar uma medalha: "premiacoes_encontradas" conta só as do recorte (aqui, OBM 2023);
# "medalhas" continua sendo o total da carreira
curl "https://medalhas.online/api/v1/alunos?nome=erick+akira+koga&competicao=OBM&ano=2023&premiacoes=0"

# as 10 cidades de Minas Gerais com mais medalhas na OBMEP, pela nossa pontuação
curl "https://medalhas.online/api/v1/ranking/cidades?uf=MG&competicao=OBMEP&metodo=site&limite=10"

# ranking das meninas na matemática
curl "https://medalhas.online/api/v1/ranking/alunos?sexo=F&area=Matem%C3%A1tica&metodo=site"
```

Todos os medalhistas de uma escola, em Python:

```python
import requests
from urllib.parse import quote

BASE = "https://medalhas.online/api/v1"
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

Cada aluno traz `medalhas`, `pontos` e `posicao` (nacional e estadual) nos três métodos, e cada premiação
traz `olimpiada`, `ano`, `nivel`, `medalha`, `escola`, `municipio`, `uf`, `pontos` e `fonte` (a página oficial).

### Baixar os dados

```bash
curl --compressed -OJ "https://medalhas.online/api/v1/exportar?formato=csv"             # base inteira (CSV)
curl --compressed -OJ "https://medalhas.online/api/v1/exportar?formato=csv&separador=;" # para o Excel em português
curl --compressed -OJ "https://medalhas.online/api/v1/exportar?formato=json"            # base inteira (JSON)
curl --compressed -OJ "https://medalhas.online/api/v1/exportar?competicao=OBM&uf=SP"    # só um recorte
curl --compressed -OJ "https://medalhas.online/api/v1/exportar?conjunto=cidades"        # ranking completo de cidades
```

- O CSV é UTF-8 com BOM (o Excel reconhece os acentos); `separador=;` abre direto no Excel em português.
- A base inteira trafega compactada quando o cliente aceita gzip (`curl --compressed`, navegadores,
  `requests`). O arquivo é gerado uma vez por versão da base e reaproveitado (`data/exportar/`).
- Exportações filtradas são geradas num arquivo temporário, e a conexão com a base é liberada antes do envio.

### Proteção contra excesso de requisições

Por padrão o servidor aceita conexões só da própria máquina. A proteção (`adaptadores/http/limites.py`)
funciona por IP:

| Camada | Padrão | Ao exceder | Opção |
|---|---|---|---|
| Consultas à API pública | 60/min e 2000/dia | 429 + `Retry-After` | `--rate-limit`, `--daily-limit` |
| Exportações (downloads) | 5/hora e 10/dia | 429 + `Retry-After` | `--export-limit` |
| API usada pelo site | 600/min | 429 + `Retry-After` | `--site-rate-limit` |
| Insistir depois do limite | 30 recusas em 60 s | IP bloqueado por 10 min em todo o site | — |
| Conexões abertas por IP | 12 (64 no total) | conexão recusada | `--max-connections-per-ip` |
| Consultas à base ao mesmo tempo | 8 | espera até 10 s, depois 503 | `--max-concurrent` |
| Conexão parada (sem enviar nada) | 20 s | conexão encerrada | — |

- O limite por minuto aceita rajadas curtas e recarrega aos poucos. `0` remove um limite.
- Toda resposta traz `X-RateLimit-Limit` e `X-RateLimit-Remaining`; a recusa traz `Retry-After` e
  `{"erro": "...", "tente_em_segundos": N}`.
- Textos de busca têm no máximo 100 caracteres e 8 palavras, e as páginas têm tamanho máximo.
- Atrás de um proxy reverso, rode com `--trust-proxy` para usar o IP real de `X-Forwarded-For`. Sem proxy, não
  use: qualquer um poderia forjar o cabeçalho e fugir do limite.

## Publicar na internet (Firebase Hosting + Cloud Run)

> Publicar o site exige autorização do autor (ver [licença](#licença)). Esta seção documenta como o
> medalhas.online é publicado.

```
visitante -> medalhas.online (Firebase Hosting: HTTPS, CDN, arquivos de web/)
                 └── /api/**, /aluno/**, /escola/**, /cidade/**, /ranking/**, /estados, /dados, /busca,
                     /sobre, /og/**, /sitemap.xml, /sitemaps/**
                       ->  Cloud Run "medalhas" (server.py + data/medalhas.db dentro da imagem)
```

- `Dockerfile`: imagem do servidor, com a base dentro (só leitura).
- `firebase.json`: publica `web/` e repassa a API, as páginas e o sitemap ao Cloud Run em `southamerica-east1`.
- O servidor roda com `--trust-proxy`: lê o IP do visitante em `X-Forwarded-For` e o domínio em
  `X-Forwarded-Host`.

```bash
gcloud run deploy medalhas --source . --region southamerica-east1 --allow-unauthenticated
firebase deploy --only hosting
```

Rode sempre os dois, nessa ordem, depois de mudar o código ou rodar `python build_db.py`: as páginas e o
`/api/overview` ficam até um dia no CDN, e é o `firebase deploy` que limpa esse cache. O `firebase deploy`
roda `npm run css` antes (`predeploy`), então precisa do `npm install` feito. Sem tráfego, o Cloud Run
desliga (custo zero; a primeira visita depois demora alguns segundos).

## Arquitetura

O código segue a **arquitetura hexagonal** (portas e adaptadores): as regras de negócio ficam no centro, sem
saber de banco, rede ou HTTP, e as dependências apontam sempre para dentro.

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
    olimpiadas.py              catálogo das olimpíadas (área, escala, regras do IMPA)
    pontuacao.py               tabela do IMPA Tech, escala da nossa versão e métodos
    escolas.py                 siglas, chave da escola, escolas renomeadas, cidade das escolas sem ela
    identidade.py              quem é a mesma pessoa, grafias corrigidas à mão
    sexo.py                    filtro de meninas
    ranking.py                 ordenação e posição (empates dividem a posição)
    gamificacao.py             níveis e conquistas
    enderecos.py               endereços legíveis (/aluno/…, /escola/…, /cidade/…)
    texto.py                   normalização de nomes
  aplicacao/
    portas.py                  interfaces: Coletor, RepositorioPremiacoes, FonteDeLeitura, SessaoDeLeitura
    gerar_base.py              caso de uso: coletar -> corrigir -> identificar -> indexar -> gravar
  adaptadores/
    coletores/                 um módulo por fonte; http.py baixa com cache em cache/, pdf.py lê PDFs
    sqlite/                    esquema, gravação, tabelas-resumo e consultas (site e API)
    http/                      servidor, site estático, API do site, limites por IP
      paginas.py               páginas com título e resumo para buscadores, e o sitemap
      imagens.py, fontes/      imagens de compartilhamento e de story
      api_v1/                  API pública: parâmetros, rotas, apresentação JSON, exportação, OpenAPI
web/
  index.html, styles.css       página única e estilos próprios
  404.html, erro.html          endereço inexistente; modelo das páginas de erro do servidor (429, 503, 500)
  css/site.css                 classes do Tailwind, geradas por `npm run css`
  js/util.js, graficos.js      chamada à API, formatação, ícones; gráficos, mapa, confete
  js/documentacao-api.js       conteúdo da página API & Dados
  js/app.js                    componente Alpine: rotas, estado e ações
tests/                         testes (unittest, sem dependências)
```

Decisões:
- **Leitura sem caso de uso intermediário.** As consultas do site e da API são relatórios (agregações,
  rankings, paginação) e passam direto pela porta `SessaoDeLeitura`; as regras que usam (pontuação, ranking,
  níveis) continuam no domínio.
- **Uma conexão por requisição**, fechada antes de enviar arquivos de exportação.
- **O HTTP não conhece o SQLite.** O `Servidor` recebe a fonte de leitura pronta (`server.py` faz a montagem).
- **Contrato público isolado.** O formato das respostas da API v1 fica só em `api_v1/apresentacao.py`.
- **Ids estáveis.** A ordem de coleta define o id de cada premiação: olimpíadas novas entram no fim do
  catálogo para não mudar os ids das que já existem.

## Testes

```bash
python -m unittest discover -s tests
```

- `test_arquitetura.py`: direção das dependências (o domínio não importa adaptadores nem faz I/O; o HTTP não
  importa o SQLite…).
- `test_dominio.py`: pontuação, identidade de alunos, escolas, filtro de meninas, ranking e gamificação.
- `test_adaptadores.py`: leitura das páginas e PDFs oficiais, limites por IP e validação da API.
- `test_integracao.py`: ponta a ponta com uma base pequena (coletor falso, SQLite temporário e servidor HTTP
  numa porta livre). Não usa a base real nem a internet.

## Como contribuir

**Correção de dados** (nome errado, perfis duplicados, escola que mudou de nome, pedido de remoção ou para
entrar no filtro de meninas): escreva para **pedro.vasconcelosneves@gmail.com** ou abra uma *issue* com o
link do perfil no site. Pedidos de remoção são atendidos.

**Código** (pull requests são bem-vindos):

1. Faça um *fork* e uma branch.
2. Rode os testes (`python -m unittest discover -s tests`) e, se mexer em coleta, gere a base
   (`python build_db.py`) e confira o que mudou.
3. Abra o pull request explicando o porquê da mudança.

Para **adicionar uma olimpíada**:
1. cadastre-a no fim de `CATALOGO` (`dominio/olimpiadas.py`): nome, área, degrau da escala e, se o edital do
   IMPA aceitar, `tabela_impa` e `niveis_impa`;
2. escreva o coletor em `adaptadores/coletores/<sigla>.py`, com uma função `coletar(log)` que devolve
   premiações (`dominio/premiacao.py`), e registre-o em `coletores/__init__.py` (um teste acusa se faltar);
3. rode `python build_db.py`. Os filtros do site e da API são montados a partir dos dados.

**Padrão de código:**
- Python 3.10+, só biblioteca padrão no servidor. Nomes e comentários em português (o domínio é
  brasileiro); mensagens de commit em inglês ([Conventional Commits](https://www.conventionalcommits.org)).
- Linhas de até 120 caracteres; *type hints* nas funções públicas; docstring em todo módulo dizendo a
  responsabilidade dele.
- Comentários explicam o **porquê** (uma regra do edital, uma armadilha do site oficial), não o quê.
- SQL sempre com parâmetros (`?`); nomes de coluna interpolados vêm só de listas fixas do código.

## Licença

**Código:** todos os direitos reservados. O código está aberto para leitura e contribuições: você pode
fazer *fork* para mandar *pull requests* e rodar localmente para desenvolver e testar uma contribuição.
Publicar ou hospedar o site, a API ou outro serviço baseado neste código, redistribuí-lo ou usá-lo em outro
projeto exige autorização prévia e por escrito do autor. Veja o arquivo [`LICENSE`](LICENSE).

**Dados:** as premiações vêm de listas oficiais públicas, e cada registro traz o link da sua fonte. Você pode
baixá-las e usá-las pelo site e pela API, citando o Medalhas e a fonte oficial. Para correção ou remoção de
dados, escreva para pedro.vasconcelosneves@gmail.com.
