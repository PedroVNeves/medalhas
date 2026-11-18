# Identidade de alunos: as regras de produção

Como o Medalhas decide que duas premiações são da mesma pessoa. O código está em
`medalhas/dominio/identidade.py` e roda ao gerar a base (`medalhas/aplicacao/gerar_base.py`). A pesquisa que
escolheu a regra das grafias diferentes, com todos os métodos testados e os números, está em
`docs/identidade-pesquisa.md`.

## O problema

As listas oficiais não têm CPF, data de nascimento nem código de escola: trazem nome, escola, cidade, estado,
olimpíada, ano e nível. Com isso, dá para errar de dois jeitos:

- **separar a mesma pessoa** em dois perfis: o perfil fica incompleto, mas cada premiação continua certa, e a
  pessoa pode pedir a correção;
- **juntar duas pessoas** num perfil: alguém aparece com uma medalha que não ganhou, e quem lê não tem como
  perceber.

O segundo erro é o grave. Por isso as regras só juntam quando há prova e, na dúvida, separam.

## A ordem das regras

1. **Correções à mão** (`GRAFIAS_CORRIGIDAS`): vêm antes de tudo e sempre valem.
2. **Estado de quem veio sem ele** (IMO, IMC, EGOI…) e nomes abreviados das listas internacionais.
3. **Mesmo nome, mesmo estado**, com as travas que separam homônimos e a união entre estados para nomes raros.
4. Cidade das escolas que vieram sem cidade (não é identidade, mas a regra seguinte usa a cidade).
5. **Grafias diferentes da mesma pessoa** (a regra nova, de novembro de 2026).

## 1. Correções à mão

Quando uma lista escreve o nome errado e nenhuma regra resolve, a grafia errada entra em `GRAFIAS_CORRIGIDAS`
(`dominio/identidade.py`) com um comentário dizendo a origem do erro. Exemplo: a OBMEP 2017 escreveu "Sofia
Azeredo de Moura Moteiro"; a correção troca para Monteiro e as premiações vão para o perfil certo. Para um nome
comum, a correção vale só para uma olimpíada e um ano ("João Ferreira" na IMC 2026).

O endereço do perfil com a grafia errada continua valendo e redireciona (301) para o perfil certo.

**Como pedir uma correção:** escreva para o contato do site (no README, em "Como contribuir") ou abra uma
*issue* com o link dos perfis. Para quem mantém o site: acrescente a grafia errada em `GRAFIAS_CORRIGIDAS`, com o
nome certo e um comentário (olimpíada, ano, escola, quem confirmou), rode os testes e gere a base. Isso serve
também para os casos que a regra automática deixa de fora de propósito (seção 5).

## 2. Mesmo nome, mesmo estado

O aluno é identificado por **nome sem acento + estado**: `MARIA SOUZA LIMA|AL`, endereço
`/aluno/maria-souza-lima-al`. O estado do perfil é o da premiação mais recente.

## 3. Travas: quando as premiações não cabem numa pessoa

Premiações com o mesmo nome no mesmo estado são divididas em pessoas diferentes quando:

- aparecem **na mesma olimpíada, no mesmo ano, em duas cidades** (ou em duas escolas da mesma cidade): ninguém
  estuda em dois lugares ao mesmo tempo. A OBI na mesma escola é exceção: ela premia modalidades diferentes no
  mesmo ano;
- a **carreira passa de 12 anos** (do 6º ano do fundamental ao fim da faculdade); a divisão é nos intervalos de
  8 anos ou mais sem premiação;
- o **nível da OBMEP regride** (nível 2 num ano e nível 1 depois);
- o **mesmo nível da OBMEP aparece anos demais depois** (trava nova): mais de 3 anos nos níveis 1 e 2, que cobrem
  2 séries cada; mais de 5 anos no nível 3. O nível 3 tem folga maior porque o ensino médio técnico (IFs,
  Liberato, ETEs) dura 4 anos e há quem recomece o médio ao entrar numa dessas escolas. Na base sem menções, 20
  perfis têm o nível 3 a 4 anos de distância, quase todos de escola técnica ou militar e com carreira coerente
  (nível 1, 2 e depois 3 seguidos); com o limite de 3 anos, 14 perfis assim seriam divididos.

A divisão é por cidade, depois por escola, depois no tempo. O maior pedaço fica com `NOME|UF` e os outros
ganham a cidade no id (`LUCAS ANTONIO SILVA|MG|DIVINOPOLIS`).

## 4. Mesmo nome em estados diferentes; premiações sem estado

