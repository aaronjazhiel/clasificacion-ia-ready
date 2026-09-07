const $ = (id) => document.getElementById(id);

const dropzone = $("dropzone");
const inputArchivo = $("input-archivo");
const cajaArchivo = $("archivo");
const btnAnalizar = $("btn-analizar");
const cajaError = $("error");

let archivo = null;
let activo = null;
let catalogos = null;

const ETIQUETAS = {
  id: ["Identificador", "Identidad"],
  tipo: ["Categoría PKH", "Naturaleza"],
  tipo_activo: ["Tipo de activo", "Naturaleza"],
  fase: ["Fase", "Identidad"],
  descripcion: ["Descripción", "Semántica"],
  version: ["Versión", "Identidad"],
  estado: ["Estado", "Gobierno"],
  responsable: ["Responsable", "Gobierno"],
  fecha: ["Fecha del documento", "Identidad"],
  fuente: ["Fuente", "Procedencia"],
  confidencialidad: ["Confidencialidad", "Gobierno"],
  contexto: ["Contexto", "Semántica"],
  relaciones: ["Relaciones", "Grafo"],
  trazabilidad: ["Trazabilidad", "Calidad"],
};

const EJES = {
  contexto_funcional: "Contexto funcional",
  contexto_tecnico: "Contexto técnico",
  dominio: "Dominio o área",
  sistemas_involucrados: "Sistemas involucrados",
  proceso_relacionado: "Proceso relacionado",
};

fetch("/api/taxonomy").then(r => r.json()).then(d => { catalogos = d; }).catch(() => {});

/* ---------- carga ---------- */

dropzone.addEventListener("click", () => inputArchivo.click());
dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); inputArchivo.click(); }
});
["dragenter", "dragover"].forEach(ev =>
  dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("activa"); }));
["dragleave", "drop"].forEach(ev =>
  dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.remove("activa"); }));
dropzone.addEventListener("drop", (e) => tomarArchivo(e.dataTransfer.files[0]));
inputArchivo.addEventListener("change", () => tomarArchivo(inputArchivo.files[0]));
$("btn-quitar").addEventListener("click", limpiar);

const EXTENSIONES_VALIDAS = [".docx", ".pdf", ".json", ".png", ".jpg", ".jpeg", ".pptx"];

function tomarArchivo(f) {
  if (!f) return;
  const ext = "." + f.name.toLowerCase().split(".").pop();
  if (!EXTENSIONES_VALIDAS.includes(ext)) {
    return mostrarError("Formato no soportado. Formatos aceptados: .docx, .pdf, .json, .png, .jpg, .jpeg, .pptx");
  }
  archivo = f;
  cajaError.hidden = true;
  $("archivo-nombre").textContent = f.name;
  $("archivo-meta").textContent =
    `${(f.size / 1024 / 1024).toFixed(2)} MB · ${f.name.split(".").pop().toUpperCase()}`;
  cajaArchivo.hidden = false;
  btnAnalizar.disabled = false;
}

function limpiar() {
  archivo = null; activo = null;
  inputArchivo.value = "";
  cajaArchivo.hidden = true;
  btnAnalizar.disabled = true;
  $("bloque-proceso").hidden = true;
  $("bloque-resultado").hidden = true;
  cajaError.hidden = true;
  $("confirmacion").hidden = true;
}

function mostrarError(msg) {
  cajaError.textContent = msg;
  cajaError.hidden = false;
}

/* ---------- análisis ---------- */

const FASES = ["recibido", "texto", "imagenes", "analisis", "metadatos"];

function fase(nombre, estado) {
  const li = document.querySelector(`[data-fase="${nombre}"]`);
  if (li) li.className = estado;
}

