/* ============================================================
   Récipes — Espacio Corporal · Pestaña «Exámenes» (2.1 · §5 y §6)

   Orden de análisis de laboratorio, calcada de «Nuevo récipe»: se emite en la
   misma hoja —carta apaisada, dos mitades, línea de corte—. La mitad izquierda
   («Solicito:») lleva la lista de análisis con su muestra y es la que se
   entrega en el laboratorio; la derecha («Ind.») lleva la preparación que el
   paciente tiene que leer.

   Todo el archivo vive dentro de un IIFE: la única variable global de la app
   sigue siendo `window.Recipes`, y de ahí sale todo lo que este módulo
   necesita del resto de la interfaz (red, autocompletado, el paciente abierto
   en la Historia clínica).

   Regla de la casa (§0.6): esto es registro documental. El catálogo de
   análisis es un punto de partida —el médico puede escribir cualquier cosa que
   no figure y se emite igual—; la app no sugiere ni indica nada por su cuenta.
   ============================================================ */
"use strict";

(function () {

const R = window.Recipes;
if (!R) {
  // Sin el puente no hay nada que hacer, pero la app de récipes tiene que
  // seguir funcionando: se anota y se sale sin romper nada.
  console.error("«Exámenes» necesita el puente `window.Recipes` de app.js.");
  return;
}

const $x = (sel, raiz) => (raiz || document).querySelector(sel);
const limpio = R.limpio;

/* ------------------------------------------------------------
   0. Constantes
   ------------------------------------------------------------ */

/* Orden en que se muestran los grupos del catálogo (§2). Lo que venga con un
   grupo que no esté acá se agrupa al final, por orden alfabético: el catálogo
   crece con lo que el médico escriba, y un grupo nuevo no puede desaparecer
   de la pantalla. */
const ORDEN_GRUPOS = [
  "Hematología",
  "Química sanguínea",
  "Hormonas",
  "Orina y heces",
  "Inmunología y serología",
  "Marcadores",
  "Estudios"
];
const GRUPO_SIN_NOMBRE = "Otros";

const TEXTO_PREVIA_VACIA = "Escribí el paciente y al menos un análisis para ver la vista previa.";

/* ------------------------------------------------------------
   1. Estado
   ------------------------------------------------------------ */

function pacienteVacioEx() {
  return {
    id: null,
    codigo: "",
    sexo: null,
    telefono: null,
    // ¿Lo puso la Historia como predeterminado? Es lo que decide si se ve la
    // banda de arriba, igual que en el récipe (dec. 18).
    desdeHistoria: false,
    // Lo que escribió la app sola al elegir un paciente de la lista: sirve
    // para distinguirlo de lo que escribió el médico con su mano.
    autoCedula: null,
    autoEdad: null
  };
}

const est = {
  paciente: pacienteVacioEx(),
  entra: true,             // último resultado de /api/examenes/medir
  guardando: false,
  urlPrevia: null,         // blob: de la vista previa vigente
  // El paciente cuyo predeterminado el médico ya rechazó con «Cambiar de
  // paciente». Mientras sea el mismo que está abierto en la Historia, volver a
  // la pestaña NO se lo vuelve a poner.
  soltadoDe: null,
  catalogo: null,          // el catálogo de análisis ya traído
  pidiendoCatalogo: false,
  montado: false
};

/* El título que trae el HTML para la sección de órdenes anteriores. Se guarda
   al montar para poder volver a él, en vez de repetir el texto acá. */
let ROTULO_ORDENES = "Órdenes emitidas de este paciente";

let contadorRenglonesEx = 0;
let medidaNroEx = 0;
let previaNroEx = 0;
let ordenesNro = 0;

/* Nodos fijos: se llenan en `montarExamenes()`, cuando el HTML del panel ya
   está en la página. */
const n = {};

/* ------------------------------------------------------------
   2. Lectura del formulario
   ------------------------------------------------------------ */

function edadTexto() {
  return limpio(n.pacEdad.value);
}

function leerRenglonesEx() {
  return Array.prototype.map.call(n.renglones.children, (renglon) => ({
    examen:       limpio($x('[data-campo="examen"]', renglon).value),
    muestra:      limpio($x('[data-campo="muestra"]', renglon).value),
    indicaciones: limpio($x('[data-campo="indicaciones"]', renglon).value)
  }));
}

/** Renglones que tienen al menos el nombre del análisis. */
function itemsUtilesEx() {
  return leerRenglonesEx().filter((it) => it.examen !== "");
}

/** Cuerpo para POST api/examenes/medir (mismo molde que /api/medir). */
function cuerpoMedidaEx() {
  return {
    paciente_nombre: limpio(n.pacNombre.value),
    items: itemsUtilesEx(),
    indicaciones_generales: limpio(n.indGenerales.value)
  };
}

/**
 * Cuerpo de POST api/examenes y de la vista previa (§5, el contrato es el
 * mismo para las dos). Las claves son exactamente las del contrato: ni una
 * más, ni una menos.
 */
function cuerpoOrden() {
  return {
    paciente: {
      id:       est.paciente.id,
      nombre:   limpio(n.pacNombre.value),
      cedula:   limpio(n.pacCedula.value),
      edad:     edadTexto(),
      sexo:     est.paciente.sexo || "",
      telefono: est.paciente.telefono || ""
    },
    items: itemsUtilesEx(),
    diagnostico: limpio(n.diagnostico.value),
    indicaciones_generales: limpio(n.indGenerales.value),
    fecha_emision: null
  };
}

/* ------------------------------------------------------------
   3. Renglones de análisis
   ------------------------------------------------------------ */

/**
 * Agrega un renglón. `datos` (opcional) es `{examen, muestra, indicaciones}`:
 * lo usan las casillas de los análisis frecuentes.
 */
function agregarRenglonEx(darFoco, datos) {
  const nodo = n.plantilla.content.firstElementChild.cloneNode(true);
  const nro = ++contadorRenglonesEx;

  const eExamen  = $x('[data-campo="examen"]', nodo);
  const eMuestra = $x('[data-campo="muestra"]', nodo);
  const ePrep    = $x('[data-campo="indicaciones"]', nodo);

  // Etiquetas con id único, para que el clic en la etiqueta enfoque el campo.
  eExamen.id  = "ex-r" + nro + "-examen";
  eMuestra.id = "ex-r" + nro + "-muestra";
  ePrep.id    = "ex-r" + nro + "-prep";
  $x('[data-para="examen"]',  nodo).setAttribute("for", eExamen.id);
  $x('[data-para="muestra"]', nodo).setAttribute("for", eMuestra.id);
  $x('[data-para="prep"]',    nodo).setAttribute("for", ePrep.id);

  // ---- Análisis (autocompletado sobre el catálogo) ----
  R.montarAutocompletar(eExamen, $x('[data-lista="examen"]', nodo), {
    buscar: (q) => R.pedirSugerencias("api/sugerencias/analisis", { q: q }),
    aTexto: (it) => it.texto,
    aDetalle: (it) => {
      const partes = [];
      if (limpio(it.grupo)) partes.push(limpio(it.grupo));
      if (limpio(it.muestra)) partes.push(limpio(it.muestra));
      return partes.join(" · ");
    },
    alElegir: (it) => {
      // Elección explícita del catálogo: la muestra y la preparación vienen
      // con ella, pero los dos campos quedan editables (§6).
      eExamen.value = it.texto || "";
      if (limpio(it.muestra)) eMuestra.value = it.muestra;
      if (limpio(it.preparacion)) ePrep.value = it.preparacion;
      eMuestra.focus();
      alCambiarAlgoEx();
    }
  });

  // ---- Quitar renglón ----
  $x("[data-quitar]", nodo).addEventListener("click", () => {
    if (n.renglones.children.length <= 1) return;
    const siguiente = nodo.nextElementSibling || nodo.previousElementSibling;
    nodo.remove();
    renumerarRenglonesEx();
    if (siguiente) $x('[data-campo="examen"]', siguiente).focus();
    alCambiarAlgoEx();
  });

  // Cualquier tecla en el renglón recalcula medida y vista previa.
  nodo.addEventListener("input", alCambiarAlgoEx);

  if (datos) {
    eExamen.value  = limpio(datos.examen);
    eMuestra.value = limpio(datos.muestra);
    ePrep.value    = limpio(datos.indicaciones);
  }

  n.renglones.appendChild(nodo);
  renumerarRenglonesEx();

  if (darFoco) eExamen.focus();
  return nodo;
}

function renumerarRenglonesEx() {
  const total = n.renglones.children.length;
  Array.prototype.forEach.call(n.renglones.children, (renglon, i) => {
    $x(".renglon-numero", renglon).textContent = "Análisis " + (i + 1);
    $x("[data-quitar]", renglon).hidden = total <= 1;
  });
}

/** El primer renglón completamente en blanco, o `null`. */
function renglonEnBlanco() {
  return Array.prototype.filter.call(n.renglones.children, (renglon) =>
    limpio($x('[data-campo="examen"]', renglon).value) === "" &&
    limpio($x('[data-campo="muestra"]', renglon).value) === "" &&
    limpio($x('[data-campo="indicaciones"]', renglon).value) === ""
  )[0] || null;
}

/** Pone un análisis del catálogo en un renglón: el primero en blanco, o uno nuevo. */
function ponerAnalisisEnRenglon(item) {
  const datos = {
    examen: limpio(item.texto),
    muestra: limpio(item.muestra),
    indicaciones: limpio(item.preparacion)
  };
  const vacio = renglonEnBlanco();
  if (!vacio) return agregarRenglonEx(false, datos);

  $x('[data-campo="examen"]', vacio).value       = datos.examen;
  $x('[data-campo="muestra"]', vacio).value      = datos.muestra;
  $x('[data-campo="indicaciones"]', vacio).value = datos.indicaciones;
  return vacio;
}

/* ------------------------------------------------------------
   4. Paciente y diagnóstico
   ------------------------------------------------------------ */

function montarPacienteEx() {
  R.montarAutocompletar(n.pacNombre, n.listaPacNombre, {
    buscar: (q) => R.pedirSugerencias("api/sugerencias/pacientes", { q: q }),
    aTexto: (it) => it.nombre,
    aDetalle: (it) => {
      const partes = [];
      if (it.cedula) partes.push("C.I. " + it.cedula);
      if (it.edad !== null && it.edad !== undefined && it.edad !== "") partes.push(it.edad + " años");
      if (it.sexo) partes.push(it.sexo);
      return partes.join(" · ");
    },
    alElegir: (it) => {
      n.pacNombre.value = it.nombre || "";
      n.pacCedula.value = it.cedula || "";
      n.pacEdad.value = (it.edad === null || it.edad === undefined) ? "" : String(it.edad);

      est.paciente = pacienteVacioEx();
      est.paciente.id = it.id != null ? it.id : null;
      est.paciente.codigo = limpio(it.codigo);
      est.paciente.sexo = it.sexo || null;
      est.paciente.telefono = it.telefono || null;
      est.paciente.autoCedula = n.pacCedula.value;
      est.paciente.autoEdad = n.pacEdad.value;

      n.hintPaciente.textContent =
        "Paciente ya conocido: se completaron cédula y edad. Podés corregirlas.";
      n.hintPaciente.hidden = false;

      pintarBandaEx();
      cargarOrdenesDe(est.paciente.id);
      n.pacCedula.focus();
      alCambiarAlgoEx();
    }
  });

  // Si cambia el nombre a mano, deja de ser el paciente elegido: con la
  // identidad se van todos los datos que trajo esa ficha. Lo que escribió el
  // médico con su mano se respeta.
  n.pacNombre.addEventListener("input", () => {
    if (est.paciente.id === null) return;

    if (n.pacCedula.value === est.paciente.autoCedula) n.pacCedula.value = "";
    if (n.pacEdad.value === est.paciente.autoEdad) n.pacEdad.value = "";

    if (est.paciente.desdeHistoria) est.soltadoDe = est.paciente.id;

    est.paciente = pacienteVacioEx();
    n.hintPaciente.hidden = true;
    pintarBandaEx();
    esconderOrdenes();
  });

  n.bandaCambiar.addEventListener("click", () => soltarPacienteEx(true));

  // La edad es un entero en la base: solo dígitos.
  n.pacEdad.addEventListener("input", () => {
    const solo = n.pacEdad.value.replace(/[^\d]/g, "").slice(0, 3);
    if (solo !== n.pacEdad.value) n.pacEdad.value = solo;
  });

  R.montarAutocompletar(n.diagnostico, n.listaDiagnostico, {
    buscar: (q) => R.pedirSugerencias("api/sugerencias/diagnosticos", { q: q }),
    aTexto: (it) => it.texto,
    alElegir: (it) => { n.diagnostico.value = it.texto || ""; }
  });
}

function pintarBandaEx() {
  const p = est.paciente;
  if (!p.desdeHistoria || p.id === null) {
    n.banda.hidden = true;
    return;
  }
  const codigo = limpio(p.codigo);
  const nombre = limpio(n.pacNombre.value) || "(sin nombre)";
  n.bandaTexto.textContent =
    "Orden de exámenes para " + (codigo ? codigo + " · " : "") + nombre;
  n.banda.hidden = false;
}

/** Pone en el formulario al paciente que está abierto en la Historia. */
function ponerPacienteDeLaHistoriaEx(p) {
  n.pacNombre.value = limpio(p.nombre);
  n.pacCedula.value = limpio(p.cedula);
  n.pacEdad.value =
    (p.edad === null || p.edad === undefined || p.edad === "") ? "" : String(p.edad);

  est.paciente = pacienteVacioEx();
  est.paciente.id = p.id != null ? p.id : null;
  est.paciente.codigo = limpio(p.codigo);
  est.paciente.sexo = p.sexo || null;
  est.paciente.telefono = p.telefono || null;
  est.paciente.autoCedula = n.pacCedula.value;
  est.paciente.autoEdad = n.pacEdad.value;
  est.paciente.desdeHistoria = true;

  // La banda ya dice de quién es la orden: el aviso de «paciente conocido»
  // sería el mismo cartel dos veces.
  n.hintPaciente.hidden = true;
  pintarBandaEx();
  ocultarErrorEx();
  cargarOrdenesDe(est.paciente.id);
  alCambiarAlgoEx();
}

/** Suelta la identidad y deja el campo libre. */
function soltarPacienteEx(darFoco) {
  if (est.paciente.desdeHistoria) est.soltadoDe = est.paciente.id;

  n.pacNombre.value = "";
  n.pacCedula.value = "";
  n.pacEdad.value = "";
  est.paciente = pacienteVacioEx();
  n.hintPaciente.hidden = true;
  pintarBandaEx();
  esconderOrdenes();
  alCambiarAlgoEx();
  if (darFoco) n.pacNombre.focus();
}

/** ¿Hay algo escrito del paciente que pisar? */
function formularioLibreEx() {
  return est.paciente.id === null &&
         limpio(n.pacNombre.value) === "" &&
         limpio(n.pacCedula.value) === "" &&
         limpio(n.pacEdad.value) === "";
}

/**
 * Al entrar a la pestaña. Pone el predeterminado de la Historia solo si no hay
 * nada que pisar: lo que el médico haya escrito manda siempre sobre la
 * comodidad.
 */
function aplicarDefaultDeHistoriaEx() {
  const p = R.pacienteDeLaHistoria;
  if (!p) return;

  if (est.paciente.desdeHistoria && est.paciente.id === p.id) {
    pintarBandaEx();                      // ya estaba puesto: solo refrescar
    cargarOrdenesDe(p.id);
    return;
  }
  if (est.soltadoDe === p.id) return;     // dijo que no para este
  if (!formularioLibreEx()) return;       // hay algo escrito: no se toca

  ponerPacienteDeLaHistoriaEx(p);
}

/* ------------------------------------------------------------
   5. Catálogo de análisis frecuentes
   ------------------------------------------------------------ */

async function cargarFrecuentes(forzar) {
  if (est.pidiendoCatalogo) return;
  // Un catálogo vacío se vuelve a pedir: puede haberse llenado con lo que el
  // médico escribió a mano en los renglones, que el backend aprende (§5).
  if (est.catalogo && est.catalogo.length && !forzar) return;

  est.pidiendoCatalogo = true;
  n.frecuentesEstado.textContent = "Cargando el catálogo de análisis…";
  n.frecuentesEstado.hidden = false;

  try {
    // Sin `q`: el backend devuelve el catálogo entero ordenado por uso (§5).
    const resultados = await R.pedirSugerencias("api/sugerencias/analisis", {});
    est.catalogo = resultados;
    pintarFrecuentes();
  } catch (err) {
    est.catalogo = null;
    n.frecuentes.innerHTML = "";
    n.frecuentesEstado.hidden = false;
    n.frecuentesEstado.textContent = R.motivoLegible(err,
      "No se pudo traer el catálogo de análisis. Podés escribirlos a mano en los " +
      "renglones de arriba.") + " Tocá «Reintentar» para volver a pedirlo.";
    mostrarBotonReintentar(true);
  } finally {
    est.pidiendoCatalogo = false;
    actualizarTildados();
  }
}

/** El botón de reintentar vive donde el de destildar: se turnan. */
function mostrarBotonReintentar(mostrar) {
  n.btnTildados.hidden = mostrar;
  n.btnDestildar.hidden = true;
  n.btnReintentar.hidden = !mostrar;
}

function pintarFrecuentes() {
  n.frecuentes.innerHTML = "";
  mostrarBotonReintentar(false);

  const catalogo = est.catalogo || [];
  if (catalogo.length === 0) {
    n.frecuentesEstado.hidden = false;
    n.frecuentesEstado.textContent =
      "Todavía no hay análisis en el catálogo. Escribilos en los renglones de arriba: " +
      "se aprenden solos y la próxima vez van a estar acá.";
    return;
  }
  n.frecuentesEstado.hidden = true;

  // Agrupar conservando el orden en que vino cada análisis (por uso).
  const porGrupo = new Map();
  catalogo.forEach((item, indice) => {
    const grupo = limpio(item.grupo) || GRUPO_SIN_NOMBRE;
    if (!porGrupo.has(grupo)) porGrupo.set(grupo, []);
    porGrupo.get(grupo).push({ item: item, indice: indice });
  });

  const conocidos = ORDEN_GRUPOS.filter((g) => porGrupo.has(g));
  // `Array.from` y no `slice.call`: las claves de un Map son un iterador, no
  // algo parecido a un array, y con `slice` los grupos nuevos se perdían.
  const otros = Array.from(porGrupo.keys())
    .filter((g) => ORDEN_GRUPOS.indexOf(g) < 0)
    .sort((a, b) => R.normalizar(a).localeCompare(R.normalizar(b)));

  conocidos.concat(otros).forEach((grupo) => {
    n.frecuentes.appendChild(cajaDeGrupo(grupo, porGrupo.get(grupo)));
  });
}

function cajaDeGrupo(grupo, entradas) {
  const caja = document.createElement("details");
  caja.className = "ex-grupo";
  caja.dataset.grupo = grupo;

  const titulo = document.createElement("summary");
  const nombre = document.createElement("span");
  nombre.textContent = grupo;
  titulo.appendChild(nombre);

  const cuenta = document.createElement("span");
  cuenta.className = "ex-grupo-cuenta";
  cuenta.dataset.cuentaGrupo = "";
  cuenta.textContent = entradas.length + " análisis";
  titulo.appendChild(cuenta);
  caja.appendChild(titulo);

  const lista = document.createElement("div");
  lista.className = "ex-lista-frecuentes";
  lista.setAttribute("role", "group");
  lista.setAttribute("aria-label", "Análisis de " + grupo);

  entradas.forEach((entrada) => lista.appendChild(casillaDeAnalisis(entrada)));
  caja.appendChild(lista);
  return caja;
}

function casillaDeAnalisis(entrada) {
  const item = entrada.item;

  const etiqueta = document.createElement("label");
  etiqueta.className = "casilla ex-casilla";
  etiqueta.setAttribute("for", "ex-fr-" + entrada.indice);

  const casilla = document.createElement("input");
  casilla.type = "checkbox";
  casilla.id = "ex-fr-" + entrada.indice;
  casilla.dataset.indice = String(entrada.indice);
  casilla.addEventListener("change", actualizarTildados);
  etiqueta.appendChild(casilla);

  const textos = document.createElement("span");

  const nombre = document.createElement("span");
  nombre.className = "ex-casilla-nombre";
  nombre.textContent = limpio(item.texto);
  textos.appendChild(nombre);

  const detalle = [];
  if (limpio(item.muestra)) detalle.push(limpio(item.muestra));
  if (limpio(item.preparacion)) detalle.push(limpio(item.preparacion));
  if (detalle.length) {
    const sub = document.createElement("span");
    sub.className = "ex-casilla-muestra";
    sub.textContent = detalle.join(" · ");
    textos.appendChild(sub);
  }

  etiqueta.appendChild(textos);
  return etiqueta;
}

function casillasFrecuentes() {
  return Array.prototype.slice.call(
    n.frecuentes.querySelectorAll('input[type="checkbox"]'));
}

function tildadas() {
  return casillasFrecuentes().filter((c) => c.checked);
}

function actualizarTildados() {
  const marcadas = tildadas();
  const cuantas = marcadas.length;

  n.btnTildados.disabled = cuantas === 0;
  n.btnTildados.textContent = cuantas === 0
    ? "Agregar los tildados"
    : "Agregar los tildados (" + cuantas + ")";
  n.btnDestildar.hidden = cuantas === 0 || !n.btnReintentar.hidden;

  n.cuentaTildados.classList.toggle("con-tildados", cuantas > 0);
  n.cuentaTildados.textContent = cuantas === 0
    ? "No hay ningún análisis tildado."
    : (cuantas === 1 ? "1 análisis tildado." : cuantas + " análisis tildados.");

  // La cuenta de cada grupo plegado: si no se dijera, tildar y plegar
  // escondería lo que se eligió.
  Array.prototype.forEach.call(n.frecuentes.children, (caja) => {
    const cuenta = $x("[data-cuenta-grupo]", caja);
    if (!cuenta) return;
    const total = caja.querySelectorAll('input[type="checkbox"]').length;
    const marcadasAca = caja.querySelectorAll('input[type="checkbox"]:checked').length;
    cuenta.classList.toggle("con-tildados", marcadasAca > 0);
    cuenta.textContent = marcadasAca > 0
      ? marcadasAca + " de " + total + " tildados"
      : total + " análisis";
  });
}

function destildarTodo() {
  casillasFrecuentes().forEach((c) => { c.checked = false; });
  actualizarTildados();
}

function agregarTildados() {
  const marcadas = tildadas();
  if (marcadas.length === 0) return;
  const catalogo = est.catalogo || [];

  // Lo que ya está pedido, normalizado. Tildar algo que ya está en la orden no
  // puede agregarlo dos veces: la mitad «Solicito:» es la que se entrega en el
  // laboratorio, y un análisis repetido ahí se lee como dos muestras. El
  // renglón escrito a mano sigue mandando: esto solo frena el atajo de las
  // casillas, no le prohíbe al médico escribir lo que quiera.
  const yaPedidos = {};
  leerRenglonesEx().forEach((it) => {
    const clave = limpio(R.normalizar(it.examen));
    if (clave) yaPedidos[clave] = true;
  });

  let puestos = 0;
  let repetidos = 0;
  marcadas.forEach((casilla) => {
    const item = catalogo[parseInt(casilla.dataset.indice, 10)];
    if (!item) return;
    const clave = limpio(R.normalizar(item.texto));
    if (clave && yaPedidos[clave]) { repetidos++; return; }
    yaPedidos[clave] = true;
    ponerAnalisisEnRenglon(item);
    puestos++;
  });

  destildarTodo();
  alCambiarAlgoEx();

  n.cuentaTildados.classList.remove("con-tildados");
  n.cuentaTildados.textContent = textoDeLoAgregado(puestos, repetidos);
}

/** Qué decir después de «Agregar los tildados», contando los que ya estaban. */
function textoDeLoAgregado(puestos, repetidos) {
  const yaEstaban = repetidos === 0 ? ""
    : (repetidos === 1
        ? " Uno ya estaba en la orden y no se repitió."
        : " " + repetidos + " ya estaban en la orden y no se repitieron.");

  if (puestos === 0) {
    return repetidos === 1
      ? "Ese análisis ya estaba en la orden."
      : "Esos " + repetidos + " análisis ya estaban en la orden.";
  }
  return (puestos === 1
    ? "Se agregó 1 análisis a la orden. Podés corregirlo en su renglón."
    : "Se agregaron " + puestos + " análisis a la orden. Podés corregirlos en sus renglones."
  ) + yaEstaban;
}

/* ------------------------------------------------------------
   6. Medida de capacidad
   ------------------------------------------------------------ */

async function medirEx() {
  const cuerpo = cuerpoMedidaEx();

  // Sin nada que medir: no molestamos al servidor ni mostramos avisos.
  if (!cuerpo.paciente_nombre && cuerpo.items.length === 0) {
    medidaNroEx++;                       // invalida cualquier respuesta en vuelo
    aplicarMedidaEx({ entra: true }, true);
    return;
  }

  const mio = ++medidaNroEx;
  try {
    const r = await fetch("api/examenes/medir", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(cuerpo)
    });
    if (!r.ok) {
      throw new Error(await R.mensajeDeError(r,
        "No se pudo calcular si la orden entra en la hoja."));
    }
    const datos = await r.json();
    if (mio !== medidaNroEx) return;
    aplicarMedidaEx(datos, cuerpo.items.length === 0);
  } catch (err) {
    if (mio !== medidaNroEx) return;
    // Si la medición falla no bloqueamos el guardado: el backend igual rechaza
    // lo que no entre y avisa con su propio mensaje.
    aplicarMedidaEx({ entra: true }, true);
  }
}

function aplicarMedidaEx(datos, ocultarDetalle) {
  est.entra = datos.entra !== false;

  if (!est.entra) {
    let texto = "No caben tantos renglones en la hoja. Quitá análisis o acortá las preparaciones.";
    if (datos.nombre_estado === "truncado") {
      texto = "El nombre del paciente no entra en la línea. Acortalo (por ejemplo, dejá un solo apellido).";
    }
    n.avisoTexto.textContent = texto;
    n.aviso.hidden = false;
  } else {
    n.aviso.hidden = true;
  }

  if (ocultarDetalle || typeof datos.rp_usado_mm !== "number") {
    n.medida.hidden = true;
  } else {
    const solicito = Math.round((datos.rp_usado_mm / datos.rp_disponible_mm) * 100);
    const ind = Math.round((datos.ind_usado_mm / datos.ind_disponible_mm) * 100);
    let texto = "Hoja usada — Solicito: " + solicito + "% · Ind.: " + ind + "%.";
    if (datos.nombre_estado === "abreviado") {
      texto += " El nombre sale abreviado: " + (datos.nombre_impreso || "") + ".";
    }
    n.medida.textContent = texto;
    n.medida.hidden = false;
  }

  actualizarBotonGuardarEx();
}

function actualizarBotonGuardarEx() {
  n.btnGuardar.disabled = est.guardando || !est.entra;
  n.btnGuardar.textContent = est.guardando ? "Guardando…" : "Guardar e imprimir";
}

/* ------------------------------------------------------------
   7. Vista previa
   ------------------------------------------------------------ */

function faltaParaPreviaEx() {
  if (limpio(n.pacNombre.value) === "") {
    return "Escribí el nombre del paciente para ver la vista previa.";
  }
  if (itemsUtilesEx().length === 0) {
    return "Agregá al menos un análisis para ver la vista previa.";
  }
  return null;
}

function soltarPreviaEx() {
  if (est.urlPrevia) {
    URL.revokeObjectURL(est.urlPrevia);
    est.urlPrevia = null;
  }
}

function mostrarPreviaVaciaEx(mensaje) {
  soltarPreviaEx();
  n.previaIframe.hidden = true;
  n.previaIframe.removeAttribute("src");
  n.previaVacia.hidden = false;
  n.previaEstado.classList.remove("con-error");
  n.previaEstado.textContent = mensaje;
}

async function refrescarPreviaEx() {
  const falta = faltaParaPreviaEx();
  if (falta) {
    previaNroEx++;                       // invalida cualquier PDF en vuelo
    mostrarPreviaVaciaEx(falta);
    return;
  }

  // Si la medición ya dijo que no entra, el PDF va a fallar igual: se ahorra
  // el viaje y el mensaje técnico del generador. La última hoja buena se deja
  // en pantalla para que el médico vea qué está por perder.
  if (!est.entra) {
    previaNroEx++;
    n.previaMarco.classList.remove("cargando");
    n.previaEstado.classList.remove("con-error");
    n.previaEstado.textContent =
      "La orden no entra en la hoja: la vista previa quedó como estaba.";
    return;
  }

  const mio = ++previaNroEx;
  n.previaMarco.classList.add("cargando");
  n.previaEstado.classList.remove("con-error");
  n.previaEstado.textContent = "Generando vista previa…";

  try {
    const r = await fetch("api/examenes/vista-previa", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/pdf" },
      body: JSON.stringify(cuerpoOrden())
    });
    if (!r.ok) throw new Error(await R.mensajeDeError(r, "No se pudo generar la vista previa."));

    const pdf = await r.blob();
    if (mio !== previaNroEx) return;                   // llegó una vieja

    soltarPreviaEx();
    est.urlPrevia = URL.createObjectURL(pdf);
    n.previaVacia.hidden = true;
    n.previaIframe.hidden = false;
    n.previaIframe.src = est.urlPrevia;
    n.previaEstado.textContent =
      "Vista previa. Si el paciente ya está registrado sale su código; " +
      "si es nuevo, todavía dice " + R.rellenoCodigo() +
      " y el número se le asigna al guardar.";
  } catch (err) {
    if (mio !== previaNroEx) return;
    n.previaEstado.classList.add("con-error");
    n.previaEstado.textContent = R.motivoLegible(err,
      "No se pudo generar la vista previa. Probá con «Actualizar vista previa».");
  } finally {
    if (mio === previaNroEx) n.previaMarco.classList.remove("cargando");
  }
}

