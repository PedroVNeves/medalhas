/* Componente Alpine da página inteira: rotas (hash), estado e ações. Depende de util.js, graficos.js e documentacao-api.js. */

function app() {
  return {
    UF_NOMES, fmt, prettySchool, destacarEstado, initials, nivelLabel, medalClass, nivelCurto, descreveImpa,
    route: { name: "home", param: "", query: {} },
    metodo: METODO,
    aviso: null, _avisoT: null,
    ov: null,
    yearComp: "",
    mapMetric: "xp",
    mapSel: "",   // estado tocado no mapa (telas de toque, que não têm "passar o mouse")
    toque: matchMedia("(hover: none)").matches,
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
      if (r.name === "estados") { this.mapSel = ""; this.$nextTick(() => this.drawMap()); }
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
    get buscaFiltrosAtivos() { return Object.values(this.bf).filter(Boolean).length; },
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
      // no toque, o clique abre o mini card (com "ver ranking"); com mouse, o tooltip já mostra os números
      brazilMap(this.$refs.mapChart, "map", this.ov.estados, this.mapMetric,
        uf => this.toque ? this.tocarEstado(uf) : this.go(this.rankLink("alunos", { uf })), !this.toque)
        .then(() => this.mapSel && destacarEstado("map", this.mapSel));   // trocar o indicador redesenha o mapa
    },
    tocarEstado(uf) {
      this.mapSel = uf;   // rola até o card se ele nascer abaixo da dobra da tela
      this.$nextTick(() => this.$refs.mapCard?.scrollIntoView({ block: "nearest", behavior: "smooth" }));
    },
    get mapEstado() { return this.mapSel && this.ov ? this.ov.estados.find(e => e.id === this.mapSel) : null; },
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
