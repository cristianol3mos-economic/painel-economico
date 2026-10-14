/* Painel de indicadores econômicos do Brasil.
   Lê data/dados.json e data/analise.json (gerados por scripts/atualizar.py). */
"use strict";

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const MESES_LONGOS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

Plotly.register({
  moduleType: "locale", name: "pt-BR", dictionary: {},
  format: {
    days: ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"],
    shortDays: ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"],
    months: MESES_LONGOS, shortMonths: MESES,
    date: "%d/%m/%Y", decimal: ",", thousands: ".",
  },
});

let D = null;   // dados.json
let A = null;   // analise.json
const estado = { ini: null, fim: null, periodos: true };

/* ---------------------------------------------------------------- utilidades */

const $ = (s) => document.querySelector(s);
const el = (tag, attrs = {}, html = "") => { const e = document.createElement(tag); Object.assign(e, attrs); if (html) e.innerHTML = html; return e; };
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function fmt(x, casas = 2, sinal = false) {
  if (x === null || x === undefined || Number.isNaN(x)) return "n/d";
  const s = x.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
  return sinal && x > 0 ? "+" + s : s;
}
function rotMes(k) { const [a, m] = k.slice(0, 7).split("-"); return `${MESES[+m - 1]}/${a}`; }
function rotData(s) {
  if (!s) return "n/d";
  if (s.length === 7) return rotMes(s);
  const [a, m, d] = s.slice(0, 10).split("-"); return `${d}/${m}/${a}`;
}
function rotDataHora(iso) {
  if (!iso) return "n/d";
  return new Date(iso).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", dateStyle: "short", timeStyle: "short" }) + " (Brasília)";
}
function casasDe(id) { return id === "dolar" ? 4 : 2; }
function fmtValor(ind, v, id) {
  const u = ind.unidade, c = casasDe(id);
  if (u.startsWith("%")) return fmt(v, c) + u;
  if (u === "R$/US$") return "R$ " + fmt(v, c);
  return fmt(v, c);
}
function unVar(ind) { return ind.tipo_variacao === "pp" ? "p.p." : "%"; }
function cor(nome) { return getComputedStyle(document.documentElement).getPropertyValue(nome).trim(); }

function noPeriodo(serie) {
  const a = `${estado.ini}-01`, b = `${estado.fim}-12`;
  return serie.filter(([k]) => k >= a && k <= b);
}
function pearson(xs, ys) {
  const n = xs.length; if (n < 3) return null;
  const mx = xs.reduce((s, v) => s + v, 0) / n, my = ys.reduce((s, v) => s + v, 0) / n;
  let sxy = 0, sxx = 0, syy = 0;
  for (let i = 0; i < n; i++) { sxy += (xs[i] - mx) * (ys[i] - my); sxx += (xs[i] - mx) ** 2; syy += (ys[i] - my) ** 2; }
  return sxx && syy ? sxy / Math.sqrt(sxx * syy) : null;
}
function forca(r) { const a = Math.abs(r); return a >= 0.7 ? "forte" : a >= 0.4 ? "moderada" : a >= 0.2 ? "fraca" : "praticamente nula"; }
function codigoFonte(f) { return f.tipo === "sgs" ? `SGS ${f.codigo}` : `SIDRA tabela ${f.tabela}, variável ${f.variavel}`; }

