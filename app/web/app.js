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
 * Cómo se ve el código en la vista previa **de un paciente nuevo**. Tiene que
 * decir exactamente lo mismo que imprime el PDF (`codigo_relleno` de
 * rutas.py): un solo grupo de cuatro, porque desde la 2.0 el código es del
 * paciente y no lleva año (dec. 1). Se rellena con guiones bajos y no con el
 * símbolo de espacio abierto porque Lato no trae ese glifo y en la hoja
 * saldría un hueco mudo.
 *
 * Ojo: si el paciente YA existe, la previa no muestra este relleno sino el
 * código real del paciente, que es el que va a salir impreso (dec. 2). El
 * número se asigna al crear el paciente, así que un formulario abandonado de
 * alguien nuevo no quema ninguno (§6.2).
 *
 * El prefijo es configurable (§6.6), así que esto NO es una constante: arranca
 * en el valor por defecto y `fijarPrefijo()` lo pone en lo que devuelva
 * GET /api/config, que es exactamente lo que el backend le pasa al PDF. Si el
 * médico cambia el prefijo a XY, la pantalla dice XY y la hoja también.
 */
const PREFIJO_POR_DEFECTO = "EC";
let prefijoActual = PREFIJO_POR_DEFECTO;

function rellenoCodigo() {
  return prefijoActual + "-____";
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
    // Clases extra del <li>, para las opciones que no son "otro resultado
    // más": la de crear un paciente en la Historia va destacada (dec. 18).
    claseDe: () => "",
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
      const extra = limpio(cfg.claseDe(item));
      li.className = "sugerencia" + (extra ? " " + extra : "") + (i === activo ? " activa" : "");
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
    codigo: "",
    fecha_nacimiento: null,
    sexo: null,
    telefono: null,
    // ¿Lo puso la Historia como predeterminado (dec. 18)? Es lo que decide si
    // se ve la banda de arriba. Un paciente elegido en la lista del propio
    // récipe no la lleva: ese camino ya tiene su aviso de «paciente conocido»,
    // y dos carteles diciendo lo mismo se leen como un error.
    desdeHistoria: false,
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

/**
 * El paciente cuyo predeterminado el médico ya rechazó con «Cambiar de
 * paciente» (o soltó editando el nombre a mano). Mientras sea el mismo que
 * está abierto en la Historia, volver a la pestaña del récipe NO se lo vuelve
 * a poner: dijo que no una vez y eso vale hasta que abra otra historia.
 */
let recipeSueltoDe = null;

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
  banda:        $("#banda-paciente"),
  bandaTexto:   $("#banda-paciente-texto"),
  bandaCambiar: $("#banda-cambiar"),
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

    // Editar el nombre a mano también suelta el predeterminado de la Historia:
    // si vuelve a la pestaña, no se lo ponemos otra vez encima.
    if (estado.paciente.desdeHistoria) recipeSueltoDe = estado.paciente.id;

    estado.paciente = pacienteVacio();
    nodos.hintPaciente.hidden = true;
    pintarBandaPaciente();
  });

  nodos.bandaCambiar.addEventListener("click", () => soltarPacienteDelRecipe(true));

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
   5-bis. El récipe predeterminado de la historia abierta (dec. 18)

   Con un paciente abierto en la Historia, «Nuevo récipe» arranca con ESE
   paciente puesto. Nunca en silencio: mientras el récipe lleve una identidad
   que puso la app, arriba del formulario se ve la banda con el código y el
   nombre, y el botón para soltarla. Escribir el nombre a mano —el récipe
   rápido de siempre— sigue funcionando igual: si no hay historia abierta acá
   no pasa nada.
   ------------------------------------------------------------ */

function pintarBandaPaciente() {
  const p = estado.paciente;
  if (!p.desdeHistoria || p.id === null) {
    nodos.banda.hidden = true;
    return;
  }
  const codigo = limpio(p.codigo);
  const nombre = limpio(nodos.pacNombre.value) || "(sin nombre)";
  nodos.bandaTexto.textContent =
    "Récipe para " + (codigo ? codigo + " · " : "") + nombre;
  nodos.banda.hidden = false;
}

/** Pone en el formulario al paciente que está abierto en la Historia. */
function ponerPacienteDeLaHistoria(p) {
  nodos.pacNombre.value = limpio(p.nombre);
  nodos.pacCedula.value = limpio(p.cedula);
  nodos.pacEdad.value =
    (p.edad === null || p.edad === undefined || p.edad === "") ? "" : String(p.edad);

  estado.paciente = pacienteVacio();
  estado.paciente.id = p.id != null ? p.id : null;
  estado.paciente.codigo = limpio(p.codigo);
  estado.paciente.fecha_nacimiento = p.fecha_nacimiento || null;
  estado.paciente.sexo = p.sexo || null;
  estado.paciente.telefono = p.telefono || null;
  estado.paciente.autoCedula = nodos.pacCedula.value;
  estado.paciente.autoEdad = nodos.pacEdad.value;
  estado.paciente.desdeHistoria = true;

  // La banda ya dice de quién es el récipe: el aviso de «paciente conocido»
  // sería el mismo cartel dos veces (dec. 18, punto 6 del encargo).
  nodos.hintPaciente.hidden = true;
  pintarBandaPaciente();
  ocultarError();
  alCambiarAlgo();
}

/** Suelta la identidad y deja el campo libre, como un récipe rápido más. */
function soltarPacienteDelRecipe(darFoco) {
  if (estado.paciente.desdeHistoria) recipeSueltoDe = estado.paciente.id;

  nodos.pacNombre.value = "";
  nodos.pacCedula.value = "";
  nodos.pacEdad.value = "";
  estado.paciente = pacienteVacio();
  nodos.hintPaciente.hidden = true;
  pintarBandaPaciente();
  alCambiarAlgo();
  if (darFoco) nodos.pacNombre.focus();
}

/** ¿Hay algo escrito del paciente que pisar? */
function formularioRecipeLibre() {
  return estado.paciente.id === null &&
         limpio(nodos.pacNombre.value) === "" &&
         limpio(nodos.pacCedula.value) === "" &&
         limpio(nodos.pacEdad.value) === "";
}

/**
 * Al entrar a «Nuevo récipe». Pone el predeterminado solo si no hay nada que
 * pisar: lo que el médico haya escrito manda siempre sobre la comodidad.
 */
function aplicarDefaultDeHistoria() {
  if (hc.pacienteId === null || !hc.paciente) return;

  if (estado.paciente.desdeHistoria && estado.paciente.id === hc.pacienteId) {
    pintarBandaPaciente();                 // ya estaba puesto: solo refrescar
    return;
  }
  if (recipeSueltoDe === hc.pacienteId) return;   // dijo que no para este
  if (!formularioRecipeLibre()) return;           // hay algo escrito: no se toca

  ponerPacienteDeLaHistoria(hc.paciente);
}