- **Estados diferentes** viram uma pessoa só se o nome é raro (o número esperado de homônimos, estimado pela
  frequência de cada palavra, é baixo), as premiações cabem numa carreira e não há a mesma olimpíada no mesmo
  ano nos dois estados. Alunos de ponta mudam de estado para estudar.
- **Sem estado** (IMO, EGOI, IOAI, Itabirana 2020+): a premiação vai para a pessoa de mesmo nome se ela é
  única (em olimpíada de alto nível) ou se o nome é raro, ou se foi premiada na mesma escola. Senão, vira um
  perfil "sem estado".
- **Nomes abreviados nas internacionais** ("Enzo Holanda") são completados quando há um único medalhista
  compatível ("Enzo Holanda Sampaio").
- **Menções honrosas da OBMEP** (cerca de 50 mil por ano) não decidem nada nestas regras: não unem estados, não
  contam para saber se um nome é raro e só entram em perfis que as outras premiações já definiram (ou formam
  perfis novos). Na regra das grafias diferentes (seção 5) elas contam como as outras premiações.

## 5. Grafias diferentes da mesma pessoa (regra nova)

As listas escrevem o mesmo nome de jeitos diferentes: com iniciais ("Almir Sergio R dos Santos Filho"),
partículas trocadas ("R do Santos" e "R dos Santos"), erros de digitação ("Cacalcanti"). Cada grafia virava um
perfil. A etapa `juntar_grafias` junta esses perfis quando **todas** as condições abaixo valem.

### Quando junta

1. **Mesmo estado.**
2. **O nome encaixa palavra a palavra, na ordem, sem omitir nenhuma palavra**, com a **primeira palavra igual** e
   o **mesmo sufixo** (Filho, Júnior, Neto, Sobrinho). As diferenças aceitas, palavra por palavra, são:
   - **partículas** (de, da, do, dos, e): "Jefferson Caon da Costa" = "Jefferson Caon de Costa";
   - **inicial ou abreviação de até 3 letras**, dos dois lados: "Ramos dos S" = "R dos Santos" = "Ramos dos
     Santos";
   - **erro de 1 letra** (2 em palavras de 8 letras ou mais), **só em sobrenome**: "Primaki" = "Pimaki",
     "Cavalcanti" = "Cacalcanti".
3. **Prova de contexto:** uma premiação de cada perfil **na mesma escola**, ou **na mesma cidade com até 3 anos
   de distância**.
4. **Travas:** **nenhuma edição em comum** (os dois na mesma olimpíada e no mesmo ano são duas pessoas; a OBI na
   mesma escola é exceção) e as premiações juntas **cabem numa pessoa** (todas as travas da seção 3).
5. **A abreviação não tem outra leitura na cidade:** se outro nome da mesma cidade encaixa num dos lados e não
   no outro, não junta. "Ana Carolina B da Silva" e "Ana Carolina Batista da Silva" não se juntam se há uma "Ana
   Carolina Barbosa da Silva" na cidade: o "B" pode ser dela.
6. **Partícula ou uma letra só para nome pouco comum:** quando a única diferença é de partículas ou de uma letra
   (sem nenhuma inicial), o nome precisa ser raro: menos de 1 homônimo esperado com a mesma escola, menos de 0,1
   com só a mesma cidade. "Gabriel de Oliveira Santos" e "Gabriel Oliveira dos Santos" na mesma cidade são,
   muitas vezes, duas pessoas.

### O que fica de fora de propósito

- **Erro de letra no prenome** (primeira palavra, ou palavra que na base é quase sempre prenome): Natan/Natani,
  Lígia/Lívia, Gabriel/Gabriela, Wallison/Willison na mesma escola são, quase sempre, irmãos. Na pesquisa, esses
  pares foram pegos dividindo a mesma edição.
- **Palavras omitidas** ("João Ferreira" para "João Vitor Tomaz Alves Ferreira", "Leonardo Witt" para "Leonardo
  Gabriel Witt"): são a maior fonte de erro (142 mil pares candidatos na pesquisa, quase todos de pessoas
  diferentes).
- **Nomes comuns que só diferem em partícula ou numa letra** (Sousa/Souza num nome comum).
- **Três grafias em que uma atrapalha a outra:** "Agnaldo Camargo de Sousa Junior", "Camargos" e "Carmargos". Como
  "Carmargos" encaixa em "Camargos" e não em "Camargo", ela conta como outra leitura e impede a junção de Camargo
  com Camargos.

Esses casos se resolvem por correção à mão (seção 1).

