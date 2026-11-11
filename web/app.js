/* Medalhas — SPA (Alpine.js + ECharts). Sem build: tudo via CDN. */

// método de pontuação escolhido no topo (impa | impa3 | site); vai em toda chamada à API
let METODO = localStorage.getItem("metodo") || "";
const API = (path, params = {}) => {
  const all = { ...params, metodo: METODO };
  const qs = new URLSearchParams(Object.entries(all).filter(([, v]) => v !== "" && v != null));
  return fetch(`/api/${path}?${qs}`).then(r => r.json());
};

// ---------------------------------------------------------------- formatação
const fmt = n => (n ?? 0).toLocaleString("pt-BR");
const UF_NOMES = {
  AC: "Acre", AL: "Alagoas", AM: "Amazonas", AP: "Amapá", BA: "Bahia", CE: "Ceará", DF: "Distrito Federal",
  ES: "Espírito Santo", GO: "Goiás", MA: "Maranhão", MG: "Minas Gerais", MS: "Mato Grosso do Sul",
  MT: "Mato Grosso", PA: "Pará", PB: "Paraíba", PE: "Pernambuco", PI: "Piauí", PR: "Paraná",
  RJ: "Rio de Janeiro", RN: "Rio Grande do Norte", RO: "Rondônia", RR: "Roraima", RS: "Rio Grande do Sul",
  SC: "Santa Catarina", SE: "Sergipe", SP: "São Paulo", TO: "Tocantins",
};
const SMALL = new Set(["DE", "DA", "DO", "DAS", "DOS", "E", "EM", "NA", "NO", "NAS", "NOS"]);
const KEEP_UPPER = /^(I{1,3}|IV|V|VI{0,3}|IX|X|[A-Z]{1,2}|EE|EM|EMEF|EMEB|EMEIEF|EMEIF|EEEF|EEEFM|EEFM|EEF|EEM|EEEM|EEB|EEEP|EEPSG|ETEC|ETE|CEFET\w*|IF\w{0,10}|CEF|CEM|CED|CIEP|SESI|SENAI|SESC|UNICAMP|USP|UFMG|UFRJ|UFC|UFPE|UTFPR|EFM|EF|EI|LTDA|CMB|CMF|CMRJ|CAP|COC|ETAPA)$/;

function prettySchool(name) {
  if (!name) return "";
  let s = name.trim();
  const m = s.match(/^(.*),\s*([^,]{2,40})$/); // "MILITAR DE FORTALEZA, COLEGIO" -> "COLEGIO MILITAR DE FORTALEZA"
  if (m) s = `${m[2]} ${m[1]}`;
  if (s !== s.toUpperCase()) return s; // já está em caixa mista
  return s.split(/(\s+|-|\/)/).map((w, i) => {
    if (!/[A-ZÀ-Ü]/i.test(w)) return w;
    const up = w.toUpperCase();
    if (i > 0 && SMALL.has(up)) return w.toLowerCase();
    if (KEEP_UPPER.test(up.replace(/\./g, ""))) return up;
    return w.charAt(0) + w.slice(1).toLowerCase();
  }).join("");
}
const initials = n => (n || "?").split(/\s+/).filter(w => w.length > 2 || w === w.toUpperCase()).slice(0, 2).map(w => w[0]).join("").toUpperCase();
// rótulo curto do nível para os chips: "3" -> "N3", "Programação Nível 2" -> "Prog. 2", "Iniciação Nível Júnior" -> "Inic. Jr"
const nivelCurto = n => {
  if (/^\d$/.test(n)) return `N${n}`;
  if (n === "Universitário") return "Univ.";
  const m = n.match(/^(Programação|Iniciação)(?: Nível)?\s*(.*)$/);
  if (!m) return n;
  const resto = { "Júnior": "Jr", "Sênior": "Sr", "Universitário": "Univ" }[m[2]] ?? m[2];
  return `${m[1] === "Programação" ? "Prog." : "Inic."}${resto ? " " + resto : ""}`;
};
// descrição dos níveis aceitos no IMPA Tech: "3,Programação Nível 1,…" -> "Nível 3, Programação Nível 1 e Programação Nível 2"
const descreveImpa = v => {
  const ls = (v || "3").split(",").map(n => /^\d$/.test(n) ? `Nível ${n}` : n);
  return ls.length > 1 ? ls.slice(0, -1).join(", ") + " e " + ls.at(-1) : ls[0];
};
const nivelLabel = n => !n ? "" : /^\d$/.test(n) ? `Nível ${n}` : n;
const medalClass = m => ({ Ouro: "", Prata: "prata", Bronze: "bronze", "Menção Honrosa": "mencao" }[m] ?? "bronze");

