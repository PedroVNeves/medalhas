// Configuração do Tailwind para gerar web/css/site.css (npm run css). Era a mesma que ficava no
// index.html quando o CSS vinha do CDN do Tailwind, que monta as classes no navegador (lento).
//
// Tema claro e escuro: as cores que o site usa (slate, white, ink) apontam para as variáveis de
// web/styles.css, que trazem os dois valores com light-dark(). Assim as mesmas classes servem aos dois
// temas, sem reescrever o HTML. A opacidade das classes (bg-white/5) vira color-mix() com transparente.
const tema = nome => `color-mix(in srgb, var(${nome}) calc(<alpha-value> * 100%), transparent)`;
// cor de texto que muda com o tema: [no claro, no escuro]. As cores claras das classes text-*-300 não
// têm contraste sobre o papel, então no tema claro o texto usa um tom escuro da mesma família.
const texto = (claro, escuro) => `light-dark(${claro}, ${escuro})`;

/** @type {import('tailwindcss').Config} */
module.exports = {
  // o Tailwind procura as classes nestes arquivos; classe montada em pedaços ("h-" + n) não é achada
  content: ["web/**/*.html", "web/js/**/*.js"],
  theme: { extend: {
    fontFamily: { sans: ["Public Sans", "system-ui", "sans-serif"], display: ["Newsreader", "Georgia", "serif"] },
    colors: {
      ink: { 900: tema("--bg"), 800: tema("--surface"), 700: tema("--surface"), 600: tema("--surface-2") },
      gold: { 300: "#ffe08a", 400: "#f5c542", 600: "#b8860b" },
      // véus e fios (bg-white/5, divide-white/5): branco no escuro, tinta no claro
      white: tema("--tinta"),
      // texto: principal, secundário e fraco (slate-500 e 600 passam a ter contraste AA)
      slate: { 100: tema("--text"), 200: tema("--text"), 300: tema("--text-1"), 400: tema("--text-2"),
               500: tema("--muted"), 600: tema("--muted"), 700: tema("--line-2"), 800: tema("--line") },
    },
    textColor: {
      white: tema("--text"),
      gold: { 300: texto("#7A5B00", "#ffe08a"), 400: texto("#7A5B00", "#f5c542") },
      emerald: { 200: texto("#0B6B47", "#a7f3d0"), 300: texto("#0B6B47", "#6ee7b7") },
      indigo: { 200: texto("#3B3FB0", "#c7d2fe"), 300: texto("#3B3FB0", "#a5b4fc") },
      sky: { 200: texto("#075985", "#bae6fd"), 300: texto("#075985", "#7dd3fc") },
      rose: { 300: texto("#B4123C", "#fda4af") },
      pink: { 100: texto("#A3195B", "#fce7f3"), 300: texto("#A3195B", "#f9a8d4") },
      orange: { 400: texto("#9A3412", "#fb923c") },
      amber: { 300: texto("#8A4B0B", "#fcd34d") },
    },
  } },
};
