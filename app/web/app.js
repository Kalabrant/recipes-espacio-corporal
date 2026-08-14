/* ============================================================
   Récipes — Espacio Corporal · Pantalla A (Nuevo récipe)
   JavaScript puro. Sin framework, sin build, sin red externa:
   todas las llamadas son al Flask local (rutas relativas).
   ============================================================ */
"use strict";

/* ------------------------------------------------------------
   0. Utilidades
   ------------------------------------------------------------ */

const $ = (sel, raiz) => (raiz || document).querySelector(sel);

/**
 * Cómo se ve el código en la vista previa. Tiene que decir exactamente lo
 * mismo que imprime el PDF (`RELLENO_CODIGO` de rutas.py): el número se
 * asigna al guardar, así que un formulario abandonado no quema ninguno
 * (§6.2). Se rellena con guiones bajos y no con el símbolo de espacio abierto
 * porque Lato no trae ese glifo y en la hoja saldría un hueco mudo.
 *
 * El prefijo es configurable (§6.6), así que esto NO es una constante: arranca
 * en el valor por defecto y `fijarPrefijo()` lo pone en lo que devuelva
 * GET /api/config, que es exactamente lo que el backend le pasa al PDF. Si el
 * médico cambia el prefijo a XY, la pantalla dice XY y la hoja también.
 */
const PREFIJO_POR_DEFECTO = "EC";
let prefijoActual = PREFIJO_POR_DEFECTO;

function rellenoCodigo() {
  return prefijoActual + "-____-____";
}

/** Alinea el texto de la pantalla con el prefijo guardado en el backend. */
function fijarPrefijo(prefijo) {
  prefijoActual = limpio(prefijo).toUpperCase() || PREFIJO_POR_DEFECTO;
  const muestra = document.getElementById("relleno-codigo");
  if (muestra) muestra.textContent = rellenoCodigo();
}

// Marcas diacríticas que NFD deja sueltas (U+0300–U+036F). Se arma con
// RegExp para que el archivo quede en ASCII puro y ningún editor lo rompa.
const MARCAS_DIACRITICAS = new RegExp("[\\u0300-\\u036f]", "g");

/** Minúsculas y sin acentos, igual que la normalización del servidor. */
function normalizar(texto) {
  return String(texto == null ? "" : texto)
    .normalize("NFD")
    .replace(MARCAS_DIACRITICAS, "")
    .toLowerCase();
}

function escaparHtml(texto) {
  return String(texto == null ? "" : texto)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * Devuelve el texto con <mark> sobre el tramo que coincide con la consulta,
 * comparando sin acentos ni mayúsculas pero conservando el original.
 */
function resaltar(texto, consulta) {
  const original = String(texto == null ? "" : texto);
  const q = normalizar(consulta).trim();
  if (!q) return escaparHtml(original);

  // Mapa carácter a carácter: la normalización puede cambiar la longitud.
  let normal = "";
  const mapa = [];                       // índice en `normal` -> índice en `original`
  for (let i = 0; i < original.length; i++) {
    const trozo = normalizar(original[i]);
    for (let j = 0; j < trozo.length; j++) mapa.push(i);
    normal += trozo;
  }

  const pos = normal.indexOf(q);
  if (pos < 0) return escaparHtml(original);

  const desde = mapa[pos];
  const hasta = pos + q.length < mapa.length ? mapa[pos + q.length] : original.length;

  return escaparHtml(original.slice(0, desde)) +
         "<mark>" + escaparHtml(original.slice(desde, hasta)) + "</mark>" +
         escaparHtml(original.slice(hasta));
}

/** Retrasa la ejecución; cada llamada nueva reinicia el reloj. */
function retrasar(fn, ms) {
  let reloj = null;
  const envuelto = function () {
    const args = arguments;
    clearTimeout(reloj);
    reloj = setTimeout(() => fn.apply(null, args), ms);
  };
  envuelto.cancelar = () => clearTimeout(reloj);
  envuelto.ya = function () {
    clearTimeout(reloj);
    fn.apply(null, arguments);
  };
  return envuelto;
}

/**
 * Mensaje para el médico a partir de una excepción. Los errores del backend
 * ya vienen escritos para él y pasan tal cual; los del navegador («Failed to
 * fetch», cuando el servidor local no contesta) se cambian por el texto de
 * respaldo, que dice qué hacer en castellano.
 */
function motivoLegible(err, porDefecto) {
  const texto = err && err.message ? String(err.message) : "";
  if (!texto || /failed to fetch|networkerror|load failed|cancel/i.test(texto)) {
    return porDefecto;
  }
  return texto;
}

/** Mensaje de error legible a partir de una respuesta del backend. */
async function mensajeDeError(respuesta, porDefecto) {
  try {
    const cuerpo = await respuesta.json();
    if (cuerpo && cuerpo.error) return String(cuerpo.error);
  } catch (_) { /* no era JSON */ }
  return porDefecto + " (código " + respuesta.status + ")";
}

/**
 * Cuerpo JSON de una respuesta que ya se sabe buena. Si no trajera JSON
 * —un 200 con el cuerpo vacío, por ejemplo— devuelve `{}` en vez de romper:
 * la acción salió bien igual y el médico no tiene por qué ver un error.
 */
async function cuerpoJson(respuesta) {
  try {
    return await respuesta.json();
  } catch (_) {
    return {};
  }
}

/** GET a la API local; devuelve el array `resultados`. */
async function pedirSugerencias(ruta, parametros) {
  const url = new URL(ruta, window.location.href);
  Object.keys(parametros).forEach((k) => {
    const v = parametros[k];
    if (v !== null && v !== undefined && v !== "") url.searchParams.set(k, v);
  });
  const r = await fetch(url.toString(), { headers: { "Accept": "application/json" } });
  if (!r.ok) throw new Error(await mensajeDeError(r, "No se pudieron traer las sugerencias."));
  const cuerpo = await r.json();
  return Array.isArray(cuerpo.resultados) ? cuerpo.resultados : [];
}

/**
 * Como `pedirSugerencias`, pero devuelve el cuerpo entero. Lo usa el Historial,
 * que además de `resultados` necesita el `aviso` que manda el backend cuando el
 * registro de Excel quedó pendiente porque estaba abierto (§9).
 */
async function pedirCuerpo(ruta, parametros) {
  const url = new URL(ruta, window.location.href);
  Object.keys(parametros || {}).forEach((k) => {
    const v = parametros[k];
    if (v !== null && v !== undefined && v !== "") url.searchParams.set(k, v);
  });
  const r = await fetch(url.toString(), { headers: { "Accept": "application/json" } });
  if (!r.ok) throw new Error(await mensajeDeError(r, "No se pudo leer la lista."));
  return r.json();
}

/* ------------------------------------------------------------
   1. Autocompletado reutilizable (§8)
   Lista bajo el campo · máximo 8 · flechas + Enter · clic ·
   Escape cierra · resaltado · la selección SIEMPRE es explícita.
   ------------------------------------------------------------ */

let contadorListas = 0;

function montarAutocompletar(entrada, lista, opciones) {
  const cfg = Object.assign({
    buscar: async () => [],       // (consulta) -> Promise<item[]>
    aTexto: (item) => String(item),
    aDetalle: () => "",
    alElegir: () => {},
    minimo: 1,
    espera: 180
  }, opciones);

  if (!lista.id) lista.id = "lista-auto-" + (++contadorListas);
  entrada.setAttribute("aria-controls", lista.id);

  let items = [];
  let activo = -1;
  let abierta = false;
  let consultaVigente = "";
  let pedidoNro = 0;

  function cerrar() {
    abierta = false;
    lista.hidden = true;
    lista.innerHTML = "";
    items = [];
    activo = -1;
    entrada.setAttribute("aria-expanded", "false");
    entrada.removeAttribute("aria-activedescendant");
  }

  function pintar() {
    lista.innerHTML = "";
    items.forEach((item, i) => {
      const li = document.createElement("li");
      li.className = "sugerencia" + (i === activo ? " activa" : "");
      li.id = lista.id + "-op-" + i;
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", i === activo ? "true" : "false");

      let html = resaltar(cfg.aTexto(item), consultaVigente);
      const detalle = cfg.aDetalle(item);
      if (detalle) html += '<span class="sugerencia-detalle">' + escaparHtml(detalle) + "</span>";
      li.innerHTML = html;

      // mousedown y no click: evita que el blur cierre la lista antes de tiempo.
      li.addEventListener("mousedown", (ev) => {
        ev.preventDefault();
        elegir(i);
      });
      li.addEventListener("mouseenter", () => {
        activo = i;
        marcarActivo();
      });

      lista.appendChild(li);
    });
    lista.hidden = items.length === 0;
    abierta = items.length > 0;
    entrada.setAttribute("aria-expanded", abierta ? "true" : "false");
    marcarActivo();
  }

  function marcarActivo() {
    Array.prototype.forEach.call(lista.children, (li, i) => {
      const esta = i === activo;
      li.classList.toggle("activa", esta);
      li.setAttribute("aria-selected", esta ? "true" : "false");
      if (esta) {
        entrada.setAttribute("aria-activedescendant", li.id);
        if (li.scrollIntoView) li.scrollIntoView({ block: "nearest" });
      }
    });
    if (activo < 0) entrada.removeAttribute("aria-activedescendant");
  }

  function elegir(i) {
    const item = items[i];
    if (!item) return;
    cerrar();
    cfg.alElegir(item, entrada);
  }

  async function buscarYAbrir(consulta) {
    consultaVigente = consulta;
    const mio = ++pedidoNro;
    let resultados;
    try {
      resultados = await cfg.buscar(consulta);
    } catch (err) {
      // Una sugerencia que falla no puede trabar la escritura: se calla.
      if (mio === pedidoNro) cerrar();
      return;
    }
    if (mio !== pedidoNro) return;                 // llegó una respuesta vieja
    if (document.activeElement !== entrada) return; // el foco ya se fue
    items = (resultados || []).slice(0, 8);
    activo = -1;
    if (items.length === 0) { cerrar(); return; }
    pintar();
  }

  const buscarConEspera = retrasar((consulta) => buscarYAbrir(consulta), cfg.espera);

  entrada.addEventListener("input", () => {
    const consulta = entrada.value.trim();
    if (consulta.length < cfg.minimo) {
      buscarConEspera.cancelar();
      pedidoNro++;
      cerrar();
      return;
    }
    buscarConEspera(consulta);
  });

  entrada.addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowDown") {
      if (!abierta) {
        const consulta = entrada.value.trim();
        if (consulta.length >= cfg.minimo) { ev.preventDefault(); buscarConEspera.ya(consulta); }
        return;
      }
      ev.preventDefault();
      activo = (activo + 1) % items.length;
      marcarActivo();
      return;
    }
    if (ev.key === "ArrowUp") {
      if (!abierta) return;
      ev.preventDefault();
      activo = activo <= 0 ? items.length - 1 : activo - 1;
      marcarActivo();
      return;
    }
    if (ev.key === "Enter") {
      if (abierta && activo >= 0) {
        ev.preventDefault();
        ev.stopPropagation();      // no dispara el "Enter avanza de campo"
        elegir(activo);
      } else if (abierta) {
        // Lista abierta sin elección: Enter solo la cierra. Nada se rellena solo.
        ev.preventDefault();
        ev.stopPropagation();
        cerrar();
      }
      return;
    }
    if (ev.key === "Escape") {
      if (abierta) { ev.preventDefault(); ev.stopPropagation(); cerrar(); }
      return;
    }
    if (ev.key === "Tab") cerrar();
  });

  entrada.addEventListener("blur", () => { setTimeout(cerrar, 0); });

  return { cerrar };
}

/* ------------------------------------------------------------
   2. Estado
   ------------------------------------------------------------ */

/** Ficha en blanco del paciente. `auto*` recuerda lo que rellenó la app. */
function pacienteVacio() {
  return {
    id: null,
    fecha_nacimiento: null,
    sexo: null,
    telefono: null,
    // Lo que la app escribió sola al elegir un paciente de la lista. Sirve
    // para distinguir un dato que puso la app de uno que escribió el médico:
    // si suelta la identidad, se borra lo primero y se respeta lo segundo.
    autoCedula: null,
    autoEdad: null
  };
}

const estado = {
  paciente: pacienteVacio(),
  entra: true,          // último resultado de /api/medir
  guardando: false,
  urlPrevia: null       // blob: de la vista previa vigente
};

let contadorRenglones = 0;

