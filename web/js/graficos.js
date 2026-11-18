/* Gráficos (ECharts), confete e contador animado. Ficam fora do Alpine para não virarem proxies reativos. */

const charts = {};
const desenhos = {};   // por chave, a última chamada de cada gráfico: refeita quando o tema muda
// cores das séries (as mesmas nos dois temas) e, em VIZ.*, as cores da interface lidas do CSS a cada desenho
const VIZ = { ouro: "#b5870c", prata: "#6688d6", bronze: "#b5602b", mencao: "#3f9d6a" };

// Resolve uma cor do CSS (var(--text), color-mix(...)) para rgb(): o ECharts desenha em canvas e não entende
// variáveis, e as variáveis do tema guardam light-dark(), que só o navegador resolve.
const sonda = document.createElement("span");
function corCSS(valor) {
  if (!sonda.isConnected) { sonda.style.display = "none"; document.body.append(sonda); }
  sonda.style.color = ""; sonda.style.color = valor;
  return getComputedStyle(sonda).color;
}
// cores da interface no tema em uso
function coresTema() {
  const escuro = document.documentElement.dataset.tema ? document.documentElement.dataset.tema === "escuro"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  return {
    escuro,
    text: corCSS("var(--text-2)"), muted: corCSS("var(--muted)"), forte: corCSS("var(--text)"),
    grid: corCSS("color-mix(in srgb, var(--tinta) 8%, transparent)"), surface: corCSS("var(--surface)"), bg: corCSS("var(--bg)"),
    sombra: corCSS("color-mix(in srgb, var(--tinta) 5%, transparent)"), borda: corCSS("var(--line-2)"),
    // escala do mapa: do fundo ao dourado (no papel, o fim da escala escurece para ter contraste)
    escala: escuro ? ["#2a251d", "#3a3017", "#6b5212", "#a07810", "#d9a521", "#ffd76e"]
                   : ["#ece4d3", "#ead79f", "#ddb651", "#c4961f", "#9c7410", "#6e5108"],
  };
}
// o botão de tema (ou o sistema) mudou: refaz os gráficos que estão na tela com as cores novas
function temaMudou() {
  for (const [key, refazer] of Object.entries(desenhos)) if (charts[key]) refazer();
}
let brGeo = null;   // promessa do contorno dos estados: baixado uma vez, mesmo com dois desenhos ao mesmo tempo

// Mercator em graus; y cresce para baixo, como na tela (norte em cima)
const RAD = Math.PI / 180;
const MERCATOR = {
  project: ([lon, lat]) => [lon, -Math.log(Math.tan(Math.PI / 4 + lat * RAD / 2)) / RAD],
  unproject: ([x, y]) => [x, (2 * Math.atan(Math.exp(-y * RAD)) - Math.PI / 2) / RAD],
};

// O gráfico acompanha o tamanho da própria área, não só o da janela: as seções começam escondidas
// (x-show), então na criação a largura pode ser 0 e o ECharts desenharia com um tamanho padrão.
const observador = new ResizeObserver(entradas => {
  for (const { target } of entradas) {
    if (target.clientWidth && target.clientHeight) echarts.getInstanceByDom(target)?.resize();
  }
});

// Instância do ECharts guardada por chave. Se o elemento mudou (o Alpine recriou a seção), descarta a antiga
// e cria outra; null se o elemento ainda não existe.
function chart(el, key) {
  if (!el) return null;
  if (charts[key] && charts[key].getDom() !== el) { observador.unobserve(charts[key].getDom()); charts[key].dispose(); delete charts[key]; }
  if (!charts[key]) { charts[key] = echarts.init(el, null, { renderer: "canvas" }); observador.observe(el); }
  return charts[key];
}