/* ------------------------------------------------------------
   8. Disparador común de cambios
   ------------------------------------------------------------ */

const medirConEsperaEx  = R.retrasar(medirEx, 350);
const previaConEsperaEx = R.retrasar(refrescarPreviaEx, 800);

function alCambiarAlgoEx() {
  ocultarErrorEx();
  medirConEsperaEx();
  previaConEsperaEx();
}

/* ------------------------------------------------------------
   9. Errores y éxito
   ------------------------------------------------------------ */

function mostrarErrorEx(mensaje, campo) {
  n.error.textContent = mensaje;
  n.error.hidden = false;
  n.error.scrollIntoView({ block: "nearest", behavior: "smooth" });
  if (campo) {
    campo.classList.add("con-error");
    campo.focus();
    campo.addEventListener("input", function quitar() {
      campo.classList.remove("con-error");
      campo.removeEventListener("input", quitar);
    });
  }
}

function ocultarErrorEx() {
  n.error.hidden = true;
  n.error.textContent = "";
}

function mostrarExitoEx(codigo, aviso) {
  n.exitoCodigo.textContent = "Orden " + limpio(codigo);
  const nota = limpio(aviso);
  n.exitoTexto.textContent =
    "Guardada. Se abrió para imprimir." + (nota ? " " + nota : "");
  n.exito.hidden = false;
  n.columnaForm.scrollTop = 0;
  n.cerrarExito.focus();
}

