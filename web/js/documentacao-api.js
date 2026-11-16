/* Conteúdo da página "API & Dados": receitas em cURL/Python/JavaScript, rotas, filtros e campos. */

const BASE = location.origin;
const ID_ALUNO = "ERICK AKIRA KOGA|SP";
const ID_ESCOLA = "ALAGOAS FEDERAL INSTITUTO MACEIO|MACEIO|AL";
const enc = encodeURIComponent;

// receitas: código em cada linguagem ({B} = endereço do servidor)
const RECEITAS = {
  aluno: {
    curl: `# 1. Buscar pelo nome: devolve o id e já traz as premiações
curl "{B}/api/v1/alunos?nome=erick+akira+koga"

# 2. Um aluno específico pelo id (codificado: espaço = %20, | = %7C)
curl "{B}/api/v1/alunos/${enc(ID_ALUNO)}"

# Confirmar uma medalha: "total" > 0 significa que ela existe
curl "{B}/api/v1/alunos?nome=erick+akira+koga&competicao=OBM&ano=2023&premiacoes=0"

# Baixar as medalhas do aluno em CSV
curl -OJ "{B}/api/v1/exportar?aluno_id=${enc(ID_ALUNO)}"`,
    python: `import requests
from urllib.parse import quote

BASE = "{B}/api/v1"

# 1. Buscar pelo nome
r = requests.get(f"{BASE}/alunos", params={"nome": "erick akira koga"})
r.raise_for_status()
for aluno in r.json()["alunos"]:
    print(aluno["nome"], aluno["uf"], aluno["medalhas"])
    for p in aluno["premiacoes"]:
        print(f'  {p["ano"]} {p["olimpiada"]} {p["nivel"] or ""}: {p["medalha"]}  ({p["fonte"]})')

# 2. Pelo id (estável: não muda com homônimos)
aluno_id = "${ID_ALUNO}"
aluno = requests.get(f"{BASE}/alunos/{quote(aluno_id, safe='')}").json()["aluno"]
print(aluno["pontos"], aluno["posicao"])`,
    javascript: `const BASE = "{B}/api/v1";

// 1. Buscar pelo nome
const r = await fetch(\`\${BASE}/alunos?\` + new URLSearchParams({ nome: "erick akira koga" }));
const { alunos } = await r.json();
for (const a of alunos) {
  console.log(a.nome, a.uf, a.medalhas);
  for (const p of a.premiacoes) console.log(p.ano, p.olimpiada, p.medalha, p.fonte);
}

// 2. Pelo id
const id = "${ID_ALUNO}";
const { aluno } = await (await fetch(\`\${BASE}/alunos/\${encodeURIComponent(id)}\`)).json();
console.log(aluno.pontos, aluno.posicao);`,
  },
  escola: {
    curl: `# 1. Achar a escola (aceita siglas: IFAL, ETEC, EEEFM, CEFET…)
curl "{B}/api/v1/escolas?nome=ifal+maceio"

# 2. Todos os medalhistas dela (até 500 por página; use offset para as próximas)
curl "{B}/api/v1/escolas/${enc(ID_ESCOLA)}/medalhistas?limite=500"

# Só os ouros da OBMEP nível 3
curl "{B}/api/v1/escolas/${enc(ID_ESCOLA)}/medalhistas?competicao=OBMEP&nivel=3&medalha=Ouro"

# Ou baixar todas as premiações da escola em CSV
curl -OJ "{B}/api/v1/exportar?escola_id=${enc(ID_ESCOLA)}"`,
    python: `import requests
from urllib.parse import quote

BASE = "{B}/api/v1"

# 1. Achar a escola
escola = requests.get(f"{BASE}/escolas", params={"nome": "ifal maceio"}).json()["escolas"][0]
print(escola["nome"], escola["municipio"], escola["medalhas"])

# 2. Todos os medalhistas, página por página
medalhistas, offset = [], 0
while True:
    pagina = requests.get(f"{BASE}/escolas/{quote(escola['id'], safe='')}/medalhistas",
                          params={"limite": 500, "offset": offset}).json()
    medalhistas += pagina["medalhistas"]
    offset += pagina["limite"]
    if offset >= pagina["total"]:
        break

for a in medalhistas:
    print(a["nome"], a["anos"], a["medalhas_nesta_escola"])`,
    javascript: `const BASE = "{B}/api/v1";

// 1. Achar a escola
const busca = await (await fetch(\`\${BASE}/escolas?\` + new URLSearchParams({ nome: "ifal maceio" }))).json();
const escola = busca.escolas[0];

// 2. Todos os medalhistas, página por página
const medalhistas = [];
for (let offset = 0; ; offset += 500) {
  const url = \`\${BASE}/escolas/\${encodeURIComponent(escola.id)}/medalhistas?limite=500&offset=\${offset}\`;
  const pagina = await (await fetch(url)).json();
  medalhistas.push(...pagina.medalhistas);
  if (offset + 500 >= pagina.total) break;
}
console.table(medalhistas.map(a => ({ nome: a.nome, ...a.medalhas_nesta_escola })));`,
  },
  tudo: {
    curl: `# Base inteira em CSV (--compressed: transfere ~7 MB em vez de ~45 MB)
curl --compressed -OJ "{B}/api/v1/exportar?formato=csv"

# CSV para abrir direto no Excel em português (separador ;)
curl --compressed -OJ "{B}/api/v1/exportar?formato=csv&separador=;"

# Base inteira em JSON
curl --compressed -OJ "{B}/api/v1/exportar?formato=json"

# Só um recorte: ouros da OBM em SP desde 2015
curl --compressed -OJ "{B}/api/v1/exportar?competicao=OBM&uf=SP&medalha=Ouro&ano_de=2015"

# Ranking completo das escolas pelo método IMPA N3
curl --compressed -OJ "{B}/api/v1/exportar?conjunto=escolas&metodo=impa3"`,
    python: `import pandas as pd

# A base inteira direto num DataFrame (CSV em UTF-8 com BOM)
df = pd.read_csv("{B}/api/v1/exportar?formato=csv", encoding="utf-8-sig")
print(len(df), "premiações")
print(df[df.medalha == "Ouro"].groupby("olimpiada").size())

# Sem pandas: paginar /premiacoes (1000 por página) respeitando o limite
import time, requests
url, todas = "{B}/api/v1/premiacoes?limite=1000", []
while url:
    pagina = requests.get(url).json()
    todas += pagina["premiacoes"]
    url = pagina["proxima_pagina"]
    time.sleep(1)  # 1 página por segundo fica dentro do limite por IP`,
    javascript: `// A base inteira em JSON (o navegador descompacta sozinho)
const r = await fetch("{B}/api/v1/exportar?formato=json");
const { dados, total } = await r.json();
console.log(total, "premiações");

// Contagem de ouros por olimpíada
const ouros = {};
for (const p of dados) if (p.medalha === "Ouro") ouros[p.olimpiada] = (ouros[p.olimpiada] || 0) + 1;
console.table(ouros);`,
  },
};

