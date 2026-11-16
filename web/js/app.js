/* Componente Alpine da página inteira: rotas, estado e ações. Depende de util.js, graficos.js e documentacao-api.js. */

const TITULO_SITE = "Medalhas · Medalhistas da OBMEP, OBM, OBI e IMO: busca e rankings";
// os mesmos títulos que o servidor põe em cada endereço (paginas.py, TELAS): valem ao navegar sem recarregar
const TITULOS = {
  "/ranking/alunos": "Ranking dos maiores medalhistas das olimpíadas do Brasil · Medalhas",
  "/ranking/escolas": "Ranking das escolas com mais medalhas em olimpíadas · Medalhas",
  "/ranking/cidades": "Ranking das cidades com mais medalhas em olimpíadas · Medalhas",
  "/ranking/estados": "Ranking dos estados em medalhas nas olimpíadas · Medalhas",
  "/estados": "Mapa das medalhas em olimpíadas por estado do Brasil · Medalhas",
  "/dados": "API e dados abertos dos medalhistas das olimpíadas · Medalhas",
  "/busca": "Busca · Medalhas",
  "/sobre": "Sobre o Medalhas: por que reunimos os medalhistas das olimpíadas",
};
// telas do site; outro endereço mostra "página não encontrada"
const TELAS = ["home", "busca", "ranking", "estados", "sobre", "dados", "aluno", "escola", "cidade"];
// endereços que o site abre sem recarregar a página
const ROTA_INTERNA = /^\/(busca|ranking(\/(alunos|escolas|estados|cidades))?|estados|sobre|dados|(aluno|escola|cidade)\/[^/]+)?$/;

