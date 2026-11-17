/* Utilidades compartilhadas: chamada à API do site, formatação de números e nomes, ícones. */

// método de pontuação escolhido no topo (impa | impa3 | site); vai em toda chamada à API
let METODO = localStorage.getItem("metodo") || "";
// Nunca lança erro: falha do servidor (429, 503, 500…) ou de rede vira { erro: "mensagem" }, que a tela mostra.
const API = async (path, params = {}) => {
  const all = { ...params, metodo: METODO };
  const qs = new URLSearchParams(Object.entries(all).filter(([, v]) => v !== "" && v != null));
  try {
    const r = await fetch(`/api/${path}?${qs}`);
    const d = await r.json().catch(() => ({}));
    if (!r.ok && !d.erro) d.erro = r.status === 503 ? "Servidor ocupado. Tente de novo em alguns segundos."
      : `O servidor respondeu com erro ${r.status}. Tente de novo.`;
    return d;
  } catch {
    return { erro: "Falha de conexão. Confira a internet e tente de novo." };
  }
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

// Endereço legível de uma página: "MARIA SOUZA LIMA|AL" -> "maria-souza-lima-al".
// Cópia de slug() em medalhas/dominio/enderecos.py: as duas precisam dar o mesmo resultado.
const slug = t => (t || "").normalize("NFKD").replace(/\p{Mn}/gu, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");

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