btnAnalizar.addEventListener("click", async () => {
  if (!archivo) return;
  cajaError.hidden = true;
  $("confirmacion").hidden = true;
  $("bloque-resultado").hidden = true;
  $("bloque-proceso").hidden = false;
  FASES.forEach(f => fase(f, ""));
  btnAnalizar.disabled = true;
  btnAnalizar.textContent = "Analizando…";

  fase("recibido", "lista");
  fase("texto", "activa");
  const t = setTimeout(() => { fase("texto", "lista"); fase("imagenes", "lista"); fase("analisis", "activa"); }, 900);

  try {
    const datos = new FormData();
    datos.append("file", archivo);
    const res = await fetch("/api/analyze", { method: "POST", body: datos });
    clearTimeout(t);
    const ct = res.headers.get("content-type") || "";
    if (!ct.includes("application/json")) {
      throw new Error(`Error del servidor (${res.status}). El servicio no está disponible, intenta de nuevo en unos minutos.`);
    }
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || "El análisis no se completó.");

    FASES.forEach(f => fase(f, "lista"));
    activo = json.activo;
    pintar(activo, json.duracion_segundos);
  } catch (err) {
    clearTimeout(t);
    FASES.forEach(f => fase(f, ""));
    $("bloque-proceso").hidden = true;
    mostrarError(err.message);
  } finally {
    btnAnalizar.disabled = false;
    btnAnalizar.textContent = "Analizar documento con IA";
  }
});

/* ---------- ficha ---------- */

function nivelClase(score) {
  return score >= 90 ? "alta" : score >= 70 ? "media" : "revision";
}

function badge(campo) {
  const score = activo.confianza?.[campo] ?? 0;
  const nivel = activo.niveles?.[campo] ?? "";
  const span = document.createElement("span");
  span.className = `confianza ${nivelClase(score)}`;
  span.textContent = `Confianza ${score}% · ${nivel}`;
  return span;
}

function evidencia(campo) {
  const ev = activo.evidencias?.[campo];
  if (!ev) return null;
  const p = document.createElement("p");
  p.className = "evidencia";
  const cita = ev.cita ? ` · “${ev.cita}”` : "";
  p.innerHTML = `<b>${ev.metodo.replace("_", " ")}</b> desde ${ev.origen}${cita}`;
  return p;
}

function contenedorCampo(campo) {
  const [titulo, capa] = ETIQUETAS[campo];
  const div = document.createElement("div");
  div.className = "campo";
  const cab = document.createElement("div");
  cab.className = "campo-cab";
  cab.innerHTML = `<span class="campo-nombre">${titulo}</span>
                   <span class="campo-capa">${capa}</span>`;
  cab.appendChild(badge(campo));
  div.appendChild(cab);
  return div;
}

function campoTexto(campo, multilinea = false) {
  const div = contenedorCampo(campo);
  const el = document.createElement(multilinea ? "textarea" : "input");
  el.value = activo[campo] ?? "";
  el.addEventListener("input", () => { activo[campo] = el.value; });
  div.appendChild(el);
  const ev = evidencia(campo);
  if (ev) div.appendChild(ev);
  return div;
}

function campoLista(campo, opciones) {
  const div = contenedorCampo(campo);
  const sel = document.createElement("select");
  opciones.forEach(op => {
    const o = document.createElement("option");
    o.value = op; o.textContent = op;
    if (op === activo[campo]) o.selected = true;
    sel.appendChild(o);
  });
  sel.addEventListener("change", () => { activo[campo] = sel.value; });
  div.appendChild(sel);
  const ev = evidencia(campo);
  if (ev) div.appendChild(ev);
  return div;
}

function campoContexto() {
  const div = contenedorCampo("contexto");
  Object.entries(EJES).forEach(([clave, etiqueta]) => {
    const lab = document.createElement("p");
    lab.className = "evidencia";
    lab.innerHTML = `<b>${etiqueta}</b>`;
    const el = document.createElement("textarea");
    el.rows = 2;
    el.value = activo.contexto?.[clave] ?? "";
    el.addEventListener("input", () => { activo.contexto[clave] = el.value; });
    div.appendChild(lab);
    div.appendChild(el);
  });
  return div;
}