/* ------------------------------------------------------------
   10. Guardar e imprimir
   ------------------------------------------------------------ */

function validarEx() {
  if (limpio(n.pacNombre.value) === "") {
    mostrarErrorEx("Escribí el nombre del paciente antes de guardar.", n.pacNombre);
    return false;
  }
  if (itemsUtilesEx().length === 0) {
    const primero = $x('[data-campo="examen"]', n.renglones.children[0]);
    mostrarErrorEx("Agregá al menos un análisis antes de guardar.", primero);
    return false;
  }
  if (!est.entra) {
    mostrarErrorEx("No caben tantos renglones en la hoja. Quitá análisis o acortá las preparaciones.");
    return false;
  }
  return true;
}

async function guardarEx() {
  if (est.guardando) return;
  ocultarErrorEx();

  // Antes de guardar, medimos con lo último escrito (sin esperar el debounce).
  medirConEsperaEx.cancelar();
  await medirEx();
  if (!validarEx()) return;

  est.guardando = true;
  actualizarBotonGuardarEx();

  try {
    const r = await fetch("api/examenes", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(cuerpoOrden())
    });
    if (!r.ok) {
      throw new Error(await R.mensajeDeError(r,
        "No se pudo guardar la orden de exámenes. Volvé a intentar."));
    }
    const datos = await R.cuerpoJson(r);

    // De quién era esta orden, antes de que el formulario se vacíe. Si el
    // paciente ya estaba identificado, su `id` está en el formulario; si era
    // nuevo y se escribió a mano, el `id` recién existe ahora y viene en la
    // respuesta (`paciente_id` de `guardar_examenes()` en `app/rutas.py`).
    const idOrden = est.paciente.id !== null && est.paciente.id !== undefined
      ? est.paciente.id
      : (typeof datos.paciente_id === "number" ? datos.paciente_id : null);
    const nombreOrden = limpio(n.pacNombre.value);
    // Después de guardar, la pantalla habla de la orden que acaba de salir. Lo
    // que decide qué se muestra abajo no es si hay una historia abierta, sino
    // si la orden era de ESE paciente: con la historia de una abierta se puede
    // emitir a mano la orden de otra, y reponer a la de la historia con su
    // lista al lado del «Orden EC-0002 guardada» invita a leer que la orden
    // fue para ella.
    const deLaHistoria = R.pacienteDeLaHistoria;
    const eraDeLaHistoria = !!deLaHistoria && deLaHistoria.id === idOrden;

    limpiarFormularioEx();
    mostrarExitoEx(datos.codigo || "", datos.aviso);

    if (eraDeLaHistoria) {
      // El caso de todos los días: se repone ese paciente —banda incluida— y
      // la lista se recarga ya con la orden nueva adentro. El formulario quedó
      // libre recién, así que el predeterminado entra sí o sí.
      aplicarDefaultDeHistoriaEx();
    } else if (idOrden !== null) {
      // La orden fue de otro: o no había historia abierta —el paciente que
      // viene por primera vez y se escribió acá mismo— o el médico había
      // tocado «Cambiar de paciente». En los dos casos el formulario queda en
      // blanco y la lista igual se muestra, que es cómo ve que la orden salió;
      // como el formulario ya no dice de quién es, el rótulo lo nombra.
      // Y si había soltado al de la historia, ese «no» se respeta: limpiar el
      // formulario no es motivo para volvérselo a poner encima.
      if (deLaHistoria) est.soltadoDe = deLaHistoria.id;
      cargarOrdenesDe(idOrden, nombreOrden);
    }
  } catch (err) {
    mostrarErrorEx(R.motivoLegible(err,
      "No se pudo guardar la orden de exámenes. Volvé a intentar."));
  } finally {
    est.guardando = false;
    actualizarBotonGuardarEx();
  }
}