const tooltipBase = c => ({
  backgroundColor: c.surface, borderColor: c.borda, borderWidth: 1,
  textStyle: { color: c.forte, fontFamily: "Public Sans", fontSize: 12 },
  extraCssText: `border-radius:12px;box-shadow:0 12px 40px ${c.escuro ? "rgba(0,0,0,.5)" : "rgba(60,45,20,.18)"};`,
});

// log = true: eixo logarítmico, para os anos com dezenas de medalhas aparecerem ao lado dos com milhares.
// Nesse modo as barras ficam lado a lado: empilhadas num eixo log, a fatia de baixo (ouro) pareceria
// muito maior do que é. Zero não existe em escala log, então vira lacuna (o tooltip mostra 0).
function stackedYears(el, key, rows, log = false) {
  const c = chart(el, key); if (!c) return;
  desenhos[key] = () => stackedYears(el, key, rows, log);
  const T = coresTema();
  const anos = rows.map(r => r.ano);
  const serie = (name, field, color, top) => ({
    name, type: "bar", stack: log ? undefined : "m", barMaxWidth: log ? 9 : 26, barGap: log ? "10%" : undefined, barMinHeight: log ? 3 : 0,
    data: rows.map(r => (log && !r[field] ? null : r[field])),
    itemStyle: { color, borderColor: T.surface, borderWidth: log ? 0 : 1, borderRadius: top || log ? [3, 3, 0, 0] : 0 },
    emphasis: { focus: "series" },
  });
  c.setOption({
    animationDuration: 900, animationEasing: "cubicOut",
    grid: { left: 8, right: 8, top: 36, bottom: 4, containLabel: true },
    legend: { top: 0, left: 0, icon: "roundRect", itemWidth: 10, itemHeight: 10, textStyle: { color: T.text, fontFamily: "Public Sans" } },
    tooltip: { ...tooltipBase(T), trigger: "axis", axisPointer: { type: "shadow", shadowStyle: { color: T.sombra } },
      formatter: ps => `<b>${ps[0].axisValue}</b><br>` + ps.map(p => `${p.marker} ${p.seriesName}: <b>${fmt(p.value || 0)}</b>`).join("<br>")
        + `<br><span style="color:${T.muted}">Total: ${fmt(ps.reduce((s, p) => s + (p.value || 0), 0))}</span>` },
    xAxis: { type: "category", data: anos, axisLine: { lineStyle: { color: T.grid } }, axisTick: { show: false }, axisLabel: { color: T.muted, fontFamily: "Public Sans" } },
    yAxis: { type: log ? "log" : "value", min: log ? 1 : undefined, logBase: 10,
      splitLine: { lineStyle: { color: T.grid } }, axisLabel: { color: T.muted, fontFamily: "Public Sans", formatter: v => fmt(v) } },
    series: [serie("Ouro", "ouro", VIZ.ouro), serie("Prata", "prata", VIZ.prata), serie("Bronze", "bronze", VIZ.bronze),
      serie("Menção", "mencao", VIZ.mencao, true)],
  }, true);
}