/* Nodos fijos */
const nodos = {
  pacNombre:    $("#pac-nombre"),
  pacCedula:    $("#pac-cedula"),
  pacEdad:      $("#pac-edad"),
  hintPaciente: $("#hint-paciente"),
  diagnostico:  $("#diagnostico"),
  renglones:    $("#renglones"),
  btnAgregar:   $("#btn-agregar"),
  indGenerales: $("#ind-generales"),
  aviso:        $("#aviso-capacidad"),
  avisoTexto:   $("#aviso-texto"),
  medida:       $("#medida"),
  btnGuardar:   $("#btn-guardar"),
  errorGlobal:  $("#error-global"),
  exito:        $("#exito"),
  exitoCodigo:  $("#exito-codigo"),
  exitoTexto:   $("#exito-texto"),
  btnCerrarExito: $("#btn-cerrar-exito"),
  btnRefrescar: $("#btn-refrescar"),
  previaIframe: $("#previa-iframe"),
  previaVacia:  $("#previa-vacia"),
  previaEstado: $("#previa-estado"),
  previaMarco:  $(".previa-marco"),
  columnaForm:  $("#columna-form"),
  plantilla:    $("#tpl-renglon")
};

/* ------------------------------------------------------------
   3. Lectura del formulario
   ------------------------------------------------------------ */

function limpio(valor) { return String(valor == null ? "" : valor).trim(); }

function edadComoNumero() {
  const bruto = limpio(nodos.pacEdad.value);
  if (!bruto) return null;
  const n = parseInt(bruto, 10);
  return Number.isFinite(n) ? n : null;
}

function leerRenglones() {
  return Array.prototype.map.call(nodos.renglones.children, (renglon) => ({
    medicamento:  limpio($('[data-campo="medicamento"]', renglon).value),
    presentacion: limpio($('[data-campo="presentacion"]', renglon).value),
    cantidad:     limpio($('[data-campo="cantidad"]', renglon).value),
    dosis:        limpio($('[data-campo="dosis"]', renglon).value),
    indicaciones: limpio($('[data-campo="indicaciones"]', renglon).value)
  }));
}

/** Renglones que tienen al menos el nombre del medicamento. */
function itemsUtiles() {
  return leerRenglones().filter((it) => it.medicamento !== "");
}

/** Cuerpo para /api/medir. */
function cuerpoMedida() {
  return {
    paciente_nombre: limpio(nodos.pacNombre.value),
    items: itemsUtiles(),
    indicaciones_generales: limpio(nodos.indGenerales.value)
  };
}

/** Cuerpo para /api/vista-previa y /api/recipes (el contrato es el mismo). */
function cuerpoRecipe() {
  const paciente = {
    nombre:   limpio(nodos.pacNombre.value),
    cedula:   limpio(nodos.pacCedula.value),
    edad:     edadComoNumero(),
    fecha_nacimiento: estado.paciente.fecha_nacimiento || null,
    sexo:     estado.paciente.sexo || null,
    telefono: estado.paciente.telefono || null
  };
  if (estado.paciente.id !== null && estado.paciente.id !== undefined) {
    paciente.id = estado.paciente.id;
  }
  return {
    paciente: paciente,
    diagnostico: limpio(nodos.diagnostico.value),
    notas: "",
    items: itemsUtiles(),
    indicaciones_generales: limpio(nodos.indGenerales.value)
  };
}

/* ------------------------------------------------------------
   4. Renglones de medicamento
   ------------------------------------------------------------ */

function agregarRenglon(darFoco) {
  const nodo = nodos.plantilla.content.firstElementChild.cloneNode(true);
  const nro = ++contadorRenglones;

  // Etiquetas con id único, para que el clic en la etiqueta enfoque el campo.
  ["medicamento", "presentacion", "cantidad", "dosis", "indicaciones"].forEach((campo) => {
    const entrada = $('[data-campo="' + campo + '"]', nodo);
    entrada.id = "r" + nro + "-" + campo;
  });
  $('[data-para="med"]',   nodo).setAttribute("for", "r" + nro + "-medicamento");
  $('[data-para="pres"]',  nodo).setAttribute("for", "r" + nro + "-presentacion");
  $('[data-para="cant"]',  nodo).setAttribute("for", "r" + nro + "-cantidad");
  $('[data-para="dosis"]', nodo).setAttribute("for", "r" + nro + "-dosis");
  $('[data-para="ind"]',   nodo).setAttribute("for", "r" + nro + "-indicaciones");

  // Estado propio del renglón: el id del medicamento elegido explícitamente.
  const propio = { medicamentoId: null };

  const eMed  = $('[data-campo="medicamento"]', nodo);
  const ePres = $('[data-campo="presentacion"]', nodo);
  const eDosis = $('[data-campo="dosis"]', nodo);
  const eInd  = $('[data-campo="indicaciones"]', nodo);

  const cajaSug   = $("[data-sug-dosis]", nodo);
  const textoSug  = $("[data-sug-texto]", nodo);
  const btnUsar   = $("[data-usar-dosis]", nodo);
  const btnDescartar = $("[data-descartar-dosis]", nodo);

  function ocultarSugerenciaDosis() {
    cajaSug.hidden = true;
    textoSug.textContent = "";
  }

  // ---- Medicamento (sugerencias) ----
  montarAutocompletar(eMed, $('[data-lista="medicamento"]', nodo), {
    buscar: (q) => pedirSugerencias("api/sugerencias/medicamentos", { q: q }),
    aTexto: (it) => it.nombre,
    aDetalle: (it) => it.presentacion || "",
    alElegir: (it) => {
      // Selección explícita: el médico eligió ESTE registro del catálogo,
      // así que su presentación viene con él. La dosis NO (§2.5).
      eMed.value = it.nombre || "";
      propio.medicamentoId = it.id != null ? it.id : null;
      if (it.presentacion) ePres.value = it.presentacion;

      if (it.dosis_sugerida) {
        textoSug.textContent = it.dosis_sugerida;
        cajaSug.hidden = false;
      } else {
        ocultarSugerenciaDosis();
      }
      ePres.focus();
      alCambiarAlgo();
    }
  });

  // Si edita el nombre a mano, el id deja de valer y la sugerencia se cae.
  eMed.addEventListener("input", () => {
    propio.medicamentoId = null;
    ocultarSugerenciaDosis();
  });

  // ---- Dosis (sugerencias filtradas por ESE medicamento) ----
  montarAutocompletar(eDosis, $('[data-lista="dosis"]', nodo), {
    minimo: 0,
    buscar: (q) => {
      if (propio.medicamentoId == null) return Promise.resolve([]);
      return pedirSugerencias("api/sugerencias/dosis", {
        medicamento_id: propio.medicamentoId,
        q: q
      });
    },
    aTexto: (it) => it.texto,
    alElegir: (it) => { eDosis.value = it.texto || ""; alCambiarAlgo(); }
  });

  // Con el campo vacío y un medicamento elegido, la flecha abajo abre las
  // dosis ya usadas con ese medicamento. Nunca se abre sola (§2.5).

  // ---- Indicaciones (sugerencias globales) ----
  montarAutocompletar(eInd, $('[data-lista="indicaciones"]', nodo), {
    buscar: (q) => pedirSugerencias("api/sugerencias/indicaciones", { q: q }),
    aTexto: (it) => it.texto,
    alElegir: (it) => { eInd.value = it.texto || ""; alCambiarAlgo(); }
  });

  // ---- Botones de la sugerencia de dosis ----
  btnUsar.addEventListener("click", () => {
    eDosis.value = textoSug.textContent;
    ocultarSugerenciaDosis();
    eDosis.focus();
    alCambiarAlgo();
  });
  btnDescartar.addEventListener("click", () => {
    ocultarSugerenciaDosis();
    eDosis.focus();
  });

  // ---- Quitar renglón ----
  $("[data-quitar]", nodo).addEventListener("click", () => {
    if (nodos.renglones.children.length <= 1) return;
    const siguiente = nodo.nextElementSibling || nodo.previousElementSibling;
    nodo.remove();
    renumerarRenglones();
    if (siguiente) $('[data-campo="medicamento"]', siguiente).focus();
    alCambiarAlgo();
  });

  // Cualquier tecla en el renglón recalcula medida y vista previa.
  nodo.addEventListener("input", alCambiarAlgo);

  nodos.renglones.appendChild(nodo);
  renumerarRenglones();

  if (darFoco) eMed.focus();
  return nodo;
}

function renumerarRenglones() {
  const total = nodos.renglones.children.length;
  Array.prototype.forEach.call(nodos.renglones.children, (renglon, i) => {
    $(".renglon-numero", renglon).textContent = "Medicamento " + (i + 1);
    $("[data-quitar]", renglon).hidden = total <= 1;
  });
}

/* ------------------------------------------------------------
   5. Paciente y diagnóstico
   ------------------------------------------------------------ */

function montarPaciente() {
  montarAutocompletar(nodos.pacNombre, $("#lista-pac-nombre"), {
    buscar: (q) => pedirSugerencias("api/sugerencias/pacientes", { q: q }),
    aTexto: (it) => it.nombre,
    aDetalle: (it) => {
      const partes = [];
      if (it.cedula) partes.push("C.I. " + it.cedula);
      if (it.edad !== null && it.edad !== undefined && it.edad !== "") partes.push(it.edad + " años");
      if (it.sexo) partes.push(it.sexo);
      return partes.join(" · ");
    },
    alElegir: (it) => {
      nodos.pacNombre.value = it.nombre || "";
      nodos.pacCedula.value = it.cedula || "";
      nodos.pacEdad.value = (it.edad === null || it.edad === undefined) ? "" : String(it.edad);
      estado.paciente.id = it.id != null ? it.id : null;
      estado.paciente.fecha_nacimiento = it.fecha_nacimiento || null;
      estado.paciente.sexo = it.sexo || null;
      estado.paciente.telefono = it.telefono || null;
      estado.paciente.autoCedula = nodos.pacCedula.value;
      estado.paciente.autoEdad = nodos.pacEdad.value;

      nodos.hintPaciente.textContent =
        "Paciente ya conocido: se completaron cédula y edad. Podés corregirlas.";
      nodos.hintPaciente.hidden = false;

      nodos.pacCedula.focus();
      alCambiarAlgo();
    }
  });

  // Si cambia el nombre a mano, deja de ser el paciente elegido: con la
  // identidad se van TODOS los datos que trajo esa ficha. Si no, el récipe
  // del paciente nuevo saldría con el teléfono, el sexo y hasta la cédula del
  // anterior —y el servidor, que busca por cédula, lo archivaría bajo el
  // paciente equivocado—. Lo que escribió el médico con su mano se respeta.
  nodos.pacNombre.addEventListener("input", () => {
    if (estado.paciente.id === null) return;

    if (nodos.pacCedula.value === estado.paciente.autoCedula) nodos.pacCedula.value = "";
    if (nodos.pacEdad.value === estado.paciente.autoEdad) nodos.pacEdad.value = "";

    estado.paciente = pacienteVacio();
    nodos.hintPaciente.hidden = true;
  });

  // La edad es un entero en la base: solo dígitos.
  nodos.pacEdad.addEventListener("input", () => {
    const solo = nodos.pacEdad.value.replace(/[^\d]/g, "").slice(0, 3);
    if (solo !== nodos.pacEdad.value) nodos.pacEdad.value = solo;
  });

  montarAutocompletar(nodos.diagnostico, $("#lista-diagnostico"), {
    buscar: (q) => pedirSugerencias("api/sugerencias/diagnosticos", { q: q }),
    aTexto: (it) => it.texto,
    alElegir: (it) => { nodos.diagnostico.value = it.texto || ""; }
  });
}

/* ------------------------------------------------------------
   6. Medida de capacidad (§7: avisar antes de generar)
   ------------------------------------------------------------ */

let medidaNro = 0;

async function medir() {
  const cuerpo = cuerpoMedida();

  // Sin nada que medir: no molestamos al servidor ni mostramos avisos.
  if (!cuerpo.paciente_nombre && cuerpo.items.length === 0) {
    medidaNro++;                       // invalida cualquier respuesta en vuelo
    aplicarMedida({ entra: true }, true);
    return;
  }

  const mio = ++medidaNro;
  try {
    const r = await fetch("api/medir", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(cuerpo)
    });
    if (!r.ok) throw new Error(await mensajeDeError(r, "No se pudo calcular si el récipe entra en la hoja."));
    const datos = await r.json();
    if (mio !== medidaNro) return;
    // Con el nombre escrito pero sin ningún medicamento, la medición sirve
    // igual —avisa si el nombre no entra en el renglón— pero el porcentaje de
    // hoja usada sería siempre 0%: se mide, no se muestra.
    aplicarMedida(datos, cuerpo.items.length === 0);
  } catch (err) {
    if (mio !== medidaNro) return;
    // Si la medición falla, no bloqueamos el guardado: el backend
    // igual rechaza lo que no entre y avisa con su propio mensaje.
    aplicarMedida({ entra: true }, true);
  }
}