/* ------------------------------------------------------------
   11. Limpieza para la orden siguiente
   ------------------------------------------------------------ */

function limpiarFormularioEx() {
  medirConEsperaEx.cancelar();
  previaConEsperaEx.cancelar();
  medidaNroEx++;
  previaNroEx++;

  n.pacNombre.value = "";
  n.pacCedula.value = "";
  n.pacEdad.value = "";
  n.diagnostico.value = "";
  n.indGenerales.value = "";
  n.hintPaciente.hidden = true;

  est.paciente = pacienteVacioEx();
  est.entra = true;
  // La orden salió: el predeterminado vuelve a estar disponible.
  est.soltadoDe = null;
  pintarBandaEx();
  esconderOrdenes();
  destildarTodo();

  n.renglones.innerHTML = "";
  agregarRenglonEx(false);

  n.aviso.hidden = true;
  n.medida.hidden = true;
  ocultarErrorEx();
  actualizarBotonGuardarEx();

  mostrarPreviaVaciaEx(TEXTO_PREVIA_VACIA);
}

/* ------------------------------------------------------------
   12. Órdenes emitidas de este paciente
   ------------------------------------------------------------ */

function esconderOrdenes() {
  ordenesNro++;                          // invalida cualquier lista en vuelo
  n.anteriores.hidden = true;
  n.anterioresLista.innerHTML = "";
  n.anterioresEstado.hidden = true;
  rotularOrdenes("");
}