// Mapa do Brasil com cada estado pintado pela métrica (xp, ouro, total ou alunos). O contorno dos estados é
// baixado na primeira vez. comTooltip=false (telas de toque): o toque chama onClick e acende o estado.
async function brazilMap(el, key, estados, metric, onClick, comTooltip = true) {
  const c = chart(el, key); if (!c) return;
  desenhos[key] = () => brazilMap(el, key, estados, metric, onClick, comTooltip).catch(() => {});
  c.showLoading({ text: "", color: "#f5c542", maskColor: "transparent" });
  // contorno dos estados (name = sigla da UF), simplificado a partir do brazil-states.geojson do
  // projeto click_that_hood (Code for Germany): ~150 KB compactado em vez de 3,4 MB de um CDN externo
  brGeo ||= fetch("/brasil-uf.json")
    .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(geo => echarts.registerMap("BR", geo));
  try {
    await brGeo;
  } catch (e) {
    brGeo = null;   // a próxima tentativa baixa de novo
    c.hideLoading();
    throw e;        // quem chamou avisa o usuário
  }
  c.hideLoading();
  const labels = { xp: "Pontos", ouro: "Ouros", total: "Premiações", alunos: "Alunos premiados" };
  const data = estados.map(e => ({ name: e.id, value: e[metric], raw: e }));
  const max = Math.max(...data.map(d => d.value), 1);
  const T = coresTema();
  c.setOption({
    tooltip: { ...tooltipBase(T), show: comTooltip, trigger: "item", formatter: p => {
      const e = p.data?.raw; if (!e) return p.name;
      return `<b>${UF_NOMES[e.id]}</b> <span style="color:${T.muted}">#${e.pos}</span><br>
        ${labels[metric]}: <b>${fmt(e[metric])}</b><br>
        <span style="color:${VIZ.ouro}">●</span> ${fmt(e.ouro)} &nbsp;<span style="color:${VIZ.prata}">●</span> ${fmt(e.prata)} &nbsp;<span style="color:${VIZ.bronze}">●</span> ${fmt(e.bronze)} &nbsp;<span style="color:${VIZ.mencao}">●</span> ${fmt(e.mencao)}`;
    } },
    visualMap: { min: 0, max, calculable: false, orient: "horizontal", left: "center", bottom: 0, itemWidth: 12, itemHeight: 180,
      text: [fmt(max), "0"], textStyle: { color: T.text, fontFamily: "Public Sans" },
      inRange: { color: T.escala } },
    // layoutSize em % é relativo ao menor lado da área: o mapa cabe inteiro na largura e na altura
    // sem esticar (com top/bottom/left/right o ECharts deformaria o mapa para preencher o retângulo)
    // projeção de Mercator (a mesma do Google Maps/OpenStreetMap): sem ela o ECharts desenha lon/lat
    // cru com aspectScale 0.75, que espreme o Brasil 25% na horizontal e deixa o mapa alto e fino
    series: [{ type: "map", map: "BR", roam: false, data, layoutCenter: ["50%", "45%"], layoutSize: "86%", projection: MERCATOR,
      itemStyle: { borderColor: T.bg, borderWidth: 1, areaColor: T.escala[0] },
      emphasis: { label: { show: true, color: "#1a1405", fontWeight: 700 }, itemStyle: { areaColor: "#ffe08a", shadowBlur: 20, shadowColor: "rgba(245,197,66,.6)" } },
      select: { disabled: true },
      label: { show: false } }],
  }, true);
  c.off("click");
  c.on("click", p => {
    if (!p.name) return;
    if (!comTooltip) destacarEstado(key, p.name);   // no toque, o estado escolhido fica aceso
    onClick(p.name);
  });
}

// Acende um estado no mapa (ou apaga todos com nome vazio).
function destacarEstado(key, nome) {
  const c = charts[key]; if (!c) return;
  c.dispatchAction({ type: "downplay", seriesIndex: 0 });
  if (nome) c.dispatchAction({ type: "highlight", seriesIndex: 0, name: nome });
}

// ---------------------------------------------------------------- confete
// três rajadas de confete; nada acontece se o sistema pede menos movimento
function celebrate() {
  if (!window.confetti || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const colors = ["#f5c542", "#ffe08a", "#ffffff", "#7c8cff"];
  confetti({ particleCount: 90, spread: 70, origin: { y: .25 }, colors, scalar: .9 });
  setTimeout(() => confetti({ particleCount: 60, angle: 60, spread: 55, origin: { x: 0, y: .4 }, colors }), 180);
  setTimeout(() => confetti({ particleCount: 60, angle: 120, spread: 55, origin: { x: 1, y: .4 }, colors }), 300);
}

// ---------------------------------------------------------------- contador animado
// conta de 0 até `to` em 1,4 s, desacelerando no fim; direto no valor se o sistema pede menos movimento
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
