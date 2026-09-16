/*
 * Visor de seguimiento Neumo23 2026 - Ñuble
 * Este archivo SOLO lee tablas agregadas ya suprimidas (carpeta /data). No contiene
 * ni recibe en ningún momento RUN, nombres, direcciones ni ninguna base nominal.
 */

const ETIQUETAS_CATEGORIA = {
  encontrado_valido: "Registro válido encontrado",
  sin_registro: "Sin registro válido encontrado",
  requiere_revision: "Requiere revisión",
  no_cumple_criterio: "Registro válido, no cumple año/territorio",
  sin_run: "RUN no disponible",
};

const COLOR_CATEGORIA = {
  encontrado_valido: "col-encontrado",
  sin_registro: "col-sin-registro",
  requiere_revision: "col-revision",
  no_cumple_criterio: "col-no-cumple",
  sin_run: "col-sin-run",
};

function fmt(n) {
  if (n === null || n === undefined) return "s/d";
  if (typeof n === "string") return n; // ej. "<10"
  return n.toLocaleString("es-CL");
}

function pctStr(p) {
  if (p === null || p === undefined) return "s/d";
  return p.toLocaleString("es-CL", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + "%";
}

async function cargarJSON(ruta) {
  const resp = await fetch(ruta);
  if (!resp.ok) throw new Error("No se pudo cargar " + ruta);
  return resp.json();
}

/* ---------------- Navegación por pestañas ---------------- */
function initTabs() {
  const botones = document.querySelectorAll("nav.tabs button");
  const paneles = document.querySelectorAll("section.panel");
  botones.forEach((btn) => {
    btn.addEventListener("click", () => {
      botones.forEach((b) => b.classList.remove("activo"));
      paneles.forEach((p) => p.classList.remove("activo"));
      btn.classList.add("activo");
      document.getElementById(btn.dataset.panel).classList.add("activo");
    });
  });
}

/* ---------------- 1. RESUMEN ---------------- */
function pintarResumen(resumen) {
  const cat = resumen.categorias;
  document.getElementById("kpi-universo").textContent = fmt(resumen.universo_nominal);
  document.getElementById("kpi-encontrado").textContent = fmt(cat.encontrado_valido);
  document.getElementById("kpi-encontrado-pct").textContent = pctStr(resumen.pct_avance_sobre_nomina);
  document.getElementById("kpi-sin-registro").textContent = fmt(cat.sin_registro);
  document.getElementById("kpi-sin-registro-pct").textContent = pctStr(round1(100 * cat.sin_registro / resumen.universo_nominal));

  document.getElementById("mini-revision").textContent = fmt(cat.requiere_revision);
  document.getElementById("mini-no-cumple").textContent = fmt(cat.no_cumple_criterio);
  document.getElementById("mini-sin-run").textContent = fmt(cat.sin_run);
  document.getElementById("mini-suma").textContent = fmt(resumen.suma_verificacion);

  document.getElementById("fecha-datos").textContent = resumen.fecha_generacion_datos;

  // barra apilada
  const total = resumen.universo_nominal;
  const orden = ["encontrado_valido", "sin_registro", "requiere_revision", "no_cumple_criterio", "sin_run"];
  const cont = document.getElementById("barra-resumen");
  cont.innerHTML = "";
  orden.forEach((k) => {
    const seg = document.createElement("div");
    seg.className = "seg " + COLOR_CATEGORIA[k];
    seg.style.width = (100 * cat[k] / total) + "%";
    seg.title = ETIQUETAS_CATEGORIA[k] + ": " + fmt(cat[k]);
    cont.appendChild(seg);
  });
}

function round1(x) { return Math.round(x * 10) / 10; }

/* ---------------- 2. COMUNAS ---------------- */
function pintarComunas(comunas) {
  const cont = document.getElementById("lista-comunas");
  cont.innerHTML = "";
  const maxTotal = Math.max(...comunas.map((c) => c.total_nomina));
  comunas.forEach((c) => {
    const fila = document.createElement("div");
    fila.className = "fila-comuna";
    const pct = c.pct_encontrado_valido;
    const anchoBarra = 100 * (c.total_nomina / maxTotal);

    const encN = typeof c.encontrado_valido === "number" ? c.encontrado_valido : 0;
    const sinN = typeof c.sin_registro === "number" ? c.sin_registro : 0;
    const otrosN = c.total_nomina - encN - sinN; // agrupa revision+no_cumple (y su residuo suprimido)

    fila.innerHTML = `
      <div class="etq-comuna">
        <span class="nombre">${c.comuna} <span style="color:#9aa; font-weight:400;">(n=${fmt(c.total_nomina)})</span></span>
        <span class="pct">${pct !== null ? pctStr(pct) + " con registro válido" : "n/d (n insuficiente)"}</span>
      </div>
      <div class="barra-comuna" style="width:${anchoBarra}%">
        <div class="seg col-encontrado" style="width:${100*encN/c.total_nomina}%" title="Registro válido: ${fmt(c.encontrado_valido)}"></div>
        <div class="seg col-sin-registro" style="width:${100*sinN/c.total_nomina}%" title="Sin registro: ${fmt(c.sin_registro)}"></div>
        <div class="seg col-revision" style="width:${100*Math.max(otrosN,0)/c.total_nomina}%" title="Otras categorías (revisión/no cumple criterio, agregadas): ${fmt(otrosN)}"></div>
      </div>
    `;
    cont.appendChild(fila);
  });
}

/* ---------------- 3. EVOLUCION TEMPORAL ---------------- */
function pintarEvolucion(meses) {
  const svgNS = "http://www.w3.org/2000/svg";
  const cont = document.getElementById("grafico-evolucion");
  cont.innerHTML = "";
  const w = cont.clientWidth || 900, h = 260, pad = 40;
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.setAttribute("width", "100%");
  svg.setAttribute("height", h);

  const valores = meses.map((m) => (typeof m.acumulado === "number" ? m.acumulado : null));
  const maxV = Math.max(...valores.filter((v) => v !== null), 1);
  const n = meses.length;
  const xStep = (w - 2 * pad) / (n - 1);

  // eje
  const ejeX = document.createElementNS(svgNS, "line");
  ejeX.setAttribute("x1", pad); ejeX.setAttribute("x2", w - pad);
  ejeX.setAttribute("y1", h - pad); ejeX.setAttribute("y2", h - pad);
  ejeX.setAttribute("stroke", "#ccc");
  svg.appendChild(ejeX);

  let puntos = [];
  meses.forEach((m, i) => {
    const x = pad + i * xStep;
    if (typeof m.acumulado === "number") {
      const y = h - pad - (m.acumulado / maxV) * (h - 2 * pad);
      puntos.push([x, y]);
    }
  });

  if (puntos.length > 1) {
    const path = document.createElementNS(svgNS, "polyline");
    path.setAttribute("points", puntos.map((p) => p.join(",")).join(" "));
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "#0b4f6c");
    path.setAttribute("stroke-width", "2.5");
    svg.appendChild(path);
  }
  puntos.forEach(([x, y]) => {
    const c = document.createElementNS(svgNS, "circle");
    c.setAttribute("cx", x); c.setAttribute("cy", y); c.setAttribute("r", 4);
    c.setAttribute("fill", "#0b4f6c");
    svg.appendChild(c);
  });
  meses.forEach((m, i) => {
    const x = pad + i * xStep;
    const t = document.createElementNS(svgNS, "text");
    t.setAttribute("x", x); t.setAttribute("y", h - pad + 16);
    t.setAttribute("font-size", "10"); t.setAttribute("text-anchor", "middle");
    t.setAttribute("fill", "#666");
    t.textContent = m.mes.slice(5);
    svg.appendChild(t);
  });
  cont.appendChild(svg);

  // tabla de nuevos por mes
  const tbody = document.getElementById("tabla-mensual-body");
  tbody.innerHTML = "";
  meses.forEach((m) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${m.mes}</td><td class="num">${fmt(m.nuevos_encontrados)}</td><td class="num">${m.acumulado === null ? '<span class="badge-supresion">no publicado (protección de datos)</span>' : fmt(m.acumulado)}</td>`;
    tbody.appendChild(tr);
  });
}

/* ---------------- 4. ESTABLECIMIENTOS ---------------- */
function pintarEstablecimientos(lista) {
  const tbody = document.getElementById("tabla-establecimientos-body");
  tbody.innerHTML = "";
  const maxN = Math.max(...lista.map((e) => e.total_encontrados));
  lista.forEach((e) => {
    const tr = document.createElement("tr");
    const ancho = 100 * e.total_encontrados / maxN;
    tr.innerHTML = `
      <td>${e.establecimiento}</td>
      <td>${e.comuna_ocurrencia}</td>
      <td class="num">${fmt(e.total_encontrados)}</td>
      <td style="width:180px;"><div style="background:#1c7293; height:12px; border-radius:3px; width:${ancho}%;"></div></td>
    `;
    tbody.appendChild(tr);
  });
}

/* ---------------- 5. HALLAZGO FUERA DE NOMINA ---------------- */
function pintarHallazgo607(data) {
  document.getElementById("kpi-607-total").textContent = fmt(data.total);
  document.getElementById("aviso-607-texto").textContent = data.advertencia;

  const tbodyComuna = document.getElementById("tabla-607-comuna-body");
  tbodyComuna.innerHTML = "";
  data.por_comuna_residencia.forEach((c) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${c.comuna_residencia}</td><td class="num">${fmt(c.n)}</td>`;
    tbodyComuna.appendChild(tr);
  });

  const tbodyEstab = document.getElementById("tabla-607-estab-body");
  tbodyEstab.innerHTML = "";
  data.por_establecimiento.forEach((e) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${e.establecimiento}</td><td>${e.comuna_ocurrencia}</td><td class="num">${fmt(e.n)}</td>`;
    tbodyEstab.appendChild(tr);
  });

  const tbodyMes = document.getElementById("tabla-607-mes-body");
  tbodyMes.innerHTML = "";
  data.por_mes.forEach((m) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${m.mes}</td><td class="num">${fmt(m.n)}</td>`;
    tbodyMes.appendChild(tr);
  });
}

/* ---------------- Inicio ---------------- */
async function init() {
  initTabs();
  try {
    const [resumen, comunas, meses, estab, hallazgo607] = await Promise.all([
      cargarJSON("data/resumen.json"),
      cargarJSON("data/comunas.json"),
      cargarJSON("data/evolucion_mensual.json"),
      cargarJSON("data/establecimientos.json"),
      cargarJSON("data/hallazgo_607.json"),
    ]);
    pintarResumen(resumen);
    pintarComunas(comunas);
    pintarEvolucion(meses);
    pintarEstablecimientos(estab);
    pintarHallazgo607(hallazgo607);
  } catch (e) {
    document.getElementById("error-carga").style.display = "block";
    document.getElementById("error-carga").textContent =
      "No se pudieron cargar los datos (" + e.message + "). Si abrió este archivo con doble clic, " +
      "los navegadores modernos bloquean la lectura de archivos locales por seguridad. " +
      "Sirva la carpeta con un servidor local, por ejemplo ejecutando en esta carpeta: " +
      "python -m http.server 8000  y luego abra http://localhost:8000/ en su navegador.";
    console.error(e);
  }
}

document.addEventListener("DOMContentLoaded", init);