const P = (nome, tipo, desc, obrig = false) => ({ nome, tipo, desc, obrig });
const FILTROS = [
  P("uf", "texto", "Sigla do estado. Ex.: SP"),
  P("municipio", "texto", "Município (acentos ignorados)"),
  P("competicao", "lista", "Uma ou mais olimpíadas separadas por vírgula. Ex.: OBMEP,OBM"),
  P("area", "texto", "Matemática, Informática…"),
  P("medalha", "texto", "Ouro, Prata, Bronze ou Menção Honrosa"),
  P("nivel", "lista", "Um ou mais níveis. Ex.: 3 ou 1,2,3,Universitário"),
  P("ano · ano_de · ano_ate", "inteiro", "Ano exato ou intervalo"),
  P("rede", "texto", "publica ou privada (só OBMEP)"),
  P("sexo", "texto", "F: só alunas premiadas na EGMO, PAGMO ou EGOI (com todas as premiações delas)"),
];
FILTROS.forEach(f => (f.comum = true));  // marcados para a referência mostrar "aceita os filtros comuns"
const OFFSET = P("offset", "inteiro", "Quantos itens pular (paginação)");
const METODO_P = P("metodo", "texto", "Ordem dos resultados: impa (padrão), impa3 ou site");
const ROTAS = [
  { id: "alunos", path: "/api/v1/alunos", titulo: "Buscar alunos pelo nome",
    desc: "Todas as palavras precisam aparecer no nome, em qualquer ordem e sem acento. Quem tem exatamente o nome pesquisado vem primeiro. Cada aluno vem com resumo, pontos, posições e a lista de premiações.",
    params: [P("nome", "texto", "Nome ou parte dele", true), P("escola", "texto", "Só premiações por esta escola (aceita siglas)"),
      P("premiacoes", "0 | 1", "0 devolve só o resumo (mais leve)"), METODO_P, ...FILTROS, P("limite", "inteiro", "1–100 (padrão 20)"), OFFSET],
    teste: "/api/v1/alunos?nome=erick+akira+koga" },
  { id: "aluno", path: "/api/v1/alunos/{id}", titulo: "Um aluno e todas as premiações",
    desc: "Use o id devolvido pela busca. É a forma estável de apontar para uma pessoa (homônimos de outros estados têm outro id). Aceita os filtros para restringir as premiações.",
    params: [P("id", "caminho", "Id do aluno, codificado na URL", true), ...FILTROS],
    teste: `/api/v1/alunos/${enc(ID_ALUNO)}` },
  { id: "escolas", path: "/api/v1/escolas", titulo: "Buscar escolas pelo nome",
    desc: "Aceita siglas (IFAL, ETEC, EEEFM, CEFET…) e ignora acentos e ordem das palavras. Campi diferentes são escolas diferentes.",
    params: [P("nome", "texto", "Nome ou sigla", true), METODO_P, ...FILTROS, P("limite", "inteiro", "1–100 (padrão 20)"), OFFSET],
    teste: "/api/v1/escolas?nome=ifal" },
  { id: "escola", path: "/api/v1/escolas/{id}", titulo: "Resumo de uma escola",
    desc: "Medalhas, pontos nos três métodos, posição nacional e estadual e as grafias do nome encontradas nas listas oficiais.",
    params: [P("id", "caminho", "Id da escola, codificado na URL", true)],
    teste: `/api/v1/escolas/${enc(ID_ESCOLA)}` },
  { id: "medalhistas", path: "/api/v1/escolas/{id}/medalhistas", titulo: "Todos os medalhistas de uma escola",
    desc: "Cada aluno premiado pela escola, com as medalhas e premiações por ela. Até 500 por página.",
    params: [P("id", "caminho", "Id da escola", true), P("nome", "texto", "Filtra pelo nome do aluno"),
      P("ordem", "texto", "pontos (padrão), nome ou recentes"), METODO_P, ...FILTROS, P("limite", "inteiro", "1–500 (padrão 20)"), OFFSET],
    teste: `/api/v1/escolas/${enc(ID_ESCOLA)}/medalhistas?limite=2` },
  { id: "premiacoes", path: "/api/v1/premiacoes", titulo: "Todas as premiações (paginado)",
    desc: "A base inteira ou filtrada, uma premiação por item, em ordem estável. Siga proxima_pagina até ela vir null. Para baixar tudo de uma vez, prefira /exportar.",
    params: [P("nome", "texto", "Nome do aluno"), P("escola", "texto", "Nome ou sigla da escola"), P("busca", "texto", "Nome, escola ou município"),
      P("aluno_id · escola_id", "texto", "Só deste aluno / desta escola"), ...FILTROS, P("limite", "inteiro", "1–1000 (padrão 20)"), OFFSET],
    teste: "/api/v1/premiacoes?competicao=IMO&medalha=Ouro&limite=2" },
  { id: "ranking", path: "/api/v1/ranking/{tipo}", titulo: "Rankings de alunos, escolas, estados ou cidades",
    desc: "Os mesmos rankings do site. Empates dividem a posição. No método impa3 só contam os níveis aceitos pelo IMPA Tech.",
    params: [P("tipo", "caminho", "alunos, escolas, estados ou cidades", true), METODO_P, P("ordem", "texto", "xp (pontos, padrão), medalhas ou total"),
      ...FILTROS, P("limite", "inteiro", "1–500 (padrão 20)"), OFFSET],
    teste: "/api/v1/ranking/escolas?metodo=impa3&uf=CE&limite=3" },
  { id: "exportar", path: "/api/v1/exportar", titulo: "Baixar dados (CSV ou JSON)",
    desc: "Sem filtros, baixa a base inteira de premiações. Com filtros, só o recorte. conjunto=alunos|escolas|estados|cidades baixa o ranking completo. O CSV é UTF-8 com BOM; separador=; abre direto no Excel em português. A transferência é compactada (gzip) quando o cliente aceita. Tem limite próprio por IP.",
    params: [P("formato", "texto", "csv (padrão) ou json"), P("conjunto", "texto", "premiacoes (padrão), alunos, escolas, estados ou cidades"),
      P("separador", "texto", ", (padrão) ou ;"), P("aluno_id · escola_id", "texto", "Só deste aluno / desta escola"),
      P("nome · escola · busca", "texto", "Busca por texto, como em /premiacoes"), METODO_P, ...FILTROS],
    teste: null },
  { id: "olimpiadas", path: "/api/v1/olimpiadas", titulo: "Olimpíadas e valores aceitos",
    desc: "Siglas, nomes, áreas, níveis existentes, anos e pontuação de cada olimpíada. Use para montar filtros.",
    params: [], teste: "/api/v1/olimpiadas" },
];
const CAMPOS_PREMIACAO = [
  ["id", "Identificador da premiação na base"], ["olimpiada · olimpiada_nome", "Sigla e nome da olimpíada"], ["area", "Matemática, Informática…"],
  ["ano · nivel", "Edição e nível (null quando a competição não tem níveis)"], ["medalha", "Ouro, Prata, Bronze ou Menção Honrosa"],
  ["premio", "Texto do prêmio como publicado (ex.: Honra ao Mérito)"], ["nome_na_lista", "Nome exatamente como aparece na lista oficial"],
  ["aluno_id · escola_id", "Ids para as rotas /alunos/{id} e /escolas/{id}"], ["escola · municipio · uf · rede", "Como publicados (OBM e internacionais não informam escola)"],
  ["nota", "Pontuação na prova, quando publicada"], ["pontos", "Pontos da premiação nos três métodos: impa, impa3 e site"],
  ["fonte", "Página oficial onde a premiação foi publicada, para conferência"],
];

// encurta respostas grandes para mostrar na página (listas com 2 itens + aviso)
function resumirJSON(v) {
  if (Array.isArray(v)) {
    const r = v.slice(0, 2).map(resumirJSON);
    if (v.length > 2) r.push(`… mais ${v.length - 2} itens`);
    return r;
  }
  if (v && typeof v === "object") return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, resumirJSON(x)]));
  return v;
}
const escapar = t => t.replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
const realcar = (codigo, lang) => window.hljs?.getLanguage(lang) ? hljs.highlight(codigo, { language: lang }).value : escapar(codigo);