function aplicarMedida(datos, ocultarDetalle) {
  estado.entra = datos.entra !== false;

  if (!estado.entra) {
    let texto = "No caben tantos renglones en la hoja. Quitá medicamentos o acortá las dosis.";
    if (datos.nombre_estado === "truncado") {
      texto = "El nombre del paciente no entra en la línea. Acortalo (por ejemplo, dejá un solo apellido).";
    }
    nodos.avisoTexto.textContent = texto;
    nodos.aviso.hidden = false;
  } else {
    nodos.aviso.hidden = true;
  }

  if (ocultarDetalle || typeof datos.rp_usado_mm !== "number") {
    nodos.medida.hidden = true;
  } else {
    const rp = Math.round((datos.rp_usado_mm / datos.rp_disponible_mm) * 100);
    const ind = Math.round((datos.ind_usado_mm / datos.ind_disponible_mm) * 100);
    let texto = "Hoja usada — Rp.: " + rp + "% · Indicaciones: " + ind + "%.";
    if (datos.nombre_estado === "abreviado") {
      texto += " El nombre sale abreviado: " + (datos.nombre_impreso || "") + ".";
    }
    nodos.medida.textContent = texto;
    nodos.medida.hidden = false;
  }

  actualizarBotonGuardar();
}

function actualizarBotonGuardar() {
  nodos.btnGuardar.disabled = estado.guardando || !estado.entra;
  nodos.btnGuardar.textContent = estado.guardando ? "Guardando…" : "Guardar e imprimir";
}

/* ------------------------------------------------------------
   7. Vista previa (§6.2: no quema número)
   ------------------------------------------------------------ */

let previaNro = 0;

/**
 * Qué falta para que valga la pena pedir el PDF. Devuelve null si no falta
 * nada. Así no se le piden al backend hojas que no puede componer.
 */
function faltaParaPrevia() {
  if (limpio(nodos.pacNombre.value) === "") {
    return "Escribí el nombre del paciente para ver la vista previa.";
  }
  if (itemsUtiles().length === 0) {
    return "Agregá al menos un medicamento para ver la vista previa.";
  }
  return null;
}

function soltarPrevia() {
  if (estado.urlPrevia) {
    URL.revokeObjectURL(estado.urlPrevia);
    estado.urlPrevia = null;
  }
}

function mostrarPreviaVacia(mensaje) {
  soltarPrevia();
  nodos.previaIframe.hidden = true;
  nodos.previaIframe.removeAttribute("src");
  nodos.previaVacia.hidden = false;
  nodos.previaEstado.classList.remove("con-error");
  nodos.previaEstado.textContent = mensaje;
}

async function refrescarPrevia() {
  const falta = faltaParaPrevia();
  if (falta) {
    previaNro++;                       // invalida cualquier PDF en vuelo
    mostrarPreviaVacia(falta);
    return;
  }

  // Si la medición ya dijo que no entra, el PDF va a fallar igual: se ahorra
  // el viaje y, sobre todo, el mensaje técnico del generador. El aviso de
  // capacidad, que dice qué hacer, ya está a la vista. La última hoja buena
  // se deja en pantalla para que el médico vea qué está por perder.
  if (!estado.entra) {
    previaNro++;
    nodos.previaMarco.classList.remove("cargando");
    nodos.previaEstado.classList.remove("con-error");
    nodos.previaEstado.textContent =
      "El récipe no entra en la hoja: la vista previa quedó como estaba.";
    return;
  }

  const mio = ++previaNro;
  nodos.previaMarco.classList.add("cargando");
  nodos.previaEstado.classList.remove("con-error");
  nodos.previaEstado.textContent = "Generando vista previa…";

  try {
    const r = await fetch("api/vista-previa", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/pdf" },
      body: JSON.stringify(cuerpoRecipe())
    });
    if (!r.ok) throw new Error(await mensajeDeError(r, "No se pudo generar la vista previa."));

    const pdf = await r.blob();
    if (mio !== previaNro) return;                     // llegó una vieja

    soltarPrevia();
    estado.urlPrevia = URL.createObjectURL(pdf);
    nodos.previaVacia.hidden = true;
    nodos.previaIframe.hidden = false;
    nodos.previaIframe.src = estado.urlPrevia;
    nodos.previaEstado.textContent =
      "Vista previa. El número se asigna recién al guardar: acá sale " +
      rellenoCodigo() + ".";
  } catch (err) {
    if (mio !== previaNro) return;
    nodos.previaEstado.classList.add("con-error");
    nodos.previaEstado.textContent = motivoLegible(err,
      "No se pudo generar la vista previa. Probá con «Actualizar vista previa».");
  } finally {
    if (mio === previaNro) nodos.previaMarco.classList.remove("cargando");
  }
}

/* ------------------------------------------------------------
   8. Disparador común de cambios
   ------------------------------------------------------------ */

const medirConEspera  = retrasar(medir, 350);
const previaConEspera = retrasar(refrescarPrevia, 800);

function alCambiarAlgo() {
  ocultarError();
  medirConEspera();
  previaConEspera();
}

/* ------------------------------------------------------------
   9. Errores y éxito
   ------------------------------------------------------------ */

function mostrarError(mensaje, campo) {
  nodos.errorGlobal.textContent = mensaje;
  nodos.errorGlobal.hidden = false;
  nodos.errorGlobal.scrollIntoView({ block: "nearest", behavior: "smooth" });
  if (campo) {
    campo.classList.add("con-error");
    campo.focus();
    campo.addEventListener("input", function quitar() {
      campo.classList.remove("con-error");
      campo.removeEventListener("input", quitar);
    });
  }
}

function ocultarError() {
  nodos.errorGlobal.hidden = true;
  nodos.errorGlobal.textContent = "";
}

function mostrarExito(codigo) {
  nodos.exitoCodigo.textContent = "Récipe " + codigo;
  nodos.exitoTexto.textContent = "Guardado. Se abrió para imprimir.";
  nodos.exito.hidden = false;
  nodos.columnaForm.scrollTop = 0;
  nodos.btnCerrarExito.focus();
}

/* ------------------------------------------------------------
   10. Guardar e imprimir
   ------------------------------------------------------------ */

function validar() {
  if (limpio(nodos.pacNombre.value) === "") {
    mostrarError("Escribí el nombre del paciente antes de guardar.", nodos.pacNombre);
    return false;
  }
  // Renglones con medicamento escrito, junto con el nodo del que salieron:
  // así el mensaje de error puede enfocar el campo exacto.
  const conNodo = Array.prototype.map.call(nodos.renglones.children, (renglon) => ({
    renglon: renglon,
    medicamento: limpio($('[data-campo="medicamento"]', renglon).value),
    dosis: limpio($('[data-campo="dosis"]', renglon).value)
  })).filter((r) => r.medicamento !== "");

  if (conNodo.length === 0) {
    const primero = $('[data-campo="medicamento"]', nodos.renglones.children[0]);
    mostrarError("Agregá al menos un medicamento antes de guardar.", primero);
    return false;
  }

  const sinDosis = conNodo.findIndex((r) => r.dosis === "");
  if (sinDosis >= 0) {
    const renglon = conNodo[sinDosis].renglon;
    mostrarError("Falta la dosis de «" + conNodo[sinDosis].medicamento +
                 "». Escribí cómo se toma (por ejemplo: 1 tableta cada 8 horas por 7 días).",
                 $('[data-campo="dosis"]', renglon));
    return false;
  }
  if (!estado.entra) {
    mostrarError("No caben tantos renglones en la hoja. Quitá medicamentos o acortá las dosis.");
    return false;
  }
  return true;
}

async function guardar() {
  if (estado.guardando) return;
  ocultarError();

  // Antes de guardar, medimos con lo último escrito (sin esperar el debounce).
  medirConEspera.cancelar();
  await medir();
  if (!validar()) return;

  estado.guardando = true;
  actualizarBotonGuardar();

  try {
    const r = await fetch("api/recipes", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(cuerpoRecipe())
    });
    if (!r.ok) throw new Error(await mensajeDeError(r, "No se pudo guardar el récipe. Volvé a intentar."));
    const datos = await r.json();

    limpiarFormulario();
    mostrarExito(datos.codigo || "");
    alGuardarRecipe(datos);            // punto de extensión de la Fase 4
  } catch (err) {
    mostrarError(motivoLegible(err, "No se pudo guardar el récipe. Volvé a intentar."));
  } finally {
    estado.guardando = false;
    actualizarBotonGuardar();
  }
}

/* ------------------------------------------------------------
   11. Limpieza para el siguiente récipe
   ------------------------------------------------------------ */

function limpiarFormulario() {
  medirConEspera.cancelar();
  previaConEspera.cancelar();
  medidaNro++;
  previaNro++;

  nodos.pacNombre.value = "";
  nodos.pacCedula.value = "";
  nodos.pacEdad.value = "";
  nodos.diagnostico.value = "";
  nodos.indGenerales.value = "";
  nodos.hintPaciente.hidden = true;

  estado.paciente = pacienteVacio();
  estado.entra = true;

  nodos.renglones.innerHTML = "";
  agregarRenglon(false);

  nodos.aviso.hidden = true;
  nodos.medida.hidden = true;
  ocultarError();
  actualizarBotonGuardar();

  mostrarPreviaVacia("Escribí el paciente y al menos un medicamento para ver la vista previa.");
}

/* ------------------------------------------------------------
   12. Pestañas
   ------------------------------------------------------------ */

function montarPestanas() {
  const pestanas = Array.prototype.slice.call(document.querySelectorAll(".pestana"));

  function activar(destino) {
    pestanas.forEach((p) => {
      const esta = p.dataset.panel === destino;
      p.classList.toggle("activa", esta);
      p.setAttribute("aria-selected", esta ? "true" : "false");
      document.getElementById(p.dataset.panel).hidden = !esta;
    });
    // Cada panel se llena la primera vez que se abre, no al arrancar: quien
    // solo emite récipes no espera nunca por consultas que no pidió.
    if (destino === "panel-historial") alAbrirHistorial();
    if (destino === "panel-config") alAbrirConfiguracion();
  }

  pestanas.forEach((p, i) => {
    p.addEventListener("click", () => activar(p.dataset.panel));
    p.addEventListener("keydown", (ev) => {
      let salto = 0;
      if (ev.key === "ArrowRight") salto = 1;
      else if (ev.key === "ArrowLeft") salto = -1;
      else return;
      ev.preventDefault();
      const otra = pestanas[(i + salto + pestanas.length) % pestanas.length];
      otra.focus();
      activar(otra.dataset.panel);
    });
  });
}

/* ------------------------------------------------------------
   13. Enter avanza de campo (flujo de teclado, §7)
   ------------------------------------------------------------ */

function enfocables() {
  const sel = "#panel-nuevo input:not([disabled]), #panel-nuevo textarea:not([disabled]), " +
              "#panel-nuevo button:not([disabled]):not([hidden])";
  return Array.prototype.filter.call(document.querySelectorAll(sel),
    (el) => el.offsetParent !== null);
}

function montarTeclado() {
  document.addEventListener("keydown", (ev) => {
    // Con el cerrojo puesto, el tutorial arriba o un diálogo abierto, el
    // formulario no existe.
    if (cerrojoPuesto() || modalAbierto() || tutorialAbierto()) return;

    // Ctrl+Enter guarda desde cualquier campo.
    if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
      ev.preventDefault();
      if (!nodos.btnGuardar.disabled) guardar();
      return;
    }

    if (ev.key !== "Enter" || ev.shiftKey || ev.altKey) return;

    const destino = ev.target;
    if (!(destino instanceof HTMLElement)) return;
    if (destino.tagName === "TEXTAREA") return;                 // Enter = salto de línea
    if (destino.tagName === "BUTTON") return;                   // Enter = pulsar
    if (destino.tagName !== "INPUT") return;
    // Historial, Configuración y el cerrojo tienen su propio Enter.
    if (!destino.closest("#panel-nuevo")) return;
    // Si el autocompletado manejó el Enter, ya llamó a stopPropagation().

    ev.preventDefault();
    const lista = enfocables();
    const i = lista.indexOf(destino);
    if (i >= 0 && i + 1 < lista.length) lista[i + 1].focus();
  });
}

/* ------------------------------------------------------------
   14. Arranque
   ------------------------------------------------------------ */