/**
 * El título de la sección. Normalmente el formulario dice de quién es la
 * orden —la banda o el campo del nombre—, así que alcanza con «este paciente».
 * Cuando la lista sobrevive al formulario (recién se guardó y quedó en blanco)
 * el rótulo tiene que nombrarlo: «este paciente» arriba de un formulario vacío
 * no señala a nadie.
 */
function rotularOrdenes(nombre) {
  const quien = limpio(nombre);
  n.anterioresTitulo.textContent = quien
    ? "Órdenes emitidas de " + quien
    : ROTULO_ORDENES;
}

/**
 * Trae y pinta las órdenes de un paciente. `nombreSuelto` solo se pasa cuando
 * el formulario ya no muestra a ese paciente, para que el rótulo lo nombre.
 */
async function cargarOrdenesDe(pacienteId, nombreSuelto) {
  if (pacienteId === null || pacienteId === undefined) {
    esconderOrdenes();
    return;
  }
  const mio = ++ordenesNro;
  rotularOrdenes(nombreSuelto);

  try {
    const cuerpo = await R.pedirCuerpo(
      "api/pacientes/" + encodeURIComponent(pacienteId) + "/examenes", {});
    if (mio !== ordenesNro) return;

    // La clave es `examenes`, no `resultados`: la convención de la casa es que
    // la lista se llama como la cosa que lista, igual que
    // `GET /api/pacientes/<id>/informes` devuelve `{"informes": [...]}`. Sale
    // de `listar_examenes_paciente()` en `app/rutas.py`. Una sola forma, la
    // verdadera: si el cuerpo no la trae es un error y se dice, porque
    // quedarse en silencio con una lista vacía fue justo lo que escondió que
    // esto no andaba.
    if (!Array.isArray(cuerpo.examenes)) {
      throw new Error("El servidor no devolvió la lista de órdenes de este paciente.");
    }
    pintarOrdenes(cuerpo.examenes);
  } catch (err) {
    if (mio !== ordenesNro) return;
    // Que no se pueda leer el historial de un paciente no puede trabar la
    // emisión de la orden nueva: se dice en chico y la pantalla sigue viva.
    n.anterioresLista.innerHTML = "";
    n.anterioresEstado.hidden = false;
    n.anterioresEstado.textContent = R.motivoLegible(err,
      "No se pudieron leer las órdenes anteriores de este paciente.");
    n.anteriores.hidden = false;
  }
}

