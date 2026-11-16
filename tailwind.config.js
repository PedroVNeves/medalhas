// Configuração do Tailwind para gerar web/css/site.css (npm run css). Era a mesma que ficava no
// index.html quando o CSS vinha do CDN do Tailwind, que monta as classes no navegador (lento).
/** @type {import('tailwindcss').Config} */
module.exports = {
  // o Tailwind procura as classes nestes arquivos; classe montada em pedaços ("h-" + n) não é achada
  content: ["web/**/*.html", "web/js/**/*.js"],
  theme: { extend: {
    fontFamily: { sans: ["Inter", "system-ui", "sans-serif"], display: ["Space Grotesk", "Inter", "sans-serif"] },
    colors: { ink: { 900: "#070a14", 800: "#0b0f1c", 700: "#0f1424", 600: "#151b2f" }, gold: { 300: "#ffe08a", 400: "#f5c542", 600: "#b8860b" } },
  } },
};