function campoRelaciones() {
  const div = contenedorCampo("relaciones");
  const caja = document.createElement("div");
  caja.className = "relaciones";
  if (!activo.relaciones?.length) {
    caja.innerHTML = '<span class="evidencia">No se identificaron entidades relacionadas.</span>';
  } else {
    activo.relaciones.forEach(r => {
      const s = document.createElement("span");
      s.className = "rel";
      s.innerHTML = `${r.nombre} <small>${r.tipo}</small>`;
      caja.appendChild(s);
    });
  }
  div.appendChild(caja);
  return div;
}

function pintar(a, duracion) {
  const resumen = $("resumen");
  const d = a._documento || {};
  resumen.innerHTML = "";
  [
    a.id,
    a.tipo,
    `${d.parrafos || 0} párrafos · ${d.tablas || 0} tablas · ${d.imagenes_analizadas || 0} imágenes`,
    `${duracion}s`,
    a.requiere_revision?.length
      ? `${a.requiere_revision.length} campos por revisar`
      : "Sin campos críticos",
  ].forEach(txt => {
    const c = document.createElement("span");
    c.className = "chip"; c.textContent = txt;
    resumen.appendChild(c);
  });

  const ficha = $("ficha");
  ficha.innerHTML = "";
  ficha.appendChild(campoTexto("id"));
  ficha.appendChild(campoLista("tipo", catalogos?.tipos || [a.tipo]));
  ficha.appendChild(campoLista("tipo_activo", catalogos?.tipos_activo || [a.tipo_activo]));
  ficha.appendChild(campoLista("fase", catalogos?.fases || [a.fase]));
  ficha.appendChild(campoTexto("descripcion", true));
  ficha.appendChild(campoTexto("version"));
  ficha.appendChild(campoLista("estado", catalogos?.estados || [a.estado]));
  ficha.appendChild(campoTexto("responsable"));
  ficha.appendChild(campoTexto("fecha"));
  ficha.appendChild(campoTexto("fuente"));
  ficha.appendChild(campoLista("confidencialidad", catalogos?.confidencialidad || [a.confidencialidad]));
  ficha.appendChild(campoContexto());
  ficha.appendChild(campoRelaciones());
  ficha.appendChild(campoTexto("trazabilidad", true));

  const obs = $("observaciones");
  const lista = $("lista-observaciones");
  lista.innerHTML = "";
  if (a.observaciones?.length) {
    a.observaciones.forEach(o => {
      const li = document.createElement("li");
      li.textContent = o;
      lista.appendChild(li);
    });
    obs.hidden = false;
  } else {
    obs.hidden = true;
  }

  $("bloque-resultado").hidden = false;
  $("bloque-resultado").scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ---------- validación humana ---------- */

async function enviarValidacion(decision) {
  if (!activo) return;
  const res = await fetch("/api/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ activo, decision }),
  });
  const ct = res.headers.get("content-type") || "";
  if (!ct.includes("application/json")) {
    const caja = $("confirmacion");
    caja.className = "confirmacion pendiente";
    caja.textContent = `Error del servidor (${res.status}). Intenta de nuevo.`;
    caja.hidden = false;
    return;
  }
  const json = await res.json();
  const caja = $("confirmacion");
  caja.className = "confirmacion" + (decision === "pendiente" ? " pendiente" : "");
  caja.textContent = json.campos_pendientes?.length
    ? `${json.mensaje} Quedan ${json.campos_pendientes.length} campos sin identificar: ${json.campos_pendientes.join(", ")}.`
    : json.mensaje;
  caja.hidden = false;
}

$("btn-validar").addEventListener("click", () => enviarValidacion("aceptado"));
$("btn-pendiente").addEventListener("click", () => enviarValidacion("pendiente"));
$("btn-json").addEventListener("click", async () => {
  if (!activo) return;
  await navigator.clipboard.writeText(JSON.stringify(activo, null, 2));
  const caja = $("confirmacion");
  caja.className = "confirmacion";
  caja.textContent = "JSON del activo copiado al portapapeles.";
  caja.hidden = false;
});