function pintarOrdenes(lista) {
  n.anterioresLista.innerHTML = "";
  n.anterioresEstado.hidden = true;

  // Sin órdenes anteriores no se muestra nada: un bloque vacío es ruido.
  if (!lista.length) {
    n.anteriores.hidden = true;
    return;
  }

  lista.forEach((o) => n.anterioresLista.appendChild(fichaOrden(o)));
  n.anteriores.hidden = false;
}

/**
 * Una tarjeta de la lista. Los campos son los de `_json_examen()` de
 * `app/rutas.py`, leídos de ahí y no adivinados: `fecha_emision` (ISO con hora,
 * que `fechaLegible` recorta sola), `cantidad_items`, `analisis` (el resumen de
 * lo pedido, separado por comas), `anulado` y `motivo_anulacion`, y `tiene_pdf`,
 * que el backend saca de mirar el disco y no la columna. Todo entra por
 * textContent.
 */
function fichaOrden(o) {
  const anulada = o.anulado === true;
  const hayPdf = o.tiene_pdf === true;

  const caja = document.createElement("article");
  caja.className = "informe" + (anulada ? " anulado" : "");

  const cabecera = document.createElement("div");
  cabecera.className = "informe-cabecera";

  const fecha = document.createElement("span");
  fecha.className = "informe-fecha";
  fecha.textContent = R.fechaLegible(o.fecha_emision);
  cabecera.appendChild(fecha);

  const titulo = document.createElement("span");
  titulo.className = "informe-tipo";
  titulo.textContent = "Orden de exámenes · " + o.cantidad_items + " análisis";
  cabecera.appendChild(titulo);

  if (anulada) {
    const marca = document.createElement("span");
    marca.className = "informe-sin-pdf";
    marca.textContent = "Anulada";
    cabecera.appendChild(marca);
  }
  caja.appendChild(cabecera);

  // Qué se pidió ese día, para reconocer la orden sin abrir el PDF.
  const resumen = limpio(o.analisis);
  if (resumen) {
    const linea = document.createElement("p");
    linea.className = "informe-dato";
    linea.textContent = resumen;
    caja.appendChild(linea);
  }

  // El motivo de la anulación es parte de lo que pasó: se lee acá, no hay que
  // ir al historial a buscarlo.
  const motivo = limpio(o.motivo_anulacion);
  if (anulada && motivo) {
    const linea = document.createElement("p");
    linea.className = "informe-dato";
    const rotulo = document.createElement("strong");
    rotulo.textContent = "Motivo de la anulación";
    linea.appendChild(rotulo);
    linea.appendChild(document.createTextNode(motivo));
    caja.appendChild(linea);
  }

  const acciones = document.createElement("div");
  acciones.className = "acciones-fila";

  if (hayPdf) {
    const boton = document.createElement("button");
    boton.type = "button";
    boton.className = "boton-fila";
    boton.textContent = "Abrir PDF";
    boton.addEventListener("click", () => abrirPdfDeOrden(o, boton));
    acciones.appendChild(boton);
  } else {
    const sin = document.createElement("p");
    sin.className = "informe-sin-pdf";
    // `tiene_pdf` mira el disco: acá el archivo no está donde quedó anotado.
    sin.textContent = "El PDF de esta orden no está en la carpeta del paciente. " +
      "Lo que se pidió quedó guardado: para tener el papel, emitila de nuevo.";
    caja.appendChild(sin);
  }

  if (acciones.children.length) caja.appendChild(acciones);
  return caja;
}