function arrancar() {
  montarPestanas();
  montarPaciente();
  montarTeclado();
  montarHistorial();
  montarConfiguracion();
  // Antes del cerrojo: si no hay PIN, `arrancarCerrojo()` destapa la pantalla
  // en cuanto contesta /api/config y ahí mismo puede lanzar el tutorial.
  montarTutorial();
  montarCerrojo();

  agregarRenglon(false);

  nodos.btnAgregar.addEventListener("click", () => { agregarRenglon(true); alCambiarAlgo(); });
  nodos.btnGuardar.addEventListener("click", guardar);
  nodos.btnRefrescar.addEventListener("click", () => {
    previaConEspera.cancelar();
    refrescarPrevia();
  });
  nodos.btnCerrarExito.addEventListener("click", () => {
    nodos.exito.hidden = true;
    nodos.pacNombre.focus();
  });

  [nodos.pacNombre, nodos.pacCedula, nodos.pacEdad, nodos.indGenerales]
    .forEach((el) => el.addEventListener("input", alCambiarAlgo));
  nodos.diagnostico.addEventListener("input", ocultarError);   // no sale impreso: no mueve la previa

  window.addEventListener("beforeunload", soltarPrevia);

  actualizarBotonGuardar();

  // Con el cerrojo puesto el foco es del PIN: arrancarCerrojo() lo maneja.
  if (!cerrojoPuesto()) nodos.pacNombre.focus();
}

/* ------------------------------------------------------------
   15. Después de guardar un récipe
   ------------------------------------------------------------ */

function alGuardarRecipe(resultado) {
  /* Corre después de que el backend confirmó el récipe.
   *
   * Recibe el JSON de POST /api/recipes tal cual: {codigo, ruta_pdf} y, si
   * algo quedó a medias, {aviso}. Dos cosas de la Fase 4:
   *
   * 1. El registro de Excel (§9). Si el archivo estaba abierto, el récipe se
   *    guardó igual y el PDF se generó igual: el backend manda `aviso` con el
   *    texto ya escrito para el médico ("El registro está abierto en Excel.
   *    Cerralo y volvé a intentar."). Va como nota debajo del código, nunca
   *    como error rojo, porque no hay nada que rehacer: el registro se
   *    reescribe entero solo, en el próximo guardado o anulación.
   * 2. El Historial ya no refleja lo que hay en la base: se marca vencido para
   *    que se vuelva a pedir cuando el médico abra esa pestaña.
   */
  const datos = resultado || {};

  const aviso = limpio(datos.aviso);
  if (aviso) {
    nodos.exitoTexto.textContent = "Guardado. Se abrió para imprimir. " + aviso;
  }

  hist.vencido = true;
}

/* ------------------------------------------------------------
   16. Historial (§7-B)
   Buscador único + rango de fechas · tabla · ver PDF · reimprimir ·
   anular con motivo. Todo lo que muestra sale del backend: acá no se
   recalcula ni se regenera nada, se pide el archivo tal cual quedó.
   ------------------------------------------------------------ */

const LIMITE_HISTORIAL = 200;      // el mismo tope que aplica el backend

const hist = {
  cargado: false,       // ¿ya se pidió alguna vez?
  vencido: false,       // ¿cambió algo desde la última vez? (récipe nuevo, anulación)
  pidiendo: 0,          // número de pedido, para descartar respuestas viejas
  filas: [],            // último resultado, para el modal de anulación
  verId: null           // récipe que se está viendo en el marco de la derecha
};

const nHist = {
  q:        $("#hist-q"),
  desde:    $("#hist-desde"),
  hasta:    $("#hist-hasta"),
  limpiar:  $("#hist-limpiar"),
  resumen:  $("#hist-resumen"),
  aviso:    $("#hist-aviso"),
  error:    $("#hist-error"),
  cuerpo:   $("#hist-cuerpo"),
  vacio:    $("#hist-vacio"),
  columna:  $("#columna-historial"),
  iframe:   $("#hist-iframe"),
  previaVacia:  $("#hist-previa-vacia"),
  previaEstado: $("#hist-previa-estado"),
  cerrarPdf: $("#hist-cerrar-pdf"),
  aside:    $(".columna-previa-historial"),
  trabajo:  $(".trabajo-historial")
};

/** `2026-08-14` → `14/08/2026`. Si viene otra cosa, se muestra tal cual. */
function fechaLegible(iso) {
  const texto = limpio(iso);
  const partes = /^(\d{4})-(\d{2})-(\d{2})/.exec(texto);
  return partes ? partes[3] + "/" + partes[2] + "/" + partes[1] : texto;
}

function hayFiltros() {
  return limpio(nHist.q.value) !== "" ||
         limpio(nHist.desde.value) !== "" ||
         limpio(nHist.hasta.value) !== "";
}

function avisoHistorial(texto) {
  nHist.aviso.textContent = texto;
  nHist.aviso.hidden = false;
  nHist.error.hidden = true;
}

function errorHistorial(texto) {
  nHist.error.textContent = texto;
  nHist.error.hidden = false;
  nHist.aviso.hidden = true;
}

function limpiarAvisosHistorial() {
  nHist.aviso.hidden = true;
  nHist.error.hidden = true;
}

/**
 * Pide la lista y la pinta. `nota` es un mensaje propio de la pantalla (por
 * ejemplo el de una anulación recién hecha) que se muestra junto con el `aviso`
 * que pueda venir del backend: los dos son noticias, no errores, y perder
 * cualquiera de los dos dejaría al médico sin saber algo que pasó.
 */
async function cargarHistorial(nota) {
  // Solo texto: esta función también se llama desde `retrasar`, que reenvía los
  // argumentos del evento, y un InputEvent no es una nota para nadie.
  const notaTexto = typeof nota === "string" ? limpio(nota) : "";
  const mio = ++hist.pidiendo;
  const parametros = {
    q: limpio(nHist.q.value),
    desde: limpio(nHist.desde.value),
    hasta: limpio(nHist.hasta.value)
  };

  // Rango al revés: se avisa antes de molestar al backend.
  if (parametros.desde && parametros.hasta && parametros.desde > parametros.hasta) {
    nHist.resumen.textContent = "";
    pintarHistorial([], "La fecha «Desde» es posterior a la de «Hasta». Cambiá una de las dos.");
    return;
  }

  nHist.resumen.textContent = "Buscando…";

  try {
    const cuerpo = await pedirCuerpo("api/recipes", parametros);
    if (mio !== hist.pidiendo) return;                 // llegó una respuesta vieja
    const resultados = Array.isArray(cuerpo.resultados) ? cuerpo.resultados : [];
    hist.cargado = true;
    hist.vencido = false;
    hist.filas = resultados;
    pintarHistorial(resultados, null);

    // §9: el registro quedó desactualizado porque estaba abierto en Excel.
    const partes = [notaTexto, limpio(cuerpo.aviso)].filter(Boolean);
    if (partes.length) avisoHistorial(partes.join(" "));
    // Sin nada que decir, el cartel se va: si el médico cerró el Excel y el
    // registro se puso al día, dejar el aviso viejo sería mentirle.
    else nHist.aviso.hidden = true;
  } catch (err) {
    if (mio !== hist.pidiendo) return;
    nHist.resumen.textContent = "";
    nHist.cuerpo.innerHTML = "";
    nHist.vacio.hidden = true;
    errorHistorial(motivoLegible(err,
      "No se pudo leer el historial. Cerrá la app y volvé a abrirla."));
  }
}

function pintarHistorial(resultados, mensajeVacio) {
  nHist.cuerpo.innerHTML = "";

  if (resultados.length === 0) {
    nHist.vacio.textContent = mensajeVacio ||
      (hayFiltros() ? "No encontré récipes con eso."
                    : "Todavía no hay récipes emitidos.");
    nHist.vacio.hidden = false;
    nHist.resumen.textContent = "";
    return;
  }

  nHist.vacio.hidden = true;
  resultados.forEach((r) => nHist.cuerpo.appendChild(filaHistorial(r)));

  const cuantos = resultados.length;
  let resumen = cuantos === 1 ? "1 récipe." : cuantos + " récipes.";
  if (cuantos >= LIMITE_HISTORIAL) {
    resumen = "Los " + LIMITE_HISTORIAL + " más recientes. Hay más: " +
              "afiná la búsqueda o poné un rango de fechas.";
  }
  nHist.resumen.textContent = resumen;
}

/** Una fila de la tabla. Todo lo que viene del backend entra por textContent. */
function filaHistorial(r) {
  const anulado = r.anulado === true || r.anulado === 1;
  const tr = document.createElement("tr");
  if (anulado) tr.className = "fila-anulada";

  // Código
  const tdCodigo = document.createElement("td");
  tdCodigo.className = "celda-codigo";
  tdCodigo.textContent = r.codigo || "";
  tr.appendChild(tdCodigo);

  // Fecha
  const tdFecha = document.createElement("td");
  tdFecha.className = "celda-fecha";
  tdFecha.textContent = fechaLegible(r.fecha_emision);
  tr.appendChild(tdFecha);

  // Paciente (+ cédula debajo)
  const tdPaciente = document.createElement("td");
  const nombre = document.createElement("span");
  nombre.className = "celda-paciente-nombre";
  nombre.textContent = r.paciente_nombre || "(sin nombre)";
  tdPaciente.appendChild(nombre);
  if (limpio(r.cedula)) {
    const ci = document.createElement("span");
    ci.className = "celda-paciente-cedula";
    ci.textContent = "C.I. " + r.cedula;
    tdPaciente.appendChild(ci);
  }
  tr.appendChild(tdPaciente);

  // Medicamentos (resumen) + diagnóstico, que se guarda y se busca pero no se imprime
  const tdMed = document.createElement("td");
  tdMed.className = "celda-medicamentos";
  tdMed.textContent = r.medicamentos || "—";
  if (limpio(r.diagnostico)) {
    const dx = document.createElement("span");
    dx.className = "celda-diagnostico";
    dx.textContent = "Dx: " + r.diagnostico;
    tdMed.appendChild(dx);
  }
  tr.appendChild(tdMed);

  // Estado (+ motivo al lado, §10)
  const tdEstado = document.createElement("td");
  if (anulado) {
    const marca = document.createElement("span");
    marca.className = "estado-anulado";
    marca.textContent = r.fecha_anulacion
      ? "Anulado el " + fechaLegible(r.fecha_anulacion)
      : "Anulado";
    const motivo = document.createElement("span");
    motivo.className = "estado-motivo";
    motivo.textContent = limpio(r.motivo_anulacion) || "Sin motivo registrado.";
    marca.appendChild(motivo);
    tdEstado.appendChild(marca);
  } else {
    const marca = document.createElement("span");
    marca.className = "estado-vigente";
    marca.textContent = "Vigente";
    tdEstado.appendChild(marca);
  }
  tr.appendChild(tdEstado);

  // Acciones: siempre con texto, nunca un ícono suelto (§7)
  const tdAcciones = document.createElement("td");
  const caja = document.createElement("div");
  caja.className = "acciones-fila";

  caja.appendChild(botonFila("Ver PDF", () => verPdfDeRecipe(r)));
  caja.appendChild(botonFila("Reimprimir", (boton) => reimprimirRecipe(r, boton)));

  if (!anulado) {
    const anular = botonFila("Anular…", () => abrirModalAnular(r));
    anular.classList.add("boton-fila-peligro");
    caja.appendChild(anular);
  } else {
    // Un récipe anulado no se des-anula nunca (§10): el botón no vuelve.
    const quieto = botonFila("Ya anulado", null);
    quieto.disabled = true;
    caja.appendChild(quieto);
  }

  tdAcciones.appendChild(caja);
  tr.appendChild(tdAcciones);
  return tr;
}

function botonFila(texto, alPulsar) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "boton-fila";
  b.textContent = texto;
  if (alPulsar) b.addEventListener("click", () => alPulsar(b));
  return b;
}

/* ---------- Ver PDF ---------- */

/**
 * Ancho mínimo del panel para mostrar la lista y el PDF al mismo tiempo. Por
 * debajo de eso el PDF se queda con el panel entero y se vuelve a la lista con
 * un botón: una hoja carta apretada en media pantalla no se lee, y una pestaña
 * nueva en una app de escritorio significa salir de la app.
 */
const ANCHO_PARA_DOS_COLUMNAS = 1400;