// ---------------------------------------------------------------- gráficos (fora do Alpine p/ não virar proxy)
const charts = {};
const VIZ = { ouro: "#b5870c", prata: "#6688d6", bronze: "#b5602b", text: "#a3abc2", muted: "#6b7489", grid: "rgba(255,255,255,.06)", surface: "#0f1424" };
let brGeo = null;

function chart(el, key) {
  if (!el) return null;
  if (charts[key] && charts[key].getDom() !== el) { charts[key].dispose(); delete charts[key]; }
  charts[key] = charts[key] || echarts.init(el, null, { renderer: "canvas" });
  return charts[key];
}
window.addEventListener("resize", () => Object.values(charts).forEach(c => c.resize()));

const tooltipBase = {
  backgroundColor: "rgba(12,17,32,.96)", borderColor: "rgba(255,255,255,.12)", borderWidth: 1,
  textStyle: { color: "#e8ebf5", fontFamily: "Inter", fontSize: 12 }, extraCssText: "border-radius:12px;box-shadow:0 12px 40px rgba(0,0,0,.5);",
};

function stackedYears(el, key, rows) {
  const c = chart(el, key); if (!c) return;
  const anos = rows.map(r => r.ano);
  const serie = (name, field, color, top) => ({
    name, type: "bar", stack: "m", data: rows.map(r => r[field]), barMaxWidth: 26,
    itemStyle: { color, borderColor: VIZ.surface, borderWidth: 1, borderRadius: top ? [4, 4, 0, 0] : 0 },
    emphasis: { focus: "series" },
  });
  c.setOption({
    animationDuration: 900, animationEasing: "cubicOut",
    grid: { left: 8, right: 8, top: 36, bottom: 4, containLabel: true },
    legend: { top: 0, left: 0, icon: "roundRect", itemWidth: 10, itemHeight: 10, textStyle: { color: VIZ.text, fontFamily: "Inter" } },
    tooltip: { ...tooltipBase, trigger: "axis", axisPointer: { type: "shadow", shadowStyle: { color: "rgba(255,255,255,.04)" } },
      formatter: ps => `<b>${ps[0].axisValue}</b><br>` + ps.map(p => `${p.marker} ${p.seriesName}: <b>${fmt(p.value)}</b>`).join("<br>")
        + `<br><span style="color:${VIZ.muted}">Total: ${fmt(ps.reduce((s, p) => s + p.value, 0))}</span>` },
    xAxis: { type: "category", data: anos, axisLine: { lineStyle: { color: VIZ.grid } }, axisTick: { show: false }, axisLabel: { color: VIZ.muted, fontFamily: "Inter" } },
    yAxis: { type: "value", splitLine: { lineStyle: { color: VIZ.grid } }, axisLabel: { color: VIZ.muted, fontFamily: "Inter", formatter: v => fmt(v) } },
    series: [serie("Ouro", "ouro", VIZ.ouro), serie("Prata", "prata", VIZ.prata), serie("Bronze", "bronze", VIZ.bronze, true)],
  }, true);
}

