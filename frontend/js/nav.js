// Desenha a barra lateral (igual em toda página protegida) e monta o
// layout ".app" com a área de conteúdo. Chame renderNav("animais") no
// topo da página, passando o identificador do link que deve ficar ativo.

// Ícones em SVG, desenhados na mão (sem depender de nenhuma biblioteca
// de ícones nem de internet). Todos seguem o mesmo estilo: contorno,
// 24x24, cor herdada do texto (currentColor).
const ICONES = {
  logo: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <ellipse cx="12" cy="15.3" rx="4.3" ry="3.4"/>
    <circle cx="6.9" cy="9.3" r="1.8"/><circle cx="11" cy="6.6" r="1.8"/>
    <circle cx="15.3" cy="6.8" r="1.8"/><circle cx="18.8" cy="10" r="1.8"/>
  </svg>`,
  inicio: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <path d="M4 11.2 12 4l8 7.2"/><path d="M6 9.8V20h12V9.8"/><path d="M9.8 20v-5.3h4.4V20"/>
  </svg>`,
  tutores: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="8.2" r="3.4"/><path d="M5 20c0-3.9 3.1-6.6 7-6.6s7 2.7 7 6.6"/>
  </svg>`,
  animais: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <ellipse cx="12" cy="15.5" rx="4.2" ry="3.3"/>
    <circle cx="7.1" cy="9.3" r="1.6"/><circle cx="11" cy="6.8" r="1.6"/>
    <circle cx="15" cy="6.8" r="1.6"/><circle cx="18.3" cy="9.6" r="1.6"/>
  </svg>`,
  cadastros: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <path d="M11.5 3H19a1 1 0 0 1 1 1v7.5a1 1 0 0 1-.3.7l-8 8a1 1 0 0 1-1.4 0l-6.2-6.2a1 1 0 0 1 0-1.4l8-8a1 1 0 0 1 .4-.3z"/>
    <circle cx="16" cy="8" r="1.3" fill="currentColor" stroke="none"/>
  </svg>`,
  integracoes: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 3.3 18.5 6v5.3c0 4.4-2.8 7.8-6.5 9.4-3.7-1.6-6.5-5-6.5-9.4V6L12 3.3z"/>
    <path d="M9.2 12.1l1.9 1.9 3.7-3.7"/>
  </svg>`,
  sair: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <path d="M9 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h3"/><path d="M14.5 8 18.5 12l-4 4"/><path d="M18.5 12H9.5"/>
  </svg>`,
};

const LINKS_NAV = [
  { id: "inicio", rotulo: "Início", href: "index.html", icone: "inicio" },
  { id: "tutores", rotulo: "Tutores", href: "tutores.html", icone: "tutores" },
  { id: "animais", rotulo: "Animais", href: "animais.html", icone: "animais" },
  { id: "cadastros", rotulo: "Espécies e raças", href: "cadastros.html", icone: "cadastros" },
  { id: "integracoes", rotulo: "Integração governo", href: "integracoes.html", icone: "integracoes" },
];

function iniciais(nome) {
  const partes = (nome || "").trim().split(/\s+/);
  const primeira = partes[0]?.[0] || "";
  const ultima = partes.length > 1 ? partes[partes.length - 1][0] : "";
  return (primeira + ultima).toUpperCase() || "V";
}

function renderNav(ativo) {
  exigirLogin();
  const veterinario = getVeterinarioLogado();

  document.body.innerHTML = `
    <div class="app">
      <aside class="barra-lateral">
        <div class="marca"><span class="logo-marca">${ICONES.logo}</span> Clínica Vet</div>
        <nav>
          ${LINKS_NAV.map(
            (l) => `<a href="${l.href}" class="${l.id === ativo ? "ativo" : ""}">${ICONES[l.icone]}<span>${l.rotulo}</span></a>`
          ).join("")}
        </nav>
        <div class="rodape-usuario">
          <div class="avatar">${iniciais(veterinario?.nome_completo)}</div>
          <div class="info"><span class="nome">${escaparHtml(veterinario ? veterinario.nome_completo : "")}</span></div>
          <button id="botao-sair" type="button" title="Sair">${ICONES.sair}</button>
        </div>
      </aside>
      <main class="conteudo" id="conteudo"></main>
    </div>
  `;

  document.getElementById("botao-sair").addEventListener("click", logout);
  return document.getElementById("conteudo");
}

function escaparHtml(texto) {
  const div = document.createElement("div");
  div.textContent = texto ?? "";
  return div.innerHTML;
}

// A API manda as datas "cruas" (ex.: "2026-11-24" ou "2026-11-24 14:30:00"),
// sem indicar fuso horário nenhum (ver api-clinica/app/json_provider.py).
// Por isso NÃO usamos `new Date(texto)` direto: o construtor do JavaScript
// tenta adivinhar o fuso e cada navegador adivinha diferente, deslocando a
// hora (e às vezes até o dia). Em vez disso, lemos os números na mão e
// montamos a data já no fuso local, sem nenhuma conversão.
function _partesDaData(valor) {
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/.exec(valor || "");
  if (!m) return null;
  const [, ano, mes, dia, hora, minuto] = m;
  return new Date(Number(ano), Number(mes) - 1, Number(dia), Number(hora || 0), Number(minuto || 0));
}

function formatarData(valor) {
  if (!valor) return "—";
  const d = _partesDaData(valor);
  if (!d) return valor;
  return d.toLocaleDateString("pt-BR");
}

function formatarDataHora(valor) {
  if (!valor) return "—";
  const d = _partesDaData(valor);
  if (!d) return valor;
  return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function mostrarAviso(container, mensagem, tipo = "erro") {
  container.innerHTML = `<div class="aviso aviso-${tipo}">${escaparHtml(mensagem)}</div>`;
}
