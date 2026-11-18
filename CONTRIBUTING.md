# Como contribuir com o Medalhas

Obrigado pelo interesse! O Medalhas reúne as premiações das olimpíadas de conhecimento do Brasil a partir das
listas oficiais, e quase toda melhoria vem de alguém que achou um erro, conhece uma olimpíada que falta ou teve
uma ideia melhor para uma regra. Este guia diz como ajudar em cada caso.

Antes de começar, leia a [licença](LICENSE): o código está aberto para leitura e contribuições (fork para
mandar pull requests e rodar localmente para desenvolver), mas publicar outra cópia do site ou da API exige
autorização do autor. Ao contribuir, você concorda com os termos da seção 3 dela.

## Sumário

- [Jeitos de ajudar](#jeitos-de-ajudar)
- [Correção de dados](#correção-de-dados)
- [Sugestões e problemas](#sugestões-e-problemas)
- [Preparar o ambiente](#preparar-o-ambiente)
- [Adicionar uma olimpíada](#adicionar-uma-olimpíada)
- [Melhorar a lógica (identidade, escolas, pontuação)](#melhorar-a-lógica-identidade-escolas-pontuação)
- [Mexer no site](#mexer-no-site)
- [Mandar um pull request](#mandar-um-pull-request)
- [Padrão de código](#padrão-de-código)
- [Privacidade](#privacidade)

## Jeitos de ajudar

| Você quer... | Faça |
|---|---|
| Corrigir um dado (nome errado, perfil dividido, escola, remoção) | Abra uma *issue* ou escreva para o e-mail do projeto ([Correção de dados](#correção-de-dados)) |
| Sugerir uma ideia, relatar um problema no site | Abra uma *issue* ([Sugestões e problemas](#sugestões-e-problemas)) |
| Incluir uma olimpíada que falta | *Issue* com a fonte oficial, ou um pull request com o coletor ([Adicionar uma olimpíada](#adicionar-uma-olimpíada)) |
| Melhorar uma regra (quem é a mesma pessoa, escolas, pontuação) | *Issue* com exemplos e, de preferência, um pull request com testes e números ([Melhorar a lógica](#melhorar-a-lógica-identidade-escolas-pontuação)) |
| Melhorar o site, a API ou o código | Pull request ([Mandar um pull request](#mandar-um-pull-request)) |

Para mudanças grandes (uma regra nova, uma reorganização do código, uma tela nova), abra uma *issue* antes para
combinar o caminho. Evita trabalho que não seria aceito.

## Correção de dados

Os dados vêm das listas oficiais, e o Medalhas não altera o que elas publicam. O que dá para corrigir é como as
premiações são reunidas e exibidas:

- **perfil dividido**: a mesma pessoa aparece em dois perfis (nome abreviado ou escrito diferente numa lista);
- **perfis juntados por engano**: duas pessoas diferentes no mesmo perfil;
- **nome** com grafia errada na lista, **escola** que mudou de nome, **cidade** errada;
- **filtro de meninas**: aluna premiada que quer aparecer no filtro;
- **remoção**: a própria pessoa (ou o responsável, se for menor de idade) pode pedir para sair. Pedidos de
  remoção são sempre atendidos; por e-mail, sem precisar explicar o motivo em público.

Mande **o link do perfil no site** (ex.: `https://medalhas.online/aluno/...`) e diga o que está errado. Se
souber, aponte a lista oficial que confirma (cada premiação no site tem o link da fonte). Contato:
**pedro.vasconcelosneves@gmail.com**.

Por dentro, essas correções viram uma linha em `GRAFIAS_CORRIGIDAS` (`medalhas/dominio/identidade.py`, nome
errado → nome certo, por estado ou por olimpíada e ano) ou em `ESCOLAS_RENOMEADAS`
(`medalhas/dominio/escolas.py`). Os endereços antigos continuam funcionando e levam ao perfil certo. Um pull
request com a linha nova e um teste também é bem-vindo; o critério está em [Melhorar a lógica](#melhorar-a-lógica-identidade-escolas-pontuação).

## Sugestões e problemas

Abra uma *issue* em [github.com/PedroVNeves/medalhas/issues](https://github.com/PedroVNeves/medalhas/issues).
Ajuda muito incluir:

- **problema no site**: o endereço da página, o que você esperava e o que aconteceu, o navegador e se era
  celular ou computador (uma captura de tela resolve metade dos casos);
- **problema na API**: a URL chamada e a resposta;
- **sugestão**: o que você quer fazer no site e por que, mais do que como implementar.

## Preparar o ambiente

```bash
git clone https://github.com/<seu-usuario>/medalhas.git   # o seu fork
cd medalhas
pip install -r requirements.txt pypdf   # opcionais: imagens de compartilhamento e PDFs de 3 olimpíadas
python build_db.py --sem-mencoes-obmep  # base de desenvolvimento: ~1,5 min, pouca memória
python server.py                        # http://localhost:8000
```

- Requer **Python 3.10+**. O servidor usa só a biblioteca padrão.
- A base completa (`python build_db.py`, com as ~720 mil menções honrosas da OBMEP) leva uns 5 minutos e chega
  a 3,5 GB de memória. Para desenvolver, a base sem menções basta; use a completa só para medir uma mudança
  que dependa delas.
- Na primeira vez a coleta baixa as listas oficiais (alguns minutos). Depois elas ficam em `cache/` e a base é
  regerada sem internet. `--refresh` baixa tudo de novo.
- Testes: `python -m unittest discover -s tests` (ou `python -m pytest -q`). Não usam a internet nem a base
  real.
- CSS: só quem muda classes no HTML/JS precisa do Node (`npm install`, depois `npm run css`).

## Adicionar uma olimpíada

Antes de escrever código, confira se a olimpíada tem **lista oficial pública de premiados** (página, PDF ou
planilha no site dos organizadores). O Medalhas só usa fontes oficiais, e cada premiação guarda o link da sua.
Se você só conhece a olimpíada mas não vai programar, abra uma *issue* com o nome, o site oficial e o link
das listas de premiados de cada ano.

Para programar:

1. **Cadastre** a olimpíada no **fim** de `CATALOGO` em `medalhas/dominio/olimpiadas.py`: sigla, nome, área,
   site oficial e o degrau na escala de pontos da "nossa versão" (`pontuacao.ESCALA_SITE`). Se o edital do IMPA
   Tech aceitar a olimpíada, informe `tabela_impa` e `niveis_impa`.
   - **Sempre no fim**: a ordem do catálogo é a ordem de coleta, que define o id de cada premiação. Inserir no
     meio muda os ids das que vêm depois.
2. **Escreva o coletor** em `medalhas/adaptadores/coletores/<sigla>.py`, com uma função `coletar(log)` que
   devolve uma lista de `Premiacao` (`medalhas/dominio/premiacao.py`):
   - baixe as páginas com `coletores.http.baixar` (ou `baixar_bytes` para PDF): ela guarda em cache, tenta de
     novo em falha de rede e confere o conteúdo (`esperado=`), para uma página de erro não virar lista vazia;
   - preencha `fonte` com a página oficial de cada premiação, `medalha` com as constantes `OURO`, `PRATA`,
     `BRONZE` e `MENCAO`, e `premio` com o texto original publicado;
   - deixe `None` o que a lista não informa (escola, cidade, UF, nível). Não invente: a identidade dos alunos e
     a cidade das escolas são deduzidas depois, com regras próprias;
   - os leitores de HTML (`coletores/html.py`) e de PDF pela posição na página (`coletores/pdf.py`) já resolvem
     boa parte do trabalho; os coletores existentes são bons exemplos (`omif.py` para PDF, `obi.py` para HTML);
   - documente no docstring do módulo onde ficam as listas e as armadilhas de cada ano (formato que muda,
     edição que não existiu).
3. **Registre** o coletor em `medalhas/adaptadores/coletores/__init__.py` (`_ESPECIFICOS`). Um teste falha se
   uma olimpíada do catálogo ficar sem coletor.
4. **Teste a leitura** em `tests/test_adaptadores.py` com um trecho real da página ou do PDF guardado no
   próprio teste (sem internet), cobrindo os formatos diferentes que a lista teve ao longo dos anos.
5. **Gere a base** (`python build_db.py --sem-mencoes-obmep`) e confira: quantas premiações entraram por ano,
   se os nomes, as escolas e os estados saíram certos, e se alguém já existente ganhou as medalhas novas no
   perfil certo. Conte esses números no pull request.

Os filtros de olimpíada, área e nível do site e da API são montados a partir dos dados: o front-end não precisa
mudar.

## Melhorar a lógica (identidade, escolas, pontuação)

As regras mais delicadas são as que decidem **quem é a mesma pessoa** (`medalhas/dominio/identidade.py`) e
**qual é a mesma escola** (`medalhas/dominio/escolas.py`). As listas não têm documento nem data de nascimento,
só nome, escola, cidade e ano, então toda regra equilibra dois erros:

- **separar a mesma pessoa** em dois perfis (as medalhas dela ficam divididas);
- **juntar duas pessoas** num perfil (alguém ganha medalhas que não são suas). Este é o erro pior, e uma
  mudança que aumenta esse risco precisa de números muito bons.

As regras em uso, em linguagem simples, e os números da comparação que escolheu a regra das grafias diferentes
estão em [`docs/identidade-regras.md`](docs/identidade-regras.md). Para propor uma mudança:

1. **Mostre os casos**: links de perfis do site que a regra atual erra.
2. **Escreva testes** em `tests/test_dominio.py`: os casos que devem passar a juntar (ou separar) e os que
   **não** podem mudar (homônimos na mesma cidade, a mesma olimpíada no mesmo ano em dois lugares, iniciais
   ambíguas). Desligue a sua regra e confira que o teste falha.
3. **Meça na base**: gere a base antes e depois da mudança e conte quantos perfis foram juntados ou divididos,
   quantos perfis existentes mudaram de medalhas e se algum homônimo já separado foi juntado. Traga uma amostra
   sorteada das mudanças com nome, escola, cidade e anos de cada lado, conferida à mão.
4. **Endereços**: um perfil que some continua acessível pelo endereço antigo (a geração redireciona para o
   perfil que ficou com as premiações dele). Confira que isso continua valendo.

Na **pontuação** (`medalhas/dominio/pontuacao.py`), os pontos do IMPA seguem o edital oficial e só mudam
quando ele muda (cite o edital). A "nossa versão" é uma escala própria: proponha a mudança numa *issue*,
explicando o raciocínio, antes do pull request.

## Mexer no site

O site é uma página única em `web/` (`index.html`, `js/app.js`, `js/graficos.js`, `styles.css`), feita com
Alpine.js e Tailwind CSS, servida pelo servidor Python (`medalhas/adaptadores/http/`).

- Confira as telas nos **dois temas** (claro e escuro) e no **celular** (390 px de largura).
- Mantenha o contraste de texto acessível (WCAG AA, 4,5:1) e o respeito a `prefers-reduced-motion`.
- Se mudar classes do Tailwind, rode `npm run css` e inclua o `web/css/site.css` gerado no commit.
- Endereços, sitemap e imagens de compartilhamento são feitos no servidor (`adaptadores/http/paginas.py` e
  `imagens.py`); o contrato da API pública v1 fica só em `api_v1/apresentacao.py`.

## Mandar um pull request

1. Faça um *fork* e crie uma branch a partir da `main` (`git switch -c fix/nome-curto`).
2. Faça a mudança com testes. Mudanças pequenas e focadas são revisadas mais rápido.
3. Rode os testes e confira que todos passam.
4. Se mexeu em coleta ou nas regras de dados, gere a base e traga os números (antes e depois).
5. Abra o pull request explicando **o porquê** da mudança, como você conferiu e o que muda para quem usa o
   site. O modelo do pull request traz a lista de conferência.

O autor revisa todos os pull requests. Pode haver pedido de ajuste; uma mudança que não combina com o projeto
pode não ser aceita, e a explicação vem na conversa do pull request.

## Padrão de código

- **Arquitetura hexagonal**: o domínio (`medalhas/dominio/`) não importa adaptadores nem faz entrada e saída;
  o HTTP não conhece o SQLite. Um teste (`tests/test_arquitetura.py`) confere a direção das dependências.
- **Português** em nomes, comentários e documentação (o domínio é brasileiro); **mensagens de commit em
  inglês**, no formato [Conventional Commits](https://www.conventionalcommits.org) (`fix(identidade): ...`,
  `feat(web): ...`).
- Linhas de até 120 caracteres, *type hints* nas funções públicas e docstring em todo módulo dizendo a
  responsabilidade dele. Se usar o ruff: `ruff check --select F,I,E501 --line-length 120 medalhas tests`.
- Comentários explicam o **porquê** (uma regra do edital, uma armadilha do site oficial), não o quê.
- SQL sempre com parâmetros (`?`); nomes de coluna interpolados vêm só de listas fixas do código.
- Nada de dependência nova no servidor sem conversa antes: ele roda só com a biblioteca padrão.

## Privacidade

A maior parte das pessoas na base é menor de idade. Os dados já são públicos nas listas oficiais, mas cuide
deles com respeito:

- em *issues* e pull requests, use o link do perfil no site; não poste dados pessoais além do que a lista
  oficial publica (nada de telefone, documento, endereço, redes sociais de outra pessoa);
- não suba bases, planilhas ou amostras com nomes de alunos para o repositório (`data/` e `cache/` ficam fora
  do git); testes usam casos curtos e só o necessário;
- pedidos de remoção vão por e-mail: **pedro.vasconcelosneves@gmail.com**.