async function brazilMap(el, key, estados, metric, onClick) {
  const c = chart(el, key); if (!c) return;
  c.showLoading({ text: "", color: "#f5c542", maskColor: "transparent" });
  if (!brGeo) {
    const geo = await fetch("https://cdn.jsdelivr.net/gh/codeforgermany/click_that_hood@main/public/data/brazil-states.geojson").then(r => r.json());
    geo.features.forEach(f => { f.properties.name = f.properties.sigla; });
    echarts.registerMap("BR", geo);
    brGeo = geo;
  }
  c.hideLoading();
  const labels = { xp: "Pontos", ouro: "Ouros", total: "Premiações", alunos: "Alunos premiados" };
  const data = estados.map(e => ({ name: e.id, value: e[metric], raw: e }));
  const max = Math.max(...data.map(d => d.value), 1);
  c.setOption({
    tooltip: { ...tooltipBase, trigger: "item", formatter: p => {
      const e = p.data?.raw; if (!e) return p.name;
      return `<b>${UF_NOMES[e.id]}</b> <span style="color:${VIZ.muted}">#${e.pos}</span><br>
        ${labels[metric]}: <b>${fmt(e[metric])}</b><br>
        <span style="color:${VIZ.ouro}">●</span> ${fmt(e.ouro)} &nbsp;<span style="color:${VIZ.prata}">●</span> ${fmt(e.prata)} &nbsp;<span style="color:${VIZ.bronze}">●</span> ${fmt(e.bronze)}`;
    } },
    visualMap: { min: 0, max, calculable: false, orient: "horizontal", left: "center", bottom: 0, itemWidth: 12, itemHeight: 180,
      text: [fmt(max), "0"], textStyle: { color: VIZ.text, fontFamily: "Inter" },
      inRange: { color: ["#1b2236", "#3a3017", "#6b5212", "#a07810", "#d9a521", "#ffd76e"] } },
    series: [{ type: "map", map: "BR", roam: false, data, top: 10, bottom: 50,
      itemStyle: { borderColor: "#070a14", borderWidth: 1, areaColor: "#1b2236" },
      emphasis: { label: { show: true, color: "#fff", fontWeight: 700 }, itemStyle: { areaColor: "#ffe08a", shadowBlur: 20, shadowColor: "rgba(245,197,66,.6)" } },
      select: { disabled: true },
      label: { show: false } }],
  }, true);
  c.off("click");
  c.on("click", p => p.name && onClick(p.name));
}