function verPdfDeRecipe(r) {
  const url = "api/recipes/" + encodeURIComponent(r.id) + "/pdf";
  limpiarAvisosHistorial();

  const partido = nHist.trabajo.clientWidth >= ANCHO_PARA_DOS_COLUMNAS;
  nHist.trabajo.classList.toggle("con-pdf", partido);
  nHist.trabajo.classList.toggle("con-pdf-solo", !partido);
  nHist.cerrarPdf.textContent = partido ? "Cerrar PDF" : "Volver a la lista";
  nHist.cerrarPdf.hidden = false;

  hist.verId = r.id;
  nHist.previaVacia.hidden = true;
  nHist.iframe.hidden = false;
  nHist.iframe.src = url;
  nHist.previaEstado.classList.remove("con-error");
  nHist.previaEstado.textContent = "Récipe " + (r.codigo || "") +
    " — el PDF guardado, sin regenerar." +
    ((r.anulado === true || r.anulado === 1) ? " Este récipe está anulado." : "");
  nHist.aside.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function cerrarPdfHistorial() {
  hist.verId = null;
  nHist.trabajo.classList.remove("con-pdf", "con-pdf-solo");
  nHist.iframe.hidden = true;
  nHist.iframe.removeAttribute("src");
  nHist.previaVacia.hidden = false;
  nHist.cerrarPdf.hidden = true;
  nHist.previaEstado.classList.remove("con-error");
  nHist.previaEstado.textContent = "Elegí «Ver PDF» en un récipe para verlo acá.";
  nHist.q.focus();
}

/* ---------- Reimprimir ---------- */

async function reimprimirRecipe(r, boton) {
  limpiarAvisosHistorial();
  const antes = boton.textContent;
  boton.disabled = true;
  boton.textContent = "Abriendo…";
  try {
    const respuesta = await fetch("api/recipes/" + encodeURIComponent(r.id) + "/abrir", {
      method: "POST",
      headers: { "Accept": "application/json" }
    });
    if (!respuesta.ok) {
      throw new Error(await mensajeDeError(respuesta,
        "No se pudo abrir el PDF de " + (r.codigo || "este récipe") + "."));
    }
    avisoHistorial("Se abrió el PDF original para imprimir.");
  } catch (err) {
    errorHistorial(motivoLegible(err,
      "No se pudo abrir el PDF. Buscalo en la carpeta de datos, en pdf\\."));
  } finally {
    boton.disabled = false;
    boton.textContent = antes;
  }
}

/* ---------- Anulación (modal propio, §10) ---------- */

const nModal = {
  caja:      $("#modal-anular"),
  fondo:     $("#modal-anular-fondo"),
  contenido: $("#modal-anular-caja"),
  titulo:    $("#modal-anular-titulo"),
  sub:       $("#modal-anular-sub"),
  aviso:     $("#modal-anular-aviso"),
  motivo:    $("#modal-anular-motivo"),
  error:     $("#modal-anular-error"),
  cancelar:  $("#modal-anular-cancelar"),
  aceptar:   $("#modal-anular-aceptar")
};

const modal = { recipe: null, focoPrevio: null, enviando: false };

function modalAbierto() { return !nModal.caja.hidden; }

function abrirModalAnular(r) {
  modal.recipe = r;
  modal.focoPrevio = document.activeElement;
  modal.enviando = false;

  nModal.titulo.textContent = "Anular récipe " + (r.codigo || "");
  nModal.sub.textContent = (r.paciente_nombre || "") +
    " · " + fechaLegible(r.fecha_emision);
  nModal.aviso.textContent = "El récipe queda anulado para siempre; el código " +
    (r.codigo || "EC-…") + " no se vuelve a usar.";
  nModal.motivo.value = "";
  nModal.error.hidden = true;
  nModal.aceptar.disabled = false;
  nModal.aceptar.textContent = "Anular récipe";

  nModal.caja.hidden = false;
  nModal.motivo.focus();
}

function cerrarModalAnular() {
  if (modal.enviando) return;                 // no se cierra a mitad de camino
  nModal.caja.hidden = true;
  modal.recipe = null;
  if (modal.focoPrevio && modal.focoPrevio.focus) modal.focoPrevio.focus();
  modal.focoPrevio = null;
}

async function confirmarAnulacion() {
  const r = modal.recipe;
  if (!r || modal.enviando) return;

  const motivo = limpio(nModal.motivo.value);
  if (motivo === "") {
    nModal.error.textContent = "Escribí por qué se anula: el motivo queda en el historial.";
    nModal.error.hidden = false;
    nModal.motivo.focus();
    return;
  }

  modal.enviando = true;
  nModal.aceptar.disabled = true;
  nModal.aceptar.textContent = "Anulando…";
  nModal.error.hidden = true;

  try {
    const respuesta = await fetch("api/recipes/" + encodeURIComponent(r.id) + "/anular", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify({ motivo: motivo })
    });
    if (!respuesta.ok) {
      throw new Error(await mensajeDeError(respuesta,
        "No se pudo anular el récipe. Volvé a intentar."));
    }
    await cuerpoJson(respuesta);              // el récipe actualizado

    modal.enviando = false;
    cerrarModalAnular();
    // El aviso lo pone `cargarHistorial`, junto con el del registro de Excel
    // si el backend lo mandó: los dos se leen de una sola vez.
    await cargarHistorial("Récipe " + (r.codigo || "") + " anulado. " +
                          "El PDF queda guardado y el código no se vuelve a usar.");
    // La fila que tenía el foco ya no existe: el foco vuelve al buscador.
    nHist.q.focus();
  } catch (err) {
    modal.enviando = false;
    nModal.error.textContent = motivoLegible(err,
      "No se pudo anular el récipe. Volvé a intentar.");
    nModal.error.hidden = false;
    nModal.aceptar.disabled = false;
    nModal.aceptar.textContent = "Anular récipe";
  }
}

/* ---------- Montaje ---------- */

const buscarHistorialConEspera = retrasar(cargarHistorial, 300);

function montarHistorial() {
  nHist.q.addEventListener("input", buscarHistorialConEspera);
  [nHist.desde, nHist.hasta].forEach((el) => {
    el.addEventListener("change", () => {
      buscarHistorialConEspera.cancelar();
      cargarHistorial();
    });
  });

  // Enter busca ya, sin esperar el retraso.
  [nHist.q, nHist.desde, nHist.hasta].forEach((el) => {
    el.addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter") return;
      ev.preventDefault();
      ev.stopPropagation();
      buscarHistorialConEspera.cancelar();
      cargarHistorial();
    });
  });

  nHist.limpiar.addEventListener("click", () => {
    nHist.q.value = "";
    nHist.desde.value = "";
    nHist.hasta.value = "";
    limpiarAvisosHistorial();
    buscarHistorialConEspera.cancelar();
    cargarHistorial();
    nHist.q.focus();
  });

  nHist.cerrarPdf.addEventListener("click", cerrarPdfHistorial);

  // Modal de anulación
  nModal.cancelar.addEventListener("click", cerrarModalAnular);
  nModal.fondo.addEventListener("click", cerrarModalAnular);
  nModal.aceptar.addEventListener("click", confirmarAnulacion);
  nModal.motivo.addEventListener("input", () => { nModal.error.hidden = true; });

  document.addEventListener("keydown", (ev) => {
    if (!modalAbierto()) return;
    if (ev.key === "Escape") {
      ev.preventDefault();
      cerrarModalAnular();
      return;
    }
    if (ev.key === "Tab") atraparTab(ev, nModal.contenido);
  });
}

function alAbrirHistorial() {
  if (!hist.cargado || hist.vencido) cargarHistorial();
  nHist.q.focus();
}

/** Deja el Tab dando vueltas dentro de `caja`: un modal no cede el foco. */
function atraparTab(ev, caja) {
  const foco = caja.querySelectorAll(
    "button:not([disabled]), input:not([disabled]), textarea:not([disabled]), " +
    "select:not([disabled]), a[href]");
  const visibles = Array.prototype.filter.call(foco, (el) => el.offsetParent !== null);
  if (visibles.length === 0) return;

  const primero = visibles[0];
  const ultimo = visibles[visibles.length - 1];

  if (ev.shiftKey && document.activeElement === primero) {
    ev.preventDefault();
    ultimo.focus();
  } else if (!ev.shiftKey && document.activeElement === ultimo) {
    ev.preventDefault();
    primero.focus();
  }
}

/* ------------------------------------------------------------
   17. Configuración (§7-C)

   Un solo botón «Guardar cambios», abajo y siempre a la vista, para TODOS
   los campos de texto (datos del médico + prefijo): son un único POST
   /api/config, así que un botón por sección haría dos veces lo mismo y
   obligaría a acordarse de cuál guarda qué. El logo, el PIN, el respaldo y
   «Abrir carpeta» no son campos sino acciones —cada una con su endpoint y su
   resultado— y por eso conservan su propio botón, que hace efecto al toque.
   ------------------------------------------------------------ */

/** Los campos que viajan en POST /api/config, en el orden en que se ven. */
const CAMPOS_CONFIG = ["nombre", "especialidad", "mpps", "colegio", "rif",
                       "direccion", "telefonos", "prefijo"];

const cfg = {
  cargado: false,
  guardado: {},          // última copia confirmada por el backend
  pinActivo: false,
  tutorialVisto: false,  // ¿ya vio el recorrido de primer uso? (§19)
  logoElegido: null,     // File elegido y todavía sin subir
  urlLogoLocal: null,    // blob: de la vista del archivo elegido
  logoVisto: false       // ¿ya se buscó el logo actual? (una vez por sesión)
};

const nCfg = {
  columna:   $("#columna-config"),
  error:     $("#cfg-error"),
  prefijo:   $("#cfg-prefijo"),
  muestra:   $("#cfg-muestra"),
  carpeta:   $("#cfg-carpeta"),
  version:   $("#cfg-version"),
  barra:     $("#cfg-barra"),
  barraTexto: $("#cfg-barra-texto"),
  guardar:   $("#cfg-guardar"),
  logoImg:   $("#cfg-logo-img"),
  logoSin:   $("#cfg-logo-sin"),
  logoArchivo: $("#cfg-logo-archivo"),
  logoSubir: $("#cfg-logo-subir"),
  logoEstado: $("#cfg-logo-estado"),
  pinEstado: $("#cfg-pin-estado"),
  pinActualCampo: $("#cfg-pin-actual-campo"),
  pinActual: $("#cfg-pin-actual"),
  pinNuevo:  $("#cfg-pin-nuevo"),
  pinRepetir: $("#cfg-pin-repetir"),
  pinVer:    $("#cfg-pin-ver"),
  pinGuardar: $("#cfg-pin-guardar"),
  pinQuitar: $("#cfg-pin-quitar"),
  pinResultado: $("#cfg-pin-resultado"),
  abrirCarpeta: $("#cfg-abrir-carpeta"),
  respaldar: $("#cfg-respaldar"),
  respaldoResultado: $("#cfg-respaldo-resultado"),
  verTutorial: $("#cfg-ver-tutorial")
};

function campoConfig(nombre) {
  return document.querySelector('[data-config="' + nombre + '"]');
}

/** Muestra un resultado bajo un botón de acción. `mal` lo pinta de rojo. */
function resultadoAccion(nodo, texto, mal) {
  nodo.textContent = texto;
  nodo.classList.toggle("mal", mal === true);
  nodo.hidden = false;
}