async function abrirPdfDeOrden(o, boton) {
  const antes = boton.textContent;
  boton.disabled = true;
  boton.textContent = "Abriendo…";
  n.anterioresEstado.hidden = true;
  try {
    const r = await fetch("api/examenes/" + encodeURIComponent(o.id) + "/abrir", {
      method: "POST",
      headers: { "Accept": "application/json" }
    });
    if (!r.ok) throw new Error(await R.mensajeDeError(r, "No se pudo abrir el PDF de la orden."));
    n.anterioresEstado.hidden = false;
    n.anterioresEstado.textContent = "Se abrió el PDF original para imprimir.";
  } catch (err) {
    n.anterioresEstado.hidden = false;
    n.anterioresEstado.textContent = R.motivoLegible(err,
      "No se pudo abrir el PDF. Buscalo en la carpeta del paciente, en examenes\\.");
  } finally {
    boton.disabled = false;
    boton.textContent = antes;
  }
}

/* ------------------------------------------------------------
   13. Teclado
   Enter avanza de campo, Ctrl+Enter guarda. El oyente va en el panel y
   no en `document`: así corre ANTES que el de `app.js` y le puede cortar
   la propagación, para que Ctrl+Enter acá guarde la orden y no el récipe.
   ------------------------------------------------------------ */

function enfocablesEx() {
  const sel = "#panel-examenes input:not([disabled]), " +
              "#panel-examenes textarea:not([disabled]), " +
              "#panel-examenes select:not([disabled]), " +
              "#panel-examenes button:not([disabled]):not([hidden])";
  return Array.prototype.filter.call(document.querySelectorAll(sel),
    (el) => el.offsetParent !== null);
}

function montarTecladoEx() {
  n.panel.addEventListener("keydown", (ev) => {
    if (ev.key !== "Enter" || ev.shiftKey || ev.altKey) return;

    const destino = ev.target;
    if (!(destino instanceof HTMLElement)) return;

    if (ev.ctrlKey || ev.metaKey) {
      ev.preventDefault();
      ev.stopPropagation();
      if (!n.btnGuardar.disabled) guardarEx();
      return;
    }

    if (destino.tagName === "TEXTAREA") return;      // Enter = salto de línea
    if (destino.tagName === "BUTTON") return;        // Enter = pulsar
    if (destino.tagName !== "INPUT") return;
    if (destino.type === "checkbox") return;         // la casilla se tilda con la barra
    // Si el autocompletado manejó el Enter ya llamó a stopPropagation().

    ev.preventDefault();
    const lista = enfocablesEx();
    const i = lista.indexOf(destino);
    if (i >= 0 && i + 1 < lista.length) lista[i + 1].focus();
  });
}