### Como os perfis se agrupam

Os pares aceitos entram do mais forte para o mais fraco (mesma escola antes de só a mesma cidade; menos
diferenças antes de mais). Um par é **recusado** se juntaria dois grupos que não cabem numa pessoa: com uma
edição em comum, com as travas da seção 3 ou com dois homônimos que as regras de nome exato já separaram (o mesmo
nome em perfis diferentes). É um *correlation clustering* guloso com restrições ("cannot-link"). O fechamento
transitivo simples (se A = B e B = C, então A = C) **nunca** é usado: com ele, uma abreviação que encaixa em dois
homônimos viraria uma ponte entre eles.

### Qual perfil fica, e os endereços

- **O id** é o do perfil de **nome mais completo** (menos iniciais e abreviações); no empate, o de grafia mais
  usual (a palavra mais rara do nome é a mais frequente na base: Cavalcanti, não Cacalcanti), depois o de mais
  premiações além das menções, o de mais premiações e o mais recente.
- **O nome exibido** é a grafia do id (a OBM continua preferida entre as premiações com essa grafia, por ter
  acentos). As outras grafias continuam nas premiações e na busca.
- **Os endereços dos perfis absorvidos continuam valendo** e redirecionam (301) para o perfil que ficou, como nas
  correções à mão. Um endereço antigo nunca toma o de outra pessoa.

### Números

- **Pesquisa** (base de 17/11/2026, com as menções): 16,2 mil junções, que absorvem 15,2 mil perfis (2,4% dos
  622 mil); erro estimado de ~0,06% (cerca de 10 junções erradas) pela contagem de conflitos de edição; 0 erros
  em 30 junções sorteadas e conferidas à mão.
- **Produção, base sem as menções** (18/11/2026): 2.316 perfis absorvidos em 2.067 perfis (de 83,8 mil);
  nenhum homônimo já separado juntado; todos os endereços antigos levam ao perfil certo. A trava nova do nível
  dividiu 14 perfis, todos de pessoas diferentes pelo histórico (o mesmo nível em outra cidade ou outra escola,
  4 a 12 anos depois).

## 6. Por que não embeddings, Ditto ou LLM

A pesquisa testou modelos de linguagem e os números não justificam o custo:

- **Embeddings** (MiniLM multilíngue e Serafim, em português) com cosseno ≥ 0,95: erro estimado de **56%**
  (MiniLM) e **84%** (Serafim). Com a mesma prova de contexto da regra: **6,6%** e **15%**, contra **~0,06%** da
  regra de encaixe. Eles medem semelhança de assunto, e todo nome tem o mesmo assunto; não sabem que "R" pode ser
  "Ramos" e não "Santos", nem que Batista e Barbosa são sobrenomes diferentes. Custaram 1 a 3,5 minutos de GPU
  para 180 mil nomes e até 4,4 GB de memória.
- **Ditto** (BERT ajustado para pares) precisa de milhares de pares rotulados; o gabarito tem algumas dezenas.
- **LLM como juiz**: só vê o par. Diante de "Ana Carolina B da Silva" e "Ana Carolina Batista da Silva" na mesma
  escola, não sabe que existe uma Ana Carolina Barbosa da Silva na cidade, e é isso que decide. O que decide os
  casos difíceis (quantas leituras a abreviação tem na cidade, se dois nomes dividem uma edição) é contagem na
  base.
- **Fellegi-Sunter** (probabilístico, sem rótulos) foi o de maior alcance, mas no corte 0,999 erra cerca de 13
  vezes mais que a regra (0,77%), sobretudo com erro em prenome. É o candidato para ordenar uma futura lista de
  "possíveis perfis relacionados", sem juntar.

## 7. Onde está e como testar

- Código: `medalhas/dominio/identidade.py` (`juntar_grafias` e as funções logo acima dela; as travas em
  `_cabe_numa_pessoa`). A gravação dos endereços antigos: `adaptadores/sqlite/gravacao.py`
  (`gravar_enderecos`).
- Testes: `tests/test_dominio.py` (`TestGrafiasDiferentes`: o Almir e um negativo para cada trava) e
  `tests/test_integracao.py` (`TestGrafiasJuntadas`: endereço antigo e nome exibido).
- Medir uma mudança: gere a base antes e depois (`python build_db.py --sem-mencoes-obmep` é bem mais leve) e
  compare os perfis pelas premiações: quantos perfis sumiram, quais mudaram de premiações e se algum homônimo com
  cidade no id foi juntado.