// ---------------------------------------------------------------- confete
function celebrate() {
  if (!window.confetti || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const colors = ["#f5c542", "#ffe08a", "#ffffff", "#7c8cff"];
  confetti({ particleCount: 90, spread: 70, origin: { y: .25 }, colors, scalar: .9 });
  setTimeout(() => confetti({ particleCount: 60, angle: 60, spread: 55, origin: { x: 0, y: .4 }, colors }), 180);
  setTimeout(() => confetti({ particleCount: 60, angle: 120, spread: 55, origin: { x: 1, y: .4 }, colors }), 300);
}

// ---------------------------------------------------------------- contador animado
function countUp(el, to) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) { el.textContent = fmt(to); return; }
  const from = 0, dur = 1400, t0 = performance.now();
  const step = t => {
    const p = Math.min((t - t0) / dur, 1), e = 1 - Math.pow(1 - p, 4);
    el.textContent = fmt(Math.round(from + (to - from) * e));
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

// ---------------------------------------------------------------- ícones lucide como diretiva Alpine
// x-icon="'crown'" desenha o SVG dentro do elemento (sem substituir o nó, que o Alpine controla).
const pascal = s => String(s).replace(/(^|-)(\w)/g, (_, __, c) => c.toUpperCase());
document.addEventListener("alpine:init", () => {
  Alpine.directive("icon", (el, { expression }, { effect, evaluateLater }) => {
    const get = evaluateLater(expression);
    effect(() => get(name => {
      const node = window.lucide?.icons?.[pascal(name)];
      el.replaceChildren();
      if (!node) return;
      const svg = lucide.createElement(node);
      svg.setAttribute("stroke-width", "1.8");
      svg.setAttribute("aria-hidden", "true");
      el.appendChild(svg);
    }));
  });
});

// ---------------------------------------------------------------- documentação da API
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
  { id: "ranking", path: "/api/v1/ranking/{tipo}", titulo: "Rankings de alunos, escolas ou estados",
    desc: "Os mesmos rankings do site. Empates dividem a posição. No método impa3 só contam os níveis aceitos pelo IMPA Tech.",
    params: [P("tipo", "caminho", "alunos, escolas ou estados", true), METODO_P, P("ordem", "texto", "xp (pontos, padrão), medalhas ou total"),
      ...FILTROS, P("limite", "inteiro", "1–500 (padrão 20)"), OFFSET],
    teste: "/api/v1/ranking/escolas?metodo=impa3&uf=CE&limite=3" },
  { id: "exportar", path: "/api/v1/exportar", titulo: "Baixar dados (CSV ou JSON)",
    desc: "Sem filtros, baixa a base inteira de premiações. Com filtros, só o recorte. conjunto=alunos|escolas|estados baixa o ranking completo. O CSV é UTF-8 com BOM; separador=; abre direto no Excel em português. A transferência é compactada (gzip) quando o cliente aceita. Tem limite próprio por IP.",
    params: [P("formato", "texto", "csv (padrão) ou json"), P("conjunto", "texto", "premiacoes (padrão), alunos, escolas ou estados"),
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

// ---------------------------------------------------------------- app
function app() {
  return {
    UF_NOMES, fmt, prettySchool, initials, nivelLabel, medalClass, nivelCurto, descreveImpa,
    route: { name: "home", param: "", query: {} },
    metodo: METODO,
    aviso: null, _avisoT: null,
    ov: null,
    yearComp: "",
    mapMetric: "xp",
    // busca
    q: "", campo: "nome", busca: { loading: false, total: 0, grupos: [] }, _t: null,
    bf: { uf: "", area: "", competicao: "", medalha: "", ano: "", nivel: "", rede: "" },
    // ranking
    rk: { tipo: "alunos", itens: [], total: 0, loading: false, f: { uf: "", area: "", competicao: "", ano_de: "", ano_ate: "", nivel: "", rede: "", ordem: "xp" } },
    // perfis
    aluno: null, escola: null, loadingPerfil: false,
    // exportação e documentação da API
    exportando: false,
    BASE, ROTAS, FILTROS, CAMPOS_PREMIACAO,
    doc: { lang: "curl", resp: {}, carregando: {}, limites: null, copiado: "" },

    async init() {
      window.addEventListener("hashchange", () => this.onRoute());
      window.addEventListener("keydown", e => {
        if (e.key === "/" && !/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) { e.preventDefault(); this.$refs.q?.focus(); }
      });
      this.onRoute();  // a rota não espera a visão geral: perfis e rankings carregam sozinhos
      await this.loadOverview();
    },
    async loadOverview() {
      this.ov = await API("overview");
      if (!this.metodo) { this.metodo = METODO = this.ov.metodo; }
      if (this.is("home")) this.$nextTick(() => this.drawHome());
      if (this.is("estados")) this.$nextTick(() => this.drawMap());
    },
    get impa3() { return this.metodo === "impa3"; },
    // no IMPA N3 o filtro de nível é travado nos níveis aceitos pelo edital (o servidor também força)
    get niveisAceitos() { return (this.ov?.niveis_impa || "3").split(","); },
    // no IMPA N3 vale a escolha do usuário dentro dos níveis aceitos; sem escolha válida, todos os aceitos
    nivelEfetivo(v) {
      if (!this.impa3) return v;
      const sel = (v || "").split(",").filter(n => this.niveisAceitos.includes(n));
      return (sel.length ? sel : this.niveisAceitos).join(",");
    },
    avisar(texto, acao = null) {
      this.aviso = { texto, acao };
      clearTimeout(this._avisoT);
      this._avisoT = setTimeout(() => (this.aviso = null), 7000);
    },
    get metodoAtual() { return (this.ov?.metodos || []).find(m => m.id === this.metodo); },
    // troca o método de pontuação: recarrega a visão geral e os dados da página atual
    async setMetodo(m) {
      if (m === this.metodo) return;
      this.metodo = METODO = m;
      localStorage.setItem("metodo", m);
      if (m === "impa3") this.avisar(`Pontuação IMPA N3 ativada: o filtro de níveis foi aplicado automaticamente (${descreveImpa(this.ov?.niveis_impa)}), como no edital do IMPA Tech.`);
      const y = window.scrollY;
      this.onRoute();
      await this.loadOverview();
      window.scrollTo({ top: y, behavior: "instant" });
    },

    // ------------------------------------------------ roteamento
    go(path) { location.hash = path; },
    onRoute() {
      const [path, qs] = location.hash.replace(/^#/, "").split("?");
      const parts = (path || "/").split("/").filter(Boolean);
      const query = Object.fromEntries(new URLSearchParams(qs || ""));
      this.route = { name: parts[0] || "home", param: decodeURIComponent(parts.slice(1).join("/")), query };
      // links podem fixar o método: #/ranking/alunos?metodo=impa3
      if (["impa", "impa3", "site"].includes(query.metodo) && query.metodo !== this.metodo) {
        this.metodo = METODO = query.metodo;
        localStorage.setItem("metodo", query.metodo);
        if (this.ov) this.loadOverview();
      }
      window.scrollTo({ top: 0, behavior: "instant" });
      const r = this.route;
      if (r.name === "home") this.$nextTick(() => this.drawHome());
      if (r.name === "busca") {
        this.q = query.q || ""; this.campo = query.campo || "nome";
        for (const k of Object.keys(this.bf)) this.bf[k] = query[k] || "";
        this.runSearch();
      }
      if (r.name === "ranking") { this.rk.tipo = r.param || "alunos"; Object.assign(this.rk.f, { uf: "", area: "", competicao: "", ano_de: "", ano_ate: "", nivel: "", rede: "", ordem: "xp" }, Object.fromEntries(Object.entries(query).filter(([k]) => k !== "metodo"))); this.loadRanking(); }
      if (r.name === "estados") this.$nextTick(() => this.drawMap());
      if (r.name === "api") this.loadDoc();
      if (r.name === "aluno") this.loadAluno(r.param);
      if (r.name === "escola") this.loadEscola(r.param);
    },
    is(name) { return this.route.name === name; },
    alunoLink(id) { return "#/aluno/" + encodeURIComponent(id); },
    escolaLink(id) { return "#/escola/" + encodeURIComponent(id); },
    rankLink(tipo, extra = {}) { const p = new URLSearchParams(extra).toString(); return `#/ranking/${tipo}${p ? "?" + p : ""}`; },

    // ------------------------------------------------ home
    drawHome() {
      if (!this.ov) return;
      document.querySelectorAll("[data-count]").forEach(el => countUp(el, +el.dataset.count));
      this.drawYears();
    },
    drawYears() {
      const by = {};
      for (const r of this.ov.serie) {
        if (this.yearComp && r.competicao !== this.yearComp) continue;
        const o = by[r.ano] ||= { ano: r.ano, ouro: 0, prata: 0, bronze: 0 };
        o.ouro += r.ouro; o.prata += r.prata; o.bronze += r.bronze;
      }
      stackedYears(this.$refs.yearsChart, "years", Object.values(by).sort((a, b) => a.ano - b.ano));
    },
    get podio() { return this.ov ? this.ov.top_alunos.slice(0, 3) : []; },

    // ------------------------------------------------ busca
    typed() {
      clearTimeout(this._t);
      this._t = setTimeout(() => {
        const q = this.q.trim();
        if (q.length < 2) return;
        const query = this.is("busca") ? this.buscaQuery({ q, campo: this.campo }) : { q, campo: this.campo };
        const target = `#/busca?${new URLSearchParams(query)}`;
        if (this.is("busca")) { history.replaceState(null, "", target); this.route.query = query; this.runSearch(); }
        else location.hash = target;
      }, 220);
    },
    setCampo(c) {
      this.campo = c;
      if (this.is("busca")) this.setBuscaFilter("uf", this.bf.uf);
      else if (this.q.trim().length >= 2) this.typed();
    },
    // filtros da busca (estado, olimpíada, prêmio, ano, nível, rede) ficam na URL
    buscaQuery(base) {
      const extra = Object.fromEntries(Object.entries(this.bf).filter(([, v]) => v));
      if (this.route.query.escola_chave) extra.escola_chave = this.route.query.escola_chave;
      return { ...base, ...extra };
    },
    get buscaFiltrosAtivos() { return Object.values(this.bf).some(Boolean); },
    setBuscaFilter(k, v) {
      this.bf[k] = v;
      const query = this.buscaQuery({ q: this.q.trim(), campo: this.campo });
      history.replaceState(null, "", `#/busca?${new URLSearchParams(query)}`);
      this.route.query = query;
      this.runSearch();
    },
    limparBuscaFiltros() { for (const k of Object.keys(this.bf)) this.bf[k] = ""; this.setBuscaFilter("uf", ""); },
    async runSearch() {
      const q = this.q.trim();
      // sem texto, a busca só roda com um filtro que restrinja bem (estado, ano ou escola)
      if (q.length < 2 && !(this.bf.uf || this.bf.ano || this.route.query.escola_chave)) {
        this.busca = { loading: false, total: 0, grupos: [] }; return;
      }
      this.busca.loading = true;
      const params = this.buscaQuery({ q, campo: this.campo });
      const key = JSON.stringify(params);
      this._lastSearch = key;
      const d = await API("busca", params);
      if (this._lastSearch !== key) return;
      const byEscola = this.campo === "escola";
      const map = new Map();
      for (const r of d.resultados) {
        const k = byEscola ? r.escola_chave : r.aluno_id;
        if (!map.has(k)) map.set(k, { id: k, itens: [] });
        map.get(k).itens.push(r);
      }
      const grupos = [...map.values()].map(g => {
        const f = g.itens[0];
        const cnt = m => g.itens.filter(i => i.medalha === m).length;
        return { ...g, nome: byEscola ? prettySchool(f.escola) : (g.itens.find(i => i.competicao === "OBM") || f).nome,
          sub: byEscola ? [prettySchool(f.municipio), f.uf].filter(Boolean).join(" · ") : [...new Set(g.itens.map(i => i.uf).filter(Boolean))].join(" · "),
          ouro: cnt("Ouro"), prata: cnt("Prata"), bronze: cnt("Bronze"), xp: g.itens.reduce((s, i) => s + i.xp, 0) };
      }).sort((a, b) => b.xp - a.xp);
      this.busca = { loading: false, total: d.total, limite: d.limite, grupos, byEscola };
    },

    // ------------------------------------------------ ranking
    setFilter(k, v) { this.rk.f[k] = v; this.pushRanking(); },
    pushRanking() {
      const p = Object.fromEntries(Object.entries(this.rk.f).filter(([k, v]) => v && !(k === "ordem" && v === "xp")));
      history.replaceState(null, "", this.rankLink(this.rk.tipo, p));
      this.loadRanking();
    },
    async loadRanking(more = false) {
      this.rk.loading = true;
      const offset = more ? this.rk.itens.length : 0;
      const d = await API("ranking", { tipo: this.rk.tipo, ...this.rk.f, limite: 50, offset });
      this.rk.itens = more ? this.rk.itens.concat(d.itens) : d.itens;
      this.rk.total = d.total;
      this.rk.loading = false;
    },
    // ------------------------------------------------ filtros de múltipla escolha ("OBMEP,OBM", "1,3")
    temValor(valor, v) { return (valor || "").split(",").includes(v); },
    toggleMulti(escopo, campo, v) {
      if (campo === "nivel" && this.impa3 && !this.niveisAceitos.includes(v)) {
        this.avisar(`Está filtrado pela pontuação IMPA N3, que só considera os níveis aceitos pelo edital (${descreveImpa(this.ov?.niveis_impa)}). Para ver outros níveis, troque o método de pontuação.`,
          { label: "Usar IMPA · todos os níveis", fn: () => this.setMetodo("impa") });
        return;
      }
      const f = escopo === "rk" ? this.rk.f : this.bf;
      const sel = new Set((f[campo] || "").split(",").filter(Boolean));
      sel.has(v) ? sel.delete(v) : sel.add(v);
      const ordem = campo === "nivel" ? (this.ov?.niveis || []).map(n => n.id) : (this.ov?.olimpiadas || []).map(o => o.sigla);
      const valor = ordem.filter(id => sel.has(id)).join(",");
      escopo === "rk" ? this.setFilter(campo, valor) : this.setBuscaFilter(campo, valor);
    },
    // olimpíadas da área escolhida; níveis que existem nas olimpíadas escolhidas
    olimpiadasVisiveis(area) { return (this.ov?.olimpiadas || []).filter(o => !area || o.area === area); },
    niveisVisiveis(comps) {
      const sel = (comps || "").split(",").filter(Boolean);
      return (this.ov?.niveis || []).filter(n => !sel.length || n.competicoes.some(c => sel.includes(c)));
    },
    descreveNiveis(valor) {
      const ls = (valor || "").split(",").filter(Boolean).map(n => /^\d$/.test(n) ? `nível ${n}` : n.toLowerCase());
      return ls.length > 1 ? ls.slice(0, -1).join(", ") + " e " + ls.at(-1) : ls[0] || "";
    },
    get rkLeader() { return this.rk.itens.length ? Math.max(1, this.rk.itens[0].xp) : 1; },
    get rkPodio() { return this.rk.tipo !== "estados" ? this.rk.itens.slice(0, 3) : []; },
    get filtrosAtivos() { return Object.entries(this.rk.f).filter(([k, v]) => v && k !== "ordem").length; },
    limparFiltros() { Object.assign(this.rk.f, { uf: "", area: "", competicao: "", ano_de: "", ano_ate: "", nivel: "", rede: "" }); this.pushRanking(); },

    // ------------------------------------------------ estados
    drawMap() {
      if (!this.ov) return;
      brazilMap(this.$refs.mapChart, "map", this.ov.estados, this.mapMetric, uf => this.go(this.rankLink("alunos", { uf })));
    },
    get estadosOrdenados() { return this.ov ? [...this.ov.estados].sort((a, b) => b[this.mapMetric] - a[this.mapMetric]) : []; },

    // ------------------------------------------------ perfis
    async loadAluno(id) {
      this.loadingPerfil = true; this.aluno = null;
      const d = await API("aluno", { id });
      this.aluno = d; this.loadingPerfil = false;
      if (d.medalhas?.ouro && !sessionStorage.getItem("cf:" + id)) { sessionStorage.setItem("cf:" + id, 1); setTimeout(celebrate, 350); }
    },
    async loadEscola(id) {
      this.loadingPerfil = true; this.escola = null;
      const d = await API("escola", { id });
      this.escola = d; this.loadingPerfil = false;
      this.$nextTick(() => {
        if (d.serie) stackedYears(this.$refs.schoolChart, "school", d.serie.map(s => ({ ano: s.ano, ouro: s.Ouro, prata: s.Prata, bronze: s.Bronze })));
        if (d.medalhas?.ouro >= 10 && !sessionStorage.getItem("cf:" + id)) { sessionStorage.setItem("cf:" + id, 1); setTimeout(celebrate, 350); }
      });
    },
    get alunoPorAno() {
      if (!this.aluno?.premiacoes) return [];
      const m = new Map();
      for (const r of this.aluno.premiacoes) { if (!m.has(r.ano)) m.set(r.ano, []); m.get(r.ano).push(r); }
      return [...m.entries()].map(([ano, itens]) => ({ ano, itens }));
    },
    // ------------------------------------------------ exportação
    // baixa /api/v1/exportar com os parâmetros dados; formato: csv | excel | json
    async baixar(params, formato = "csv") {
      if (this.exportando) return;
      const p = { ...params, formato: formato === "json" ? "json" : "csv" };
      if (formato === "excel") p.separador = ";";
      const qs = new URLSearchParams(Object.entries(p).filter(([, v]) => v !== "" && v != null));
      this.exportando = true;
      this.avisar("Preparando o arquivo…");
      try {
        const r = await fetch(`/api/v1/exportar?${qs}`);
        if (!r.ok) {
          const e = await r.json().catch(() => ({}));
          this.avisar(e.erro ? `Não deu para exportar: ${e.erro}` : `Não deu para exportar (erro ${r.status}).`);
          return;
        }
        const nome = (r.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/)?.[1] || `medalhas.${p.formato}`;
        const linhas = +r.headers.get("X-Total-Rows") || 0;
        const blob = await r.blob();
        const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: nome });
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 30000);
        this.avisar(`${nome} baixado · ${fmt(linhas)} ${linhas === 1 ? "linha" : "linhas"}.`);
      } catch {
        this.avisar("Não deu para exportar: falha de conexão.");
      } finally {
        this.exportando = false;
      }
    },
    // filtros da tela atual no formato da API pública
    get exportBusca() {
      const q = this.q.trim(), p = { metodo: this.metodo };
      if (q) p[{ nome: "nome", escola: "escola", tudo: "busca" }[this.campo] || "nome"] = q;
      for (const [k, v] of Object.entries(this.bf)) if (v) p[k] = v;
      if (this.impa3) p.nivel = this.nivelEfetivo(this.bf.nivel);
      if (this.route.query.escola_chave) p.escola_id = this.route.query.escola_chave;
      return p;
    },
    exportRanking(conjunto) {
      const { ordem, ...f } = this.rk.f;
      const p = { metodo: this.metodo, ...Object.fromEntries(Object.entries(f).filter(([, v]) => v)) };
      if (this.impa3) p.nivel = this.nivelEfetivo(f.nivel);
      if (conjunto !== "premiacoes") { p.conjunto = conjunto; if (ordem && ordem !== "xp") p.ordem = ordem; }
      if (conjunto === "estados") delete p.uf;
      return p;
    },

    // ------------------------------------------------ documentação da API
    async loadDoc() {
      if (this.doc.limites) return;
      try { this.doc.limites = (await (await fetch("/api/v1")).json()).limites; } catch { /* a página funciona sem */ }
    },
    codigo(receita) { const l = this.doc.lang; return realcar(RECEITAS[receita][l].replaceAll("{B}", BASE), l === "curl" ? "bash" : l); },
    async copiar(texto, chave) {
      try {
        await navigator.clipboard.writeText(texto.replaceAll("{B}", BASE));
        this.doc.copiado = chave;
        setTimeout(() => (this.doc.copiado = ""), 1500);
      } catch { this.avisar("Não foi possível copiar."); }
    },
    receitaTexto(receita) { return RECEITAS[receita][this.doc.lang]; },
    async testar(rota) {
      this.doc.carregando[rota.id] = true;
      try {
        const r = await fetch(rota.teste);
        const corpo = await r.json();
        this.doc.resp[rota.id] = { status: r.status, restam: r.headers.get("X-RateLimit-Remaining"),
          html: realcar(JSON.stringify(resumirJSON(corpo), null, 2), "json") };
      } catch {
        this.doc.resp[rota.id] = { status: 0, html: "falha de conexão" };
      } finally {
        this.doc.carregando[rota.id] = false;
      }
    },

    percentil(rank, total) { const p = rank / total * 100; return p < 0.1 ? "Top 0,1%" : p < 1 ? `Top ${p.toFixed(1).replace(".", ",")}%` : `Top ${Math.ceil(p)}%`; },
    desbloqueadas(list) { return (list || []).filter(c => c.desbloqueada).length; },
    tierStyle(t) { return t ? `--tc:${t.cor}` : ""; },
  };
}