function errorConfig(texto) {
  nCfg.error.textContent = texto;
  nCfg.error.hidden = false;
  nCfg.error.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

async function cargarConfig() {
  try {
    const respuesta = await fetch("api/config", { headers: { "Accept": "application/json" } });
    if (!respuesta.ok) {
      throw new Error(await mensajeDeError(respuesta, "No se pudo leer la configuración."));
    }
    const datos = await respuesta.json();
    cfg.cargado = true;
    pintarConfig(datos);
    return datos;
  } catch (err) {
    errorConfig(motivoLegible(err,
      "No se pudo leer la configuración. Cerrá la app y volvé a abrirla."));
    return null;
  }
}

function pintarConfig(datos) {
  cfg.guardado = {};
  CAMPOS_CONFIG.forEach((nombre) => {
    const entrada = campoConfig(nombre);
    const valor = datos[nombre] == null ? "" : String(datos[nombre]);
    cfg.guardado[nombre] = valor;
    if (entrada) entrada.value = valor;
  });

  cfg.pinActivo = datos.pin_activo === true;
  cfg.tutorialVisto = datos.tutorial_visto === true;
  pintarEstadoPin();
  actualizarMuestraCodigo();
  // El prefijo guardado manda también en la pantalla A: la vista previa tiene
  // que anunciar el mismo relleno que imprime el PDF (§6.6).
  fijarPrefijo(datos.prefijo);

  nCfg.carpeta.textContent = datos.carpeta_datos || "—";
  nCfg.version.textContent = datos.version_app
    ? "Récipes — Espacio Corporal, versión " + datos.version_app
    : "";

  marcarCambios();
}

function pintarEstadoPin() {
  if (cfg.pinActivo) {
    nCfg.pinEstado.textContent = "El PIN está activo: se pide cada vez que abrís la app.";
    nCfg.pinActualCampo.hidden = false;
    nCfg.pinGuardar.textContent = "Cambiar PIN";
    nCfg.pinQuitar.hidden = false;
  } else {
    nCfg.pinEstado.textContent = "El PIN está desactivado: la app abre directo.";
    nCfg.pinActualCampo.hidden = true;
    nCfg.pinGuardar.textContent = "Activar PIN";
    nCfg.pinQuitar.hidden = true;
  }
  nCfg.pinActual.value = "";
  nCfg.pinNuevo.value = "";
  nCfg.pinRepetir.value = "";
}

function actualizarMuestraCodigo() {
  const prefijo = limpio(nCfg.prefijo.value).toUpperCase() || PREFIJO_POR_DEFECTO;
  const anio = new Date().getFullYear();
  nCfg.muestra.textContent = prefijo + "-" + anio + "-0001";
}

/** ¿Hay algo escrito distinto de lo guardado? Prende la barra de abajo. */
function marcarCambios() {
  let sucio = false;
  CAMPOS_CONFIG.forEach((nombre) => {
    const entrada = campoConfig(nombre);
    if (!entrada) return;
    if (limpio(entrada.value) !== limpio(cfg.guardado[nombre] || "")) sucio = true;
  });

  nCfg.guardar.disabled = !sucio || !cfg.cargado;
  nCfg.barra.classList.toggle("sin-guardar", sucio);
  nCfg.barraTexto.textContent = sucio
    ? "Tenés cambios sin guardar."
    : "Todo guardado.";
}

async function guardarConfig() {
  nCfg.error.hidden = true;

  // El prefijo se valida acá con la misma regla del backend, para que el
  // mensaje llegue antes de perder el viaje (codigos.validar_prefijo).
  const prefijo = limpio(nCfg.prefijo.value).toUpperCase();
  if (prefijo === "") {
    errorConfig("El prefijo del código no puede quedar vacío. Poné al menos una letra.");
    nCfg.prefijo.focus();
    return;
  }
  if (!/^[A-Z0-9]{1,10}$/.test(prefijo)) {
    errorConfig("El prefijo del código admite solo letras y números, de 1 a 10 " +
                "caracteres (sin espacios ni guiones).");
    nCfg.prefijo.focus();
    return;
  }

  const cuerpo = {};
  CAMPOS_CONFIG.forEach((nombre) => {
    const entrada = campoConfig(nombre);
    cuerpo[nombre] = entrada ? limpio(entrada.value) : "";
  });
  cuerpo.prefijo = prefijo;

  nCfg.guardar.disabled = true;
  nCfg.guardar.textContent = "Guardando…";

  try {
    const respuesta = await fetch("api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(cuerpo)
    });
    if (!respuesta.ok) {
      throw new Error(await mensajeDeError(respuesta,
        "No se pudieron guardar los cambios. Volvé a intentar."));
    }
    const datos = await respuesta.json();
    pintarConfig(datos);                       // lo que quedó, según el backend
    nCfg.barraTexto.textContent = "Cambios guardados.";
  } catch (err) {
    errorConfig(motivoLegible(err,
      "No se pudieron guardar los cambios. Volvé a intentar."));
    marcarCambios();
  } finally {
    nCfg.guardar.textContent = "Guardar cambios";
  }
}

/* ---------- Logo ---------- */

/**
 * Vista del logo que hoy se imprime, servido por GET /api/config/logo: es el
 * mismo archivo que el backend le pasa al PDF, así que lo que se ve acá es lo
 * que sale en la hoja. Si no hay logo (404), queda el texto en vez de un cuadro
 * roto: mejor un cartel honesto.
 *
 * El `?v=` con la hora es para saltear la caché del navegador: sin eso, después
 * de subir un logo nuevo se seguiría viendo el viejo.
 */
function verLogoActual() {
  if (cfg.logoElegido) return;                 // hay una elección local a la vista
  const prueba = new Image();
  prueba.onload = () => {
    nCfg.logoImg.src = prueba.src;          // la misma URL: no se pide dos veces
    nCfg.logoImg.hidden = false;
    nCfg.logoSin.hidden = true;
  };
  prueba.onerror = () => {
    nCfg.logoImg.hidden = true;
    nCfg.logoImg.removeAttribute("src");
    nCfg.logoSin.hidden = false;
  };
  prueba.src = "api/config/logo?v=" + Date.now();
}

function soltarLogoLocal() {
  if (cfg.urlLogoLocal) {
    URL.revokeObjectURL(cfg.urlLogoLocal);
    cfg.urlLogoLocal = null;
  }
}

function alElegirLogo() {
  const archivo = nCfg.logoArchivo.files && nCfg.logoArchivo.files[0];
  nCfg.logoEstado.hidden = true;
  soltarLogoLocal();

  if (!archivo) {
    cfg.logoElegido = null;
    nCfg.logoSubir.disabled = true;
    verLogoActual();
    return;
  }

  cfg.logoElegido = archivo;
  cfg.urlLogoLocal = URL.createObjectURL(archivo);
  nCfg.logoImg.src = cfg.urlLogoLocal;
  nCfg.logoImg.hidden = false;
  nCfg.logoSin.hidden = true;

  // El ancho se mide acá también: el aviso llega antes de subir nada. El
  // backend vuelve a medirlo y tiene la última palabra.
  const prueba = new Image();
  prueba.onload = () => {
    if (prueba.naturalWidth < 350) {
      nCfg.logoSubir.disabled = true;
      resultadoAccion(nCfg.logoEstado,
        "Esta imagen mide " + prueba.naturalWidth + " píxeles de ancho: " +
        "va a salir pixelada al imprimir; buscá una imagen más grande.", true);
    } else {
      nCfg.logoSubir.disabled = false;
      resultadoAccion(nCfg.logoEstado,
        "Elegiste «" + archivo.name + "» (" + prueba.naturalWidth + " píxeles de ancho). " +
        "Pulsá «Guardar logo» para que salga en los próximos récipes.", false);
    }
  };
  prueba.onerror = () => {
    nCfg.logoSubir.disabled = true;
    resultadoAccion(nCfg.logoEstado,
      "No pude leer esa imagen. Tiene que ser un PNG o un JPG.", true);
  };
  prueba.src = cfg.urlLogoLocal;
}

async function subirLogo() {
  if (!cfg.logoElegido) return;
  const formulario = new FormData();
  formulario.append("archivo", cfg.logoElegido);

  nCfg.logoSubir.disabled = true;
  nCfg.logoSubir.textContent = "Guardando…";

  try {
    const respuesta = await fetch("api/config/logo", { method: "POST", body: formulario });
    if (!respuesta.ok) {
      throw new Error(await mensajeDeError(respuesta,
        "No se pudo guardar el logo. Probá con otra imagen."));
    }
    await cuerpoJson(respuesta);

    cfg.logoElegido = null;
    nCfg.logoArchivo.value = "";
    soltarLogoLocal();
    verLogoActual();
    resultadoAccion(nCfg.logoEstado,
      "Logo guardado. Sale en los récipes que emitas desde ahora.", false);
  } catch (err) {
    nCfg.logoSubir.disabled = false;
    resultadoAccion(nCfg.logoEstado,
      motivoLegible(err, "No se pudo guardar el logo. Probá con otra imagen."), true);
  } finally {
    nCfg.logoSubir.textContent = "Guardar logo";
  }
}

/* ---------- PIN ---------- */

function soloDigitos(entrada, maximo) {
  entrada.addEventListener("input", () => {
    const solo = entrada.value.replace(/[^\d]/g, "").slice(0, maximo);
    if (solo !== entrada.value) entrada.value = solo;
  });
}

async function enviarPin(pinNuevo, pinActual) {
  const respuesta = await fetch("api/config/pin", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Accept": "application/json" },
    body: JSON.stringify({ pin_nuevo: pinNuevo, pin_actual: pinActual })
  });
  if (!respuesta.ok) {
    throw new Error(await mensajeDeError(respuesta,
      "No se pudo cambiar el PIN. Volvé a intentar."));
  }
  return cuerpoJson(respuesta);
}

async function guardarPin() {
  nCfg.pinResultado.hidden = true;
  const nuevo = limpio(nCfg.pinNuevo.value);
  const repetido = limpio(nCfg.pinRepetir.value);
  const actual = limpio(nCfg.pinActual.value);

  if (cfg.pinActivo && actual === "") {
    resultadoAccion(nCfg.pinResultado, "Escribí tu PIN actual para poder cambiarlo.", true);
    nCfg.pinActual.focus();
    return;
  }
  if (!/^\d{4,6}$/.test(nuevo)) {
    resultadoAccion(nCfg.pinResultado,
      "El PIN nuevo tiene que ser de 4 a 6 dígitos.", true);
    nCfg.pinNuevo.focus();
    return;
  }
  if (nuevo !== repetido) {
    resultadoAccion(nCfg.pinResultado,
      "Los dos PIN no coinciden. Escribilos de nuevo.", true);
    nCfg.pinRepetir.focus();
    return;
  }

  nCfg.pinGuardar.disabled = true;
  try {
    await enviarPin(nuevo, actual);
    cfg.pinActivo = true;
    pintarEstadoPin();
    resultadoAccion(nCfg.pinResultado,
      "PIN guardado. Te lo va a pedir la próxima vez que abras la app.", false);
  } catch (err) {
    resultadoAccion(nCfg.pinResultado,
      motivoLegible(err, "No se pudo guardar el PIN. Volvé a intentar."), true);
  } finally {
    nCfg.pinGuardar.disabled = false;
  }
}

async function quitarPin() {
  nCfg.pinResultado.hidden = true;
  const actual = limpio(nCfg.pinActual.value);
  if (actual === "") {
    resultadoAccion(nCfg.pinResultado,
      "Escribí tu PIN actual para poder desactivarlo.", true);
    nCfg.pinActual.focus();
    return;
  }

  nCfg.pinQuitar.disabled = true;
  try {
    await enviarPin("", actual);
    cfg.pinActivo = false;
    pintarEstadoPin();
    resultadoAccion(nCfg.pinResultado,
      "PIN desactivado. La app va a abrir directo.", false);
  } catch (err) {
    resultadoAccion(nCfg.pinResultado,
      motivoLegible(err, "No se pudo desactivar el PIN. Volvé a intentar."), true);
  } finally {
    nCfg.pinQuitar.disabled = false;
  }
}

/* ---------- Datos y respaldo ---------- */

async function abrirCarpeta() {
  nCfg.respaldoResultado.hidden = true;
  nCfg.abrirCarpeta.disabled = true;
  try {
    const respuesta = await fetch("api/abrir-carpeta", {
      method: "POST", headers: { "Accept": "application/json" }
    });
    if (!respuesta.ok) {
      throw new Error(await mensajeDeError(respuesta, "No se pudo abrir la carpeta."));
    }
    resultadoAccion(nCfg.respaldoResultado,
      "Se abrió la carpeta en el Explorador de Windows.", false);
  } catch (err) {
    resultadoAccion(nCfg.respaldoResultado,
      motivoLegible(err,
        "No se pudo abrir la carpeta. Copiá la ruta de arriba y pegala en el Explorador."),
      true);
  } finally {
    nCfg.abrirCarpeta.disabled = false;
  }
}

async function respaldarAhora() {
  nCfg.respaldoResultado.hidden = true;
  nCfg.respaldar.disabled = true;
  nCfg.respaldar.textContent = "Respaldando…";
  try {
    const respuesta = await fetch("api/respaldo", {
      method: "POST", headers: { "Accept": "application/json" }
    });
    if (!respuesta.ok) {
      throw new Error(await mensajeDeError(respuesta,
        "No se pudo hacer el respaldo. Volvé a intentar."));
    }
    const datos = await cuerpoJson(respuesta);
    const kb = typeof datos.tamano_kb === "number"
      ? Math.round(datos.tamano_kb).toLocaleString("es-VE")
      : datos.tamano_kb;
    resultadoAccion(nCfg.respaldoResultado,
      "Respaldo creado: " + (datos.archivo || "") + " (" + kb + " KB). " +
      "Está en la carpeta respaldos\\.", false);
  } catch (err) {
    resultadoAccion(nCfg.respaldoResultado,
      motivoLegible(err, "No se pudo hacer el respaldo. Volvé a intentar."), true);
  } finally {
    nCfg.respaldar.disabled = false;
    nCfg.respaldar.textContent = "Respaldar ahora";
  }
}

/* ---------- Montaje ---------- */

