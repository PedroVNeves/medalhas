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
    percentil(rank, total) { const p = rank / total * 100; return p < 0.1 ? "Top 0,1%" : p < 1 ? `Top ${p.toFixed(1).replace(".", ",")}%` : `Top ${Math.ceil(p)}%`; },
    desbloqueadas(list) { return (list || []).filter(c => c.desbloqueada).length; },
    tierStyle(t) { return t ? `--tc:${t.cor}` : ""; },
  };
}