function baixarCSV(nome, cabecalho, linhas) {
  const corpo = [cabecalho, ...linhas].map((l) => l.map((c) => (typeof c === "number" ? String(c).replace(".", ",") : c ?? "")).join(";")).join("\r\n");
  const blob = new Blob(["﻿" + corpo], { type: "text/csv;charset=utf-8" });
  const a = el("a", { href: URL.createObjectURL(blob), download: nome });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/* ---------------------------------------------------------------- Plotly: base */

const CONFIG_PLOTLY = { responsive: true, displaylogo: false, locale: "pt-BR", modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines"] };

function eixoX(extra = {}) {
  return Object.assign({ type: "date", showgrid: false, linecolor: cor("--eixo"), tickcolor: cor("--eixo"), ticks: "outside", hoverformat: "%b/%Y", tickfont: { color: cor("--mudo") } }, extra);
}
function eixoY(extra = {}) {
  return Object.assign({ gridcolor: cor("--grade"), zeroline: false, tickfont: { color: cor("--mudo") }, automargin: true }, extra);
}
function layoutBase(extra = {}) {
  return Object.assign({
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: 'system-ui, -apple-system, "Segoe UI", sans-serif', color: cor("--texto-2"), size: 12 },
    separators: ",.", margin: { l: 8, r: 12, t: 26, b: 30 },
    hovermode: "x unified",
    hoverlabel: { bgcolor: cor("--superficie"), bordercolor: cor("--borda"), font: { color: cor("--texto") } },
    showlegend: false, xaxis: eixoX(), yaxis: eixoY(),
  }, extra);
}

/** Faixas cinzas dos períodos marcantes que cruzam o intervalo [xmin, xmax]. */
function faixas(xmin, xmax, yref = "paper") {
  if (!estado.periodos || !D.periodos_marcantes) return { shapes: [], annotations: [] };
  const shapes = [], annotations = [];
  for (const p of D.periodos_marcantes.faixas) {
    const ini = p.inicio + "-01", fim = fimDoMes(p.fim);
    if (fim < xmin || ini > xmax) continue;
    shapes.push({ type: "rect", xref: "x", yref, x0: ini < xmin ? xmin : ini, x1: fim > xmax ? xmax : fim, y0: 0, y1: 1, fillcolor: cor("--faixa"), line: { width: 0 }, layer: "below" });
    annotations.push({ x: ini < xmin ? xmin : ini, y: 1, xref: "x", yref: "paper", xanchor: "left", yanchor: "bottom", text: p.curto, showarrow: false, font: { size: 10, color: cor("--mudo") }, hovertext: p.rotulo });
  }
  return { shapes, annotations };
}
function fimDoMes(k) { const [a, m] = k.split("-").map(Number); const d = new Date(Date.UTC(a, m, 0)); return d.toISOString().slice(0, 10); }
function limitesX(pontos) { return pontos.length ? [pontos[0][0] + "-01", fimDoMes(pontos[pontos.length - 1][0])] : [null, null]; }

/* ---------------------------------------------------------------- ícones de tendência */

const ICONES = {
  alta: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 14l5-5 3 3 5-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M13 6h4v4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  queda: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 6l5 5 3-3 5 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M13 14h4v-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  "estável": '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 10h14M13 6l4 4-4 4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};

/* ---------------------------------------------------------------- cabeçalho, alertas, filtros */

function montarCabecalho() {
  $("#atualizacao").textContent = `Última atualização do painel: ${rotDataHora(D.gerado_em)}.`;
  const caixa = $("#alertas"); caixa.innerHTML = "";
  if (D.erros && D.erros.length) {
    const itens = D.erros.map((e) => `<li><strong>${esc(D.indicadores[e.indicador]?.nome || e.indicador)}</strong> (${esc(e.fonte)}): ${esc(e.erro)}</li>`).join("");
    caixa.appendChild(el("div", { className: "alerta", role: "alert" },
      `<strong>Atenção:</strong> na última atualização algumas fontes falharam. Nenhum dado foi inventado: os gráficos abaixo mostram a última versão obtida com sucesso, com a data indicada.<ul>${itens}</ul>`));
  }
  $("#textoPanorama").textContent = A.panorama || "";
}

function montarFiltros() {
  const anos = new Set();
  for (const ind of Object.values(D.indicadores)) for (const [k] of ind.serie || []) anos.add(+k.slice(0, 4));
  const lista = [...anos].sort((a, b) => a - b);
  const min = lista[0], max = lista[lista.length - 1];
  for (const sel of [$("#anoIni"), $("#anoFim")]) {
    sel.innerHTML = lista.map((a) => `<option value="${a}">${a}</option>`).join("");
  }
  const salvo = lerPreferencia();
  estado.ini = salvo?.ini && salvo.ini >= min ? salvo.ini : Math.max(2003, min);
  estado.fim = salvo?.fim && salvo.fim <= max ? salvo.fim : max;
  $("#anoIni").value = estado.ini; $("#anoFim").value = estado.fim;

  const aplicar = () => {
    let i = +$("#anoIni").value, f = +$("#anoFim").value;
    if (i > f) [i, f] = [f, i];
    estado.ini = i; estado.fim = f; $("#anoIni").value = i; $("#anoFim").value = f;
    marcarAtalho(); salvarPreferencia(); renderizarTudo();
  };
  $("#anoIni").addEventListener("change", aplicar);
  $("#anoFim").addEventListener("change", aplicar);
  document.querySelectorAll("[data-atalho]").forEach((b) => b.addEventListener("click", () => {
    const t = b.dataset.atalho;
    $("#anoFim").value = max;
    $("#anoIni").value = t === "tudo" ? min : t === "2003" ? Math.max(2003, min) : Math.max(min, max - +t + 1);
    aplicar();
  }));
  $("#mostrarPeriodos").addEventListener("change", (e) => { estado.periodos = e.target.checked; renderizarTudo(); });
  function marcarAtalho() {
    document.querySelectorAll("[data-atalho]").forEach((b) => {
      const t = b.dataset.atalho;
      const ini = t === "tudo" ? min : t === "2003" ? Math.max(2003, min) : Math.max(min, max - +t + 1);
      b.setAttribute("aria-pressed", String(estado.fim === max && estado.ini === ini));
    });
  }
  marcarAtalho();
}
function lerPreferencia() { try { return JSON.parse(localStorage.getItem("painel-periodo")); } catch { return null; } }
function salvarPreferencia() { try { localStorage.setItem("painel-periodo", JSON.stringify({ ini: estado.ini, fim: estado.fim })); } catch { /* sem armazenamento */ } }

/* ---------------------------------------------------------------- cartões dos indicadores */

function rodapeFonte(ind) {
  const erro = ind.status === "erro"
    ? ` · <span class="estado-erro">A última tentativa de atualização falhou (${esc(ind.erro)}); os dados exibidos são os da data acima</span>`
    : "";
  return `Fonte: <a href="${esc(ind.fonte_url)}" target="_blank" rel="noopener">${esc(ind.fonte_nome)}</a> · Último dado: ${rotData(ind.ultima_observacao)} · Atualizado em: ${rotDataHora(ind.atualizado_em)}${erro}`;
}

function montarCartoes() {
  const lista = $("#listaIndicadores"); lista.innerHTML = "";
  for (const [id, ind] of Object.entries(D.indicadores)) {
    if (!ind.card) continue;
    const s = A.indicadores[id];
    const c = el("article", { className: "cartao", id: `ind-${id}` });
    if (!s) {
      c.innerHTML = `<p class="grupo-titulo">${esc(ind.grupo)}</p><h3>${esc(ind.nome)}</h3>
        <p class="estado-erro">Dados indisponíveis: ${esc(ind.erro || "a fonte não retornou dados")}.</p><div class="rodape-grafico">${rodapeFonte(ind)}</div>`;
      lista.appendChild(c); continue;
    }
    const u = unVar(ind);
    const difMedia = s.atual - s.media;
    const posMedia = s.desvio_padrao && Math.abs(difMedia) < 0.1 * s.desvio_padrao ? "em linha com a média" : difMedia > 0 ? "acima da média" : "abaixo da média";
    c.innerHTML = `
      <p class="grupo-titulo">${esc(ind.grupo)}</p>
      <h3>${esc(ind.nome)}</h3>
      <div class="cartao-grade">
        <div>
          <div class="kpis">
            <div class="kpi principal"><div class="rotulo">Valor atual</div><div class="valor">${fmtValor(ind, s.atual, id)}</div><div class="detalhe">${rotData(s.data_atual)}${ind.unidade.startsWith("índice") ? " · " + esc(ind.unidade) : ""}</div></div>
            <div class="kpi"><div class="rotulo">Variação em 12 meses</div><div class="valor">${s.var12 === null ? "n/d" : fmt(s.var12, 2, true) + " " + u}</div><div class="detalhe">${s.data_12m ? "vs. " + rotData(s.data_12m) : ""}</div></div>
            <div class="kpi"><div class="rotulo">Média histórica</div><div class="valor">${fmtValor(ind, s.media, id)}</div><div class="detalhe">${posMedia} · desde ${rotMes(s.inicio_media)}</div></div>
            <div class="kpi"><div class="rotulo">Tendência (6 meses)</div><div class="valor tendencia">${ICONES[s.tendencia]}${s.tendencia === "estável" ? "Estável" : s.tendencia === "alta" ? "Alta" : "Queda"}</div><div class="detalhe">${fmt(s.var6, 2, true)} ${u} em 6 meses</div></div>
          </div>
          <p class="texto">${esc(s.texto)}</p>
        </div>
        <div>
          <div class="grafico" id="g-${id}" role="img" aria-label="Gráfico de ${esc(ind.nome)}"></div>
          <div class="rodape-grafico">${rodapeFonte(ind)}</div>
          <div class="acoes">
            <button type="button" class="botao" data-csv="${id}">Baixar CSV (período selecionado)</button>
          </div>
          <details><summary>Ver dados em tabela</summary><div class="tabela-rolagem" id="t-${id}"></div></details>
        </div>
      </div>`;
    lista.appendChild(c);
  }
  lista.querySelectorAll("[data-csv]").forEach((b) => b.addEventListener("click", () => {
    const id = b.dataset.csv, ind = D.indicadores[id];
    baixarCSV(`${id}_${estado.ini}-${estado.fim}.csv`, ["mes", `${ind.nome_curto} (${ind.unidade})`], noPeriodo(ind.serie));
  }));
}

function graficoIndicador(id) {
  const ind = D.indicadores[id], s = A.indicadores[id], div = $(`#g-${id}`);
  if (!div || !s) return;
  const pts = noPeriodo(ind.serie);
  const [x0, x1] = limitesX(pts);
  const traces = [{
    x: pts.map((p) => p[0] + "-01"), y: pts.map((p) => p[1]), type: "scatter", mode: "lines", name: ind.nome_curto,
    line: { color: cor("--serie-1"), width: 2 }, hovertemplate: `%{y:,.${casasDe(id)}f} ${esc(ind.unidade)}<extra></extra>`,
  }];
  const inicioMedia = (s.inicio_media + "-01") > x0 ? s.inicio_media + "-01" : x0;
  const anot = [];
  if (pts.length && inicioMedia <= x1) {
    traces.push({ x: [inicioMedia, x1], y: [s.media, s.media], type: "scatter", mode: "lines", name: "Média histórica",
      line: { color: cor("--mudo"), width: 1 }, hoverinfo: "skip" });
    anot.push({ x: x1, y: s.media, xanchor: "right", yanchor: "bottom", text: `média ${fmt(s.media, casasDe(id))}`, showarrow: false, font: { size: 10, color: cor("--mudo") } });
  }
  const f = faixas(x0, x1);
  Plotly.react(div, traces, layoutBase({ shapes: f.shapes, annotations: [...f.annotations, ...anot], xaxis: eixoX({ range: [x0, x1] }) }), CONFIG_PLOTLY);

  const t = $(`#t-${id}`);
  if (t) {
    const linhas = [...pts].reverse().map(([k, v]) => `<tr><td>${rotMes(k)}</td><td class="num">${fmt(v, casasDe(id))}</td></tr>`).join("");
    t.innerHTML = `<table><thead><tr><th>Mês</th><th>${esc(ind.unidade)}</th></tr></thead><tbody>${linhas}</tbody></table>`;
  }
}

/* ---------------------------------------------------------------- comparação */

const MODOS_NOTA = {
  original: "Valores originais no mesmo eixo: disponível só quando as duas séries estão na mesma unidade (percentuais).",
  base100: "Base 100: cada série é dividida pelo seu primeiro valor no período e multiplicada por 100. Mostra a variação relativa desde o início do período.",
  z: "Padronizado: cada série é expressa em desvios-padrão em relação à sua própria média no período (0 = média). Permite comparar o formato das séries sem usar dois eixos, que distorcem a leitura.",
};

function montarComparar() {
  const ids = Object.keys(D.indicadores).filter((i) => (D.indicadores[i].serie || []).length);
  const opcoes = ids.map((i) => `<option value="${i}">${esc(D.indicadores[i].nome_curto)} (${esc(D.indicadores[i].unidade)})</option>`).join("");
  $("#compA").innerHTML = opcoes; $("#compB").innerHTML = opcoes;
  $("#compA").value = ids.includes("selic") ? "selic" : ids[0];
  $("#compB").value = ids.includes("ipca12") ? "ipca12" : ids[1] || ids[0];
  const ajustarModo = () => {
    const a = D.indicadores[$("#compA").value], b = D.indicadores[$("#compB").value];
    const mesmaUnidade = a.unidade.startsWith("%") && b.unidade.startsWith("%");
    const radio = document.querySelector('input[name="modo"][value="original"]');
    radio.disabled = !mesmaUnidade;
    if (!mesmaUnidade && radio.checked) document.querySelector('input[name="modo"][value="z"]').checked = true;
  };
  $("#compA").addEventListener("change", () => { ajustarModo(); graficoComparar(); });
  $("#compB").addEventListener("change", () => { ajustarModo(); graficoComparar(); });
  document.querySelectorAll('input[name="modo"]').forEach((r) => r.addEventListener("change", graficoComparar));
  ajustarModo();
  if (!document.querySelector('input[name="modo"][value="original"]').disabled) document.querySelector('input[name="modo"][value="original"]').checked = true;
  $("#csvComparar").addEventListener("click", () => {
    const [ia, ib] = [$("#compA").value, $("#compB").value];
    const a = Object.fromEntries(noPeriodo(D.indicadores[ia].serie)), b = Object.fromEntries(noPeriodo(D.indicadores[ib].serie));
    const meses = [...new Set([...Object.keys(a), ...Object.keys(b)])].sort();
    baixarCSV(`comparacao_${ia}_${ib}_${estado.ini}-${estado.fim}.csv`,
      ["mes", `${D.indicadores[ia].nome_curto} (${D.indicadores[ia].unidade})`, `${D.indicadores[ib].nome_curto} (${D.indicadores[ib].unidade})`],
      meses.map((m) => [m, a[m], b[m]]));
  });
}

function transformarModo(pts, modo) {
  if (modo === "base100") { const b = pts[0]?.[1]; return pts.map(([k, v]) => [k, b ? (v / b) * 100 : null]); }
  if (modo === "z") {
    const vs = pts.map((p) => p[1]); const m = vs.reduce((s, v) => s + v, 0) / vs.length;
    const sd = Math.sqrt(vs.reduce((s, v) => s + (v - m) ** 2, 0) / vs.length);
    return pts.map(([k, v]) => [k, sd ? (v - m) / sd : 0]);
  }
  return pts;
}

function graficoComparar() {
  const ia = $("#compA").value, ib = $("#compB").value;
  const a = D.indicadores[ia], b = D.indicadores[ib];
  const modo = document.querySelector('input[name="modo"]:checked').value;
  $("#notaModo").textContent = MODOS_NOTA[modo];
  const pa = noPeriodo(a.serie), pb = noPeriodo(b.serie);
  const ta = transformarModo(pa, modo), tb = transformarModo(pb, modo);
  const sufixo = modo === "z" ? " desvios-padrão" : modo === "base100" ? "" : "";
  const traces = [
    { x: ta.map((p) => p[0] + "-01"), y: ta.map((p) => p[1]), customdata: pa.map((p) => p[1]), type: "scatter", mode: "lines", name: a.nome_curto,
      line: { color: cor("--serie-1"), width: 2 }, hovertemplate: `${esc(a.nome_curto)}: %{customdata:,.${casasDe(ia)}f} ${esc(a.unidade)}<extra></extra>` },
    { x: tb.map((p) => p[0] + "-01"), y: tb.map((p) => p[1]), customdata: pb.map((p) => p[1]), type: "scatter", mode: "lines", name: b.nome_curto,
      line: { color: cor("--serie-2"), width: 2 }, hovertemplate: `${esc(b.nome_curto)}: %{customdata:,.${casasDe(ib)}f} ${esc(b.unidade)}<extra></extra>` },
  ];
  const todos = [...pa, ...pb].map((p) => p[0]).sort();
  const x0 = todos.length ? todos[0] + "-01" : null, x1 = todos.length ? fimDoMes(todos[todos.length - 1]) : null;
  const f = faixas(x0, x1);
  const tituloY = modo === "z" ? "desvios-padrão da média" : modo === "base100" ? "índice (início do período = 100)" : "%";
  Plotly.react($("#graficoComparar"), traces, layoutBase({
    showlegend: true, legend: { orientation: "h", y: 1.12, x: 0, font: { color: cor("--texto") } },
    margin: { l: 8, r: 12, t: 40, b: 30 },
    shapes: f.shapes, annotations: f.annotations, xaxis: eixoX({ range: [x0, x1] }), yaxis: eixoY({ title: { text: tituloY + sufixo.replace(" desvios-padrão", ""), font: { size: 11 } } }),
  }), CONFIG_PLOTLY);

  // Correlação no período selecionado (calculada aqui, a partir dos dados)
  const mb = Object.fromEntries(pb);
  const comuns = pa.filter(([k]) => k in mb);
  const r = pearson(comuns.map((p) => p[1]), comuns.map((p) => mb[p[0]]));
  let txt;
  if (ia === ib) txt = "Escolha dois indicadores diferentes para ver a correlação.";
  else if (r === null || comuns.length < 12) txt = `As duas séries têm apenas ${comuns.length} meses em comum no período selecionado, insuficiente para uma correlação confiável.`;
  else txt = `No período selecionado (${rotMes(comuns[0][0])} a ${rotMes(comuns[comuns.length - 1][0])}, ${comuns.length} meses em comum), a correlação entre ${a.nome_curto} e ${b.nome_curto} é ${fmt(r)}: ${forca(r)}, ${Math.abs(r) < 0.2 ? "sem relação linear relevante entre as séries" : r > 0 ? "as séries tendem a se mover na mesma direção" : "as séries tendem a se mover em direções opostas"}. Correlação não implica causalidade, e séries com tendência longa podem parecer correlacionadas só por isso.`;
  $("#textoComparar").textContent = txt;
  $("#rodapeComparar").innerHTML = `<div>A: ${rodapeFonte(a)}</div><div>B: ${rodapeFonte(b)}</div>`;
}

/* ---------------------------------------------------------------- conjuntura */

function montarRelacoes() {
  const lista = $("#listaRelacoes"); lista.innerHTML = "";
  for (const r of A.relacoes) {
    const md = r.melhor_defasagem;
    const defTxt = !md ? "n/d" : md.k === 0 ? "mesmo mês" : md.k > 0 ? `A antecede B em ${md.k} meses` : `B antecede A em ${-md.k} meses`;
    const c = el("article", { className: "cartao", id: `rel-${r.id}` });
    c.innerHTML = `
      <h3>${esc(r.titulo)}</h3>
      <p class="pergunta">${esc(r.pergunta)}</p>
      <div class="numeros">
        <div><div class="nota">Correlação (histórico em comum)</div><div class="valor">${fmt(r.r_total)}</div></div>
        <div><div class="nota">Últimos 36 meses</div><div class="valor">${fmt(r.r_recente)}</div></div>
        <div><div class="nota">Associação mais forte</div><div class="valor">${defTxt}${md ? ` (${fmt(md.r)})` : ""}</div></div>
      </div>
      <p class="texto">${esc(r.texto)}</p>
      <div class="relacao-grade">
        <div><div class="grafico alto" id="gr-${r.id}" role="img" aria-label="${esc(r.titulo)} ao longo do tempo"></div></div>
        <div><div class="grafico" id="gd-${r.id}" role="img" aria-label="Correlação por defasagem"></div>
          <p class="nota">Correlação entre A (${esc(r.a_rotulo)}) no mês t e B (${esc(r.b_rotulo)}) no mês t+k. Valores de k positivos indicam que A vem antes.</p></div>
      </div>
      <div class="rodape-grafico"><div>A: ${rodapeFonte(D.indicadores[r.a])}</div><div>B: ${rodapeFonte(D.indicadores[r.b])}</div><div>Análise recalculada em ${rotDataHora(A.gerado_em)}.</div></div>`;
    lista.appendChild(c);
    if (r.id === "juros_inflacao" && A.juro_real && A.juro_real.length) lista.appendChild(blocoJuroReal());
  }
}

function graficoRelacao(r) {
  const pa = noPeriodo(r.serie_a), pb = noPeriodo(r.serie_b), pc = noPeriodo(r.corr_movel);
  const [x0, x1] = limitesX(pa.length ? pa : pb);
  const f = faixas(x0, x1);
  const linha = (pts, eixo, corVar, nome, casas) => ({ x: pts.map((p) => p[0] + "-01"), y: pts.map((p) => p[1]), xaxis: "x", yaxis: eixo, type: "scatter", mode: "lines",
    name: nome, line: { color: cor(corVar), width: 2 }, hovertemplate: `${esc(nome)}: %{y:,.${casas}f}<extra></extra>` });
  const titulo = (txt, y) => ({ text: txt, x: 0, xref: "paper", y, yref: "paper", xanchor: "left", yanchor: "bottom", showarrow: false, font: { size: 11, color: cor("--texto-2") } });
  const layout = layoutBase({
    margin: { l: 8, r: 12, t: 26, b: 30 },
    xaxis: eixoX({ range: [x0, x1], anchor: "y3" }),
    yaxis: eixoY({ domain: [0.68, 0.95] }),
    yaxis2: eixoY({ domain: [0.36, 0.63] }),
    yaxis3: eixoY({ domain: [0, 0.25], range: [-1.05, 1.05], zeroline: true, zerolinecolor: cor("--eixo") }),
    shapes: f.shapes,
    annotations: [...f.annotations, titulo("A: " + r.a_rotulo, 0.95), titulo("B: " + r.b_rotulo, 0.63), titulo("Correlação móvel de 36 meses", 0.25)],
  });
  Plotly.react($(`#gr-${r.id}`), [
    linha(pa, "y", "--serie-1", D.indicadores[r.a].nome_curto, 2),
    linha(pb, "y2", "--serie-2", D.indicadores[r.b].nome_curto, 2),
    linha(pc, "y3", "--serie-3", "Correlação 36m", 2),
  ], layout, CONFIG_PLOTLY);

  const defs = r.defasagens || [];
  const md = r.melhor_defasagem;
  Plotly.react($(`#gd-${r.id}`), [{
    x: defs.map((d) => d.k), y: defs.map((d) => d.r), type: "bar", marker: { color: cor("--serie-1") },
    hovertemplate: "k = %{x} meses<br>correlação %{y:,.2f}<extra></extra>",
  }], layoutBase({
    hovermode: "closest", bargap: 0.25,
    xaxis: { title: { text: "defasagem k (meses)", font: { size: 11 } }, zeroline: false, linecolor: cor("--eixo"), tickfont: { color: cor("--mudo") } },
    yaxis: eixoY({ range: [-1.05, 1.05], zeroline: true, zerolinecolor: cor("--eixo") }),
    margin: { l: 8, r: 12, t: 26, b: 44 },
    annotations: md ? [{ x: md.k, y: md.r, text: `${fmt(md.r)} (k=${md.k})`, showarrow: true, arrowhead: 0, ax: 0, ay: md.r > 0 ? -22 : 22, font: { size: 11, color: cor("--texto") } }] : [],
  }), CONFIG_PLOTLY);
}

function blocoJuroReal() {
  const jr = A.juro_real;
  const vs = jr.map((p) => p[1]);
  const media = vs.reduce((s, v) => s + v, 0) / vs.length;
  const [k, v] = jr[jr.length - 1];
  const acima = vs.filter((x) => x < v).length / vs.length * 100;
  const c = el("article", { className: "cartao", id: "juro-real" });
  c.innerHTML = `
    <h3>Juro real ex-post</h3>
    <p class="pergunta">Quanto rendem os juros básicos depois de descontada a inflação?</p>
    <p class="texto">Calculado como (1 + Selic meta) ÷ (1 + IPCA de 12 meses) − 1, no fim de cada mês. Em ${rotMes(k)}, o juro real ex-post era de ${fmt(v)}% a.a., ${v > media ? "acima" : "abaixo"} da média de ${fmt(media)}% desde ${rotMes(jr[0][0])}, e maior que ${fmt(acima, 0)}% dos meses desde então. Juro real alto indica política monetária restritiva; juro real baixo ou negativo, política estimulativa.</p>
    <div class="grafico" id="g-juro-real" role="img" aria-label="Juro real ex-post ao longo do tempo"></div>
    <div class="rodape-grafico"><div>${rodapeFonte(D.indicadores.selic)}</div><div>${rodapeFonte(D.indicadores.ipca12)}</div></div>`;
  return c;
}
function graficoJuroReal() {
  if (!$("#g-juro-real")) return;
  const pts = noPeriodo(A.juro_real);
  const [x0, x1] = limitesX(pts);
  const vs = A.juro_real.map((p) => p[1]); const media = vs.reduce((s, v) => s + v, 0) / vs.length;
  const f = faixas(x0, x1);
  Plotly.react($("#g-juro-real"), [
    { x: pts.map((p) => p[0] + "-01"), y: pts.map((p) => p[1]), type: "scatter", mode: "lines", line: { color: cor("--serie-1"), width: 2 }, hovertemplate: "%{y:,.2f}% a.a.<extra></extra>" },
    { x: [x0, x1], y: [media, media], type: "scatter", mode: "lines", line: { color: cor("--mudo"), width: 1 }, hoverinfo: "skip" },
  ], layoutBase({ shapes: f.shapes, annotations: [...f.annotations, { x: x1, y: media, xanchor: "right", yanchor: "bottom", text: `média ${fmt(media)}`, showarrow: false, font: { size: 10, color: cor("--mudo") } }],
    xaxis: eixoX({ range: [x0, x1] }), yaxis: eixoY({ zeroline: true, zerolinecolor: cor("--eixo") }) }), CONFIG_PLOTLY);
}

/* ---------------------------------------------------------------- dados e metodologia */

function montarDados() {
  const corpo = $("#tabelaFontes tbody"); corpo.innerHTML = "";
  for (const [id, ind] of Object.entries(D.indicadores)) {
    const serie = ind.serie || [];
    corpo.appendChild(el("tr", {}, `
      <td>${esc(ind.nome)}</td>
      <td>${esc(ind.nome_oficial)}<br><span class="nota">${esc(codigoFonte(ind.fonte))}</span></td>
      <td><a href="${esc(ind.fonte_url)}" target="_blank" rel="noopener">${esc(ind.fonte_nome)}</a></td>
      <td>${serie.length ? rotMes(serie[0][0]) : "n/d"}</td>
      <td>${rotData(ind.ultima_observacao)}</td>
      <td>${ind.status === "ok" ? "Atualizado em " + rotDataHora(ind.atualizado_em) : `<span class="estado-erro">Falha: ${esc(ind.erro)}</span>`}</td>`));
  }
  const notas = [];
  for (const ind of Object.values(D.indicadores)) for (const n of ind.notas || []) notas.push(`<strong>${esc(ind.nome_curto)}:</strong> ${esc(n)}`);
  notas.push("<strong>Uso da capacidade instalada:</strong> o IBGE/SIDRA não publica essa série. Usamos a sondagem da FGV/IBRE republicada pelo Banco Central (SGS 28561, dessazonalizada, e 24352, original). A série da CNI no SGS (código 1341) foi descontinuada em 2006, e os dados atuais da CNI não têm API pública estável, por isso não são usados.");
  notas.push("<strong>Desemprego:</strong> a PNAD Contínua é divulgada em trimestres móveis; no painel, cada valor é datado pelo último mês do trimestre (ex.: “jun–ago” aparece como agosto).");
  notas.push("<strong>Selic:</strong> meta definida pelo Copom no último dia de cada mês. <strong>Dólar:</strong> média mensal das cotações diárias de venda; o valor atual é a última cotação diária.");
  notas.push("<strong>Variação em 12 meses:</strong> em pontos percentuais (p.p.) para taxas e percentuais; em % para o dólar e a produção industrial.");
  notas.push("<strong>Tendência:</strong> a variação dos últimos 6 meses é comparada com a variação típica de 6 meses da própria série nos últimos 10 anos (desvio-padrão das variações mensais × √6). Acima de +0,5 desvio-padrão é “alta”, abaixo de −0,5 é “queda”, e entre os dois é “estável”. Para dólar e produção industrial, a comparação usa variações percentuais.");
  notas.push("<strong>Correlações:</strong> coeficiente de Pearson. Abaixo de 0,2 em módulo é tratada como praticamente nula, de 0,2 a 0,4 como fraca, de 0,4 a 0,7 como moderada e a partir de 0,7 como forte. Uma defasagem só é citada quando sua correlação passa de 0,2 em módulo.");
  const per = D.periodos_marcantes;
  notas.push(`<strong>Períodos marcantes:</strong> ${esc(per._fonte)} ${per.faixas.map((p) => `${esc(p.rotulo)}: ${rotMes(p.inicio)} a ${rotMes(p.fim)}`).join("; ")}.`);
  $("#notasMetodo").innerHTML = notas.map((n) => `<li>${n}</li>`).join("");

  $("#csvTudo").onclick = () => {
    const ids = Object.keys(D.indicadores).filter((i) => (D.indicadores[i].serie || []).length);
    const mapas = ids.map((i) => Object.fromEntries(noPeriodo(D.indicadores[i].serie)));
    const meses = [...new Set(mapas.flatMap((m) => Object.keys(m)))].sort();
    baixarCSV(`indicadores_brasil_${estado.ini}-${estado.fim}.csv`,
      ["mes", ...ids.map((i) => `${D.indicadores[i].nome_curto} (${D.indicadores[i].unidade})`)],
      meses.map((m) => [m, ...mapas.map((mp) => mp[m])]));
  };
}

/* ---------------------------------------------------------------- render */

function renderizarTudo() {
  for (const id of Object.keys(D.indicadores)) if (D.indicadores[id].card) graficoIndicador(id);
  graficoComparar();
  for (const r of A.relacoes) graficoRelacao(r);
  graficoJuroReal();
}

async function iniciar() {
  try {
    const v = Date.now();
    [D, A] = await Promise.all([
      fetch(`data/dados.json?v=${v}`).then((r) => { if (!r.ok) throw new Error(`dados.json: HTTP ${r.status}`); return r.json(); }),
      fetch(`data/analise.json?v=${v}`).then((r) => { if (!r.ok) throw new Error(`analise.json: HTTP ${r.status}`); return r.json(); }),
    ]);
  } catch (e) {
    $("#atualizacao").innerHTML = `<span class="estado-erro">Não foi possível carregar os dados (${esc(e.message)}).</span>`;
    return;
  }
  montarCabecalho();
  montarFiltros();
  montarCartoes();
  montarComparar();
  montarRelacoes();
  montarDados();
  renderizarTudo();
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", renderizarTudo);
}

iniciar();