/* ------------------------------------------------------------
   14. Montaje y apertura
   ------------------------------------------------------------ */

function montarExamenes() {
  n.panel            = $x("#panel-examenes");
  if (!n.panel) {
    console.error("Falta la sección #panel-examenes en index.html.");
    return;
  }

  n.columnaForm      = $x("#ex-columna-form");
  n.banda            = $x("#ex-banda");
  n.bandaTexto       = $x("#ex-banda-texto");
  n.bandaCambiar     = $x("#ex-banda-cambiar");
  n.exito            = $x("#ex-exito");
  n.exitoCodigo      = $x("#ex-exito-codigo");
  n.exitoTexto       = $x("#ex-exito-texto");
  n.cerrarExito      = $x("#ex-cerrar-exito");
  n.error            = $x("#ex-error");
  n.pacNombre        = $x("#ex-pac-nombre");
  n.listaPacNombre   = $x("#ex-lista-pac-nombre");
  n.pacCedula        = $x("#ex-pac-cedula");
  n.pacEdad          = $x("#ex-pac-edad");
  n.hintPaciente     = $x("#ex-hint-paciente");
  n.diagnostico      = $x("#ex-diagnostico");
  n.listaDiagnostico = $x("#ex-lista-diagnostico");
  n.renglones        = $x("#ex-renglones");
  n.btnAgregar       = $x("#ex-btn-agregar");
  n.frecuentes       = $x("#ex-frecuentes");
  n.frecuentesEstado = $x("#ex-frecuentes-estado");
  n.btnTildados      = $x("#ex-btn-tildados");
  n.btnDestildar     = $x("#ex-btn-destildar");
  n.cuentaTildados   = $x("#ex-cuenta-tildados");
  n.indGenerales     = $x("#ex-ind-generales");
  n.aviso            = $x("#ex-aviso");
  n.avisoTexto       = $x("#ex-aviso-texto");
  n.medida           = $x("#ex-medida");
  n.btnGuardar       = $x("#ex-btn-guardar");
  n.btnRefrescar     = $x("#ex-btn-refrescar");
  n.previaEstado     = $x("#ex-previa-estado");
  n.previaMarco      = $x("#ex-previa-marco");
  n.previaIframe     = $x("#ex-previa-iframe");
  n.previaVacia      = $x("#ex-previa-vacia");
  n.rellenoCodigo    = $x("#ex-relleno-codigo");
  n.anteriores       = $x("#ex-anteriores");
  n.anterioresTitulo = $x("#ex-anteriores-titulo");
  n.anterioresEstado = $x("#ex-anteriores-estado");
  n.anterioresLista  = $x("#ex-anteriores-lista");
  n.plantilla        = $x("#ex-tpl-renglon");

  // Si el fragmento del panel todavía no se empalmó, no se monta nada y la
  // app sigue andando sin esta pestaña.
  const faltantes = ["columnaForm", "renglones", "btnGuardar", "plantilla",
                     "previaIframe", "frecuentes", "anterioresTitulo"]
                    .filter((k) => !n[k]);
  if (faltantes.length) {
    console.error("«Exámenes»: falta el contenido de #panel-examenes (" +
                  faltantes.join(", ") + ").");
    return;
  }

  // El botón de reintentar el catálogo se arma acá y no en el HTML: solo
  // existe si algo falló, y así no hay un botón muerto en la pantalla.
  n.btnReintentar = document.createElement("button");
  n.btnReintentar.type = "button";
  n.btnReintentar.className = "boton-secundario";
  n.btnReintentar.id = "ex-btn-reintentar";
  n.btnReintentar.textContent = "Reintentar";
  n.btnReintentar.hidden = true;
  n.btnReintentar.addEventListener("click", () => cargarFrecuentes(true));
  n.btnTildados.parentNode.insertBefore(n.btnReintentar, n.btnTildados);

  // El rótulo por defecto sale del propio HTML, para no tenerlo escrito en
  // dos lugares que después se despegan.
  ROTULO_ORDENES = limpio(n.anterioresTitulo.textContent) || ROTULO_ORDENES;

  montarPacienteEx();
  montarTecladoEx();

  agregarRenglonEx(false);

  n.btnAgregar.addEventListener("click", () => { agregarRenglonEx(true); alCambiarAlgoEx(); });
  n.btnTildados.addEventListener("click", agregarTildados);
  n.btnDestildar.addEventListener("click", destildarTodo);
  n.btnGuardar.addEventListener("click", guardarEx);
  n.btnRefrescar.addEventListener("click", () => {
    previaConEsperaEx.cancelar();
    refrescarPreviaEx();
  });
  n.cerrarExito.addEventListener("click", () => {
    n.exito.hidden = true;
    n.pacNombre.focus();
  });

  [n.pacNombre, n.pacCedula, n.pacEdad, n.indGenerales]
    .forEach((el) => el.addEventListener("input", alCambiarAlgoEx));
  // El diagnóstico se guarda pero no sale impreso: no mueve la previa.
  n.diagnostico.addEventListener("input", ocultarErrorEx);

  if (n.rellenoCodigo) n.rellenoCodigo.textContent = R.rellenoCodigo();

  window.addEventListener("beforeunload", soltarPreviaEx);

  actualizarTildados();
  actualizarBotonGuardarEx();
  est.montado = true;
}

/** Cada vez que el médico entra a la pestaña. */
function alAbrirExamenes() {
  if (!est.montado) return;
  if (n.rellenoCodigo) n.rellenoCodigo.textContent = R.rellenoCodigo();
  aplicarDefaultDeHistoriaEx();
  // El catálogo se pide la primera vez que se abre la pestaña, no al arrancar
  // la app: quien solo emite récipes no espera por consultas que no pidió.
  cargarFrecuentes(false);
}

/* ------------------------------------------------------------
   15. Registro en el puente
   ------------------------------------------------------------ */

R.registrar({
  nombre: "Exámenes",
  panel: "panel-examenes",
  montar: montarExamenes,
  alAbrir: alAbrirExamenes
});

})();