/** El botón «Nuevo récipe para este paciente» de la cabecera de la Historia. */
function irAlRecipeConEstePaciente() {
  if (hc.pacienteId === null || !hc.paciente) return;
  // Acá el médico lo pidió con el dedo: se pone aunque lo hubiera soltado
  // antes. Los medicamentos y las indicaciones que hubiera escrito quedan.
  recipeSueltoDe = null;
  irAPestana("panel-nuevo");
  ponerPacienteDeLaHistoria(hc.paciente);

  const primero = nodos.renglones.children[0];
  const campo = primero ? $('[data-campo="medicamento"]', primero) : null;
  if (campo && limpio(campo.value) === "") campo.focus();
  else nodos.pacNombre.focus();
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
    let texto = "No caben tantos renglones en la hoja. Quitá medicamentos o acortá las indicaciones.";
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
    // El código que sale en la hoja lo decide el backend (`codigo_para_previa`):
    // el del paciente si ya está registrado, `EC-____` si es alguien nuevo. La
    // pantalla no lo adivina —no tiene cómo saber si la cédula o el nombre ya
    // están en la base—, así que el cartel cubre los dos casos.
    nodos.previaEstado.textContent =
      "Vista previa. Si el paciente ya está registrado sale su código; " +
      "si es nuevo, todavía dice " + rellenoCodigo() +
      " y el número se le asigna al guardar.";
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
    mostrarError("No caben tantos renglones en la hoja. Quitá medicamentos o acortá las indicaciones.");
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
  // El récipe salió: el predeterminado vuelve a estar disponible para la
  // próxima vez que entre a la pestaña con la misma historia abierta.
  recipeSueltoDe = null;
  pintarBandaPaciente();

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

/**
 * Cambia de pestaña desde cualquier parte de la app. Lo llena
 * `montarPestanas()`; hasta entonces no hace nada, que es lo correcto: si
 * todavía no se montó la barra, tampoco hay a dónde ir.
 */
let irAPestana = () => {};

/**
 * Qué pestaña está a la vista. Arranca en la Historia clínica, que es la que
 * el HTML deja activa (dec. 18: la historia es la puerta de entrada).
 */
let pestanaActiva = "panel-historia";

function montarPestanas() {
  const pestanas = Array.prototype.slice.call(document.querySelectorAll(".pestana"));

  function activar(destino) {
    pestanaActiva = destino;
    pestanas.forEach((p) => {
      const esta = p.dataset.panel === destino;
      p.classList.toggle("activa", esta);
      p.setAttribute("aria-selected", esta ? "true" : "false");
      document.getElementById(p.dataset.panel).hidden = !esta;
    });
    // Cada panel se llena la primera vez que se abre, no al arrancar: quien
    // solo emite récipes no espera nunca por consultas que no pidió.
    if (destino === "panel-historia") alAbrirHistoria();
    if (destino === "panel-nuevo") aplicarDefaultDeHistoria();
    if (destino === "panel-historial") alAbrirHistorial();
    if (destino === "panel-config") alAbrirConfiguracion();
  }

  irAPestana = activar;

  const activaAlArrancar = pestanas.filter((p) => p.classList.contains("activa"))[0];
  if (activaAlArrancar) pestanaActiva = activaAlArrancar.dataset.panel;

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
  montarHistoria();
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
  if (!cerrojoPuesto()) enfocarPestanaActiva();
}

/**
 * El primer campo de la pestaña que está a la vista. Al arrancar es el
 * buscador de la Historia (dec. 18); si el médico está en «Nuevo récipe»,
 * el nombre del paciente, como siempre.
 */
function enfocarPestanaActiva() {
  const campo = pestanaActiva === "panel-historia" ? nHc.buscar : nodos.pacNombre;
  if (campo && campo.focus) campo.focus();
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

function modalAnularAbierto() { return !nModal.caja.hidden; }

/**
 * ¿Hay algún diálogo encima de la pantalla? Lo consultan el «Enter avanza de
 * campo» y el tutorial para no pisarse con lo que está arriba: la anulación, el
 * anexado de una imagen y el visor de anexos tapan el formulario de abajo.
 */
function modalAbierto() {
  return modalAnularAbierto() || modalAnularInformeAbierto() ||
         dialogoAnexoAbierto() || visorAbierto();
}

function abrirModalAnular(r) {
  modal.recipe = r;
  modal.focoPrevio = document.activeElement;
  modal.enviando = false;

  nModal.titulo.textContent = "Anular récipe " + (r.codigo || "");
  nModal.sub.textContent = (r.paciente_nombre || "") +
    " · " + fechaLegible(r.fecha_emision);
  // Desde la 2.0 el código es del paciente y lo comparten todos sus récipes
  // (dec. 2): anular ESTE no toca a los demás ni retira el código.
  nModal.aviso.textContent = "Este récipe queda anulado para siempre. El código " +
    (r.codigo || "EC-…") + " es el del paciente: sus otros récipes no se tocan.";
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
    await cargarHistorial("Récipe del " + fechaLegible(r.fecha_emision) + " (" +
                          (r.codigo || "") + ") anulado. El PDF queda guardado.");
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
    if (!modalAnularAbierto()) return;
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
const CAMPOS_CONFIG = ["nombre", "especialidad", "mpps", "comezu", "rif",
                       "colegio", "ciudad", "direccion", "telefonos", "prefijo"];

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
  // Sin año: el correlativo es de por vida y se asigna al crear el paciente
  // (dec. 1). Pasado el 9999 el número crece a cinco dígitos, no se recicla.
  const prefijo = limpio(nCfg.prefijo.value).toUpperCase() || PREFIJO_POR_DEFECTO;
  nCfg.muestra.textContent = prefijo + "-0001";
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
  enfocarPestanaActiva();
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
 * Los pasos, en orden, siguiendo el camino real de la app (dec. 18): la
 * historia primero, y desde ella el récipe y el informe.
 *
 * `destino` es el selector del elemento que se resalta; puede ser una lista,
 * y entonces se usa el primero que esté a la vista. Eso importa porque la
 * primera vez no hay ningún paciente abierto y media pantalla de la Historia
 * todavía no existe: el paso cae sobre la tarjeta de invitación, que sí está,
 * en vez de sobre la nada. `null` es un globo centrado, sin recorte.
 *
 * `pestana` es la pantalla que hay que tener a la vista para ese paso. El
 * recorrido cambia de pestaña —no hay forma de mostrar el récipe desde la
 * Historia— pero no toca ningún formulario, y al cerrarse devuelve al médico
 * a la pestaña donde estaba: lo que hubiera escrito queda intacto.
 */
const PASOS_TUTORIAL = [
  {
    destino: null,
    pestana: "panel-historia",
    titulo: "Bienvenido",
    texto: "Todo empieza en la historia clínica: buscás al paciente y, desde su " +
           "historia, salen el récipe y el informe."
  },
  {
    destino: ["#hc-buscar"],
    pestana: "panel-historia",
    titulo: "Buscá o creá al paciente",
    texto: "Escribí el nombre o la cédula. Si el paciente no aparece, la lista " +
           "termina en «➕ Crear paciente nuevo»: lo das de alta ahí mismo y se " +
           "abre su historia."
  },
  {
    destino: ["#hc-guia", "#hc-invitacion"],
    pestana: "panel-historia",
    titulo: "La medición de WhatsApp",
    texto: "Guardá los escaneos siempre en la carpeta «MEDICIONES — soltar aquí» " +
           "de tu Escritorio: la app la creó para que no queden regados por la " +
           "computadora. En una historia nueva te guía paso a paso, la imagen " +
           "aparece acá abajo, la tocás y queda anexada. Si no la tenés, seguís " +
           "sin ella."
  },
  {
    destino: ["#hc-nueva-consulta", "#hc-invitacion"],
    pestana: "panel-historia",
    titulo: "La consulta",
    texto: "Motivo, signos vitales, examen, evolución y plan. El IMC y la TAM se " +
           "calculan solos, y cada visita queda comparable con las anteriores."
  },
  {
    destino: [".ficha-acciones", "#hc-invitacion"],
    pestana: "panel-historia",
    titulo: "De acá salen el récipe y el informe",
    texto: "Con la historia abierta, «Nuevo récipe para este paciente» y «Nuevo " +
           "informe» arrancan con ese paciente puesto: no lo escribís de nuevo."
  },
  {
    destino: ["#panel-nuevo .columna-previa"],
    pestana: "panel-nuevo",
    titulo: "El récipe",
    texto: "El paciente ya viene puesto —la banda de arriba lo dice y lo podés " +
           "cambiar—. La app te sugiere la dosis de siempre, acá ves la hoja tal " +
           "cual sale impresa y «Guardar e imprimir» hace todo el resto."
  },
  {
    destino: ["#tab-historial"],
    titulo: "Récipes emitidos",
    texto: "Todo lo emitido queda acá para reimprimir o anular."
  },
  {
    destino: ["#tab-config"],
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
  focoPrevio: null,
  pestanaPrevia: null  // dónde estaba el médico antes de empezar
};

function tutorialAbierto() { return tuto.abierto; }

/* ---------- Colocación ---------- */

/** El elemento del paso actual, o `null` si el globo va centrado. */
function destinoTutorial() {
  if (!tuto.abierto || tuto.final) return null;
  const paso = PASOS_TUTORIAL[tuto.paso];
  if (!paso || !paso.destino) return null;

  const selectores = Array.isArray(paso.destino) ? paso.destino : [paso.destino];
  for (let i = 0; i < selectores.length; i++) {
    const nodo = document.querySelector(selectores[i]);
    // offsetParent nulo = está oculto; se prueba el siguiente de la lista y,
    // si no queda ninguno, el globo va centrado: mejor eso que un recuadro
    // sobre la nada.
    if (nodo && nodo.offsetParent !== null) return nodo;
  }
  return null;
}

/** Lleva la pantalla a la pestaña que ese paso necesita mostrar. */
function pestanaDelPaso() {
  if (!tuto.abierto || tuto.final || tuto.cerrando) return;
  const paso = PASOS_TUTORIAL[tuto.paso];
  if (!paso || !paso.pestana) return;
  if (pestanaActiva === paso.pestana) return;
  irAPestana(paso.pestana);
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
  // Antes de medir nada: el elemento del paso puede vivir en otra pestaña.
  pestanaDelPaso();

  nTuto.cuerpo.hidden = tuto.cerrando;
  nTuto.confirma.hidden = !tuto.cerrando;

  if (!tuto.cerrando) {
    if (tuto.final) {
      nTuto.paso.hidden = true;
      nTuto.titulo.textContent = "¡Listo!";
      nTuto.texto.textContent = "Buscá a tu primer paciente y abrile la historia.";
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
  tuto.pestanaPrevia = pestanaActiva;

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

  // El recorrido cambió de pestaña; el médico vuelve a la suya.
  if (tuto.pestanaPrevia && tuto.pestanaPrevia !== pestanaActiva) {
    irAPestana(tuto.pestanaPrevia);
  }
  tuto.pestanaPrevia = null;

  // Saltarlo cuenta como haberlo visto: si no, volvería a aparecer en cada
  // arranque y el médico tendría que saltarlo para siempre.
  marcarTutorialVisto();

  const volver = tuto.focoPrevio && document.contains(tuto.focoPrevio) &&
                 tuto.focoPrevio.offsetParent !== null
    ? tuto.focoPrevio
    : null;
  tuto.focoPrevio = null;
  if (volver && volver.focus) volver.focus();
  else enfocarPestanaActiva();
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

/**
 * El botón de Configuración › Ayuda. No fuerza ninguna pestaña: el primer
 * paso ya lleva a la Historia clínica, y al cerrarse el recorrido devuelve al
 * médico a Configuración, que es donde lo pidió.
 */
function relanzarTutorial() {
  // Un turno después, para que el clic termine antes de medir el globo.
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

/* ============================================================
   20. HISTORIA CLÍNICA (dec. 3 a 17)

   La pantalla que el médico usa cuando el paciente está sentado enfrente:
   ficha y antecedentes arriba (se llenan una vez), consultas en el medio (lo
   que cambia en cada visita), anexos y evolución abajo.

   Todo sale del backend local, con el mismo contrato que el resto de la app:
   JSON, errores `{"error": "qué hacer"}`, rutas relativas. Nada de esto
   inventa datos: si una sección no tiene qué mostrar, lo dice con palabras.
   ============================================================ */

/**
 * Los siete numeradores del cuestionario de alimentación con su denominador
 * impreso (Parte A §2.4 del análisis: `__/3 comidas al día`, `__/7 frutas y
 * verduras`, …). Son los mismos que `DENOMINADORES_ALIMENTACION` de
 * basedatos.py; están fijos acá porque la API no los publica todavía. Si algún
 * día `GET /api/pacientes/<id>/historia` devuelve `denominadores`, la pantalla
 * los usa sin tocar este archivo: `pintarDenominadores()` los pisa.
 */
const DENOMINADORES_ALIMENTACION = {
  alim_comidas_dia: 3,
  alim_frutas_verduras: 7,
  alim_pollo: 7,
  alim_pescado: 7,
  alim_carnes_rojas: 7,
  alim_carbohidratos: 7,
  alim_litros_agua: 2
};

/** Las métricas del gráfico de evolución, en el orden en que se muestran. */
const METRICAS_EVOLUCION = [
  { clave: "peso",           titulo: "Peso",           unidad: " kg" },
  { clave: "imc",            titulo: "IMC",            unidad: "" },
  { clave: "grasa_pct",      titulo: "% de grasa",     unidad: " %" },
  { clave: "musculo_kg",     titulo: "Músculo",        unidad: " kg" },
  { clave: "grasa_visceral", titulo: "Grasa visceral", unidad: "" }
];

/** Nombre legible de cada tipo de anexo (dec. 11). */
const TIPOS_ANEXO = {
  medicion: "Medición de composición corporal",
  laboratorio: "Laboratorio",
  imagen: "Estudio de imagen",
  otro: "Otro"
};

const hc = {
  pacienteId: null,
  paciente: null,
  historia: null,
  consultas: [],
  anexos: [],
  mediciones: [],
  esNueva: false,        // el paciente todavía no tiene historia (dec. 15)
  guiaSaltada: false,    // ya tocó «Ahora no»
  pidiendo: 0,           // número de pedido, para descartar respuestas viejas
  editando: null,        // id de la consulta que se está editando (PUT)
  urlArchivo: null       // blob: de la previa del archivo elegido de una carpeta
};

const bandeja = {
  items: [],
  estado: "",            // texto que se muestra sobre la grilla
  error: false,
  pidiendo: 0,
  cargada: false
};

const nHc = {
  panel:        $("#panel-historia"),
  columna:      $("#columna-historia"),
  buscar:       $("#hc-buscar"),
  listaBuscar:  $("#lista-hc-buscar"),
  cabecera:     $("#hc-cabecera"),
  codigo:       $("#hc-codigo"),
  nombre:       $("#hc-nombre"),
  linea:        $("#hc-linea"),
  alergias:     $("#hc-alergias"),
  imprimir:     $("#hc-imprimir"),
  otro:         $("#hc-otro"),
  error:        $("#hc-error"),
  aviso:        $("#hc-aviso"),
  invitacion:   $("#hc-invitacion"),
  crearNuevo:   $("#hc-crear-nuevo"),
  contenido:    $("#hc-contenido"),

  nuevoRecipe:  $("#hc-nuevo-recipe"),
  irInforme:    $("#hc-ir-informe"),

  pdf:          $("#hc-pdf"),
  pdfIframe:    $("#hc-pdf-iframe"),
  pdfCerrar:    $("#hc-pdf-cerrar"),

  guia:         $("#hc-guia"),
  guiaSaltar:   $("#hc-guia-saltar"),

  fichaEstado:  $("#hc-ficha-estado"),
  fichaError:   $("#hc-ficha-error"),
  guardarFicha: $("#hc-guardar-ficha"),

  nuevaConsulta: $("#hc-nueva-consulta"),
  form:          $("#hc-form-consulta"),
  formTitulo:    $("#hc-form-titulo"),
  cFecha:        $("#hc-c-fecha"),
  cMotivo:       $("#hc-c-motivo"),
  cTas:          $("#hc-c-tas"),
  cTad:          $("#hc-c-tad"),
  cFc:           $("#hc-c-fc"),
  cFr:           $("#hc-c-fr"),
  cTemp:         $("#hc-c-temp"),
  cSpo2:         $("#hc-c-spo2"),
  cPeso:         $("#hc-c-peso"),
  cTalla:        $("#hc-c-talla"),
  cImc:          $("#hc-c-imc"),
  cTam:          $("#hc-c-tam"),
  cPistas:       $("#hc-c-pistas"),
  cExamen:       $("#hc-c-examen"),
  cEvolucion:    $("#hc-c-evolucion"),
  cDiagnostico:  $("#hc-c-diagnostico"),
  cPlan:         $("#hc-c-plan"),
  cError:        $("#hc-c-error"),
  cGuardar:      $("#hc-c-guardar"),
  cCancelar:     $("#hc-c-cancelar"),
  listaConsultas: $("#hc-lista-consultas"),
  consultasVacio: $("#hc-consultas-vacio"),

  grillaAnexos:  $("#hc-grilla-anexos"),
  anexosVacio:   $("#hc-anexos-vacio"),
  archivo:       $("#hc-archivo"),

  graficos:      $("#hc-graficos"),
  evolucionVacio: $("#hc-evolucion-vacio")
};

/* Alta de un paciente nuevo desde la Historia (dec. 18). */
const nAlta = {
  caja:      $("#hc-alta"),
  nombre:    $("#hc-alta-nombre"),
  cedula:    $("#hc-alta-cedula"),
  edad:      $("#hc-alta-edad"),
  nacimiento: $("#hc-alta-nacimiento"),
  sexo:      $("#hc-alta-sexo"),
  telefono:  $("#hc-alta-telefono"),
  error:     $("#hc-alta-error"),
  crear:     $("#hc-alta-crear"),
  cancelar:  $("#hc-alta-cancelar")
};

const alta = { enviando: false };

const nAnexo = {
  caja:       $("#modal-anexo"),
  fondo:      $("#modal-anexo-fondo"),
  contenido:  $("#modal-anexo-caja"),
  sub:        $("#modal-anexo-sub"),
  previa:     $("#modal-anexo-previa"),
  previaVacia: $("#modal-anexo-previa-vacia"),
  fecha:      $("#modal-anexo-fecha"),
  avisoFecha: $("#modal-anexo-aviso-fecha"),
  tipo:       $("#modal-anexo-tipo"),
  consulta:   $("#modal-anexo-consulta"),
  nota:       $("#modal-anexo-nota"),
  valores:    $("#modal-anexo-valores"),
  error:      $("#modal-anexo-error"),
  cancelar:   $("#modal-anexo-cancelar"),
  aceptar:    $("#modal-anexo-aceptar")
};

const anexo = { origen: null, focoPrevio: null, enviando: false };

const nVisor = {
  caja:      $("#visor"),
  titulo:    $("#visor-titulo"),
  lienzo:    $("#visor-lienzo"),
  img:       $("#visor-img"),
  alejar:    $("#visor-alejar"),
  acercar:   $("#visor-acercar"),
  ajustar:   $("#visor-ajustar"),
  windows:   $("#visor-windows"),
  cerrar:    $("#visor-cerrar"),
  anterior:  $("#visor-anterior"),
  siguiente: $("#visor-siguiente"),
  pie:       $("#visor-pie-texto")
};

const visor = { indice: -1, escala: 1, focoPrevio: null };

/* ---------- Utilidades chicas ---------- */

function hoyISO() {
  const d = new Date();
  const mes = String(d.getMonth() + 1).padStart(2, "0");
  const dia = String(d.getDate()).padStart(2, "0");
  return d.getFullYear() + "-" + mes + "-" + dia;
}

/** Solo la parte `AAAA-MM-DD` de una fecha que puede traer hora. */
function soloFecha(valor) {
  const texto = limpio(valor);
  const partes = /^(\d{4}-\d{2}-\d{2})/.exec(texto);
  return partes ? partes[1] : texto;
}

/** Texto → número, aceptando la coma decimal que usa el médico. */
function aNumero(valor) {
  const texto = limpio(valor).replace(",", ".");
  if (texto === "") return null;
  const n = Number(texto);
  return Number.isFinite(n) ? n : null;
}

function aEntero(valor) {
  const n = aNumero(valor);
  return n === null ? null : Math.round(n);
}

/** Número → texto con coma decimal y un decimal como mucho. */
function numeroLegible(valor, decimales) {
  if (valor === null || valor === undefined || valor === "") return "";
  const n = Number(valor);
  if (!Number.isFinite(n)) return "";
  const cuantos = decimales === undefined ? 1 : decimales;
  const factor = Math.pow(10, cuantos);
  return String(Math.round(n * factor) / factor).replace(".", ",");
}

/**
 * La talla como la escribe el médico: `1,68` o `168`. Se guarda en metros,
 * que es lo que dice la columna `talla` de signos_vitales.
 */
function tallaEnMetros(valor) {
  const n = aNumero(valor);
  if (n === null) return null;
  return n > 3 ? n / 100 : n;
}

function errorHistoria(texto) {
  nHc.error.textContent = texto;
  nHc.error.hidden = false;
  nHc.aviso.hidden = true;
}

function avisoHistoria(texto) {
  nHc.aviso.textContent = texto;
  nHc.aviso.hidden = false;
  nHc.error.hidden = true;
}

function limpiarAvisosHistoria() {
  nHc.error.hidden = true;
  nHc.aviso.hidden = true;
}

/* ---------- Alta de un paciente nuevo (dec. 18) ----------
   La historia es la puerta de entrada: si el paciente no está, se crea acá,
   sin emitir ningún récipe. El backend (POST /api/pacientes) le asigna el
   código de por vida y le arma la carpeta, y nunca duplica: si ya existía
   alguien con esa cédula —o con ese mismo nombre— devuelve ESE paciente con
   `ya_existia`, y entonces lo que se abre es la historia que ya tenía. */

function errorAlta(texto, campo) {
  nAlta.error.textContent = texto;
  nAlta.error.hidden = false;
  if (campo && campo.focus) campo.focus();
}

function altaAbierta() { return !nAlta.caja.hidden; }

/** Abre la tarjeta con el nombre que el médico venía escribiendo. */
function abrirAltaPaciente(nombre) {
  nAlta.error.hidden = true;
  nAlta.nombre.value = limpio(nombre);
  nAlta.cedula.value = "";
  nAlta.edad.value = "";
  nAlta.nacimiento.value = "";
  nAlta.sexo.value = "";
  nAlta.telefono.value = "";

  nAlta.caja.hidden = false;
  nAlta.caja.scrollIntoView({ block: "nearest", behavior: "smooth" });
  // Con el nombre ya puesto, lo siguiente que va a escribir es la cédula.
  if (limpio(nAlta.nombre.value)) nAlta.cedula.focus();
  else nAlta.nombre.focus();
}

function cerrarAltaPaciente(callado) {
  if (nAlta.caja.hidden) return;
  nAlta.caja.hidden = true;
  nAlta.error.hidden = true;
  if (!callado) nHc.buscar.focus();
}

/** La edad que se desprende de una fecha de nacimiento (años cumplidos). */
function edadDesdeNacimiento(iso) {
  const texto = soloFecha(iso);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(texto)) return null;
  const partes = texto.split("-").map(Number);
  const hoy = new Date();
  let anios = hoy.getFullYear() - partes[0];
  const mes = hoy.getMonth() + 1 - partes[1];
  if (mes < 0 || (mes === 0 && hoy.getDate() < partes[2])) anios--;
  return anios >= 0 && anios <= 130 ? anios : null;
}

async function crearPacienteDesdeHistoria() {
  if (alta.enviando) return;

  const nombre = limpio(nAlta.nombre.value);
  if (nombre === "") {
    // El mismo texto que contesta el backend si el pedido llega igual.
    errorAlta("Escribí el nombre del paciente para darlo de alta. Es lo único " +
              "obligatorio; la cédula, la edad y el teléfono se pueden completar " +
              "después.", nAlta.nombre);
    return;
  }

  const edad = aEntero(nAlta.edad.value);
  if (edad !== null && (edad < 0 || edad > 130)) {
    errorAlta("La edad va de 0 a 130 años.", nAlta.edad);
    return;
  }

  const cuerpo = {
    nombre: nombre,
    cedula: limpio(nAlta.cedula.value),
    edad: edad,
    fecha_nacimiento: limpio(nAlta.nacimiento.value),
    sexo: limpio(nAlta.sexo.value),
    telefono: limpio(nAlta.telefono.value)
  };

  alta.enviando = true;
  nAlta.error.hidden = true;
  nAlta.crear.disabled = true;
  nAlta.crear.textContent = "Creando…";

  try {
    const respuesta = await fetch("api/pacientes", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(cuerpo)
    });
    if (!respuesta.ok) {
      throw new Error(await mensajeDeError(respuesta,
        "No se pudo crear el paciente. Volvé a intentar."));
    }
    const datos = await cuerpoJson(respuesta);
    const paciente = datos.paciente || {};
    const id = paciente.id;
    if (id === null || id === undefined) {
      throw new Error("El paciente se creó, pero no pude abrir su historia. " +
                      "Buscalo por su nombre acá arriba.");
    }

    const codigo = limpio(datos.codigo) || limpio(paciente.codigo);
    const comoQuedo = limpio(paciente.nombre) || nombre;

    cerrarAltaPaciente(true);
    nHc.buscar.value = comoQuedo;
    hc.guiaSaltada = false;
    recipeSueltoDe = null;            // el récipe de este paciente sí se ofrece
    await cargarHistoria(id);

    // Después de cargar, que limpia los avisos. Y sin pisar un error de carga.
    if (!nHc.error.hidden) return;
    if (datos.ya_existia === true) {
      avisoHistoria("Este paciente ya estaba registrado" +
                    (codigo ? " como " + codigo : "") + ": se abrió su historia y " +
                    "no se creó otro. Si no es el mismo, cambiale el nombre o la cédula.");
    } else {
      avisoHistoria("Paciente creado" + (codigo ? ": " + codigo : "") +
                    ". Su historia está lista.");
    }
  } catch (err) {
    errorAlta(motivoLegible(err, "No se pudo crear el paciente. Volvé a intentar."));
  } finally {
    alta.enviando = false;
    nAlta.crear.disabled = false;
    nAlta.crear.textContent = "Crear paciente y abrir su historia";
  }
}

/* ---------- Carga de la historia ---------- */

async function cargarHistoria(pacienteId) {
  const mio = ++hc.pidiendo;
  hc.pacienteId = pacienteId;
  // Otro paciente, otra historia: el «no» que dijo para el anterior no cuenta.
  if (recipeSueltoDe !== pacienteId) recipeSueltoDe = null;
  limpiarAvisosHistoria();
  cerrarAltaPaciente(true);
  nHc.invitacion.hidden = true;
  nHc.contenido.hidden = true;
  nHc.cabecera.hidden = true;
  nHc.alergias.hidden = true;
  cerrarPdfHistoria();
  prepararInformes();

  try {
    const datos = await pedirCuerpo("api/pacientes/" + encodeURIComponent(pacienteId) + "/historia", {});
    if (mio !== hc.pidiendo) return;

    hc.paciente   = datos.paciente || {};
    hc.historia   = datos.historia || null;
    hc.consultas  = Array.isArray(datos.consultas) ? datos.consultas : [];
    hc.anexos     = Array.isArray(datos.anexos) ? datos.anexos : [];
    hc.mediciones = Array.isArray(datos.mediciones) ? datos.mediciones : [];
    hc.esNueva    = !datos.historia;
    hc.editando   = null;

    if (datos.denominadores) pintarDenominadores(datos.denominadores);

    pintarCabecera();
    pintarFicha();
    pintarConsultas();
    pintarAnexos();
    sincronizarInformes();
    nHc.form.hidden = true;
    nHc.contenido.hidden = false;
    nHc.guia.hidden = !(hc.esNueva && !hc.guiaSaltada);

    // La bandeja se pide sola cuando hay dónde mostrarla: en la guía de la
    // historia nueva y en la sección Anexos, que están las dos a la vista.
    cargarBandeja();
    cargarEvolucion();
  } catch (err) {
    if (mio !== hc.pidiendo) return;
    errorHistoria(motivoLegible(err,
      "No se pudo leer la historia. Cerrá la app y volvé a abrirla."));
    nHc.invitacion.hidden = false;
  }
}

function pintarDenominadores(denominadores) {
  Object.keys(denominadores || {}).forEach((campo) => {
    const n = denominadores[campo];
    if (!Number.isFinite(Number(n))) return;
    DENOMINADORES_ALIMENTACION[campo] = Number(n);
    const marca = $('[data-denominador-de="' + campo + '"]', nHc.panel);
    if (marca) marca.textContent = "/" + n;
  });
}

function pintarCabecera() {
  const p = hc.paciente || {};
  nHc.codigo.textContent = limpio(p.codigo) || rellenoCodigo();

  nHc.nombre.textContent = limpio(p.nombre) || "(sin nombre)";

  const partes = [];
  if (limpio(p.cedula)) partes.push("C.I. " + p.cedula);
  if (p.edad !== null && p.edad !== undefined && p.edad !== "") partes.push(p.edad + " años");
  if (limpio(p.sexo)) partes.push(p.sexo);
  if (limpio(p.telefono)) partes.push(p.telefono);
  nHc.linea.textContent = partes.join(" · ");

  nHc.cabecera.hidden = false;

  const alergias = limpio((hc.historia || {}).alergias);
  if (alergias) {
    nHc.alergias.textContent = "Alergias: " + alergias;
    nHc.alergias.hidden = false;
  } else {
    nHc.alergias.hidden = true;
  }
}

/* ---------- Ficha y antecedentes ---------- */

/**
 * Lo que se muestra en la ficha sale de la historia y, en su defecto, del
 * paciente: estado civil y ocupación pueden vivir en cualquiera de los dos
 * según cómo lo devuelva el backend, y lo que manda es la historia.
 */
function fuenteFicha() {
  return Object.assign({}, hc.paciente || {}, hc.historia || {});
}

function pintarFicha() {
  const datos = fuenteFicha();

  Array.prototype.forEach.call(nHc.panel.querySelectorAll("[data-historia]"), (campo) => {
    const valor = datos[campo.dataset.historia];
    campo.value = valor === null || valor === undefined ? "" : String(valor);
  });

  Array.prototype.forEach.call(nHc.panel.querySelectorAll("[data-alimentacion]"), (campo) => {
    const valor = datos[campo.dataset.alimentacion];
    campo.value = valor === null || valor === undefined || valor === "" ? "" : String(valor);
  });

  nHc.fichaError.hidden = true;
  nHc.fichaEstado.hidden = true;
}

function leerFicha() {
  const cuerpo = {};

  Array.prototype.forEach.call(nHc.panel.querySelectorAll("[data-historia]"), (campo) => {
    cuerpo[campo.dataset.historia] = limpio(campo.value);
  });

  Array.prototype.forEach.call(nHc.panel.querySelectorAll("[data-alimentacion]"), (campo) => {
    const nombre = campo.dataset.alimentacion;
    const texto = limpio(campo.value);
    if (texto === "") { cuerpo[nombre] = null; return; }
    const n = aEntero(texto);
    // El denominador impreso es la referencia del papel, NO un tope: quien
    // toma 3 litros sobre un «/2» escribe 3, y rechazárselo sería corregirle
    // la realidad al médico. El backend acepta 0 a 99; la pantalla también.
    if (n === null || n < 0 || n > 99) {
      const etiqueta = $('label[for="' + campo.id + '"]', nHc.panel);
      const comoSeLlama = etiqueta ? etiqueta.textContent : nombre;
      throw new Error("En «" + comoSeLlama + "» poné un número entero de 0 a 99. " +
                      "El número chiquito de al lado es lo que dice el papel, no un límite.");
    }
    cuerpo[nombre] = n;
  });

  return cuerpo;
}

async function guardarFicha() {
  if (hc.pacienteId === null) return;

  let cuerpo;
  try {
    cuerpo = leerFicha();
  } catch (err) {
    nHc.fichaError.textContent = err.message;
    nHc.fichaError.hidden = false;
    return;
  }

  nHc.fichaError.hidden = true;
  nHc.guardarFicha.disabled = true;
  nHc.guardarFicha.textContent = "Guardando…";

  try {
    const respuesta = await fetch("api/pacientes/" + encodeURIComponent(hc.pacienteId) + "/historia", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(cuerpo)
    });
    if (!respuesta.ok) {
      throw new Error(await mensajeDeError(respuesta,
        "No se pudo guardar la ficha. Volvé a intentar."));
    }
    const datos = await cuerpoJson(respuesta);
    hc.historia = datos.historia || datos || cuerpo;
    hc.esNueva = false;
    nHc.guia.hidden = true;

    pintarCabecera();
    nHc.fichaEstado.textContent = "Guardado.";
    nHc.fichaEstado.hidden = false;
    avisoHistoria("Ficha y antecedentes guardados.");
  } catch (err) {
    nHc.fichaError.textContent = motivoLegible(err,
      "No se pudo guardar la ficha. Volvé a intentar.");
    nHc.fichaError.hidden = false;
  } finally {
    nHc.guardarFicha.disabled = false;
    nHc.guardarFicha.textContent = "Guardar ficha y antecedentes";
  }
}

/* ---------- Consultas ---------- */

/** Los signos vitales, vengan anidados o aplanados en la misma fila. */
function signosDe(consulta) {
  if (!consulta) return {};
  return consulta.signos_vitales || consulta.signos || consulta;
}

function resumenSignos(consulta) {
  const s = signosDe(consulta);
  const partes = [];
  if (s.ta_sistolica && s.ta_diastolica) {
    partes.push("TA " + s.ta_sistolica + "/" + s.ta_diastolica);
  }
  if (s.fc) partes.push("FC " + s.fc);
  if (s.peso) partes.push("Peso " + numeroLegible(s.peso) + " kg");
  if (s.imc) partes.push("IMC " + numeroLegible(s.imc));
  return partes.join(" · ");
}

function pintarConsultas() {
  nHc.listaConsultas.innerHTML = "";

  if (hc.consultas.length === 0) {
    nHc.consultasVacio.hidden = false;
    return;
  }
  nHc.consultasVacio.hidden = true;

  hc.consultas.forEach((c) => nHc.listaConsultas.appendChild(fichaConsulta(c)));
}

function fichaConsulta(c) {
  const caja = document.createElement("details");
  caja.className = "consulta";

  const titulo = document.createElement("summary");

  const fecha = document.createElement("span");
  fecha.className = "consulta-fecha";
  fecha.textContent = fechaLegible(soloFecha(c.fecha));
  titulo.appendChild(fecha);

  const motivo = document.createElement("span");
  motivo.className = "consulta-motivo";
  motivo.textContent = limpio(c.motivo) || "(sin motivo)";
  titulo.appendChild(motivo);

  const signos = resumenSignos(c);
  if (signos) {
    const resumen = document.createElement("span");
    resumen.className = "consulta-signos";
    resumen.textContent = signos;
    titulo.appendChild(resumen);
  }

  caja.appendChild(titulo);

  const cuerpo = document.createElement("div");
  cuerpo.className = "consulta-cuerpo";

  const s = signosDe(c);
  const detalleSignos = [];
  if (s.ta_sistolica || s.ta_diastolica) {
    detalleSignos.push("TA " + (s.ta_sistolica || "—") + "/" + (s.ta_diastolica || "—") + " mmHg");
  }
  if (s.tam) detalleSignos.push("TAM " + numeroLegible(s.tam, 0));
  if (s.fc) detalleSignos.push("FC " + s.fc + " lpm");
  if (s.fr) detalleSignos.push("FR " + s.fr + " rpm");
  if (s.temperatura) detalleSignos.push("Temp " + numeroLegible(s.temperatura) + " °C");
  if (s.spo2) detalleSignos.push("SpO2 " + s.spo2 + " %");
  if (s.peso) detalleSignos.push("Peso " + numeroLegible(s.peso) + " kg");
  if (s.talla) detalleSignos.push("Talla " + numeroLegible(s.talla, 2) + " m");
  if (s.imc) detalleSignos.push("IMC " + numeroLegible(s.imc));

  if (detalleSignos.length) {
    cuerpo.appendChild(campoConsulta("Signos vitales", detalleSignos.join(" · ")));
  }
  if (limpio(c.examen_fisico)) cuerpo.appendChild(campoConsulta("Examen físico", c.examen_fisico));
  if (limpio(c.evolucion))     cuerpo.appendChild(campoConsulta("Evolución", c.evolucion));
  if (limpio(c.diagnostico))   cuerpo.appendChild(campoConsulta("Diagnóstico", c.diagnostico));
  if (limpio(c.plan))          cuerpo.appendChild(campoConsulta("Plan", c.plan));

  if (cuerpo.children.length === 0) {
    cuerpo.appendChild(campoConsulta("Sin datos",
      "Esta consulta se guardó sin signos vitales ni notas."));
  }

  // La consulta del día se corrige en el lugar; las de otros días quedan como
  // quedaron (el backend solo acepta la edición del día, dec. 3).
  if (soloFecha(c.fecha) === hoyISO()) {
    const acciones = document.createElement("div");
    acciones.className = "consulta-acciones";
    const editar = document.createElement("button");
    editar.type = "button";
    editar.className = "boton-secundario";
    editar.textContent = "Editar esta consulta";
    editar.addEventListener("click", () => abrirFormConsulta(c));
    acciones.appendChild(editar);
    cuerpo.appendChild(acciones);
  }

  caja.appendChild(cuerpo);
  return caja;
}

function campoConsulta(rotulo, texto) {
  const p = document.createElement("p");
  p.className = "consulta-campo";
  const fuerte = document.createElement("strong");
  fuerte.textContent = rotulo;
  const span = document.createElement("span");
  span.textContent = texto;
  p.appendChild(fuerte);
  p.appendChild(span);
  return p;
}

/** Abre el formulario. Sin argumento es una consulta nueva; con uno, la edita. */
function abrirFormConsulta(consulta) {
  hc.editando = consulta ? consulta.id : null;
  nHc.cError.hidden = true;

  const s = signosDe(consulta);
  const anterior = hc.consultas.length ? signosDe(hc.consultas[0]) : {};

  nHc.formTitulo.textContent = consulta
    ? "Editar la consulta del " + fechaLegible(soloFecha(consulta.fecha))
    : "Consulta nueva";

  nHc.cFecha.value       = consulta ? soloFecha(consulta.fecha) : hoyISO();
  nHc.cMotivo.value      = consulta ? limpio(consulta.motivo) : "";
  nHc.cTas.value         = consulta && s.ta_sistolica ? String(s.ta_sistolica) : "";
  nHc.cTad.value         = consulta && s.ta_diastolica ? String(s.ta_diastolica) : "";
  nHc.cFc.value          = consulta && s.fc ? String(s.fc) : "";
  nHc.cFr.value          = consulta && s.fr ? String(s.fr) : "";
  nHc.cTemp.value        = consulta && s.temperatura ? numeroLegible(s.temperatura) : "";
  nHc.cSpo2.value        = consulta && s.spo2 ? String(s.spo2) : "";
  nHc.cPeso.value        = consulta && s.peso ? numeroLegible(s.peso) : "";
  nHc.cExamen.value      = consulta ? limpio(consulta.examen_fisico) : "";
  nHc.cEvolucion.value   = consulta ? limpio(consulta.evolucion) : "";
  nHc.cDiagnostico.value = consulta ? limpio(consulta.diagnostico) : "";
  nHc.cPlan.value        = consulta ? limpio(consulta.plan) : "";

  // La talla casi nunca cambia: se arrastra de la consulta anterior. El peso
  // NO se arrastra —es justo lo que se viene a medir— pero se dice cuál era.
  const talla = consulta ? s.talla : anterior.talla;
  nHc.cTalla.value = talla ? numeroLegible(talla, 2) : "";

  let pistas = "La talla podés escribirla 1,68 o 168: se guarda en metros. " +
               "El IMC y la TAM se calculan solos.";
  if (!consulta && anterior.peso) {
    pistas += " En la consulta anterior (" + fechaLegible(soloFecha(hc.consultas[0].fecha)) +
              ") pesaba " + numeroLegible(anterior.peso) + " kg.";
  }
  nHc.cPistas.textContent = pistas;

  calcularCalculados();
  nHc.form.hidden = false;
  nHc.cMotivo.focus();
  nHc.form.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function cerrarFormConsulta() {
  nHc.form.hidden = true;
  hc.editando = null;
  nHc.nuevaConsulta.focus();
}

/** IMC y TAM en vivo. Se muestran calculados; el backend guarda lo que valga. */
function calcularCalculados() {
  const peso = aNumero(nHc.cPeso.value);
  const talla = tallaEnMetros(nHc.cTalla.value);
  if (peso && talla && talla > 0) {
    nHc.cImc.textContent = numeroLegible(peso / (talla * talla));
    nHc.cImc.classList.remove("sin-valor");
  } else {
    nHc.cImc.textContent = "—";
    nHc.cImc.classList.add("sin-valor");
  }

  const sis = aEntero(nHc.cTas.value);
  const dia = aEntero(nHc.cTad.value);
  if (sis && dia) {
    nHc.cTam.textContent = numeroLegible((sis + 2 * dia) / 3, 0);
    nHc.cTam.classList.remove("sin-valor");
  } else {
    nHc.cTam.textContent = "—";
    nHc.cTam.classList.add("sin-valor");
  }
}

async function guardarConsulta() {
  if (hc.pacienteId === null) return;

  const fecha = limpio(nHc.cFecha.value);
  if (!fecha) {
    nHc.cError.textContent = "Poné la fecha de la consulta: sin fecha no se puede ordenar el historial.";
    nHc.cError.hidden = false;
    nHc.cFecha.focus();
    return;
  }

  const cuerpo = {
    fecha: fecha,
    motivo: limpio(nHc.cMotivo.value),
    examen_fisico: limpio(nHc.cExamen.value),
    evolucion: limpio(nHc.cEvolucion.value),
    diagnostico: limpio(nHc.cDiagnostico.value),
    plan: limpio(nHc.cPlan.value),
    signos: {
      ta_sistolica: aEntero(nHc.cTas.value),
      ta_diastolica: aEntero(nHc.cTad.value),
      fc: aEntero(nHc.cFc.value),
      fr: aEntero(nHc.cFr.value),
      temperatura: aNumero(nHc.cTemp.value),
      spo2: aEntero(nHc.cSpo2.value),
      peso: aNumero(nHc.cPeso.value),
      talla: tallaEnMetros(nHc.cTalla.value)
    }
  };

  const editando = hc.editando;
  nHc.cError.hidden = true;
  nHc.cGuardar.disabled = true;
  nHc.cGuardar.textContent = "Guardando…";

  try {
    const url = editando
      ? "api/consultas/" + encodeURIComponent(editando)
      : "api/pacientes/" + encodeURIComponent(hc.pacienteId) + "/consultas";
    const respuesta = await fetch(url, {
      method: editando ? "PUT" : "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(cuerpo)
    });
    if (!respuesta.ok) {
      throw new Error(await mensajeDeError(respuesta,
        "No se pudo guardar la consulta. Volvé a intentar."));
    }
    await cuerpoJson(respuesta);

    nHc.form.hidden = true;
    hc.editando = null;
    await cargarHistoria(hc.pacienteId);
    avisoHistoria(editando
      ? "Consulta actualizada."
      : "Consulta del " + fechaLegible(fecha) + " guardada.");
  } catch (err) {
    nHc.cError.textContent = motivoLegible(err,
      "No se pudo guardar la consulta. Volvé a intentar.");
    nHc.cError.hidden = false;
  } finally {
    nHc.cGuardar.disabled = false;
    nHc.cGuardar.textContent = "Guardar consulta";
  }
}

/* ---------- Bandeja de imágenes recientes (dec. 11) ---------- */

function cajasDeBandeja() {
  return Array.prototype.slice.call(nHc.panel.querySelectorAll("[data-bandeja]"));
}

async function cargarBandeja() {
  const mio = ++bandeja.pidiendo;
  bandeja.estado = "Buscando imágenes recientes…";
  bandeja.error = false;
  pintarBandejas();

  try {
    const datos = await pedirCuerpo("api/bandeja", {});
    if (mio !== bandeja.pidiendo) return;
    bandeja.items = Array.isArray(datos.imagenes) ? datos.imagenes : [];
    bandeja.cargada = true;
    bandeja.error = false;
    bandeja.estado = bandeja.items.length
      ? "Tocá la imagen que le corresponde a este paciente."
      : "No hay imágenes nuevas en Descargas ni en el Escritorio. Descargá la " +
        "imagen desde WhatsApp y tocá «Actualizar».";
    pintarBandejas();
  } catch (err) {
    if (mio !== bandeja.pidiendo) return;
    bandeja.items = [];
    bandeja.error = true;
    bandeja.estado = motivoLegible(err,
      "No se pudieron mirar las carpetas. Usá «Adjuntar desde una carpeta…».");
    pintarBandejas();
  }
}

function pintarBandejas() {
  cajasDeBandeja().forEach((caja) => {
    caja.innerHTML = "";

    const titulo = document.createElement("p");
    titulo.className = "bandeja-titulo";
    titulo.textContent = "Imágenes recientes en tu computadora";
    caja.appendChild(titulo);

    const estado = document.createElement("p");
    estado.className = "bandeja-estado" + (bandeja.error ? " con-error" : "");
    estado.setAttribute("role", "status");
    estado.textContent = bandeja.estado;
    caja.appendChild(estado);

    if (bandeja.items.length === 0) return;

    const grilla = document.createElement("div");
    grilla.className = "grilla-bandeja";
    bandeja.items.forEach((it) => grilla.appendChild(miniaturaBandeja(it)));
    caja.appendChild(grilla);
  });
}

function miniaturaBandeja(it) {
  const boton = document.createElement("button");
  boton.type = "button";
  boton.className = "mini-bandeja";

  const img = document.createElement("img");
  img.className = "mini-imagen";
  img.src = "api/bandeja/" + encodeURIComponent(it.token) + "/miniatura";
  img.alt = "Vista chica de " + (it.nombre || "la imagen");
  img.addEventListener("error", () => { img.hidden = true; });
  boton.appendChild(img);

  const fecha = document.createElement("span");
  fecha.className = "mini-fecha";
  fecha.textContent = fechaLegible(soloFecha(it.fecha_archivo));
  boton.appendChild(fecha);

  const carpeta = document.createElement("span");
  carpeta.className = "mini-carpeta";
  carpeta.textContent = (it.carpeta || "") + " · " + (it.nombre || "");
  carpeta.title = it.nombre || "";
  boton.appendChild(carpeta);

  boton.addEventListener("click", () => {
    abrirDialogoAnexo({
      token: it.token,
      nombre: it.nombre,
      fecha: soloFecha(it.fecha_archivo),
      url: "api/bandeja/" + encodeURIComponent(it.token) + "/miniatura",
      carpeta: it.carpeta
    });
  });

  return boton;
}

/* ---------- Diálogo de anexado ---------- */

function dialogoAnexoAbierto() { return !nAnexo.caja.hidden; }

function abrirDialogoAnexo(origen) {
  if (hc.pacienteId === null) return;

  anexo.origen = origen;
  anexo.focoPrevio = document.activeElement;
  anexo.enviando = false;

  nAnexo.sub.textContent = (origen.nombre || "Imagen") + " → " +
    limpio((hc.paciente || {}).nombre);

  if (origen.url) {
    nAnexo.previa.src = origen.url;
    nAnexo.previa.hidden = false;
    nAnexo.previaVacia.hidden = true;
  } else {
    nAnexo.previa.removeAttribute("src");
    nAnexo.previa.hidden = true;
    nAnexo.previaVacia.hidden = false;
  }

  nAnexo.fecha.value = origen.fecha || hoyISO();
  nAnexo.tipo.value = "medicion";
  nAnexo.nota.value = "";
  nAnexo.error.hidden = true;
  nAnexo.valores.open = false;
  Array.prototype.forEach.call(nAnexo.caja.querySelectorAll("[data-medicion]"),
    (campo) => { campo.value = ""; });

  // Las consultas del paciente, por si la imagen pertenece a una visita.
  nAnexo.consulta.innerHTML = "";
  const suelta = document.createElement("option");
  suelta.value = "";
  suelta.textContent = "Sin consulta — queda colgada del paciente";
  nAnexo.consulta.appendChild(suelta);
  hc.consultas.forEach((c) => {
    const op = document.createElement("option");
    op.value = String(c.id);
    op.textContent = fechaLegible(soloFecha(c.fecha)) + " · " + (limpio(c.motivo) || "sin motivo");
    nAnexo.consulta.appendChild(op);
  });

  nAnexo.caja.hidden = false;
  nAnexo.fecha.focus();
}

function cerrarDialogoAnexo() {
  if (anexo.enviando) return;
  nAnexo.caja.hidden = true;
  anexo.origen = null;
  soltarArchivoElegido();
  if (anexo.focoPrevio && anexo.focoPrevio.focus) anexo.focoPrevio.focus();
  anexo.focoPrevio = null;
}

function soltarArchivoElegido() {
  if (hc.urlArchivo) {
    URL.revokeObjectURL(hc.urlArchivo);
    hc.urlArchivo = null;
  }
  nHc.archivo.value = "";
}

/** Los cinco valores del gráfico, o null si el médico no cargó ninguno. */
function leerMedicion() {
  const medicion = {};
  let hayAlguno = false;
  Array.prototype.forEach.call(nAnexo.caja.querySelectorAll("[data-medicion]"), (campo) => {
    const n = aNumero(campo.value);
    if (n !== null) { medicion[campo.dataset.medicion] = n; hayAlguno = true; }
  });
  return hayAlguno ? medicion : null;
}

async function guardarAnexo() {
  const origen = anexo.origen;
  if (!origen || anexo.enviando || hc.pacienteId === null) return;

  const fecha = limpio(nAnexo.fecha.value);
  if (!fecha) {
    nAnexo.error.textContent = "Poné la fecha de la medición: es la que ordena la historia.";
    nAnexo.error.hidden = false;
    nAnexo.fecha.focus();
    return;
  }

  const medicion = leerMedicion();
  const consultaId = limpio(nAnexo.consulta.value);

  anexo.enviando = true;
  nAnexo.error.hidden = true;
  nAnexo.aceptar.disabled = true;
  nAnexo.aceptar.textContent = "Anexando…";

  const url = "api/pacientes/" + encodeURIComponent(hc.pacienteId) + "/anexos";

  try {
    let respuesta;
    if (origen.archivo) {
      // Subida desde una carpeta: multipart, con el archivo en «archivo».
      const formulario = new FormData();
      formulario.append("archivo", origen.archivo, origen.nombre || "imagen.jpg");
      formulario.append("fecha_medicion", fecha);
      formulario.append("tipo", nAnexo.tipo.value);
      formulario.append("nota", limpio(nAnexo.nota.value));
      if (consultaId) formulario.append("consulta_id", consultaId);
      if (medicion) {
        // Los dos formatos: el objeto entero como JSON y cada valor suelto,
        // para que el backend lo lea como le resulte más natural.
        formulario.append("medicion", JSON.stringify(medicion));
        Object.keys(medicion).forEach((k) => formulario.append(k, String(medicion[k])));
      }
      respuesta = await fetch(url, {
        method: "POST",
        headers: { "Accept": "application/json" },
        body: formulario
      });
    } else {
      const cuerpo = {
        token: origen.token,
        fecha_medicion: fecha,
        tipo: nAnexo.tipo.value,
        nota: limpio(nAnexo.nota.value)
      };
      if (consultaId) cuerpo.consulta_id = Number(consultaId);
      if (medicion) cuerpo.medicion = medicion;
      respuesta = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify(cuerpo)
      });
    }

    if (!respuesta.ok) {
      // El 409 de una imagen repetida ya viene explicado por el backend.
      throw new Error(await mensajeDeError(respuesta,
        "No se pudo anexar la imagen. Volvé a intentar."));
    }
    await cuerpoJson(respuesta);

    anexo.enviando = false;
    cerrarDialogoAnexo();
    // La guía de la historia nueva ya cumplió: la imagen está adentro. Al
    // volver a pintar, la pantalla arranca directo en la ficha.
    hc.guiaSaltada = true;
    await cargarHistoria(hc.pacienteId);
    avisoHistoria("Imagen anexada con fecha " + fechaLegible(fecha) +
                  ". El archivo original quedó donde estaba.");
  } catch (err) {
    anexo.enviando = false;
    nAnexo.error.textContent = motivoLegible(err,
      "No se pudo anexar la imagen. Volvé a intentar.");
    nAnexo.error.hidden = false;
  } finally {
    anexo.enviando = false;
    nAnexo.aceptar.disabled = false;
    nAnexo.aceptar.textContent = "Anexar a la historia";
  }
}

/* ---------- Anexos guardados ---------- */

function pintarAnexos() {
  nHc.grillaAnexos.innerHTML = "";

  if (hc.anexos.length === 0) {
    nHc.anexosVacio.hidden = false;
    return;
  }
  nHc.anexosVacio.hidden = true;

  hc.anexos.forEach((a, i) => nHc.grillaAnexos.appendChild(tarjetaAnexo(a, i)));
}

function tarjetaAnexo(a, indice) {
  const boton = document.createElement("button");
  boton.type = "button";
  boton.className = "tarjeta-anexo";

  const img = document.createElement("img");
  img.className = "anexo-imagen";
  img.src = "api/anexos/" + encodeURIComponent(a.id) + "/miniatura";
  img.alt = "Anexo del " + fechaLegible(soloFecha(a.fecha_medicion));
  img.addEventListener("error", () => { img.hidden = true; });
  boton.appendChild(img);

  const fecha = document.createElement("span");
  fecha.className = "anexo-fecha";
  fecha.textContent = fechaLegible(soloFecha(a.fecha_medicion));
  boton.appendChild(fecha);

  const tipo = document.createElement("span");
  tipo.className = "anexo-tipo";
  tipo.textContent = TIPOS_ANEXO[a.tipo] || a.tipo || "Anexo";
  boton.appendChild(tipo);

  if (limpio(a.nota)) {
    const nota = document.createElement("span");
    nota.className = "anexo-nota";
    nota.textContent = a.nota;
    boton.appendChild(nota);
  }

  boton.addEventListener("click", () => abrirVisor(indice));
  return boton;
}

/* ---------- Visor de anexos (lightbox propio) ---------- */

function visorAbierto() { return !nVisor.caja.hidden; }

function abrirVisor(indice) {
  const a = hc.anexos[indice];
  if (!a) return;

  visor.indice = indice;
  if (!visorAbierto()) visor.focoPrevio = document.activeElement;

  nVisor.titulo.textContent = "Anexo del " + fechaLegible(soloFecha(a.fecha_medicion)) +
    " · " + (TIPOS_ANEXO[a.tipo] || a.tipo || "");
  nVisor.img.src = "api/anexos/" + encodeURIComponent(a.id) + "/imagen";
  nVisor.img.alt = "Anexo del " + fechaLegible(soloFecha(a.fecha_medicion));
  nVisor.pie.textContent = (limpio(a.nota) ? a.nota + " · " : "") +
    "Imagen " + (indice + 1) + " de " + hc.anexos.length;

  nVisor.anterior.disabled = indice <= 0;
  nVisor.siguiente.disabled = indice >= hc.anexos.length - 1;

  nVisor.caja.hidden = false;
  ajustarVisor();
  nVisor.cerrar.focus();
}

function cerrarVisor() {
  nVisor.caja.hidden = true;
  nVisor.img.removeAttribute("src");
  visor.indice = -1;
  if (visor.focoPrevio && visor.focoPrevio.focus) visor.focoPrevio.focus();
  visor.focoPrevio = null;
}

function ajustarVisor() {
  visor.escala = 1;
  nVisor.img.style.maxWidth = "100%";
  nVisor.img.style.width = "auto";
}

function zoomVisor(factor) {
  visor.escala = Math.min(6, Math.max(0.5, visor.escala * factor));
  nVisor.img.style.maxWidth = "none";
  nVisor.img.style.width = Math.round(visor.escala * 100) + "%";
}

function moverVisor(salto) {
  const siguiente = visor.indice + salto;
  if (siguiente < 0 || siguiente >= hc.anexos.length) return;
  abrirVisor(siguiente);
}

/**
 * «Abrir con el visor de Windows»: para imprimir la imagen sola o agrandarla
 * más allá de lo que da la pantalla.
 *
 * Primero se le pide al backend que la abra con el programa de siempre. Si esa
 * ruta todavía no existe, se cae a abrir la carpeta de datos —que sí existe
 * desde la 1.0— y se dice exactamente en qué archivo está: el médico llega al
 * archivo igual, sin ventanas en blanco ni mensajes de error sin salida.
 */
async function abrirAnexoEnWindows() {
  const a = hc.anexos[visor.indice];
  if (!a) return;

  const donde = limpio(a.ruta_relativa) || limpio(a.nombre) ||
                "la carpeta del paciente, en anexos\\";

  const antes = nVisor.windows.textContent;
  nVisor.windows.disabled = true;
  nVisor.windows.textContent = "Abriendo…";
  try {
    const respuesta = await fetch("api/anexos/" + encodeURIComponent(a.id) + "/abrir", {
      method: "POST",
      headers: { "Accept": "application/json" }
    });
    if (!respuesta.ok) throw new Error("todavía no existe ese botón");
    nVisor.pie.textContent = "Se abrió con el visor de Windows.";
  } catch (_) {
    try {
      const carpeta = await fetch("api/abrir-carpeta", {
        method: "POST",
        headers: { "Accept": "application/json" }
      });
      if (!carpeta.ok) throw new Error("tampoco se pudo abrir la carpeta");
      nVisor.pie.textContent = "Te abrí la carpeta de datos: la imagen es " + donde + ".";
    } catch (__) {
      nVisor.pie.textContent = "No pude abrirla desde acá. Está guardada en la " +
        "carpeta de datos, en " + donde + ".";
    }
  } finally {
    nVisor.windows.disabled = false;
    nVisor.windows.textContent = antes;
  }
}

/* ---------- Evolución: gráficos SVG hechos a mano ---------- */

const SVG = "http://www.w3.org/2000/svg";

function svgEl(nombre, atributos) {
  const el = document.createElementNS(SVG, nombre);
  Object.keys(atributos || {}).forEach((k) => el.setAttribute(k, String(atributos[k])));
  return el;
}

async function cargarEvolucion() {
  const mio = hc.pidiendo;
  nHc.graficos.innerHTML = "";
  nHc.evolucionVacio.hidden = true;

  let series = {};
  try {
    const datos = await pedirCuerpo(
      "api/pacientes/" + encodeURIComponent(hc.pacienteId) + "/evolucion", {});
    if (mio !== hc.pidiendo) return;
    series = datos.series || {};
  } catch (err) {
    if (mio !== hc.pidiendo) return;
    nHc.evolucionVacio.textContent = motivoLegible(err,
      "No se pudo armar el gráfico. Los datos de las mediciones están guardados igual.");
    nHc.evolucionVacio.hidden = false;
    return;
  }

  const conAlgo = METRICAS_EVOLUCION.filter(
    (m) => Array.isArray(series[m.clave]) && series[m.clave].length > 0);

  if (conAlgo.length === 0) {
    nHc.evolucionVacio.textContent = "Todavía no hay suficientes mediciones para graficar. " +
      "Cargá peso, IMC, % de grasa, músculo o grasa visceral al anexar una imagen, " +
      "o tomá el peso en una consulta.";
    nHc.evolucionVacio.hidden = false;
    return;
  }

  conAlgo.forEach((m) => {
    nHc.graficos.appendChild(graficoDeSerie(m, series[m.clave]));
  });
}

/**
 * Un mini-gráfico de línea por métrica (small multiples). Sin librerías: es un
 * SVG armado a mano, con los valores de los extremos escritos y las fechas
 * abajo. Los puntos que vienen de una consulta salen huecos y los de una
 * medición anexada, llenos.
 */
function graficoDeSerie(metrica, puntosCrudos) {
  const figura = document.createElement("figure");
  figura.className = "grafico-tarjeta";

  const titulo = document.createElement("figcaption");
  titulo.className = "grafico-titulo";
  titulo.textContent = metrica.titulo;
  figura.appendChild(titulo);

  const puntos = (puntosCrudos || [])
    .map((p) => ({
      fecha: soloFecha(p.fecha),
      valor: Number(p.valor),
      deConsulta: limpio(p.fuente).toLowerCase() === "consulta"
    }))
    .filter((p) => Number.isFinite(p.valor))
    .sort((a, b) => (a.fecha < b.fecha ? -1 : a.fecha > b.fecha ? 1 : 0));

  if (puntos.length < 2) {
    const nota = document.createElement("p");
    nota.className = "grafico-vacio";
    nota.textContent = puntos.length === 1
      ? "Todavía no hay suficientes mediciones para graficar: hay una sola (" +
        numeroLegible(puntos[0].valor) + metrica.unidad + " el " +
        fechaLegible(puntos[0].fecha) + ")."
      : "Todavía no hay suficientes mediciones para graficar.";
    figura.appendChild(nota);
    return figura;
  }

  const ANCHO = 320, ALTO = 150;
  const IZQ = 34, DER = 34, ARRIBA = 30, ABAJO = 30;

  const valores = puntos.map((p) => p.valor);
  let minimo = Math.min.apply(null, valores);
  let maximo = Math.max.apply(null, valores);
  if (maximo === minimo) { minimo -= 1; maximo += 1; }

  // Eje x por tiempo real cuando las fechas se entienden; si no, por orden.
  const tiempos = puntos.map((p) => Date.parse(p.fecha));
  const tiempoSirve = tiempos.every((t) => Number.isFinite(t)) &&
                      tiempos[tiempos.length - 1] > tiempos[0];
  const t0 = tiempos[0];
  const t1 = tiempos[tiempos.length - 1];

  function x(i) {
    const proporcion = tiempoSirve
      ? (tiempos[i] - t0) / (t1 - t0)
      : (puntos.length === 1 ? 0 : i / (puntos.length - 1));
    return IZQ + proporcion * (ANCHO - IZQ - DER);
  }
  function y(valor) {
    const proporcion = (valor - minimo) / (maximo - minimo);
    return ALTO - ABAJO - proporcion * (ALTO - ARRIBA - ABAJO);
  }

  const svg = svgEl("svg", {
    class: "grafico-svg",
    viewBox: "0 0 " + ANCHO + " " + ALTO,
    role: "img",
    "aria-label": metrica.titulo + ": de " + numeroLegible(puntos[0].valor) +
      " el " + fechaLegible(puntos[0].fecha) + " a " +
      numeroLegible(puntos[puntos.length - 1].valor) + " el " +
      fechaLegible(puntos[puntos.length - 1].fecha)
  });

  // Piso del gráfico
  svg.appendChild(svgEl("line", {
    x1: 6, y1: ALTO - ABAJO + 8, x2: ANCHO - 6, y2: ALTO - ABAJO + 8,
    stroke: "#D1D5DB", "stroke-width": 1
  }));

  // La línea
  svg.appendChild(svgEl("polyline", {
    fill: "none",
    stroke: "#157F6F",
    "stroke-width": 2,
    "stroke-linejoin": "round",
    points: puntos.map((p, i) => x(i).toFixed(1) + "," + y(p.valor).toFixed(1)).join(" ")
  }));

  // Los puntos
  puntos.forEach((p, i) => {
    svg.appendChild(svgEl("circle", {
      cx: x(i).toFixed(1),
      cy: y(p.valor).toFixed(1),
      r: 4.5,
      fill: p.deConsulta ? "#FFFFFF" : "#157F6F",
      stroke: "#157F6F",
      "stroke-width": 2
    }));
  });

  // Valores de los extremos y fechas
  const extremos = [0, puntos.length - 1];
  extremos.forEach((i, cual) => {
    const p = puntos[i];
    // El halo blanco (`paint-order`) es para que el número se lea aunque la
    // línea le pase por debajo, que es lo normal en el punto final.
    const texto = svgEl("text", {
      x: Math.min(ANCHO - 4, Math.max(4, x(i))).toFixed(1),
      y: Math.max(12, y(p.valor) - 10).toFixed(1),
      "text-anchor": cual === 0 ? "start" : "end",
      "font-size": 15,
      "font-weight": 700,
      fill: "#1F2937",
      stroke: "#FFFFFF",
      "stroke-width": 4,
      "stroke-linejoin": "round",
      "paint-order": "stroke"
    });
    texto.textContent = numeroLegible(p.valor) + metrica.unidad;
    svg.appendChild(texto);

    const fecha = svgEl("text", {
      x: cual === 0 ? 4 : ANCHO - 4,
      y: ALTO - 8,
      "text-anchor": cual === 0 ? "start" : "end",
      "font-size": 13,
      fill: "#6B7280"
    });
    fecha.textContent = fechaLegible(p.fecha);
    svg.appendChild(fecha);
  });

  figura.appendChild(svg);

  const deConsulta = puntos.filter((p) => p.deConsulta).length;
  const cuantos = document.createElement("p");
  cuantos.className = "grafico-vacio";
  cuantos.textContent = deConsulta
    ? puntos.length + " valores · " + deConsulta + " de consultas (puntos huecos)."
    : puntos.length + " mediciones anexadas.";
  figura.appendChild(cuantos);

  return figura;
}

/* ------------------------------------------------------------
   Informes (dec. 10 y 12)

   Va en la misma pantalla de la historia, después de Anexos: cuando el médico
   llega acá ya tiene a la vista los antecedentes (que arman la frase inicial),
   la consulta del día (el motivo) y las imágenes que puede querer pegarle al
   final. El formulario NO es un modal —es largo y se escribe mirando la
   historia— y el informe se emite con un solo botón, igual que el récipe.
   ------------------------------------------------------------ */

/** Los dos tipos, con el nombre que ve el médico (Parte B §2). */
const TIPOS_INFORME = {
  clinico: "Informe médico",
  aseguradora: "Informe para la aseguradora"
};

/** El mismo tope que aplica el backend, para avisar antes de mandar. */
const MAX_ANEXOS_INFORME = 20;

const inf = {
  lista: [],            // los informes del paciente, como los devuelve la API
  cargada: false,       // ¿ya contestó la API para este paciente?
  pidiendo: 0,          // número de pedido, para descartar respuestas viejas
  abierto: false,       // ¿está abierto el formulario?
  pacienteId: null,     // de quién es el formulario abierto
  marcados: [],         // ids de los anexos tildados
  deshacerCuerpo: null, // texto anterior del cuerpo, para «Deshacer»
  deshacerTrat: null,   // ídem del tratamiento
  enviando: false,
  verId: null,          // informe que se está viendo en el marco del PDF
  anular: null,         // informe que se está anulando
  anulando: false,
  focoPrevio: null
};

const nInf = {
  seccion:     $("#hc-informes"),
  nuevo:       $("#hc-nuevo-informe"),
  exito:       $("#hc-inf-exito"),
  exitoVer:    $("#hc-inf-exito-ver"),
  exitoCerrar: $("#hc-inf-exito-cerrar"),
  errorLista:  $("#hc-inf-error-lista"),

  form:        $("#hc-form-informe"),
  titulo:      $("#hc-inf-titulo"),
  tipoClinico: $("#hc-inf-tipo-clinico"),
  tipoSeguro:  $("#hc-inf-tipo-aseguradora"),
  camposClinico:    $("#hc-inf-campos-clinico"),
  camposAseguradora: $("#hc-inf-campos-aseguradora"),

  motivo:      $("#hc-inf-motivo"),
  rehacer:     $("#hc-inf-rehacer"),
  cuerpo:      $("#hc-inf-cuerpo"),
  hintCuerpo:  $("#hc-inf-hint-cuerpo"),
  avisoCuerpo: $("#hc-inf-aviso-cuerpo"),
  avisoCuerpoTexto: $("#hc-inf-aviso-cuerpo-texto"),
  deshacerCuerpo:   $("#hc-inf-deshacer-cuerpo"),
  diagnostico: $("#hc-inf-diagnostico"),
  traerRecipe: $("#hc-inf-traer-recipe"),
  tratamiento: $("#hc-inf-tratamiento"),
  avisoTrat:   $("#hc-inf-aviso-trat"),
  avisoTratTexto:  $("#hc-inf-aviso-trat-texto"),
  deshacerTrat:    $("#hc-inf-deshacer-trat"),

  poliza:      $("#hc-inf-poliza"),
  prestacion:  $("#hc-inf-prestacion"),
  antecedentes: $("#hc-inf-antecedentes"),
  motivoSeg:   $("#hc-inf-motivo-seg"),
  diagnosticoSeg: $("#hc-inf-diagnostico-seg"),
  evolucion:   $("#hc-inf-evolucion"),

  anexos:      $("#hc-inf-anexos"),
  anexosVacio: $("#hc-inf-anexos-vacio"),
  anexosCuenta: $("#hc-inf-anexos-cuenta"),

  error:       $("#hc-inf-error"),
  generar:     $("#hc-inf-generar"),
  cancelar:    $("#hc-inf-cancelar"),

  pdf:         $("#hc-inf-pdf"),
  pdfIframe:   $("#hc-inf-pdf-iframe"),
  pdfEstado:   $("#hc-inf-pdf-estado"),
  pdfCerrar:   $("#hc-inf-pdf-cerrar"),

  lista:       $("#hc-lista-informes"),
  vacio:       $("#hc-informes-vacio")
};

const nInfModal = {
  caja:      $("#modal-anular-informe"),
  fondo:     $("#modal-inf-anular-fondo"),
  contenido: $("#modal-inf-anular-caja"),
  titulo:    $("#modal-inf-anular-titulo"),
  sub:       $("#modal-inf-anular-sub"),
  motivo:    $("#modal-inf-anular-motivo"),
  error:     $("#modal-inf-anular-error"),
  cancelar:  $("#modal-inf-anular-cancelar"),
  aceptar:   $("#modal-inf-anular-aceptar")
};

function errorInformes(texto) {
  nInf.errorLista.textContent = texto;
  nInf.errorLista.hidden = false;
}

function limpiarErrorInformes() {
  nInf.errorLista.hidden = true;
}

/* ---------- La lista ---------- */

async function cargarInformes() {
  const paciente = hc.pacienteId;
  if (paciente === null) return;

  const mio = ++inf.pidiendo;
  try {
    const datos = await pedirCuerpo(
      "api/pacientes/" + encodeURIComponent(paciente) + "/informes", {});
    if (mio !== inf.pidiendo || hc.pacienteId !== paciente) return;
    inf.lista = Array.isArray(datos.informes) ? datos.informes : [];
    inf.cargada = true;
    limpiarErrorInformes();
    pintarInformes();
  } catch (err) {
    if (mio !== inf.pidiendo || hc.pacienteId !== paciente) return;
    inf.lista = [];
    inf.cargada = true;
    pintarInformes();
    errorInformes(motivoLegible(err,
      "No se pudieron leer los informes de este paciente. Cerrá la app y " +
      "volvé a abrirla; los informes que ya emitiste están guardados igual."));
  }
}

function pintarInformes() {
  nInf.lista.innerHTML = "";

  if (!inf.cargada) {          // todavía se está pidiendo: nada, ni el vacío
    nInf.vacio.hidden = true;
    return;
  }
  if (inf.lista.length === 0) {
    nInf.vacio.hidden = false;
    return;
  }
  nInf.vacio.hidden = true;
  inf.lista.forEach((i) => nInf.lista.appendChild(fichaInforme(i)));
}

function fichaInforme(i) {
  const anulado = i.anulado === true || i.anulado === 1;
  const hayPdf = !(i.tiene_pdf === false || i.tiene_pdf === 0);

  const caja = document.createElement("article");
  caja.className = "informe" + (anulado ? " anulado" : "");

  const cabecera = document.createElement("div");
  cabecera.className = "informe-cabecera";

  const fecha = document.createElement("span");
  fecha.className = "informe-fecha";
  fecha.textContent = fechaLegible(soloFecha(i.fecha));
  cabecera.appendChild(fecha);

  const tipo = document.createElement("span");
  tipo.className = "informe-tipo";
  tipo.textContent = TIPOS_INFORME[i.tipo] || "Informe";
  cabecera.appendChild(tipo);

  if (anulado) {
    const marca = document.createElement("span");
    marca.className = "estado-anulado";
    marca.textContent = "Anulado";
    const motivo = document.createElement("span");
    motivo.className = "estado-motivo";
    motivo.textContent = limpio(i.motivo_anulacion) || "Sin motivo registrado.";
    marca.appendChild(motivo);
    cabecera.appendChild(marca);
  } else {
    const marca = document.createElement("span");
    marca.className = "estado-vigente";
    marca.textContent = "Vigente";
    cabecera.appendChild(marca);
  }
  caja.appendChild(cabecera);

  const dx = document.createElement("p");
  dx.className = "informe-dato";
  const rotulo = document.createElement("strong");
  rotulo.textContent = "Diagnóstico";
  const texto = document.createElement("span");
  texto.textContent = limpio(i.diagnostico) || "(sin diagnóstico escrito)";
  dx.appendChild(rotulo);
  dx.appendChild(texto);
  caja.appendChild(dx);

  const cuantos = Number(i.cantidad_anexos) || 0;
  if (cuantos > 0) {
    const anexos = document.createElement("p");
    anexos.className = "informe-dato";
    anexos.textContent = cuantos === 1
      ? "Lleva 1 imagen anexada como página final."
      : "Lleva " + cuantos + " imágenes anexadas como páginas finales.";
    caja.appendChild(anexos);
  }

  if (!hayPdf) {
    const sin = document.createElement("p");
    sin.className = "informe-sin-pdf";
    sin.textContent = "El PDF de este informe no está guardado. El texto sí " +
      "quedó en la historia: para tener el papel, emitilo de nuevo con " +
      "«Nuevo informe».";
    caja.appendChild(sin);
  }

  const acciones = document.createElement("div");
  acciones.className = "acciones-fila";

  const ver = botonFila("Ver PDF", () => verPdfDeInforme(i));
  ver.disabled = !hayPdf;
  acciones.appendChild(ver);

  const reimprimir = botonFila("Reimprimir", (boton) => reimprimirInforme(i, boton));
  reimprimir.disabled = !hayPdf;
  acciones.appendChild(reimprimir);

  if (!anulado) {
    const anular = botonFila("Anular…", () => abrirModalAnularInforme(i));
    anular.classList.add("boton-fila-peligro");
    acciones.appendChild(anular);
  } else {
    const quieto = botonFila("Ya anulado", null);
    quieto.disabled = true;
    acciones.appendChild(quieto);
  }

  caja.appendChild(acciones);
  return caja;
}

/* ---------- Ver y reimprimir ---------- */

function verPdfDeInforme(i) {
  limpiarErrorInformes();
  inf.verId = i.id;
  nInf.pdf.hidden = false;
  nInf.pdfEstado.classList.remove("con-error");
  nInf.pdfEstado.textContent = (TIPOS_INFORME[i.tipo] || "Informe") + " del " +
    fechaLegible(soloFecha(i.fecha)) + " — el PDF guardado, sin regenerar." +
    ((i.anulado === true || i.anulado === 1) ? " Este informe está anulado." : "");
  nInf.pdfIframe.src = "api/informes/" + encodeURIComponent(i.id) + "/pdf";
  nInf.pdf.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function cerrarPdfInforme() {
  inf.verId = null;
  nInf.pdf.hidden = true;
  nInf.pdfIframe.removeAttribute("src");
}

async function reimprimirInforme(i, boton) {
  limpiarErrorInformes();
  const antes = boton.textContent;
  boton.disabled = true;
  boton.textContent = "Abriendo…";
  try {
    const respuesta = await fetch(
      "api/informes/" + encodeURIComponent(i.id) + "/abrir",
      { method: "POST", headers: { "Accept": "application/json" } });
    if (!respuesta.ok) {
      throw new Error(await mensajeDeError(respuesta,
        "No se pudo abrir el PDF de este informe."));
    }
    avisoHistoria("Se abrió el PDF del informe para imprimir.");
  } catch (err) {
    errorInformes(motivoLegible(err,
      "No se pudo abrir el PDF. Buscalo en la carpeta del paciente, en informes\\."));
  } finally {
    boton.disabled = false;
    boton.textContent = antes;
  }
}

/* ---------- Anulación (mismo patrón que el récipe) ---------- */

function modalAnularInformeAbierto() { return !nInfModal.caja.hidden; }

function abrirModalAnularInforme(i) {
  inf.anular = i;
  inf.focoPrevio = document.activeElement;
  inf.anulando = false;

  nInfModal.titulo.textContent = "Anular " +
    ((TIPOS_INFORME[i.tipo] || "informe").toLowerCase());
  nInfModal.sub.textContent = limpio((hc.paciente || {}).nombre) +
    " · " + fechaLegible(soloFecha(i.fecha));
  nInfModal.motivo.value = "";
  nInfModal.error.hidden = true;
  nInfModal.aceptar.disabled = false;
  nInfModal.aceptar.textContent = "Anular informe";

  nInfModal.caja.hidden = false;
  nInfModal.motivo.focus();
}

function cerrarModalAnularInforme() {
  if (inf.anulando) return;                   // no se cierra a mitad de camino
  nInfModal.caja.hidden = true;
  inf.anular = null;
  if (inf.focoPrevio && inf.focoPrevio.focus) inf.focoPrevio.focus();
  inf.focoPrevio = null;
}

async function confirmarAnulacionInforme() {
  const i = inf.anular;
  if (!i || inf.anulando) return;

  const motivo = limpio(nInfModal.motivo.value);
  if (motivo === "") {
    nInfModal.error.textContent =
      "Escribí por qué se anula: el motivo queda en la historia.";
    nInfModal.error.hidden = false;
    nInfModal.motivo.focus();
    return;
  }

  inf.anulando = true;
  nInfModal.aceptar.disabled = true;
  nInfModal.aceptar.textContent = "Anulando…";
  nInfModal.error.hidden = true;

  try {
    const respuesta = await fetch(
      "api/informes/" + encodeURIComponent(i.id) + "/anular",
      {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify({ motivo: motivo })
      });
    if (!respuesta.ok) {
      throw new Error(await mensajeDeError(respuesta,
        "No se pudo anular el informe. Volvé a intentar."));
    }
    await cuerpoJson(respuesta);

    inf.anulando = false;
    cerrarModalAnularInforme();
    if (inf.verId === i.id) cerrarPdfInforme();
    await cargarInformes();
    avisoHistoria("Informe del " + fechaLegible(soloFecha(i.fecha)) +
                  " anulado. El PDF queda guardado en la carpeta del paciente.");
    nInf.nuevo.focus();
  } catch (err) {
    inf.anulando = false;
    nInfModal.error.textContent = motivoLegible(err,
      "No se pudo anular el informe. Volvé a intentar.");
    nInfModal.error.hidden = false;
    nInfModal.aceptar.disabled = false;
    nInfModal.aceptar.textContent = "Anular informe";
  }
}

/* ---------- El formulario ---------- */

function tipoInformeElegido() {
  return nInf.tipoSeguro.checked ? "aseguradora" : "clinico";
}

/**
 * Muestra los campos del tipo elegido. El diagnóstico existe en los dos
 * formularios (el backend lo pide en los dos) pero en distinto lugar de la
 * hoja, así que son dos campos: lo escrito se copia de uno al otro para que
 * cambiar de idea no cueste volver a tipearlo.
 */
function elegirTipoInforme() {
  const tipo = tipoInformeElegido();
  const alSeguro = tipo === "aseguradora";

  if (alSeguro && limpio(nInf.diagnosticoSeg.value) === "") {
    nInf.diagnosticoSeg.value = nInf.diagnostico.value;
  }
  if (!alSeguro && limpio(nInf.diagnostico.value) === "") {
    nInf.diagnostico.value = nInf.diagnosticoSeg.value;
  }

  nInf.camposClinico.hidden = alSeguro;
  nInf.camposAseguradora.hidden = !alSeguro;

  nInf.tipoClinico.closest(".tipo-informe").classList.toggle("elegido", !alSeguro);
  nInf.tipoSeguro.closest(".tipo-informe").classList.toggle("elegido", alSeguro);
  nInf.error.hidden = true;
}

function limpiarFormularioInforme() {
  nInf.tipoClinico.checked = true;
  nInf.tipoSeguro.checked = false;
  [nInf.motivo, nInf.cuerpo, nInf.diagnostico, nInf.tratamiento,
   nInf.poliza, nInf.prestacion, nInf.antecedentes, nInf.motivoSeg,
   nInf.diagnosticoSeg, nInf.evolucion].forEach((campo) => { campo.value = ""; });

  inf.marcados = [];
  inf.deshacerCuerpo = null;
  inf.deshacerTrat = null;
  nInf.avisoCuerpo.hidden = true;
  nInf.avisoTrat.hidden = true;
  nInf.error.hidden = true;
  nInf.hintCuerpo.textContent = "La frase se carga sola al abrir el formulario. " +
    "Es un punto de partida: editala como quieras.";
  elegirTipoInforme();
}

function abrirFormInforme() {
  if (hc.pacienteId === null) return;

  limpiarErrorInformes();
  nInf.exito.hidden = true;
  limpiarFormularioInforme();

  inf.abierto = true;
  inf.pacienteId = hc.pacienteId;

  // El motivo de la consulta de hoy, si la hay: es exactamente lo que pide la
  // frase inicial, y así el médico no lo escribe dos veces.
  const hoy = hc.consultas.length ? hc.consultas[0] : null;
  if (hoy && soloFecha(hoy.fecha) === hoyISO()) {
    nInf.motivo.value = limpio(hoy.motivo);
    if (limpio(nInf.diagnostico.value) === "") {
      nInf.diagnostico.value = limpio(hoy.diagnostico);
    }
  }

  pintarAnexosDelInforme();
  nInf.form.hidden = false;
  nInf.form.scrollIntoView({ block: "nearest", behavior: "smooth" });
  nInf.motivo.focus();

  // Una sola vez al abrir: después la frase es del médico (dec. 10).
  pedirFraseInicial(false);
}

function cerrarFormInforme(callado) {
  inf.abierto = false;
  inf.pacienteId = null;
  nInf.form.hidden = true;
  nInf.error.hidden = true;
  if (!callado) nInf.nuevo.focus();
}

/* ---------- La frase inicial ---------- */

/**
 * Pide la frase de la plantilla B al backend, que la arma con el sexo, la edad
 * y los antecedentes de la historia. `reemplazar` distingue la carga de apertura
 * —que llena el recuadro vacío— del botón «Rehacer», que pisa lo que hay y deja
 * un «Deshacer» a mano.
 */
async function pedirFraseInicial(reemplazar) {
  const paciente = hc.pacienteId;
  if (paciente === null) return;

  const motivo = limpio(nInf.motivo.value);
  const antes = nInf.cuerpo.value;

  if (reemplazar) {
    nInf.rehacer.disabled = true;
    nInf.rehacer.textContent = "Armando…";
  }
  try {
    const datos = await pedirCuerpo(
      "api/pacientes/" + encodeURIComponent(paciente) + "/frase-inicial",
      { motivo: motivo });
    if (!inf.abierto || hc.pacienteId !== paciente) return;

    const frase = limpio(datos.frase);
    if (frase === "") {
      nInf.hintCuerpo.textContent = "No pude armar la frase sola: escribí el " +
        "cuerpo del informe a mano.";
      return;
    }
    if (!reemplazar && limpio(antes) !== "") return;   // no pisa lo escrito

    nInf.cuerpo.value = frase;
    if (reemplazar) {
      inf.deshacerCuerpo = antes;
      nInf.avisoCuerpoTexto.textContent = limpio(antes) === ""
        ? "Frase armada con el motivo que escribiste."
        : "Frase rehecha. Lo que había en el cuerpo se reemplazó.";
      nInf.avisoCuerpo.hidden = false;
      nInf.cuerpo.focus();
    }
  } catch (err) {
    if (!inf.abierto || hc.pacienteId !== paciente) return;
    nInf.hintCuerpo.textContent = motivoLegible(err,
      "No pude armar la frase sola: escribí el cuerpo del informe a mano.");
  } finally {
    nInf.rehacer.disabled = false;
    nInf.rehacer.textContent = "Rehacer la frase inicial";
  }
}

function deshacerCuerpoInforme() {
  if (inf.deshacerCuerpo === null) return;
  nInf.cuerpo.value = inf.deshacerCuerpo;
  inf.deshacerCuerpo = null;
  nInf.avisoCuerpo.hidden = true;
  nInf.cuerpo.focus();
}

/* ---------- Traer el tratamiento del último récipe ---------- */

/** `1. Amoxicilina Tabletas 500 mg — 1 tableta cada 8 horas`. */
function tratamientoDeItems(items) {
  return items.map((it, i) => {
    const remedio = [limpio(it.medicamento), limpio(it.presentacion)]
      .filter((parte) => parte !== "").join(" ");
    const como = limpio(it.dosis) || limpio(it.cantidad);
    return (i + 1) + ". " + remedio + (como ? " — " + como : "");
  }).filter((linea) => limpio(linea.slice(3)) !== "").join("\n");
}

async function traerTratamientoDelUltimoRecipe() {
  const paciente = hc.pacienteId;
  if (paciente === null) return;

  nInf.traerRecipe.disabled = true;
  nInf.traerRecipe.textContent = "Buscando…";
  try {
    const datos = await pedirCuerpo(
      "api/pacientes/" + encodeURIComponent(paciente) + "/ultimo-recipe", {});
    if (!inf.abierto || hc.pacienteId !== paciente) return;

    const items = Array.isArray(datos.items) ? datos.items : [];
    const texto = tratamientoDeItems(items);
    if (texto === "") {
      nInf.avisoTratTexto.textContent = "Este paciente todavía no tiene récipes " +
        "con medicamentos. Escribí el tratamiento a mano.";
      nInf.avisoTrat.hidden = false;
      inf.deshacerTrat = null;
      nInf.deshacerTrat.hidden = true;
      return;
    }

    const antes = nInf.tratamiento.value;
    inf.deshacerTrat = antes;
    nInf.tratamiento.value = limpio(antes) === "" ? texto : antes + "\n" + texto;
    nInf.deshacerTrat.hidden = false;
    nInf.avisoTratTexto.textContent = "Medicamentos del récipe del " +
      fechaLegible(soloFecha(datos.fecha)) + ". Editalos como quieras: esto es " +
      "texto, no toca el récipe.";
    nInf.avisoTrat.hidden = false;
    nInf.tratamiento.focus();
  } catch (err) {
    if (!inf.abierto || hc.pacienteId !== paciente) return;
    nInf.avisoTratTexto.textContent = motivoLegible(err,
      "No pude traer el último récipe. Escribí el tratamiento a mano.");
    nInf.avisoTrat.hidden = false;
    inf.deshacerTrat = null;
    nInf.deshacerTrat.hidden = true;
  } finally {
    nInf.traerRecipe.disabled = false;
    nInf.traerRecipe.textContent = "Traer del último récipe";
  }
}

function deshacerTratamiento() {
  if (inf.deshacerTrat === null) return;
  nInf.tratamiento.value = inf.deshacerTrat;
  inf.deshacerTrat = null;
  nInf.avisoTrat.hidden = true;
  nInf.tratamiento.focus();
}

/* ---------- Anexos opt-in (dec. 12) ---------- */

function esPdfElAnexo(a) {
  const nombre = limpio(a.nombre) || limpio(a.ruta_relativa);
  return /\.pdf$/i.test(nombre);
}

/**
 * Repinta las casillas conservando lo tildado: si el médico anexa una imagen
 * con el formulario abierto, la nueva aparece acá sin perder ni lo marcado ni
 * lo escrito.
 */
function pintarAnexosDelInforme() {
  nInf.anexos.innerHTML = "";

  const vivos = hc.anexos.map((a) => Number(a.id));
  inf.marcados = inf.marcados.filter((id) => vivos.indexOf(Number(id)) >= 0);

  if (hc.anexos.length === 0) {
    nInf.anexosVacio.hidden = false;
    nInf.anexosCuenta.hidden = true;
    return;
  }
  nInf.anexosVacio.hidden = true;
  hc.anexos.forEach((a) => nInf.anexos.appendChild(casillaDeAnexo(a)));
  contarAnexosMarcados();
}

function casillaDeAnexo(a) {
  const esPdf = esPdfElAnexo(a);
  const id = Number(a.id);
  const fecha = fechaLegible(soloFecha(a.fecha_medicion));

  const caja = document.createElement("label");
  caja.className = "anexo-elegible" + (esPdf ? " sin-uso" : "");

  const linea = document.createElement("span");
  linea.className = "anexo-casilla";
  const casilla = document.createElement("input");
  casilla.type = "checkbox";
  casilla.value = String(id);
  casilla.checked = inf.marcados.indexOf(id) >= 0;
  casilla.disabled = esPdf;
  const rotulo = document.createElement("span");
  rotulo.className = "anexo-fecha";
  rotulo.textContent = fecha;
  linea.appendChild(casilla);
  linea.appendChild(rotulo);
  caja.appendChild(linea);

  if (esPdf) {
    // Un PDF no se pega como página: se entrega aparte. Se muestra igual, con
    // su nombre, para que el médico sepa que la app lo tiene guardado.
    const archivo = document.createElement("span");
    archivo.className = "anexo-archivo";
    archivo.textContent = limpio(a.nombre) || "Archivo PDF";
    caja.appendChild(archivo);
  } else {
    const img = document.createElement("img");
    img.className = "anexo-imagen";
    img.src = "api/anexos/" + encodeURIComponent(a.id) + "/miniatura";
    img.alt = "Anexo del " + fecha;
    img.addEventListener("error", () => { img.hidden = true; });
    caja.appendChild(img);
  }

  const tipo = document.createElement("span");
  tipo.className = "anexo-tipo";
  tipo.textContent = TIPOS_ANEXO[a.tipo] || a.tipo || "Anexo";
  caja.appendChild(tipo);

  if (limpio(a.nota)) {
    const nota = document.createElement("span");
    nota.className = "anexo-nota";
    nota.textContent = a.nota;
    caja.appendChild(nota);
  }

  if (esPdf) {
    const aparte = document.createElement("span");
    aparte.className = "anexo-no-va";
    aparte.textContent = "Es un PDF: no se puede pegar adentro del informe. " +
      "Entregalo impreso aparte.";
    caja.appendChild(aparte);
    return caja;
  }

  casilla.addEventListener("change", () => {
    const donde = inf.marcados.indexOf(id);
    if (casilla.checked && donde < 0) inf.marcados.push(id);
    if (!casilla.checked && donde >= 0) inf.marcados.splice(donde, 1);
    caja.classList.toggle("marcado", casilla.checked);
    contarAnexosMarcados();
    nInf.error.hidden = true;
  });
  caja.classList.toggle("marcado", casilla.checked);
  return caja;
}

function contarAnexosMarcados() {
  const cuantos = inf.marcados.length;
  if (cuantos === 0) {
    nInf.anexosCuenta.hidden = true;
    return;
  }
  nInf.anexosCuenta.textContent = cuantos === 1
    ? "1 imagen marcada: sale como una página al final del informe."
    : cuantos + " imágenes marcadas: salen como páginas al final del informe.";
  nInf.anexosCuenta.hidden = false;
}

/* ---------- Generar ---------- */

/** Lo que se manda, según el tipo. Los nombres son los del backend. */
function cuerpoDelInforme() {
  const tipo = tipoInformeElegido();
  const datos = { paciente_id: hc.pacienteId, tipo: tipo };

  if (tipo === "aseguradora") {
    datos.numero_poliza = limpio(nInf.poliza.value);
    datos.prestacion_sanitaria = limpio(nInf.prestacion.value);
    datos.antecedentes = limpio(nInf.antecedentes.value);
    datos.motivo_consulta = limpio(nInf.motivoSeg.value);
    datos.diagnostico = limpio(nInf.diagnosticoSeg.value);
    datos.evolucion = limpio(nInf.evolucion.value);
  } else {
    datos.cuerpo = limpio(nInf.cuerpo.value);
    datos.diagnostico = limpio(nInf.diagnostico.value);
    datos.tratamiento = limpio(nInf.tratamiento.value);
  }

  // `anexos` es como se llama hoy en el backend y `anexo_ids` como lo nombra el
  // contrato: van los dos, con la misma lista, así el informe sale con sus
  // páginas lea el nombre que lea el servidor.
  datos.anexos = inf.marcados.slice();
  datos.anexo_ids = inf.marcados.slice();

  // Si hay consulta de hoy, el informe queda colgado de esa visita.
  const hoy = hc.consultas.length ? hc.consultas[0] : null;
  if (hoy && soloFecha(hoy.fecha) === hoyISO()) datos.consulta_id = hoy.id;

  return datos;
}

function errorFormInforme(texto, campo) {
  nInf.error.textContent = texto;
  nInf.error.hidden = false;
  if (campo) {
    campo.focus();
    campo.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

async function generarInforme() {
  if (inf.enviando || hc.pacienteId === null) return;

  const datos = cuerpoDelInforme();
  const tipo = datos.tipo;

  const algo = ["cuerpo", "diagnostico", "tratamiento", "numero_poliza",
                "prestacion_sanitaria", "antecedentes", "motivo_consulta",
                "evolucion"].some((campo) => limpio(datos[campo]) !== "");
  if (!algo) {
    errorFormInforme(tipo === "aseguradora"
      ? "El informe está vacío. Escribí al menos el motivo de la consulta o el diagnóstico."
      : "El informe está vacío. Escribí al menos el cuerpo o el diagnóstico.",
      tipo === "aseguradora" ? nInf.motivoSeg : nInf.cuerpo);
    return;
  }
  if (inf.marcados.length > MAX_ANEXOS_INFORME) {
    errorFormInforme("Marcaste " + inf.marcados.length + " anexos y el informe " +
      "admite hasta " + MAX_ANEXOS_INFORME + ". Destildá los que no hagan falta.");
    return;
  }

  inf.enviando = true;
  nInf.error.hidden = true;
  nInf.generar.disabled = true;
  nInf.generar.textContent = "Generando…";
  try {
    const respuesta = await fetch("api/informes", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(datos)
    });
    if (!respuesta.ok) {
      throw new Error(await mensajeDeError(respuesta,
        "No se pudo generar el informe. Volvé a intentar."));
    }
    const hecho = await cuerpoJson(respuesta);

    inf.enviando = false;
    cerrarFormInforme(true);
    limpiarErrorInformes();
    nInf.exito.hidden = false;
    inf.verId = hecho && hecho.id ? hecho.id : null;
    nInf.exitoVer.hidden = inf.verId === null;
    await cargarInformes();
    nInf.exito.scrollIntoView({ block: "nearest", behavior: "smooth" });
    nInf.exitoCerrar.focus();
  } catch (err) {
    inf.enviando = false;
    errorFormInforme(motivoLegible(err,
      "No se pudo generar el informe. Volvé a intentar."));
  } finally {
    inf.enviando = false;
    nInf.generar.disabled = false;
    nInf.generar.textContent = "Generar e imprimir informe";
  }
}

/* ---------- Enganche con la pantalla de la historia ---------- */

/**
 * Antes de pedir la historia. Deja la sección en blanco y, si el formulario
 * había quedado abierto para OTRO paciente, lo cierra: el informe a medio
 * escribir de alguien no puede terminar arriba de la historia de otro. Va acá
 * —y no cuando llegan los datos— para que también se limpie si la historia no
 * se pudo leer.
 */
function prepararInformes() {
  cerrarPdfInforme();
  nInf.exito.hidden = true;
  limpiarErrorInformes();
  if (inf.abierto && inf.pacienteId !== hc.pacienteId) cerrarFormInforme(true);
  inf.pidiendo++;
  inf.lista = [];
  inf.cargada = false;
  pintarInformes();
}

/**
 * Con la historia ya en pantalla. Si el formulario sigue abierto (es del mismo
 * paciente) se conserva tal cual y solo se repintan las casillas de los
 * anexos: anexar una imagen con el informe a medio escribir no borra nada.
 */
function sincronizarInformes() {
  if (inf.abierto) pintarAnexosDelInforme();
  cargarInformes();
}

function soltarInformes() {
  inf.pidiendo++;
  inf.lista = [];
  inf.cargada = false;
  inf.marcados = [];
  inf.verId = null;
  cerrarFormInforme(true);
  cerrarPdfInforme();
  nInf.exito.hidden = true;
  limpiarErrorInformes();
  nInf.lista.innerHTML = "";
  nInf.vacio.hidden = true;
}

function montarInformes() {
  montarAutocompletar(nInf.diagnostico, $("#lista-hc-inf-diagnostico"), {
    buscar: (q) => pedirSugerencias("api/sugerencias/diagnosticos", { q: q }),
    aTexto: (it) => it.texto,
    alElegir: (it) => { nInf.diagnostico.value = it.texto || ""; }
  });
  montarAutocompletar(nInf.diagnosticoSeg, $("#lista-hc-inf-diagnostico-seg"), {
    buscar: (q) => pedirSugerencias("api/sugerencias/diagnosticos", { q: q }),
    aTexto: (it) => it.texto,
    alElegir: (it) => { nInf.diagnosticoSeg.value = it.texto || ""; }
  });

  nInf.nuevo.addEventListener("click", abrirFormInforme);
  nInf.cancelar.addEventListener("click", () => cerrarFormInforme(false));
  nInf.generar.addEventListener("click", generarInforme);

  [nInf.tipoClinico, nInf.tipoSeguro].forEach(
    (radio) => radio.addEventListener("change", elegirTipoInforme));

  nInf.rehacer.addEventListener("click", () => pedirFraseInicial(true));
  nInf.deshacerCuerpo.addEventListener("click", deshacerCuerpoInforme);
  nInf.traerRecipe.addEventListener("click", traerTratamientoDelUltimoRecipe);
  nInf.deshacerTrat.addEventListener("click", deshacerTratamiento);

  nInf.pdfCerrar.addEventListener("click", () => {
    cerrarPdfInforme();
    nInf.nuevo.focus();
  });

  nInf.exitoVer.addEventListener("click", () => {
    const emitido = inf.lista.filter((i) => i.id === inf.verId)[0];
    if (emitido) verPdfDeInforme(emitido);
  });
  nInf.exitoCerrar.addEventListener("click", () => {
    nInf.exito.hidden = true;
    nInf.nuevo.focus();
  });

  // Modal de anulación del informe
  nInfModal.cancelar.addEventListener("click", cerrarModalAnularInforme);
  nInfModal.fondo.addEventListener("click", cerrarModalAnularInforme);
  nInfModal.aceptar.addEventListener("click", confirmarAnulacionInforme);
  nInfModal.motivo.addEventListener("input", () => { nInfModal.error.hidden = true; });

  document.addEventListener("keydown", (ev) => {
    if (!modalAnularInformeAbierto()) return;
    if (ev.key === "Escape") {
      ev.preventDefault();
      cerrarModalAnularInforme();
      return;
    }
    if (ev.key === "Tab") atraparTab(ev, nInfModal.contenido);
  });
}

/* ---------- La historia imprimible ---------- */

function imprimirHistoria() {
  if (hc.pacienteId === null) return;
  nHc.pdf.hidden = false;
  nHc.pdfIframe.src = "api/pacientes/" + encodeURIComponent(hc.pacienteId) + "/historia/pdf";
  nHc.pdf.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function cerrarPdfHistoria() {
  nHc.pdf.hidden = true;
  nHc.pdfIframe.removeAttribute("src");
}

/* ---------- Montaje ---------- */

function soltarPacienteHistoria() {
  hc.pidiendo++;
  hc.pacienteId = null;
  hc.paciente = null;
  hc.historia = null;
  hc.consultas = [];
  hc.anexos = [];
  hc.mediciones = [];
  hc.guiaSaltada = false;
  hc.editando = null;
  nHc.buscar.value = "";
  nHc.cabecera.hidden = true;
  nHc.alergias.hidden = true;
  nHc.contenido.hidden = true;
  nHc.form.hidden = true;
  nHc.invitacion.hidden = false;
  cerrarAltaPaciente(true);
  cerrarPdfHistoria();
  soltarInformes();
  limpiarAvisosHistoria();
  nHc.buscar.focus();
}

function montarHistoria() {
  montarAutocompletar(nHc.buscar, nHc.listaBuscar, {
    /*
     * La lista de siempre y, al pie, la salida para el paciente que no está:
     * «➕ Crear paciente nuevo» (dec. 18). Se ofrece cuando ninguno de los
     * resultados SE LLAMA como lo escrito —no solo cuando la lista viene
     * vacía—, porque «María Pérez» puede traer a «María Pérez González» y aun
     * así ser otra persona que todavía no existe. Con una letra sola no
     * aparece: nadie da de alta a un paciente llamado «g».
     */
    buscar: async (q) => {
      const resultados = await pedirSugerencias("api/sugerencias/pacientes", { q: q });
      const escrito = limpio(q);
      const mismoNombre = resultados.some(
        (it) => normalizar(it.nombre) === normalizar(escrito));
      if (escrito.length < 2 || mismoNombre) return resultados;
      // Uno menos de los ocho que muestra la lista: la opción de crear nunca
      // se cae del final por venir muchos homónimos.
      return resultados.slice(0, 7).concat([{ crearNuevo: true, nombre: escrito }]);
    },
    aTexto: (it) => it.crearNuevo
      ? "➕ Crear paciente nuevo: «" + it.nombre + "»"
      : it.nombre,
    aDetalle: (it) => {
      if (it.crearNuevo) return "Se le asigna su código y se abre su historia vacía.";
      const partes = [];
      if (limpio(it.codigo)) partes.push(it.codigo);
      if (it.cedula) partes.push("C.I. " + it.cedula);
      if (it.edad !== null && it.edad !== undefined && it.edad !== "") partes.push(it.edad + " años");
      return partes.join(" · ");
    },
    claseDe: (it) => (it.crearNuevo ? "sugerencia-crear" : ""),
    alElegir: (it) => {
      if (it.crearNuevo) {
        abrirAltaPaciente(it.nombre);
        return;
      }
      cerrarAltaPaciente(true);
      nHc.buscar.value = it.nombre || "";
      hc.guiaSaltada = false;
      cargarHistoria(it.id);
    }
  });

  montarAutocompletar(nHc.cDiagnostico, $("#lista-hc-diagnostico"), {
    buscar: (q) => pedirSugerencias("api/sugerencias/diagnosticos", { q: q }),
    aTexto: (it) => it.texto,
    alElegir: (it) => { nHc.cDiagnostico.value = it.texto || ""; }
  });

  nHc.otro.addEventListener("click", soltarPacienteHistoria);

  // Alta desde la tarjeta de invitación: el mismo formulario, con lo que
  // hubiera escrito en el buscador ya puesto.
  nHc.crearNuevo.addEventListener("click", () => abrirAltaPaciente(nHc.buscar.value));
  nAlta.crear.addEventListener("click", crearPacienteDesdeHistoria);
  nAlta.cancelar.addEventListener("click", () => cerrarAltaPaciente(false));
  // Escape adentro de la tarjeta la cierra, como en cualquier diálogo.
  nAlta.caja.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape" || !altaAbierta() || alta.enviando) return;
    ev.preventDefault();
    ev.stopPropagation();
    cerrarAltaPaciente(false);
  });
  [nAlta.nombre, nAlta.cedula, nAlta.edad, nAlta.telefono].forEach(
    (campo) => campo.addEventListener("input", () => { nAlta.error.hidden = true; }));
  nAlta.edad.addEventListener("input", () => {
    const solo = nAlta.edad.value.replace(/[^\d]/g, "").slice(0, 3);
    if (solo !== nAlta.edad.value) nAlta.edad.value = solo;
  });
  // La fecha de nacimiento llena la edad si estaba vacía. Se ve en el campo:
  // el médico la puede corregir, y nada se manda a espaldas suyas.
  nAlta.nacimiento.addEventListener("change", () => {
    nAlta.error.hidden = true;
    if (limpio(nAlta.edad.value) !== "") return;
    const anios = edadDesdeNacimiento(nAlta.nacimiento.value);
    if (anios !== null) nAlta.edad.value = String(anios);
  });

  // Los dos atajos de la cabecera (dec. 18).
  nHc.nuevoRecipe.addEventListener("click", irAlRecipeConEstePaciente);
  nHc.irInforme.addEventListener("click", () => {
    if (hc.pacienteId === null) return;
    if (nInf.form.hidden) abrirFormInforme();
    else {
      nInf.form.scrollIntoView({ block: "nearest", behavior: "smooth" });
      nInf.motivo.focus();
    }
  });

  nHc.imprimir.addEventListener("click", imprimirHistoria);
  nHc.pdfCerrar.addEventListener("click", () => {
    cerrarPdfHistoria();
    nHc.imprimir.focus();
  });

  nHc.guiaSaltar.addEventListener("click", () => {
    hc.guiaSaltada = true;
    nHc.guia.hidden = true;
    const primero = $("#hc-estado-civil");
    if (primero) primero.focus();
  });

  nHc.guardarFicha.addEventListener("click", guardarFicha);
  Array.prototype.forEach.call(nHc.panel.querySelectorAll("[data-historia], [data-alimentacion]"),
    (campo) => campo.addEventListener("input", () => {
      nHc.fichaEstado.hidden = true;
      nHc.fichaError.hidden = true;
    }));

  nHc.nuevaConsulta.addEventListener("click", () => abrirFormConsulta(null));
  nHc.cGuardar.addEventListener("click", guardarConsulta);
  nHc.cCancelar.addEventListener("click", cerrarFormConsulta);
  [nHc.cPeso, nHc.cTalla, nHc.cTas, nHc.cTad].forEach(
    (campo) => campo.addEventListener("input", calcularCalculados));

  // Bandeja: los dos botones «Actualizar» y los dos «Adjuntar…» viven en
  // secciones distintas y hacen lo mismo.
  nHc.panel.addEventListener("click", (ev) => {
    const destino = ev.target;
    if (!(destino instanceof HTMLElement)) return;
    if (destino.closest("[data-bandeja-actualizar]")) {
      cargarBandeja();
      return;
    }
    if (destino.closest("[data-adjuntar-carpeta]")) {
      if (hc.pacienteId === null) return;
      nHc.archivo.click();
    }
  });

  nHc.archivo.addEventListener("change", () => {
    const archivo = nHc.archivo.files && nHc.archivo.files[0];
    if (!archivo) return;
    if (hc.urlArchivo) URL.revokeObjectURL(hc.urlArchivo);
    hc.urlArchivo = URL.createObjectURL(archivo);
    const fecha = archivo.lastModified ? new Date(archivo.lastModified) : new Date();
    const mes = String(fecha.getMonth() + 1).padStart(2, "0");
    const dia = String(fecha.getDate()).padStart(2, "0");
    abrirDialogoAnexo({
      archivo: archivo,
      nombre: archivo.name,
      fecha: fecha.getFullYear() + "-" + mes + "-" + dia,
      url: hc.urlArchivo
    });
  });

  // Diálogo de anexado
  nAnexo.cancelar.addEventListener("click", cerrarDialogoAnexo);
  nAnexo.fondo.addEventListener("click", cerrarDialogoAnexo);
  nAnexo.aceptar.addEventListener("click", guardarAnexo);
  nAnexo.fecha.addEventListener("input", () => { nAnexo.error.hidden = true; });

  // Visor
  nVisor.cerrar.addEventListener("click", cerrarVisor);
  nVisor.acercar.addEventListener("click", () => zoomVisor(1.5));
  nVisor.alejar.addEventListener("click", () => zoomVisor(1 / 1.5));
  nVisor.ajustar.addEventListener("click", ajustarVisor);
  nVisor.windows.addEventListener("click", abrirAnexoEnWindows);
  nVisor.anterior.addEventListener("click", () => moverVisor(-1));
  nVisor.siguiente.addEventListener("click", () => moverVisor(1));

  document.addEventListener("keydown", (ev) => {
    if (visorAbierto()) {
      if (ev.key === "Escape") { ev.preventDefault(); cerrarVisor(); return; }
      if (ev.key === "ArrowLeft")  { ev.preventDefault(); moverVisor(-1); return; }
      if (ev.key === "ArrowRight") { ev.preventDefault(); moverVisor(1); return; }
      if (ev.key === "+" || ev.key === "=") { ev.preventDefault(); zoomVisor(1.5); return; }
      if (ev.key === "-") { ev.preventDefault(); zoomVisor(1 / 1.5); return; }
      if (ev.key === "Tab") atraparTab(ev, nVisor.caja);
      return;
    }
    if (dialogoAnexoAbierto()) {
      if (ev.key === "Escape") { ev.preventDefault(); cerrarDialogoAnexo(); return; }
      if (ev.key === "Tab") atraparTab(ev, nAnexo.contenido);
      return;
    }
  });

  // Teclado de la pantalla: Enter avanza de campo, Ctrl+Enter guarda.
  nHc.panel.addEventListener("keydown", (ev) => {
    if (ev.key !== "Enter" || ev.shiftKey || ev.altKey) return;
    const destino = ev.target;
    if (!(destino instanceof HTMLElement)) return;

    if (ev.ctrlKey || ev.metaKey) {
      ev.preventDefault();
      // Ctrl+Enter guarda lo que se está escribiendo, y lo que se está
      // escribiendo es el formulario donde está el cursor.
      if (destino.closest("#hc-alta")) crearPacienteDesdeHistoria();
      else if (destino.closest("#hc-form-informe")) generarInforme();
      else if (!nHc.form.hidden) guardarConsulta();
      else guardarFicha();
      return;
    }

    if (destino.tagName === "TEXTAREA" || destino.tagName === "BUTTON") return;
    if (destino.tagName !== "INPUT" && destino.tagName !== "SELECT") return;

    // La tarjeta de alta es su propio formulario: el Enter se mueve adentro de
    // ella y no se escapa al resto del bloque del paciente.
    const caja = destino.closest("#hc-alta") ||
                 destino.closest(".form-consulta") ||
                 destino.closest(".bloque-config");
    if (!caja) return;

    ev.preventDefault();
    const lista = Array.prototype.filter.call(
      caja.querySelectorAll("input:not([disabled]), textarea:not([disabled]), " +
                            "select:not([disabled]), button:not([disabled])"),
      (el) => el.offsetParent !== null);
    const i = lista.indexOf(destino);
    if (i >= 0 && i + 1 < lista.length) lista[i + 1].focus();
  });

  montarInformes();

  window.addEventListener("beforeunload", soltarArchivoElegido);
}

/**
 * Al volver a la pestaña. Si ya hay un paciente abierto se vuelve a mirar la
 * bandeja: entre que el médico se fue a WhatsApp y volvió, puede haber
 * descargado la imagen (Parte C §4: se escanea al abrir la pantalla o con el
 * botón, nunca en segundo plano). La historia en sí no se recarga sola para no
 * pisar lo que esté escribiendo en la ficha.
 */
function alAbrirHistoria() {
  if (hc.pacienteId === null) {
    nHc.buscar.focus();
    return;
  }
  cargarBandeja();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", arrancar);
} else {
  arrancar();
}