function montarConfiguracion() {
  CAMPOS_CONFIG.forEach((nombre) => {
    const entrada = campoConfig(nombre);
    if (entrada) entrada.addEventListener("input", marcarCambios);
  });

  nCfg.prefijo.addEventListener("input", () => {
    const solo = nCfg.prefijo.value.replace(/[^A-Za-z0-9]/g, "").toUpperCase().slice(0, 10);
    if (solo !== nCfg.prefijo.value) nCfg.prefijo.value = solo;
    actualizarMuestraCodigo();
  });

  nCfg.guardar.addEventListener("click", guardarConfig);

  // Enter en cualquier campo de texto de Configuración guarda.
  nCfg.columna.addEventListener("keydown", (ev) => {
    if (ev.key !== "Enter") return;
    const destino = ev.target;
    if (!(destino instanceof HTMLElement) || destino.tagName !== "INPUT") return;
    if (destino.type === "file" || destino.type === "checkbox") return;
    ev.preventDefault();
    ev.stopPropagation();
    if (destino.id.indexOf("cfg-pin") === 0) guardarPin();
    else if (!nCfg.guardar.disabled) guardarConfig();
  });

  nCfg.logoArchivo.addEventListener("change", alElegirLogo);
  nCfg.logoSubir.addEventListener("click", subirLogo);

  [nCfg.pinActual, nCfg.pinNuevo, nCfg.pinRepetir].forEach((el) => soloDigitos(el, 6));
  nCfg.pinVer.addEventListener("change", () => {
    const tipo = nCfg.pinVer.checked ? "text" : "password";
    [nCfg.pinActual, nCfg.pinNuevo, nCfg.pinRepetir].forEach((el) => { el.type = tipo; });
  });
  nCfg.pinGuardar.addEventListener("click", guardarPin);
  nCfg.pinQuitar.addEventListener("click", quitarPin);

  nCfg.abrirCarpeta.addEventListener("click", abrirCarpeta);
  nCfg.respaldar.addEventListener("click", respaldarAhora);
  nCfg.verTutorial.addEventListener("click", relanzarTutorial);

  window.addEventListener("beforeunload", soltarLogoLocal);
}

function alAbrirConfiguracion() {
  if (!cfg.cargado) cargarConfig();
  // El logo se busca al abrir la pantalla y no al arrancar: quien nunca entra
  // acá no gasta dos pedidos por arranque.
  if (!cfg.logoVisto) {
    cfg.logoVisto = true;
    verLogoActual();
  }
}

/* ------------------------------------------------------------
   18. Cerrojo del PIN al abrir (§10)

   Tapa TODO hasta que /api/pin/verificar diga que sí. No se cierra con
   Escape ni haciendo clic afuera, y el foco no se le escapa: es la barrera
   contra el que pasa frente a la computadora, no una caja fuerte, así que no
   cuenta intentos ni bloquea nada (el backend ya se toma su medio segundo).
   ------------------------------------------------------------ */

const nCerrojo = {
  caja:   $("#cerrojo"),
  dialogo: $(".cerrojo-caja"),
  logo:   $("#cerrojo-logo"),
  pin:    $("#cerrojo-pin"),
  boton:  $("#cerrojo-btn"),
  error:  $("#cerrojo-error")
};

const cerrojo = { activo: false, verificando: false };

function cerrojoPuesto() { return cerrojo.activo; }

/**
 * Apaga (o vuelve a encender) todo lo que está detrás del cerrojo. `inert` lo
 * saca del Tab, del clic y del lector de pantalla de una sola vez; donde no
 * exista, quedan igual la trampa de foco y el Tab atrapado de más abajo.
 */
function fondoInerte(apagado) {
  ["header.barra", "main", "#modal-anular"].forEach((sel) => {
    const nodo = document.querySelector(sel);
    if (!nodo) return;
    nodo.inert = apagado;
    if (apagado) nodo.setAttribute("inert", "");
    else nodo.removeAttribute("inert");
  });
}

function mostrarCerrojo(listo) {
  cerrojo.activo = true;
  fondoInerte(true);
  nCerrojo.caja.hidden = false;
  nCerrojo.boton.disabled = !listo;
  nCerrojo.boton.textContent = listo ? "Entrar" : "Abriendo…";
  nCerrojo.pin.disabled = !listo;
  if (listo) nCerrojo.pin.focus();
}

function sacarCerrojo() {
  cerrojo.activo = false;
  fondoInerte(false);
  nCerrojo.caja.hidden = true;
  nCerrojo.pin.value = "";
  nodos.pacNombre.focus();
  // Recién ahora, con la pantalla a la vista: si había PIN, el tutorial
  // esperó a que se desbloqueara; si no había, esto corre igual (§19).
  quizasArrancarTutorial();
}

async function verificarPin() {
  if (cerrojo.verificando) return;
  const pin = limpio(nCerrojo.pin.value);
  if (pin === "") {
    nCerrojo.error.textContent = "Escribí tu PIN.";
    nCerrojo.error.hidden = false;
    nCerrojo.pin.focus();
    return;
  }

  cerrojo.verificando = true;
  nCerrojo.boton.disabled = true;
  nCerrojo.boton.textContent = "Verificando…";
  nCerrojo.error.hidden = true;

  try {
    const respuesta = await fetch("api/pin/verificar", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify({ pin: pin })
    });
    if (!respuesta.ok) {
      throw new Error(await mensajeDeError(respuesta, "No se pudo verificar el PIN."));
    }
    const datos = await respuesta.json();
    if (datos.ok === true) {
      sacarCerrojo();
      return;
    }
    // Sin contar intentos: el mensaje es siempre el mismo (§10).
    nCerrojo.error.textContent = "PIN incorrecto. Probá de nuevo.";
    nCerrojo.error.hidden = false;
    nCerrojo.pin.value = "";
    nCerrojo.pin.focus();
  } catch (err) {
    nCerrojo.error.textContent = motivoLegible(err,
      "No se pudo verificar el PIN. Probá de nuevo.");
    nCerrojo.error.hidden = false;
  } finally {
    cerrojo.verificando = false;
    nCerrojo.boton.disabled = false;
    nCerrojo.boton.textContent = "Entrar";
  }
}

function montarCerrojo() {
  // Se pone antes de preguntar nada: si hay PIN, la pantalla no se ve ni un
  // parpadeo. Si no lo hay, el cerrojo se saca en cuanto llega la respuesta.
  mostrarCerrojo(false);

  soloDigitos(nCerrojo.pin, 6);
  nCerrojo.pin.addEventListener("input", () => { nCerrojo.error.hidden = true; });
  nCerrojo.boton.addEventListener("click", verificarPin);
  nCerrojo.pin.addEventListener("keydown", (ev) => {
    if (ev.key !== "Enter") return;
    ev.preventDefault();
    ev.stopPropagation();
    verificarPin();
  });

  // Ni Escape ni Tab hacia afuera: el cerrojo no se puede esquivar.
  document.addEventListener("keydown", (ev) => {
    if (!cerrojo.activo) return;
    if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); return; }
    if (ev.key === "Tab") atraparTab(ev, nCerrojo.dialogo);
  }, true);

  document.addEventListener("focusin", (ev) => {
    if (!cerrojo.activo) return;
    if (!nCerrojo.dialogo.contains(ev.target)) nCerrojo.pin.focus();
  });

  arrancarCerrojo();
}

/** El logo de la carpeta del médico sobre el cerrojo, si se puede mostrar. */
function verLogoDelCerrojo() {
  const prueba = new Image();
  prueba.onload = () => {
    nCerrojo.logo.src = prueba.src;
    nCerrojo.logo.hidden = false;
  };
  prueba.onerror = () => { /* sin logo queda la marca en texto */ };
  prueba.src = "api/config/logo";
}

async function arrancarCerrojo() {
  const datos = await cargarConfig();

  // Si la configuración no se pudo leer, la app abre igual. Cerrar el paso por
  // una consulta fallida dejaría al médico sin poder emitir nada, y el PIN es
  // una barrera de escritorio, no la que protege los datos (§10): el archivo
  // está en el disco de todos modos.
  if (!datos || datos.pin_activo !== true) {
    sacarCerrojo();
    return;
  }
  verLogoDelCerrojo();
  mostrarCerrojo(true);
}

/* ------------------------------------------------------------
   19. Tutorial de primer uso

   Un recorrido de siete globos sobre la pantalla real, no una pantalla
   de ayuda aparte: el médico ve el campo del que se le habla, con el
   resto de la ventana en penumbra. Aparece solo la primera vez —lo dice
   `tutorial_visto` en la tabla `config`, no el navegador— y se vuelve a
   ver cuando quiera desde Configuración › Ayuda.

   Si hay PIN, esto no existe hasta que el PIN se desbloquee: el único
   que lo lanza es `sacarCerrojo()`, que corre tanto cuando no hay PIN
   como cuando el PIN se acertó.
   ------------------------------------------------------------ */

/**
 * Los pasos, en orden. `destino` es el selector del elemento que se
 * resalta; `null` es un globo centrado sin recorte (la bienvenida).
 *
 * Los siete apuntan a cosas que están a la vista en «Nuevo récipe» o en
 * la barra de pestañas, así que el recorrido no cambia de pantalla ni
 * toca nada del formulario: el médico termina donde empezó, con lo que
 * hubiera escrito intacto.
 */
const PASOS_TUTORIAL = [
  {
    destino: null,
    titulo: "Bienvenido",
    texto: "Con esta pantalla emitís un récipe en menos de un minuto."
  },
  {
    destino: "#panel-nuevo .fila-paciente",
    titulo: "El paciente",
    texto: "Escribí el nombre; si ya lo atendiste, aparece solo."
  },
  {
    destino: "#renglones .renglon",
    titulo: "El medicamento",
    texto: "La app aprende los que usás y te sugiere la dosis de siempre."
  },
  {
    destino: "#panel-nuevo .columna-previa",
    titulo: "La vista previa",
    texto: "La hoja tal cual sale impresa."
  },
  {
    destino: "#btn-guardar",
    titulo: "Guardar e imprimir",
    texto: "Hace todo: número, guardado, PDF listo para imprimir."
  },
  {
    destino: "#tab-historial",
    titulo: "Historial",
    texto: "Todo lo emitido queda acá para reimprimir o anular."
  },
  {
    destino: "#tab-config",
    titulo: "Configuración",
    texto: "Tu PIN, tu logo y el respaldo de tus datos."
  }
];

/** Aire entre el elemento resaltado y el globo, y contra el borde de la ventana. */
const SEPARACION_GLOBO = 16;
const MARGEN_VENTANA = 14;
/** Cuánto se agranda el recorte alrededor del elemento, para que respire. */
const HOLGURA_FOCO = 6;

const nTuto = {
  caja:      $("#tutorial"),
  foco:      $("#tutorial-foco"),
  globo:     $("#tutorial-globo"),
  punta:     $("#tutorial-punta"),
  cuerpo:    $("#tutorial-cuerpo"),
  paso:      $("#tutorial-paso"),
  titulo:    $("#tutorial-titulo"),
  texto:     $("#tutorial-texto"),
  anterior:  $("#tutorial-anterior"),
  siguiente: $("#tutorial-siguiente"),
  saltar:    $("#tutorial-saltar"),
  confirma:  $("#tutorial-confirma"),
  seguir:    $("#tutorial-seguir"),
  cerrar:    $("#tutorial-cerrar")
};

const tuto = {
  abierto: false,
  paso: 0,
  final: false,        // el cartel de cierre, después del último paso
  cerrando: false,     // la confirmación del Escape, en el mismo globo
  focoPrevio: null
};

function tutorialAbierto() { return tuto.abierto; }

/* ---------- Colocación ---------- */

/** El elemento del paso actual, o `null` si el globo va centrado. */
function destinoTutorial() {
  if (!tuto.abierto || tuto.final) return null;
  const paso = PASOS_TUTORIAL[tuto.paso];
  if (!paso || !paso.destino) return null;
  const nodo = document.querySelector(paso.destino);
  // offsetParent nulo = está oculto; mejor un globo centrado que un
  // recuadro sobre la nada.
  return nodo && nodo.offsetParent !== null ? nodo : null;
}

function centrarGlobo() {
  const alto = nTuto.globo.offsetHeight;
  const ancho = nTuto.globo.offsetWidth;
  nTuto.globo.style.left = Math.max(MARGEN_VENTANA, (window.innerWidth - ancho) / 2) + "px";
  nTuto.globo.style.top = Math.max(MARGEN_VENTANA, (window.innerHeight - alto) / 2) + "px";
}

