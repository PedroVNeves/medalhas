/* Gráficos (ECharts), confete e contador animado. Ficam fora do Alpine para não virarem proxies reativos. */

const charts = {};
const VIZ = { ouro: "#b5870c", prata: "#6688d6", bronze: "#b5602b", text: "#a3abc2", muted: "#6b7489", grid: "rgba(255,255,255,.06)", surface: "#0f1424" };
let brGeo = null;

// O gráfico acompanha o tamanho da própria área, não só o da janela: as seções começam escondidas
// (x-show), então na criação a largura pode ser 0 e o ECharts desenharia com um tamanho padrão.
const observador = new ResizeObserver(entradas => {
  for (const { target } of entradas) {
    if (target.clientWidth && target.clientHeight) echarts.getInstanceByDom(target)?.resize();
  }
});

function chart(el, key) {
  if (!el) return null;
  if (charts[key] && charts[key].getDom() !== el) { observador.unobserve(charts[key].getDom()); charts[key].dispose(); delete charts[key]; }
  if (!charts[key]) { charts[key] = echarts.init(el, null, { renderer: "canvas" }); observador.observe(el); }
  return charts[key];
}

const tooltipBase = {
  backgroundColor: "rgba(12,17,32,.96)", borderColor: "rgba(255,255,255,.12)", borderWidth: 1,
  textStyle: { color: "#e8ebf5", fontFamily: "Inter", fontSize: 12 }, extraCssText: "border-radius:12px;box-shadow:0 12px 40px rgba(0,0,0,.5);",
};

// log = true: eixo logarítmico, para os anos com dezenas de medalhas aparecerem ao lado dos com milhares.
// Nesse modo as barras ficam lado a lado: empilhadas num eixo log, a fatia de baixo (ouro) pareceria
// muito maior do que é. Zero não existe em escala log, então vira lacuna (o tooltip mostra 0).
function stackedYears(el, key, rows, log = false) {
  const c = chart(el, key); if (!c) return;
  const anos = rows.map(r => r.ano);
  const serie = (name, field, color, top) => ({
    name, type: "bar", stack: log ? undefined : "m", barMaxWidth: log ? 9 : 26, barGap: log ? "10%" : undefined, barMinHeight: log ? 3 : 0,
    data: rows.map(r => (log && !r[field] ? null : r[field])),
    itemStyle: { color, borderColor: VIZ.surface, borderWidth: log ? 0 : 1, borderRadius: top || log ? [3, 3, 0, 0] : 0 },
    emphasis: { focus: "series" },
  });
  c.setOption({
    animationDuration: 900, animationEasing: "cubicOut",
    grid: { left: 8, right: 8, top: 36, bottom: 4, containLabel: true },
    legend: { top: 0, left: 0, icon: "roundRect", itemWidth: 10, itemHeight: 10, textStyle: { color: VIZ.text, fontFamily: "Inter" } },
    tooltip: { ...tooltipBase, trigger: "axis", axisPointer: { type: "shadow", shadowStyle: { color: "rgba(255,255,255,.04)" } },
      formatter: ps => `<b>${ps[0].axisValue}</b><br>` + ps.map(p => `${p.marker} ${p.seriesName}: <b>${fmt(p.value || 0)}</b>`).join("<br>")
        + `<br><span style="color:${VIZ.muted}">Total: ${fmt(ps.reduce((s, p) => s + (p.value || 0), 0))}</span>` },
    xAxis: { type: "category", data: anos, axisLine: { lineStyle: { color: VIZ.grid } }, axisTick: { show: false }, axisLabel: { color: VIZ.muted, fontFamily: "Inter" } },
    yAxis: { type: log ? "log" : "value", min: log ? 1 : undefined, logBase: 10,
      splitLine: { lineStyle: { color: VIZ.grid } }, axisLabel: { color: VIZ.muted, fontFamily: "Inter", formatter: v => fmt(v) } },
    series: [serie("Ouro", "ouro", VIZ.ouro), serie("Prata", "prata", VIZ.prata), serie("Bronze", "bronze", VIZ.bronze, true)],
  }, true);
}

async function brazilMap(el, key, estados, metric, onClick, comTooltip = true) {
  const c = chart(el, key); if (!c) return;
  c.showLoading({ text: "", color: "#f5c542", maskColor: "transparent" });
  if (!brGeo) {
    // contorno dos estados (name = sigla da UF), simplificado a partir do brazil-states.geojson do
    // projeto click_that_hood (Code for Germany): ~150 KB compactado em vez de 3,4 MB de um CDN externo
    const geo = await fetch("brasil-uf.json").then(r => r.json());
    echarts.registerMap("BR", geo);
    brGeo = geo;
  }
  c.hideLoading();
  const labels = { xp: "Pontos", ouro: "Ouros", total: "Premiações", alunos: "Alunos premiados" };
  const data = estados.map(e => ({ name: e.id, value: e[metric], raw: e }));
  const max = Math.max(...data.map(d => d.value), 1);
  c.setOption({
    tooltip: { ...tooltipBase, show: comTooltip, trigger: "item", formatter: p => {
      const e = p.data?.raw; if (!e) return p.name;
      return `<b>${UF_NOMES[e.id]}</b> <span style="color:${VIZ.muted}">#${e.pos}</span><br>
        ${labels[metric]}: <b>${fmt(e[metric])}</b><br>
        <span style="color:${VIZ.ouro}">●</span> ${fmt(e.ouro)} &nbsp;<span style="color:${VIZ.prata}">●</span> ${fmt(e.prata)} &nbsp;<span style="color:${VIZ.bronze}">●</span> ${fmt(e.bronze)}`;
    } },
    visualMap: { min: 0, max, calculable: false, orient: "horizontal", left: "center", bottom: 0, itemWidth: 12, itemHeight: 180,
      text: [fmt(max), "0"], textStyle: { color: VIZ.text, fontFamily: "Inter" },
      inRange: { color: ["#1b2236", "#3a3017", "#6b5212", "#a07810", "#d9a521", "#ffd76e"] } },
    // layoutSize em % é relativo ao menor lado da área: o mapa cabe inteiro na largura e na altura
    // sem esticar (com top/bottom/left/right o ECharts deformaria o mapa para preencher o retângulo)
    series: [{ type: "map", map: "BR", roam: false, data, layoutCenter: ["50%", "45%"], layoutSize: "86%",
      itemStyle: { borderColor: "#070a14", borderWidth: 1, areaColor: "#1b2236" },
      emphasis: { label: { show: true, color: "#fff", fontWeight: 700 }, itemStyle: { areaColor: "#ffe08a", shadowBlur: 20, shadowColor: "rgba(245,197,66,.6)" } },
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