function app() {
  return {
    UF_NOMES, fmt, prettySchool, destacarEstado, initials, nivelLabel, medalClass, nivelCurto, descreveImpa,
    route: { name: "home", param: "", query: {} },
    metodo: METODO,
    aviso: null, _avisoT: null,
    ov: null,
    yearComp: "",
    yearLog: true,
    mapMetric: "xp",
    mapSel: "",   // estado tocado no mapa (telas de toque, que não têm "passar o mouse")
    toque: matchMedia("(hover: none)").matches,
    // busca
    _rotaAtual: null,
    q: "", campo: "nome", busca: { loading: false, total: 0, grupos: [] }, _t: null,
    // sugestões enquanto digita (início e barra do topo): onde = qual campo mostra a lista; ativo = item do teclado
    sug: { lista: [], onde: "", ativo: -1, q: "" }, _ts: null,
    bf: { uf: "", area: "", competicao: "", medalha: "", ano: "", nivel: "", rede: "", sexo: "" },
    // ranking
    rk: { tipo: "alunos", itens: [], total: 0, loading: false, f: { uf: "", area: "", competicao: "", ano_de: "", ano_ate: "", nivel: "", rede: "", sexo: "", municipio: "", ordem: "xp" } },
    // perfis
    aluno: null, escola: null, cidade: null, loadingPerfil: false,
    // exportação e documentação da API
    exportando: false,
    BASE, ROTAS, FILTROS, CAMPOS_PREMIACAO,
    doc: { lang: "curl", resp: {}, carregando: {}, limites: null, copiado: "" },
    // story do Instagram (perfis): imagem vertical desenhada pelo servidor em /og/story/...
    story: { aberto: false, src: "", link: "", nomeArquivo: "", arquivo: null, carregando: false, erro: false,
             copiado: false, podeCompartilhar: false },

    async init() {
      // voltar/avançar do navegador (popstate) e endereço com # editado à mão (hashchange)
      window.addEventListener("popstate", () => this.onRoute());
      window.addEventListener("hashchange", () => this.onRoute());
      // links internos trocam de página sem recarregar o site (Ctrl/Cmd+clique continua abrindo outra aba)
      document.addEventListener("click", e => {
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        const a = e.target.closest("a[href]");
        if (!a || a.target || a.hasAttribute("download")) return;
        const url = new URL(a.href, location.href);
        if (url.origin !== location.origin) return;
        if (url.pathname === location.pathname && url.search === location.search && url.hash && !url.hash.startsWith("#/")) return;   // âncora na mesma página
        if (ROTA_INTERNA.test(url.pathname)) { e.preventDefault(); this.navegar(url.pathname + url.search + url.hash); }
      });
      window.addEventListener("keydown", e => {
        if (e.key === "/" && !/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) { e.preventDefault(); (this.is("home") ? this.$refs.q : this.is("busca") ? this.$refs.qBusca : this.$refs.qNav)?.focus(); }
      });
      this.onRoute(true);  // a rota não espera a visão geral: perfis e rankings carregam sozinhos
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
      this.onRoute(true);
      await this.loadOverview();
      window.scrollTo({ top: y, behavior: "instant" });
    },

    // ------------------------------------------------ roteamento
    // Cada tela tem endereço próprio, que o Google indexa: /ranking/alunos, /estados, /sobre,
    // /aluno/maria-souza-lima-al... (o servidor entrega o index.html com o título e um resumo daquela
    // página). Links antigos com # (/#/ranking/alunos, #/aluno/NOME%7CUF, #/api) são convertidos.
    go(path) { this.navegar(path); },
    navegar(url) {
      if (url !== location.pathname + location.search + location.hash) history.pushState(null, "", url);
      this.onRoute();
    },
    onRoute(forcar = false) {
      const atual = location.pathname + location.search + location.hash;
      if (atual === this._rotaAtual && !forcar) return;   // popstate e hashchange chegam juntos
      this._rotaAtual = atual;
      this.fecharSugestoes();
      let caminho = location.pathname + location.search;
      if (location.hash.startsWith("#/")) {   // link antigo
        const perfil = location.hash.match(/^#\/(aluno|escola)\/([^?]+)/);
        caminho = perfil ? `/${perfil[1]}/${slug(decodeURIComponent(perfil[2]))}`
          : location.hash.slice(1).replace(/^\/api(?=\?|$)/, "/dados");
        history.replaceState(null, "", caminho);
        this._rotaAtual = caminho;
      }
      const [path, qs] = caminho.split("?");
      const parts = (path || "/").split("/").filter(Boolean);
      const query = Object.fromEntries(new URLSearchParams(qs || ""));
      this.route = { name: parts[0] || "home", param: decodeURIComponent(parts.slice(1).join("/")), query };
      if (!["aluno", "escola", "cidade"].includes(this.route.name)) document.title = TITULOS[path] || TITULO_SITE;
      // links podem fixar o método: /ranking/alunos?metodo=impa3
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
        if (!this.q) this.$nextTick(() => this.$refs.qBusca?.focus());   // veio pelo menu: já pode digitar
      }
      if (r.name === "ranking" && !r.param) { history.replaceState(null, "", this.rankLink("alunos")); this._rotaAtual = location.pathname + location.search; r.param = "alunos"; }
      if (r.name === "ranking") { this.rk.tipo = r.param || "alunos"; Object.assign(this.rk.f, { uf: "", area: "", competicao: "", ano_de: "", ano_ate: "", nivel: "", rede: "", sexo: "", municipio: "", ordem: "xp" }, Object.fromEntries(Object.entries(query).filter(([k]) => k !== "metodo"))); this.loadRanking(); }
      if (r.name === "estados") { this.mapSel = ""; this.$nextTick(() => this.drawMap()); }
      if (r.name === "dados") this.loadDoc();
      if (r.name === "aluno") this.loadAluno(r.param);
      if (r.name === "escola") this.loadEscola(r.param);
      if (r.name === "cidade") this.loadCidade(r.param);
    },
    is(name) { return this.route.name === name; },
    get naoEncontrada() { return !TELAS.includes(this.route.name); },
    alunoLink(id) { return "/aluno/" + slug(id); },
    escolaLink(id) { return "/escola/" + slug(id); },
    // id da cidade = MUNICIPIO|UF sem acento: o slug do id é o endereço (/cidade/sao-paulo-sp)
    cidadeLink(municipio, uf) { return municipio && uf ? "/cidade/" + slug(`${municipio} ${uf}`) : null; },
    rankLink(tipo, extra = {}) { const p = new URLSearchParams(extra).toString(); return `/ranking/${tipo}${p ? "?" + p : ""}`; },

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
      stackedYears(this.$refs.yearsChart, "years", Object.values(by).sort((a, b) => a.ano - b.ano), this.yearLog);
    },
    // Todas as olimpíadas juntas vão de dezenas (anos 80/90) a ~9 mil medalhas (OBMEP): começa em escala log.
    // Uma olimpíada só tem ordens de grandeza parecidas entre os anos, então volta para a escala linear.
    escolherYearComp(sigla) {
      this.yearComp = sigla;
      this.yearLog = !sigla;
      this.drawYears();
    },
    get podio() { return this.ov ? this.ov.top_alunos.slice(0, 3) : []; },

    // ------------------------------------------------ busca
    // Na página de busca os resultados acompanham a digitação. Nas outras (início, rankings, perfis)
    // digitar não muda de página: a busca só abre com Enter ou com o botão Buscar (buscar()).
    typed(onde = "") {
      clearTimeout(this._t);
      if (!this.is("busca")) { this.pedirSugestoes(onde); return; }
      this._t = setTimeout(() => {
        const q = this.q.trim();
        if (q.length === 1) return;   // vazio limpa os resultados (ou mostra só os filtros); 2+ letras busca
        const query = this.buscaQuery({ q, campo: this.campo });
        history.replaceState(null, "", `/busca?${new URLSearchParams(query)}`); this._rotaAtual = location.pathname + location.search + location.hash;
        this.route.query = query; this.runSearch();
      }, 220);
    },
    buscar() {
      clearTimeout(this._t);
      this.fecharSugestoes();
      const q = this.q.trim();
      if (q.length < 2) { (this.is("busca") ? this.$refs.qBusca : this.$refs.q)?.focus(); return; }
      if (this.is("busca")) { this.typed(); return; }
      this.go(`/busca?${new URLSearchParams({ q, campo: this.campo })}`);
    },
    // ------------------------------------------------ sugestões (fora da página de busca)
    // Digitar mostra, embaixo do campo, os alunos e escolas mais premiados que casam com o texto;
    // Enter sem item escolhido abre a busca completa.
    pedirSugestoes(onde) {
      clearTimeout(this._ts);
      if (this.is("busca")) return;   // lá os resultados completos já acompanham a digitação
      if (onde) this.sug.onde = onde;
      const q = this.q.trim();
      if (q.length < 2) { this.sug.lista = []; this.sug.q = ""; return; }
      this._ts = setTimeout(() => this.carregarSugestoes(q), 120);
    },
    // a barra do topo não tem o seletor Pessoa/Escola/Tudo: sugere os dois
    get campoSugestoes() { return this.sug.onde === "nav" ? "tudo" : this.campo; },
    async carregarSugestoes(q) {
      const campo = this.campoSugestoes;
      let d;
      try { d = await API("sugestoes", { q, campo }); } catch { return; }
      if (q !== this.q.trim() || campo !== this.campoSugestoes || !this.sug.onde) return;   // já digitou outra coisa
      const local = (municipio, uf) => [prettySchool(municipio), uf].filter(Boolean).join(" · ");
      this.sug.lista = [
        ...d.alunos.map(a => ({ ...a, tipo: "aluno", link: this.alunoLink(a.id),
          sub: [prettySchool(a.escola), local(a.municipio, a.uf)].filter(Boolean).join(" · ") })),
        ...d.escolas.map(e => ({ ...e, tipo: "escola", link: this.escolaLink(e.id), nome: prettySchool(e.nome),
          sub: [local(e.municipio, e.uf), e.alunos ? `${fmt(e.alunos)} ${e.alunos === 1 ? "medalhista" : "medalhistas"}` : ""]
            .filter(Boolean).join(" · ") })),
      ];
      this.sug.q = q;
      this.sug.ativo = -1;
    },
    get sugAberta() { return !!this.sug.onde && this.q.trim().length >= 2 && this.sug.q !== "" && !this.is("busca"); },
    fecharSugestoes() {
      clearTimeout(this._ts);
      this.sug.onde = ""; this.sug.ativo = -1;
    },
    teclaSugestoes(e, onde) {
      if (this.is("busca")) { if (e.key === "Enter") this.buscar(); return; }
      const n = this.sug.lista.length;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        if (!this.sugAberta) { this.pedirSugestoes(onde); return; }
        e.preventDefault();
        // n = "ver todos os resultados", último item da lista
        this.sug.ativo = e.key === "ArrowDown" ? (this.sug.ativo >= n ? 0 : this.sug.ativo + 1) : (this.sug.ativo <= 0 ? n : this.sug.ativo - 1);
      } else if (e.key === "Enter") {
        e.preventDefault();
        const item = this.sugAberta && this.sug.lista[this.sug.ativo];
        if (item) { this.q = ""; this.go(item.link); } else this.buscar();
      } else if (e.key === "Escape" && this.sugAberta) {
        e.preventDefault(); this.fecharSugestoes();
      }
    },
    setCampo(c) {
      this.campo = c;
      if (!this.is("busca") && this.sug.onde) this.pedirSugestoes();
      if (this.is("busca")) this.setBuscaFilter("uf", this.bf.uf);
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
      history.replaceState(null, "", `/busca?${new URLSearchParams(query)}`); this._rotaAtual = location.pathname + location.search + location.hash;
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
    get rkPodio() { return ["alunos", "escolas"].includes(this.rk.tipo) ? this.rk.itens.slice(0, 3) : []; },
    get filtrosAtivos() { return Object.entries(this.rk.f).filter(([k, v]) => v && k !== "ordem").length; },
    limparFiltros() { Object.assign(this.rk.f, { uf: "", area: "", competicao: "", ano_de: "", ano_ate: "", nivel: "", rede: "", sexo: "", municipio: "" }); this.pushRanking(); },

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
    // a página do perfil vem pelo endereço (/aluno/maria-souza-lima-al); a resposta traz o endereço
    // oficial (o de escolas usa o nome de exibição), que substitui o da barra sem criar outra entrada
    perfilCarregado(d) {
      if (d.endereco && d.endereco !== location.pathname) {
        history.replaceState(null, "", d.endereco + location.search);
        this._rotaAtual = location.pathname + location.search + location.hash;
      }
      if (!d.nome) return;
      const nome = this.is("escola") ? prettySchool(d.nome) : d.nome;
      document.title = `${d.uf ? `${nome} (${d.uf})` : nome} · Medalhas`;
    },
    async loadAluno(endereco) {
      this.loadingPerfil = true; this.aluno = null;
      const d = await API("aluno", { endereco });
      this.aluno = d; this.loadingPerfil = false;
      this.perfilCarregado(d);
      const id = d.id;
      if (d.medalhas?.ouro && !sessionStorage.getItem("cf:" + id)) { sessionStorage.setItem("cf:" + id, 1); setTimeout(celebrate, 350); }
    },
    async loadEscola(endereco) {
      this.loadingPerfil = true; this.escola = null;
      const d = await API("escola", { endereco });
      this.escola = d; this.loadingPerfil = false;
      this.perfilCarregado(d);
      const id = d.id;
      this.$nextTick(() => {
        if (d.serie) stackedYears(this.$refs.schoolChart, "school", d.serie.map(s => ({ ano: s.ano, ouro: s.Ouro, prata: s.Prata, bronze: s.Bronze })));
        if (d.medalhas?.ouro >= 10 && !sessionStorage.getItem("cf:" + id)) { sessionStorage.setItem("cf:" + id, 1); setTimeout(celebrate, 350); }
      });
    },
    async loadCidade(endereco) {
      this.loadingPerfil = true; this.cidade = null;
      const d = await API("cidade", { endereco });
      this.cidade = d; this.loadingPerfil = false;
      this.perfilCarregado(d);
      this.$nextTick(() => {
        if (d.serie) stackedYears(this.$refs.cityChart, "city", d.serie.map(s => ({ ano: s.ano, ouro: s.Ouro, prata: s.Prata, bronze: s.Bronze })));
      });
    },
    get alunoPorAno() {
      if (!this.aluno?.premiacoes) return [];
      const m = new Map();
      for (const r of this.aluno.premiacoes) { if (!m.has(r.ano)) m.set(r.ano, []); m.get(r.ano).push(r); }
      return [...m.entries()].map(([ano, itens]) => ({ ano, itens }));
    },
    // ------------------------------------------------ story do Instagram
    // A imagem é baixada assim que a janela abre: no celular, o navigator.share precisa ser chamado direto no
    // toque em "Compartilhar" (sem esperar download), senão o Safari recusa.
    async abrirStory() {
      const caminho = location.pathname;   // endereço oficial do perfil, ex. /aluno/maria-souza-lima-al
      const nome = caminho.split("/").pop();
      Object.assign(this.story, { aberto: true, src: `/og/story${caminho}.png`, link: location.origin + caminho,
        nomeArquivo: `medalhas-${nome}-story.png`, arquivo: null, carregando: true, erro: false, copiado: false,
        podeCompartilhar: false });
      try {
        const r = await fetch(this.story.src);
        if (!r.ok) throw new Error(r.status);
        const arquivo = new File([await r.blob()], this.story.nomeArquivo, { type: "image/png" });
        if (this.story.src !== `/og/story${caminho}.png`) return;   // a janela foi reaberta em outro perfil
        this.story.arquivo = arquivo;
        this.story.podeCompartilhar = !!navigator.canShare?.({ files: [arquivo] });
      } catch { /* a prévia mostra o erro pelo <img>; "Baixar" continua tentando pelo link */ }
    },
    async compartilharStory() {
      if (!this.story.arquivo) return;
      this.copiarLinkStory();
      try {
        // só o arquivo: com texto ou link junto, alguns apps (o Instagram entre eles) descartam a imagem
        await navigator.share({ files: [this.story.arquivo] });
      } catch (e) {
        if (e.name !== "AbortError") this.avisar("Não deu para compartilhar daqui. Use Baixar imagem.");
      }
    },
    async copiarLinkStory() {
      try {
        await navigator.clipboard.writeText(this.story.link);
        this.story.copiado = true;
        setTimeout(() => (this.story.copiado = false), 2500);
      } catch { /* sem permissão de copiar: o endereço está na tela */ }
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