function entre(valor, minimo, maximo) {
  if (maximo < minimo) return minimo;
  return Math.min(Math.max(valor, minimo), maximo);
}

/**
 * Pone el recuadro sobre el elemento y el globo del lado donde entre.
 *
 * Prueba abajo, arriba, derecha e izquierda en ese orden y se queda con
 * el primero que quepa entero en la ventana; si no cabe en ninguno —una
 * ventana muy chica, un elemento muy alto— el globo se centra y se apaga
 * la punta, que es lo único que quedaría apuntando a cualquier lado.
 * Por eso la ventana de 1200×800 nunca deja un globo cortado.
 */
function colocarTutorial() {
  if (!tuto.abierto) return;

  const destino = destinoTutorial();
  if (!destino) {
    nTuto.caja.classList.add("sin-foco");
    nTuto.foco.hidden = true;
    nTuto.punta.hidden = true;
    centrarGlobo();
    return;
  }

  nTuto.caja.classList.remove("sin-foco");
  const r = destino.getBoundingClientRect();

  // El recuadro se recorta contra la ventana: las pestañas de arriba están
  // pegadas al borde y, sin esto, el borde teal de arriba quedaría afuera.
  const arriba = Math.max(2, r.top - HOLGURA_FOCO);
  const izquierda = Math.max(2, r.left - HOLGURA_FOCO);
  const abajo = Math.min(window.innerHeight - 2, r.bottom + HOLGURA_FOCO);
  const derecha = Math.min(window.innerWidth - 2, r.right + HOLGURA_FOCO);

  nTuto.foco.hidden = false;
  nTuto.foco.style.top = arriba + "px";
  nTuto.foco.style.left = izquierda + "px";
  nTuto.foco.style.width = Math.max(0, derecha - izquierda) + "px";
  nTuto.foco.style.height = Math.max(0, abajo - arriba) + "px";

  const ancho = nTuto.globo.offsetWidth;
  const alto = nTuto.globo.offsetHeight;
  const anchoVentana = window.innerWidth;
  const altoVentana = window.innerHeight;
  const topeX = anchoVentana - ancho - MARGEN_VENTANA;
  const topeY = altoVentana - alto - MARGEN_VENTANA;

  const centrado = {
    x: entre(r.left + r.width / 2 - ancho / 2, MARGEN_VENTANA, topeX),
    y: entre(r.top + r.height / 2 - alto / 2, MARGEN_VENTANA, topeY)
  };

  const opciones = [
    { lado: "abajo",     x: centrado.x, y: r.bottom + SEPARACION_GLOBO },
    { lado: "arriba",    x: centrado.x, y: r.top - SEPARACION_GLOBO - alto },
    { lado: "derecha",   x: r.right + SEPARACION_GLOBO, y: centrado.y },
    { lado: "izquierda", x: r.left - SEPARACION_GLOBO - ancho, y: centrado.y }
  ];

  const elegida = opciones.filter((o) =>
    o.x >= MARGEN_VENTANA && o.x <= topeX &&
    o.y >= MARGEN_VENTANA && o.y <= topeY)[0];

  if (!elegida) {
    nTuto.punta.hidden = true;
    centrarGlobo();
    return;
  }

  nTuto.globo.style.left = elegida.x + "px";
  nTuto.globo.style.top = elegida.y + "px";

  // La punta, sobre el borde del globo que mira al elemento. Se alinea con el
  // centro del elemento, sin pasarse de las esquinas redondeadas del globo.
  nTuto.punta.hidden = false;
  const medioX = elegida.x + entre(r.left + r.width / 2 - elegida.x - 9, 16, ancho - 34);
  const medioY = elegida.y + entre(r.top + r.height / 2 - elegida.y - 9, 16, alto - 34);

  if (elegida.lado === "abajo") {
    nTuto.punta.style.top = (elegida.y - 9) + "px";
    nTuto.punta.style.left = medioX + "px";
  } else if (elegida.lado === "arriba") {
    nTuto.punta.style.top = (elegida.y + alto - 9) + "px";
    nTuto.punta.style.left = medioX + "px";
  } else if (elegida.lado === "derecha") {
    nTuto.punta.style.left = (elegida.x - 9) + "px";
    nTuto.punta.style.top = medioY + "px";
  } else {
    nTuto.punta.style.left = (elegida.x + ancho - 9) + "px";
    nTuto.punta.style.top = medioY + "px";
  }
}

/* ---------- Pintado ---------- */

function pintarTutorial() {
  nTuto.cuerpo.hidden = tuto.cerrando;
  nTuto.confirma.hidden = !tuto.cerrando;

  if (!tuto.cerrando) {
    if (tuto.final) {
      nTuto.paso.hidden = true;
      nTuto.titulo.textContent = "¡Listo!";
      nTuto.texto.textContent = "Emití tu primer récipe.";
      nTuto.siguiente.textContent = "Empezar";
      nTuto.saltar.hidden = true;
      nTuto.anterior.disabled = false;
    } else {
      const paso = PASOS_TUTORIAL[tuto.paso];
      nTuto.paso.hidden = false;
      nTuto.paso.textContent = "Paso " + (tuto.paso + 1) + " de " + PASOS_TUTORIAL.length;
      nTuto.titulo.textContent = paso.titulo;
      nTuto.texto.textContent = paso.texto;
      nTuto.siguiente.textContent =
        tuto.paso === PASOS_TUTORIAL.length - 1 ? "Terminar" : "Siguiente";
      nTuto.saltar.hidden = false;
      // Visible siempre, apagado en el primero: que no se mueva de lugar.
      nTuto.anterior.disabled = tuto.paso === 0;
    }
  }

  // El elemento puede estar fuera de la parte visible de su columna: se
  // acerca primero y se mide después de que el navegador ya movió el scroll.
  const destino = destinoTutorial();
  if (destino && destino.scrollIntoView) {
    destino.scrollIntoView({ block: "center", inline: "nearest" });
  }
  colocarTutorial();
  // Y otra vez apenas el navegador terminó de acomodar el scroll y de medir el
  // globo con su texto nuevo. Va con setTimeout y no con requestAnimationFrame
  // a propósito: si la ventana está minimizada o tapada no se dibujan cuadros,
  // el rAF no llega nunca y el globo quedaría donde lo dejó la primera cuenta.
  setTimeout(colocarTutorial, 0);
}

/* ---------- Navegación ---------- */

function irAPasoTutorial(indice) {
  tuto.final = false;
  tuto.cerrando = false;
  tuto.paso = entre(indice, 0, PASOS_TUTORIAL.length - 1);
  pintarTutorial();
  nTuto.siguiente.focus();
}

function avanzarTutorial() {
  if (tuto.cerrando) return;
  if (tuto.final) { cerrarTutorial(); return; }

  if (tuto.paso < PASOS_TUTORIAL.length - 1) {
    irAPasoTutorial(tuto.paso + 1);
    return;
  }

  // Terminó los siete: cartel de cierre y marca puesta. Se marca acá y no
  // al cerrar el cartel, porque llegar al final ya es haberlo visto.
  tuto.final = true;
  pintarTutorial();
  nTuto.siguiente.focus();
  marcarTutorialVisto();
}

function retrocederTutorial() {
  if (tuto.cerrando) return;
  if (tuto.final) { irAPasoTutorial(PASOS_TUTORIAL.length - 1); return; }
  if (tuto.paso > 0) irAPasoTutorial(tuto.paso - 1);
}

/** Escape o «Saltar»: pregunta en el mismo globo, sin sacar nada de lugar. */
function pedirCierreTutorial() {
  if (tuto.cerrando || tuto.final) return;
  tuto.cerrando = true;
  pintarTutorial();
  nTuto.seguir.focus();
}

function volverDeLaConfirmacion() {
  tuto.cerrando = false;
  pintarTutorial();
  nTuto.siguiente.focus();
}

/* ---------- Abrir y cerrar ---------- */

function abrirTutorial() {
  if (tuto.abierto) return;
  tuto.abierto = true;
  tuto.paso = 0;
  tuto.final = false;
  tuto.cerrando = false;
  tuto.focoPrevio = document.activeElement;

  fondoInerte(true);                 // detrás del tutorial no se hace clic ni Tab
  nTuto.caja.hidden = false;
  pintarTutorial();
  nTuto.siguiente.focus();
}

function cerrarTutorial() {
  if (!tuto.abierto) return;
  tuto.abierto = false;
  tuto.cerrando = false;
  tuto.final = false;
  nTuto.caja.hidden = true;
  nTuto.caja.classList.remove("sin-foco");
  fondoInerte(false);

  // Saltarlo cuenta como haberlo visto: si no, volvería a aparecer en cada
  // arranque y el médico tendría que saltarlo para siempre.
  marcarTutorialVisto();

  const volver = tuto.focoPrevio && document.contains(tuto.focoPrevio) &&
                 tuto.focoPrevio.offsetParent !== null
    ? tuto.focoPrevio
    : nodos.pacNombre;
  tuto.focoPrevio = null;
  if (volver && volver.focus) volver.focus();
}

/**
 * Deja escrito en la base que el tutorial ya se vio. Va en un POST propio
 * con un solo campo: el backend guarda nada más lo que le mandan, así que
 * esto no toca los datos del médico ni el prefijo.
 *
 * Si el pedido falla no se le avisa nada al médico: no hay ninguna acción
 * que pueda tomar, no perdió ningún dato, y lo peor que pasa es que el
 * recorrido vuelva a aparecer la próxima vez.
 */
function marcarTutorialVisto() {
  if (cfg.tutorialVisto) return;
  cfg.tutorialVisto = true;
  fetch("api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Accept": "application/json" },
    body: JSON.stringify({ tutorial_visto: true })
  }).catch(() => { /* silencio: no hay nada que el médico pueda hacer */ });
}

/** ¿Toca mostrarlo? Lo llama `sacarCerrojo()`, con o sin PIN de por medio. */
function quizasArrancarTutorial() {
  // Sin configuración leída no se sabe si ya se vio ni se podría marcar:
  // mejor no mostrarlo que mostrarlo en cada arranque.
  if (!cfg.cargado || cfg.tutorialVisto || tuto.abierto) return;
  abrirTutorial();
}

/** El botón de Configuración › Ayuda: primero la pantalla, después el globo. */
function relanzarTutorial() {
  const pestana = document.getElementById("tab-nuevo");
  if (pestana) pestana.click();
  // Un turno después, con el panel ya visible y medible.
  setTimeout(abrirTutorial, 0);
}

/* ---------- Montaje ---------- */

function montarTutorial() {
  nTuto.siguiente.addEventListener("click", avanzarTutorial);
  nTuto.anterior.addEventListener("click", retrocederTutorial);
  nTuto.saltar.addEventListener("click", pedirCierreTutorial);
  nTuto.seguir.addEventListener("click", volverDeLaConfirmacion);
  nTuto.cerrar.addEventListener("click", cerrarTutorial);

  // Teclado, en captura: las flechas y el Enter son del tutorial mientras
  // esté abierto, y no del formulario ni de la barra de pestañas.
  document.addEventListener("keydown", (ev) => {
    if (!tuto.abierto) return;

    if (ev.key === "Tab") { atraparTab(ev, nTuto.globo); return; }

    if (ev.key === "Escape") {
      ev.preventDefault();
      ev.stopPropagation();
      if (tuto.cerrando) cerrarTutorial();      // segundo Escape: confirma
      else if (tuto.final) cerrarTutorial();    // ya lo terminó: no hay qué preguntar
      else pedirCierreTutorial();
      return;
    }

    if (tuto.cerrando) return;                  // los dos botones se manejan solos

    if (ev.key === "ArrowRight" || ev.key === "ArrowDown") {
      ev.preventDefault(); ev.stopPropagation(); avanzarTutorial(); return;
    }
    if (ev.key === "ArrowLeft" || ev.key === "ArrowUp") {
      ev.preventDefault(); ev.stopPropagation(); retrocederTutorial(); return;
    }
    if (ev.key === "Enter") {
      ev.stopPropagation();
      const activo = document.activeElement;
      // Si el foco está en un botón del globo, Enter pulsa ese botón.
      if (activo && activo.tagName === "BUTTON" && nTuto.globo.contains(activo)) return;
      ev.preventDefault();
      avanzarTutorial();
    }
  }, true);

  // El foco no se va del globo aunque algo de atrás intente robarlo.
  document.addEventListener("focusin", (ev) => {
    if (!tuto.abierto) return;
    if (!nTuto.globo.contains(ev.target)) nTuto.siguiente.focus();
  });

  window.addEventListener("resize", () => { if (tuto.abierto) colocarTutorial(); });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", arrancar);
} else {
  arrancar();
}
