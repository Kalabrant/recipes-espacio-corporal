/* ============================================================
   Infiltraciones — mapa facial (pestaña de la 2.1)
   ------------------------------------------------------------
   Portado del mapa suelto de «App Botox» (`plantilla.html`, ~2.900 líneas de
   JS). Se conserva el corazón del programa: el sistema de coordenadas
   faciales, la calibración de 3 clics, las 5 plantillas y los 35 puntos, el
   lienzo con overlay SVG, el deshacer/rehacer y la tabla viva.

   Lo que cambió al volverse pestaña:
     · nada de datos horneados en base64: el catálogo y las láminas salen del
       servidor (`api/infiltraciones/catalogo` y `recursos/infiltraciones/…`),
       y se piden la PRIMERA vez que se abre la pestaña, no al arrancar;
     · el paciente sale de la Historia clínica (`Recipes.pacienteDeLaHistoria`);
     · guardar va a la base (`POST`/`PUT`), no descarga un `.json`;
     · imprimir es el PDF del servidor: acá se borraron enteras la sección
       «H. IMPRESIÓN Y EXPORTACIÓN PNG» y el `@media print` del original;
     · los colores de la interfaz son los tokens de esta app; los de producto,
       que son DATOS, siguen siendo los de la fuente.

   Todo vive adentro de este IIFE: lo único que se toca del global es el
   `Recipes.registrar({...})` del final.
   ============================================================ */

(function () {
  "use strict";

  if (!window.Recipes || typeof window.Recipes.registrar !== "function") {
    console.error("Infiltraciones: falta el puente `Recipes` de app.js; la pestaña no se monta.");
    return;
  }

  /* ============================================================
     A. CATÁLOGO DEL SERVIDOR
     Reemplaza a la sección «A. DATOS HORNEADOS» del original: allá las
     láminas eran data URIs de 2 MB y las plantillas un objeto literal; acá
     todo llega por HTTP contra 127.0.0.1.
     ============================================================ */

  const RUTA_CATALOGO = "api/infiltraciones/catalogo";

  /* Valor de v de la punta del mentón en el sistema facial. Lo manda el
     catálogo; 1.667 es el de `plantillas.json`. */
  let MENTON_V = 1.667;

  /* Color de partida de un producto dado de alta a mano. Es un color de
     PRODUCTO (un dato), no un token de interfaz: por eso está escrito acá y
     no en el CSS. Sale de docs/DECISIONES.md de la fuente (7,81:1 con el
     número blanco del marcador). */
  const COLOR_PRODUCTO_NUEVO = "#6E4B1F";

  const TIPOS_PRODUCTO = ["toxina", "relleno", "bioestimulador", "mesoterapia", "otro"];
  const UNIDADES = ["U", "ml", "mg"];

  /* Límites del contrato (§5). Se comprueban antes de mandar nada. */
  const MAX_PUNTOS = 200;
  const MAX_PRODUCTOS = 20;
  const MAX_DOSIS = 999;

  /* Regiones para la agrupación plegable de la tabla (las mismas del PDF). */
  const REGIONES = [
    { id: "frente", etiqueta: "Frente" },
    { id: "glabela", etiqueta: "Glabela" },
    { id: "cejas", etiqueta: "Cejas" },
    { id: "periocular", etiqueta: "Periocular" },
    { id: "nariz", etiqueta: "Nariz" },
    { id: "medio", etiqueta: "Tercio medio" },
    { id: "perioral", etiqueta: "Perioral" },
    { id: "inferior", etiqueta: "Tercio inferior" },
    { id: "cuello", etiqueta: "Cuello" },
    { id: "otras", etiqueta: "Otras" }
  ];

  const cat = {
    estado: "vacio",        // vacio | pidiendo | listo | error
    error: "",
    vistas: [],             // {id, etiqueta, url, ancho, alto, calibracion}
    puntos: [],             // los 35 de plantillas.json
    plantillas: [],         // las 5 de fábrica
    zonas: [],              // [{grupo, region, zonas:[…]}]
    productos: []           // genéricos del servidor
  };

  /* Zona anatómica -> región. Manda lo que dicen los puntos de fábrica (ahí
     glabela y cejas son regiones propias); el catálogo cubre el resto. */
  let ZONA_A_REGION = {};

  const clon = (o) => (typeof structuredClone === "function" ? structuredClone(o) : JSON.parse(JSON.stringify(o)));

  function hoyISO() {
    const d = new Date();
    const p = (n) => String(n).padStart(2, "0");
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
  }

  function numero(v, porDefecto) {
    const n = Number(v);
    return Number.isFinite(n) ? n : porDefecto;
  }

  function texto(v) { return String(v === null || v === undefined ? "" : v).trim(); }

  /* --- Normalización de lo que manda el servidor ---
     El backend lo está escribiendo otro agente contra la misma §5: acá se
     acepta lo que dice el contrato y, cuando una clave puede venir de dos
     formas razonables, se aceptan las dos. Nada de romperse por una lista
     que llega envuelta. */

  function normalizarProducto(p, i) {
    const color = texto(p && p.color);
    return {
      id: texto(p && p.id) || "p" + (i + 1),
      nombre: texto(p && p.nombre) || "Producto",
      tipo: TIPOS_PRODUCTO.indexOf(texto(p && p.tipo)) >= 0 ? texto(p.tipo) : "otro",
      unidad: UNIDADES.indexOf(texto(p && p.unidad)) >= 0 ? texto(p.unidad) : "U",
      color: /^#[0-9a-fA-F]{6}$/.test(color) ? color : COLOR_PRODUCTO_NUEVO,
      lote: texto(p && p.lote),
      caducidad: texto(p && p.caducidad)
    };
  }

  /* Las zonas llegan como una lista plana de `{texto, region, region_etiqueta}`
     —así las manda `catalogo_zonas()` de `rutas.py`, en orden anatómico— y acá
     se reagrupan por región, que es lo que necesitan el desplegable (el
     `label` de cada opción) y, sobre todo, `ZONA_A_REGION`: de esa tabla sale
     la agrupación de la tabla viva, y el PDF agrupa por la misma región.
     También se aceptan una lista de textos sueltos y la forma agrupada
     ({grupo, region, zonas:[…]}), por si el catálogo cambia de vestido. */
  function normalizarZonas(bruto) {
    const grupos = [];
    const porRegion = {};

    function sumar(t, region, etiqueta) {
      const limpio = texto(t);
      if (!limpio) return;
      const r = texto(region) || "otras";
      if (!porRegion[r]) {
        porRegion[r] = { grupo: texto(etiqueta) || etiquetaRegion(r), region: r, zonas: [] };
        grupos.push(porRegion[r]);
      }
      if (porRegion[r].zonas.indexOf(limpio) < 0) porRegion[r].zonas.push(limpio);
    }

    (Array.isArray(bruto) ? bruto : []).forEach((z) => {
      if (typeof z === "string") { sumar(z, "otras", "Catálogo"); return; }
      if (!z || typeof z !== "object") return;
      if (Array.isArray(z.zonas)) {
        z.zonas.forEach((t) => sumar(t, z.region, z.grupo || z.region_etiqueta));
        return;
      }
      sumar(z.texto || z.zona || z.nombre, z.region, z.region_etiqueta || z.grupo);
    });
    return grupos;
  }

  function normalizarVista(v) {
    return {
      id: texto(v && v.id),
      etiqueta: texto(v && v.etiqueta) || texto(v && v.id),
      url: texto(v && v.url),
      ancho: numero(v && v.ancho, 0),
      alto: numero(v && v.alto, 0),
      calibracion: v && v.calibracion ? clon(v.calibracion) : null
    };
  }

  function normalizarCatalogo(datos) {
    const d = datos && typeof datos === "object" ? datos : {};

    cat.vistas = (Array.isArray(d.vistas) ? d.vistas : [])
      .map(normalizarVista)
      .filter((v) => v.id && v.url && calibracionValida(v.calibracion));

    cat.puntos = (Array.isArray(d.puntos) ? d.puntos : []).filter(
      (p) => p && p.id && Number.isFinite(Number(p.u)) && Number.isFinite(Number(p.v))
    ).map((p) => ({
      id: texto(p.id),
      zona: texto(p.zona),
      lado: texto(p.lado) || "C",
      grupo: texto(p.grupo) || "otras",
      u: Number(p.u),
      v: Number(p.v)
    }));

    cat.plantillas = (Array.isArray(d.plantillas) ? d.plantillas : [])
      .filter((p) => p && p.id && Array.isArray(p.puntos))
      .map((p) => ({ id: texto(p.id), nombre: texto(p.nombre) || texto(p.id), puntos: clon(p.puntos) }));

    cat.zonas = normalizarZonas(d.zonas);

    cat.productos = (Array.isArray(d.productos) ? d.productos : []).map(normalizarProducto);
    if (!cat.productos.length) {
      // Sin productos no se puede registrar nada: se deja uno para que la
      // pestaña siga viva y el médico lo renombre desde Ajustes.
      cat.productos = [normalizarProducto({ nombre: "Producto", unidad: "U" }, 0)];
    }

    const sis = d.sistemaCoordenadas || (d.puntosMeta && d.puntosMeta.sistemaCoordenadas);
    MENTON_V = numero(sis && sis.mentonV, 1.667) || 1.667;

    // Zona -> región: primero el catálogo, después los puntos de fábrica.
    ZONA_A_REGION = {};
    cat.zonas.forEach((g) => { g.zonas.forEach((z) => { ZONA_A_REGION[z] = g.region; }); });
    cat.puntos.forEach((p) => { if (p.zona && p.grupo) ZONA_A_REGION[p.zona] = p.grupo; });

    // Calibraciones: la de fábrica queda intacta y la viva arranca igual.
    CALIBRACION_FABRICA = {};
    CALIBRACIONES_VIVAS = {};
    cat.vistas.forEach((v) => {
      CALIBRACION_FABRICA[v.id] = clon(v.calibracion);
      CALIBRACIONES_VIVAS[v.id] = clon(v.calibracion);
    });
  }

  function regionDeZona(zona) {
    const r = zona ? ZONA_A_REGION[zona] : null;
    return r || "otras";
  }
  function etiquetaRegion(id) {
    const r = REGIONES.filter((x) => x.id === id)[0];
    return r ? r.etiqueta : "Otras";
  }

  /* ============================================================
     B. ESTADO
     Un solo objeto. Nada de datos sueltos por el DOM.
     ============================================================ */

  /* La lámina con la que arranca una sesión nueva. Si la historia dice el sexo
     del paciente, se abre la lámina que le corresponde: es lo que el médico
     iba a elegir a mano igual, y elegirla mal cuesta un clic más y ningún
     dato (los puntos se reproyectan al cambiar de lámina). Sin ese dato, la
     primera del catálogo. */
  function vistaPorDefecto() {
    const sexo = texto((estado.paciente || {}).sexo).toUpperCase();
    const inicial = sexo.charAt(0);
    const buscada = inicial === "F" ? "mujer" : (inicial === "M" ? "hombre" : "");
    if (buscada) {
      const v = cat.vistas.filter((x) => x.id.indexOf(buscada) >= 0)[0];
      if (v) return v;
    }
    return cat.vistas[0] || null;
  }

  function sesionVacia() {
    const v = vistaPorDefecto();
    return {
      fecha: hoyISO(),
      vista: v ? v.id : "",
      calibracion: v ? clon(v.calibracion) : null,
      productos: clon(cat.productos),
      puntos: [],
      observaciones: ""
    };
  }

  const estado = {
    montado: false,
    pacienteId: null,
    paciente: null,
    sesionId: null,          // id en la base cuando se está corrigiendo una sesión guardada
    codigo: "",
    sesion: {
      fecha: hoyISO(), vista: "", calibracion: null, productos: [], puntos: [], observaciones: ""
    },
    /* Las plantillas propias y las zonas propias NO viajan en el cuerpo que
       manda el contrato (§5), así que viven mientras la app esté abierta y se
       conservan exportándolas a un archivo. Nada de localStorage. */
    misPlantillas: [],
    zonasPropias: [],
    ui: {
      vistaId: "",
      zoom: 1,
      pan: { x: 0, y: 0 },
      seleccionId: null,
      mostrarDosis: false,
      tamMarcador: 11,          // radio en píxeles de pantalla
      productoId: "",           // producto con el que nacen los puntos nuevos
      refVisible: false,
      sesionReferencia: null,
      refEtiqueta: "",
      lienzo: { ancho: 0, alto: 0 },
      cambiosSinGuardar: false,
      modoCalibracion: null,
      gruposPlegados: {},
      espacioPulsado: false,
      sesionesAbiertas: false,
      guardando: false
    }
  };

  /* Sesiones anteriores del paciente (reemplazan al «Abrir sesión» y a la
     «sesión anterior como referencia» del programa suelto). */
  const listaSesiones = { estado: "vacio", filas: [], error: "" };

  /* ---- Historial de deshacer / rehacer (≥ 50 pasos) ---- */
  const HISTORIAL_MAX = 80;
  const historial = { pasos: [], indice: -1 };

  function historialIniciar() {
    historial.pasos = [clon(estado.sesion)];
    historial.indice = 0;
  }
  /* Se llama DESPUÉS de cada mutación de estado.sesion. Una llamada = un paso. */
  function registrar() {
    const instantanea = clon(estado.sesion);
    const previa = historial.pasos[historial.indice];
    // Si nada cambió no se gasta un paso de deshacer.
    if (previa && JSON.stringify(previa) === JSON.stringify(instantanea)) return;
    historial.pasos.length = historial.indice + 1;
    historial.pasos.push(instantanea);
    if (historial.pasos.length > HISTORIAL_MAX) historial.pasos.shift();
    historial.indice = historial.pasos.length - 1;
    estado.ui.cambiosSinGuardar = true;
  }
  function deshacer() {
    if (historial.indice <= 0) { avisar("No hay nada que deshacer."); return; }
    historial.indice--;
    estado.sesion = clon(historial.pasos[historial.indice]);
    trasCambioDeSesion();
  }
  function rehacer() {
    if (historial.indice >= historial.pasos.length - 1) { avisar("No hay nada que rehacer."); return; }
    historial.indice++;
    estado.sesion = clon(historial.pasos[historial.indice]);
    trasCambioDeSesion();
  }
  function trasCambioDeSesion() {
    if (!estado.sesion.puntos.some((p) => p.id === estado.ui.seleccionId)) estado.ui.seleccionId = null;
    estado.ui.vistaId = estado.sesion.vista;
    estado.ui.cambiosSinGuardar = true;
    /* Deshacer sustituye la sesión entera: hay que volver a montar la
       calibración viva de la lámina (si no, una recalibración deshecha
       seguiría vigente al cambiar de lámina) y los desplegables. */
    sincronizarCalibracionViva();
    poblarSelectores();
    render();
  }
  function marcarCambios() { estado.ui.cambiosSinGuardar = true; }

  /* ============================================================
     C. COORDENADAS Y CALIBRACIÓN
     Portado tal cual del original: es el corazón del asunto.
       - facial       (u, v)  origen en el punto medio interpupilar, unidad = DIP
       - píxel imagen (px, py) en las dimensiones nativas de la lámina
       - normalizado  (x, y)  0–1 sobre la lámina: es lo que se guarda
     La aritmética se hace en píxeles porque la lámina no es cuadrada y en
     normalizadas las distancias no serían isótropas.
     ============================================================ */

  let CALIBRACION_FABRICA = {};
  let CALIBRACIONES_VIVAS = {};

  function vistaPorId(id) {
    return cat.vistas.filter((v) => v.id === id)[0] || cat.vistas[0] || null;
  }
  function vistaActual() { return vistaPorId(estado.ui.vistaId); }

  function calibracionDeVista(id) {
    const v = vistaPorId(id);
    if (!v) return null;
    return CALIBRACIONES_VIVAS[v.id] || v.calibracion;
  }
  function fijarCalibracionVista(id, cal) {
    const v = vistaPorId(id);
    if (v) CALIBRACIONES_VIVAS[v.id] = clon(cal);
  }
  /* La calibración de la sesión manda: se copia a la calibración viva de su
     lámina para que cambiar de lámina y volver no la sustituya por la de fábrica. */
  function sincronizarCalibracionViva() {
    if (estado.sesion && calibracionValida(estado.sesion.calibracion)) {
      fijarCalibracionVista(estado.sesion.vista, estado.sesion.calibracion);
    }
  }
  function calibracionActual() {
    return estado.sesion.calibracion || calibracionDeVista(estado.ui.vistaId);
  }

  /* Un par [x, y] utilizable: dos números finitos. */
  function parValido(p) {
    return Array.isArray(p) && p.length >= 2 && Number.isFinite(Number(p[0])) && Number.isFinite(Number(p[1]));
  }
  /* Una calibración solo sirve si trae las tres referencias y las dos pupilas
     no coinciden (si coincidieran, la DIP sería 0 y no habría marco facial). */
  function calibracionValida(c) {
    if (!c || typeof c !== "object") return false;
    if (!parValido(c.pupilaIzq) || !parValido(c.pupilaDer) || !parValido(c.menton)) return false;
    return Math.hypot(c.pupilaDer[0] - c.pupilaIzq[0], c.pupilaDer[1] - c.pupilaIzq[1]) > 1e-6;
  }

  /* Marco facial derivado de la calibración: origen, ejes, DIP y factor vertical k. */
  function marcoFacial(vista, calibracion) {
    const v = vista || vistaActual();
    const c = calibracion || calibracionActual();
    if (!v || !calibracionValida(c)) return null;
    const W = v.ancho || 1, H = v.alto || 1;
    const pi = [c.pupilaIzq[0] * W, c.pupilaIzq[1] * H];
    const pd = [c.pupilaDer[0] * W, c.pupilaDer[1] * H];
    const me = [c.menton[0] * W, c.menton[1] * H];
    const O = [(pi[0] + pd[0]) / 2, (pi[1] + pd[1]) / 2];
    const dx = pd[0] - pi[0], dy = pd[1] - pi[1];
    const dip = Math.hypot(dx, dy) || 1;
    const ex = [dx / dip, dy / dip];          // unitario pupila izq → pupila der (absorbe la rotación)
    const ey = [-ex[1], ex[0]];               // ex girado 90°: apunta hacia abajo
    const distV = (me[0] - O[0]) * ey[0] + (me[1] - O[1]) * ey[1];
    const k = distV / (MENTON_V * dip) || 1;  // corrige el alargamiento vertical de cada lámina
    return { O: O, ex: ex, ey: ey, dip: dip, k: k, W: W, H: H };
  }

  /* facial (u, v) -> normalizadas (x, y) */
  function facialANormalizada(u, v, m) {
    const mf = m || marcoFacial();
    if (!mf) return { x: 0.5, y: 0.5 };
    const px = mf.O[0] + u * mf.dip * mf.ex[0] + v * mf.dip * mf.k * mf.ey[0];
    const py = mf.O[1] + u * mf.dip * mf.ex[1] + v * mf.dip * mf.k * mf.ey[1];
    return { x: px / mf.W, y: py / mf.H };
  }

  /* normalizadas (x, y) -> facial (u, v)  (la inversa exacta de la anterior) */
  function normalizadaAFacial(x, y, m) {
    const mf = m || marcoFacial();
    if (!mf) return { u: 0, v: 0 };
    const dx = x * mf.W - mf.O[0];
    const dy = y * mf.H - mf.O[1];
    const u = (dx * mf.ex[0] + dy * mf.ex[1]) / mf.dip;
    const v = (dx * mf.ey[0] + dy * mf.ey[1]) / (mf.dip * mf.k);
    return { u: u, v: v };
  }

  /* Lado clínico (lateralidad DEL PACIENTE, que es lo que se anota en la
     historia). u es positivo hacia la derecha de la lámina y las láminas son
     vistas frontales, así que la mitad derecha de la lámina es el hemifacial
     IZQUIERDO del paciente: u > 0 -> 'I', u < 0 -> 'D'. */
  function ladoDesdeNormalizada(x, y) {
    const f = normalizadaAFacial(x, y);
    if (f.u > 0.08) return "I";
    if (f.u < -0.08) return "D";
    return "C";
  }
  const TITULO_LADO = "Lateralidad del paciente: I = hemifacial izquierdo, D = derecho, C = línea media. " +
    "La lámina es una vista frontal, así que el lado I del paciente aparece a la derecha de la imagen.";

  /* Conversión entre normalizadas y píxeles de pantalla del lienzo. */
  function normalizadaAPantalla(x, y) {
    return { px: x * estado.ui.lienzo.ancho, py: y * estado.ui.lienzo.alto };
  }
  function pantallaANormalizada(px, py) {
    const a = estado.ui.lienzo.ancho || 1, b = estado.ui.lienzo.alto || 1;
    return { x: Math.min(1, Math.max(0, px / a)), y: Math.min(1, Math.max(0, py / b)) };
  }
  /* Igual que la anterior, descontando el zoom y el desplazamiento. */
  function marcoANormalizada(cx, cy) {
    const z = estado.ui.zoom || 1;
    return pantallaANormalizada((cx - estado.ui.pan.x) / z, (cy - estado.ui.pan.y) / z);
  }
  /* El desplazamiento nunca deja hueco: con zoom 1 la lámina queda pegada al marco. */
  function limitarPan() {
    const z = estado.ui.zoom || 1;
    const w = estado.ui.lienzo.ancho, h = estado.ui.lienzo.alto;
    estado.ui.pan.x = Math.min(0, Math.max(Math.min(0, w - w * z), estado.ui.pan.x));
    estado.ui.pan.y = Math.min(0, Math.max(Math.min(0, h - h * z), estado.ui.pan.y));
  }

  function redondear5(n) { return Math.round(n * 100000) / 100000; }
  function redondear(n) { return Math.round(n * 100) / 100; }

  /* ============================================================
     D. PLANTILLAS
     ============================================================ */

  function listaPlantillas() {
    const fabrica = cat.plantillas.map((p) => ({ id: p.id, nombre: p.nombre, propia: false }));
    const propias = estado.misPlantillas.map((p) => ({ id: p.id, nombre: p.nombre, propia: true }));
    return fabrica.concat(propias);
  }
  function plantillaPorId(id) {
    return cat.plantillas.filter((p) => p.id === id)[0] ||
           estado.misPlantillas.filter((p) => p.id === id)[0] || null;
  }
  function puntoDePlantilla(idPunto) {
    return cat.puntos.filter((p) => p.id === idPunto)[0] || null;
  }
  /* Las plantillas de fábrica listan identificadores de punto; las propias
     llevan el punto entero. Devuelve siempre {id, zona, lado, grupo, u, v}. */
  function puntosDePlantilla(plant) {
    return ((plant && plant.puntos) || [])
      .map((p) => (typeof p === "string" ? puntoDePlantilla(p) : p))
      .filter(Boolean);
  }

  /* Pregunta sustituir / agregar cuando ya hay puntos. Devuelve
     'sustituir', 'anadir' o null. */
  function preguntarModoPlantilla(plant, cuantos) {
    return new Promise((resolver) => {
      const dlg = nodos.dlgPlantilla;
      nodos.dlgPlantillaTexto.textContent =
        "En el mapa ya hay " + estado.sesion.puntos.length +
        (estado.sesion.puntos.length === 1 ? " punto" : " puntos") + ". La plantilla «" + plant.nombre +
        "» trae " + cuantos + ". ¿Qué preferís?";
      const alCerrar = () => {
        dlg.removeEventListener("close", alCerrar);
        const v = dlg.returnValue;
        resolver(v === "sustituir" || v === "anadir" ? v : null);
      };
      dlg.addEventListener("close", alCerrar);
      dlg.returnValue = "cancelar";
      if (typeof dlg.showModal === "function") dlg.showModal();
      else resolver(window.confirm("¿Sustituir los puntos actuales? (Cancelar = agregar)") ? "sustituir" : "anadir");
    });
  }

  /* Siembra los puntos de una plantilla: (u, v) -> normalizadas con la
     calibración de la lámina actual. Dedupla por plantillaId, deja la dosis
     vacía y gasta UNA sola operación de deshacer. */
  async function aplicarPlantilla(id) {
    const plant = plantillaPorId(id);
    if (!plant) { avisar("No encuentro esa plantilla."); return; }
    const defs = puntosDePlantilla(plant);
    if (!defs.length) { avisar("Esa plantilla no tiene puntos."); return; }

    let modo = "sustituir";
    if (estado.sesion.puntos.length) {
      modo = await preguntarModoPlantilla(plant, defs.length);
      if (!modo) return;
    }
    if (modo === "sustituir") { estado.sesion.puntos = []; estado.ui.seleccionId = null; }

    const m = marcoFacial();
    if (!m) { avisar("Esta lámina no tiene una calibración utilizable: recalibrala desde Ajustes."); return; }

    const yaPuestos = {};
    estado.sesion.puntos.forEach((p) => { if (p.plantillaId) yaPuestos[p.plantillaId] = true; });
    let siguiente = numeroSiguienteDeId();
    let agregados = 0;
    let saltados = 0;
    let tope = 0;

    defs.forEach((def) => {
      if (yaPuestos[def.id]) return;                        // ya está puesto: no se duplica
      if (estado.sesion.puntos.length >= MAX_PUNTOS) { tope++; return; }
      // Cinturón de seguridad: un punto sin coordenadas faciales daría NaN.
      if (!Number.isFinite(Number(def.u)) || !Number.isFinite(Number(def.v))) { saltados++; return; }
      const n = facialANormalizada(Number(def.u), Number(def.v), m);
      estado.sesion.puntos.push({
        id: "n" + (siguiente++),
        orden: 0,
        x: redondear5(n.x),
        y: redondear5(n.y),
        lado: def.lado || ladoDesdeNormalizada(n.x, n.y),
        zona: def.zona || "",
        productoId: productoParaPuntoNuevo(),
        dosis: null,                                        // las dosis siempre nacen vacías
        notas: "",
        plantillaId: def.id,
        manual: false                                       // sembrado: una reaplicación puede volver a tocarlo
      });
      yaPuestos[def.id] = true;
      agregados++;
    });

    renumerar();
    registrar();                                            // un único paso de deshacer para toda la plantilla
    render();

    const aviso = modo === "sustituir"
      ? "Plantilla «" + plant.nombre + "» aplicada: " + agregados + " puntos, dosis vacías."
      : (agregados ? agregados + " puntos agregados de «" + plant.nombre + "»."
                   : "Esa plantilla ya estaba puesta entera: no se agregó ningún punto.");
    avisar(aviso +
      (saltados ? " " + saltados + " puntos de la plantilla no tenían coordenadas válidas y se omitieron." : "") +
      (tope ? " " + tope + " puntos no entraron: el tope es " + MAX_PUNTOS + " por sesión." : ""));
  }

  /* Guarda las posiciones actuales como plantilla propia, en coordenadas faciales. */
  async function guardarComoPlantilla() {
    if (!estado.sesion.puntos.length) { avisar("No hay puntos que guardar como plantilla."); return; }
    const m = marcoFacial();
    if (!m) { avisar("Sin calibración no se pueden convertir las posiciones a coordenadas faciales."); return; }
    const nombre = await pedirTexto("Guardar como plantilla", "Nombre de la plantilla",
      "Mi plantilla " + hoyISO(),
      "Se guardan las posiciones (en coordenadas faciales) y la zona de cada punto; ni las dosis ni el producto.");
    if (!nombre) return;
    const sello = Date.now().toString(36);
    const plant = {
      id: "mia-" + sello,
      nombre: nombre,
      puntos: estado.sesion.puntos.map((p, i) => {
        const f = normalizadaAFacial(p.x, p.y, m);
        return {
          id: "mia-" + sello + "-" + (i + 1),
          zona: p.zona || "",
          lado: p.lado || "C",
          grupo: regionDeZona(p.zona),
          u: Math.round(f.u * 1000) / 1000,
          v: Math.round(f.v * 1000) / 1000
        };
      })
    };
    estado.misPlantillas.push(plant);
    poblarSelectores();
    render();
    avisar("Plantilla «" + nombre + "» guardada. Vive mientras la app esté abierta: exportala desde Ajustes para conservarla.");
  }

  const FORMATO_PLANTILLAS = "mapa-infiltraciones/mis-plantillas/v1";

  /* Descarga de un objeto como archivo JSON (Blob + enlace temporal; nada de
     red y nada de almacenamiento del navegador). */
  function descargarJSON(nombre, objeto) {
    const contenido = JSON.stringify(objeto, null, 2);
    const blob = new Blob([contenido], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = nombre;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  function exportarMisPlantillas() {
    if (!estado.misPlantillas.length) { avisar("Todavía no hay plantillas propias que exportar."); return; }
    descargarJSON("mis-plantillas.json", { formato: FORMATO_PLANTILLAS, plantillas: clon(estado.misPlantillas) });
    avisar("mis-plantillas.json descargado.");
  }

  function importarMisPlantillas() { nodos.archivoPlantillas.click(); }

  /* Acepta el archivo exportado acá, un array suelto o una sesión con misPlantillas. */
  function recibirMisPlantillas(contenido) {
    let datos;
    try { datos = JSON.parse(contenido); }
    catch (e) { avisar("Ese archivo no es un JSON válido; no se importó nada."); return; }
    let lista = null;
    if (Array.isArray(datos)) lista = datos;
    else if (datos && Array.isArray(datos.plantillas)) lista = datos.plantillas;
    else if (datos && Array.isArray(datos.misPlantillas)) lista = datos.misPlantillas;
    if (!lista) { avisar("Ese archivo no trae plantillas propias (falta la lista «plantillas»)."); return; }

    /* Cada punto tiene que traer coordenadas faciales utilizables: sin esto un
       punto sin u/v se sembraría como NaN, o sea un marcador invisible. */
    const puntoUtil = (q) => q && Number.isFinite(Number(q.u)) && Number.isFinite(Number(q.v));
    let descartados = 0;
    const validas = [];
    lista.forEach((p) => {
      if (!p || !p.nombre || !Array.isArray(p.puntos)) return;
      const buenos = p.puntos.filter(puntoUtil);
      descartados += p.puntos.length - buenos.length;
      if (!buenos.length) return;
      const copia = clon(p);
      copia.puntos = buenos.map((q) => Object.assign(clon(q), { u: Number(q.u), v: Number(q.v) }));
      validas.push(copia);
    });
    if (!validas.length) {
      avisar("No encontré ninguna plantilla con nombre y con puntos en coordenadas faciales (u, v). No se importó nada.");
      return;
    }

    const usados = {};
    listaPlantillas().forEach((p) => { usados[p.id] = true; });
    let n = 0;
    validas.forEach((copia) => {
      if (!copia.id || usados[copia.id]) copia.id = "mia-" + Date.now().toString(36) + "-" + (++n);
      usados[copia.id] = true;
      estado.misPlantillas.push(copia);
    });
    poblarSelectores();
    render();
    avisar(validas.length + (validas.length === 1 ? " plantilla importada." : " plantillas importadas.") +
      (descartados ? " Se descartaron " + descartados + " puntos sin coordenadas válidas." : ""));
  }

  function borrarMiPlantilla(id) {
    estado.misPlantillas = estado.misPlantillas.filter((p) => p.id !== id);
    poblarSelectores();
    render();
  }

  /* ============================================================
     E. RENDER
     Una única función render(). Nadie más toca el DOM de la vista.
     ============================================================ */

  const nodos = {};

  function tomarNodos() {
    const $ = (sel) => document.querySelector(sel);
    nodos.mesa = $("#inf-mesa");
    if (!nodos.mesa) return false;

    nodos.sinPaciente = $("#inf-sin-paciente");
    nodos.irHistoria = $("#inf-ir-historia");
    nodos.cartelCatalogo = $("#inf-cartel-catalogo");
    nodos.catalogoEstado = $("#inf-catalogo-estado");
    nodos.reintentar = $("#inf-reintentar");

    nodos.banda = $("#inf-banda");
    nodos.bandaTexto = $("#inf-banda-texto");
    nodos.bandaSesion = $("#inf-banda-sesion");
    nodos.bandaCambiar = $("#inf-banda-cambiar");
    nodos.avisoPaciente = $("#inf-aviso-paciente");
    nodos.avisoPacienteTexto = $("#inf-aviso-paciente-texto");
    nodos.avisoPacienteCambiar = $("#inf-aviso-paciente-cambiar");

    nodos.fecha = $("#inf-fecha");
    nodos.selVista = $("#inf-vista");
    nodos.selPlantilla = $("#inf-plantilla");
    nodos.btnGuardarPlantilla = $("#inf-guardar-plantilla");
    nodos.btnAjustes = $("#inf-ajustes");
    nodos.btnNueva = $("#inf-nueva");
    nodos.btnGuardar = $("#inf-guardar");
    nodos.error = $("#inf-error");
    nodos.exito = $("#inf-exito");

    nodos.btnDeshacer = $("#inf-deshacer");
    nodos.btnRehacer = $("#inf-rehacer");
    nodos.btnEspejo = $("#inf-espejo");
    nodos.btnZoomMenos = $("#inf-zoom-menos");
    nodos.btnZoomMas = $("#inf-zoom-mas");
    nodos.btnAjustar = $("#inf-ajustar");
    nodos.selProducto = $("#inf-sel-producto");
    nodos.chkDosis = $("#inf-chk-dosis");
    nodos.rngTam = $("#inf-rng-tam");
    nodos.chkReferencia = $("#inf-chk-referencia");
    nodos.etqReferencia = $("#inf-etq-referencia");

    nodos.barraCalibracion = $("#inf-barra-calibracion");
    nodos.calibPaso = $("#inf-calib-paso");
    nodos.calibInstruccion = $("#inf-calib-instruccion");
    nodos.calibRepetir = $("#inf-calib-repetir");
    nodos.calibCancelar = $("#inf-calib-cancelar");
    nodos.calibAceptar = $("#inf-calib-aceptar");

    nodos.areaLienzo = $("#inf-area-lienzo");
    nodos.marco = $("#inf-marco");
    nodos.lamina = $("#inf-lamina");
    nodos.overlay = $("#inf-overlay");
    nodos.capaZoom = $("#inf-capa-zoom");
    nodos.capaReferencia = $("#inf-capa-referencia");
    nodos.capaPuntos = $("#inf-capa-puntos");
    nodos.capaCalibracion = $("#inf-capa-calibracion");
    nodos.leyenda = $("#inf-leyenda");

    nodos.btnBorrarSinDosis = $("#inf-borrar-sin-dosis");
    nodos.cuerpoTabla = $("#inf-cuerpo-tabla");
    nodos.sinPuntos = $("#inf-sin-puntos");
    nodos.listaTotales = $("#inf-lista-totales");
    nodos.totalPuntos = $("#inf-total-puntos");
    nodos.observaciones = $("#inf-observaciones");

    nodos.sesionesPlegar = $("#inf-sesiones-plegar");
    nodos.sesionesFlecha = $("#inf-sesiones-flecha");
    nodos.sesionesCuantas = $("#inf-sesiones-cuantas");
    nodos.sesionesCuerpo = $("#inf-sesiones-cuerpo");
    nodos.sesionesEstado = $("#inf-sesiones-estado");
    nodos.listaSesiones = $("#inf-lista-sesiones");

    nodos.dlgConfirmar = $("#inf-dlg-confirmar");
    nodos.dlgConfirmarTitulo = $("#inf-dlg-confirmar-titulo");
    nodos.dlgConfirmarTexto = $("#inf-dlg-confirmar-texto");
    nodos.dlgPlantilla = $("#inf-dlg-plantilla");
    nodos.dlgPlantillaTexto = $("#inf-dlg-plantilla-texto");
    nodos.dlgTexto = $("#inf-dlg-texto");
    nodos.dlgTextoTitulo = $("#inf-dlg-texto-titulo");
    nodos.dlgTextoEtiqueta = $("#inf-dlg-texto-etiqueta");
    nodos.dlgTextoCampo = $("#inf-dlg-texto-campo");
    nodos.dlgTextoNota = $("#inf-dlg-texto-nota");
    nodos.dlgElegirVista = $("#inf-dlg-elegir-vista");
    nodos.dlgVistaTexto = $("#inf-dlg-vista-texto");
    nodos.dlgVistaSel = $("#inf-dlg-vista-sel");
    nodos.dlgAjustes = $("#inf-dlg-ajustes");
    nodos.dlgCalibracion = $("#inf-dlg-calibracion");

    nodos.ajCuerpoProductos = $("#inf-aj-cuerpo-productos");
    nodos.ajBtnProducto = $("#inf-aj-btn-producto");
    nodos.ajZonas = $("#inf-aj-zonas");
    nodos.ajListaPlantillas = $("#inf-aj-lista-plantillas");
    nodos.ajExportar = $("#inf-aj-btn-exportar-plantillas");
    nodos.ajImportar = $("#inf-aj-btn-importar-plantillas");
    nodos.ajCalibrar = $("#inf-aj-btn-calibrar");
    nodos.ajCalibFabrica = $("#inf-aj-btn-calib-fabrica");

    nodos.listaZonas = $("#inf-lista-zonas");
    nodos.archivoPlantillas = $("#inf-archivo-plantillas");
    nodos.aviso = $("#inf-aviso");
    return true;
  }

  function productoPorId(id) {
    return estado.sesion.productos.filter((p) => p.id === id)[0] || estado.sesion.productos[0] || null;
  }
  function puntoPorId(id) { return estado.sesion.puntos.filter((p) => p.id === id)[0] || null; }
  function productoParaPuntoNuevo() {
    if (estado.sesion.productos.some((p) => p.id === estado.ui.productoId)) return estado.ui.productoId;
    return (estado.sesion.productos[0] && estado.sesion.productos[0].id) || "";
  }

  function render() {
    if (!estado.montado) return;
    renderCarteles();
    if (cat.estado !== "listo" || !hayMesa()) return;
    renderBarra();
    ajustarMarco();
    renderLamina();
    renderMapa();
    renderLeyenda();
    renderTabla();
    renderTotales();
    renderSesiones();
  }

  /* Todo lo que se dibuja sobre la lámina. */
  function renderMapa() {
    aplicarTransformacion();
    renderMarcadores();
    renderReferencia();
    renderCalibracion();
  }

  /* --- Carteles: sin paciente, catálogo cargando o caído --- */
  function hayMesa() { return estado.pacienteId !== null; }

  function renderCarteles() {
    const cargando = cat.estado === "pidiendo" || cat.estado === "vacio";
    const roto = cat.estado === "error";
    nodos.cartelCatalogo.hidden = !(cargando || roto);
    if (cargando) {
      nodos.catalogoEstado.textContent = "Cargando el catálogo de infiltraciones…";
      nodos.reintentar.hidden = true;
    } else if (roto) {
      nodos.catalogoEstado.textContent = cat.error ||
        "No se pudo traer el catálogo de infiltraciones.";
      nodos.reintentar.hidden = false;
    }
    const listo = cat.estado === "listo";
    nodos.sinPaciente.hidden = !(listo && !hayMesa());
    nodos.mesa.hidden = !(listo && hayMesa());
  }

  /* --- Barra: solo escribe si el valor cambió, para no mover el cursor --- */
  function renderBarra() {
    ponerValor(nodos.fecha, estado.sesion.fecha);
    ponerValor(nodos.selVista, estado.ui.vistaId);
    ponerValor(nodos.selProducto, productoParaPuntoNuevo());
    ponerValor(nodos.observaciones, estado.sesion.observaciones);

    if (nodos.chkDosis.checked !== estado.ui.mostrarDosis) nodos.chkDosis.checked = estado.ui.mostrarDosis;
    if (Number(nodos.rngTam.value) !== estado.ui.tamMarcador) nodos.rngTam.value = String(estado.ui.tamMarcador);

    nodos.chkReferencia.disabled = !estado.ui.sesionReferencia;
    if (nodos.chkReferencia.checked !== estado.ui.refVisible) nodos.chkReferencia.checked = estado.ui.refVisible;
    nodos.etqReferencia.textContent = estado.ui.sesionReferencia
      ? "Ver referencia (" + estado.ui.refEtiqueta + ")"
      : "Ver referencia";

    nodos.btnGuardarPlantilla.disabled = estado.sesion.puntos.length === 0;
    nodos.btnDeshacer.disabled = historial.indice <= 0;
    nodos.btnRehacer.disabled = historial.indice >= historial.pasos.length - 1;
    nodos.btnEspejo.disabled = !estado.ui.seleccionId;
    nodos.btnBorrarSinDosis.disabled = estado.sesion.puntos.length === 0;

    nodos.btnGuardar.disabled = estado.ui.guardando || estado.sesion.puntos.length === 0;
    nodos.btnGuardar.textContent = estado.ui.guardando
      ? "Guardando…"
      : (estado.sesionId ? "Guardar los cambios y rehacer el PDF" : "Guardar y generar PDF");

    // Banda de paciente, con el mismo orden que la de «Nuevo récipe»:
    // código primero y nombre después.
    const pac = estado.paciente || {};
    const codigo = texto(pac.codigo);
    const nombre = texto(pac.nombre) || "(sin nombre)";
    nodos.bandaTexto.textContent = "Infiltraciones de " + (codigo ? codigo + " · " : "") + nombre;
    nodos.bandaSesion.textContent = estado.sesionId
      ? "Corrigiendo la sesión guardada del " + fechaLegible(estado.sesion.fecha) +
        (estado.codigo ? " (" + estado.codigo + ")" : "")
      : "Sesión nueva";
  }

  function ponerValor(nodo, valor) {
    const v = valor === null || valor === undefined ? "" : String(valor);
    if (nodo && nodo.value !== v && document.activeElement !== nodo) nodo.value = v;
  }

  function fechaLegible(iso) {
    if (window.Recipes && Recipes.fechaLegible) return Recipes.fechaLegible(iso);
    const p = String(iso || "").split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : String(iso || "");
  }

  /* --- Lámina: tamaño del marco y fuente de la imagen --- */
  function ajustarMarco() {
    const v = vistaActual();
    if (!v) return;
    const dispW = nodos.areaLienzo.clientWidth - 16;
    const dispH = nodos.areaLienzo.clientHeight - 16;
    if (dispW <= 0 || dispH <= 0) return;          // la pestaña está oculta: nada que medir
    const razon = (v.ancho || 1) / (v.alto || 1);
    let w = dispW, h = w / razon;
    if (h > dispH) { h = dispH; w = h * razon; }
    w = Math.max(1, Math.round(w)); h = Math.max(1, Math.round(h));
    estado.ui.lienzo = { ancho: w, alto: h };
    limitarPan();
    nodos.marco.style.width = w + "px";
    nodos.marco.style.height = h + "px";
    nodos.overlay.setAttribute("viewBox", "0 0 " + w + " " + h);   // 1 unidad SVG = 1 píxel
    nodos.overlay.setAttribute("width", w);
    nodos.overlay.setAttribute("height", h);
  }

  function renderLamina() {
    const v = vistaActual();
    if (!v) return;
    if (nodos.lamina.getAttribute("src") !== v.url) nodos.lamina.setAttribute("src", v.url);
    nodos.lamina.alt = "Lámina anatómica: " + v.etiqueta;
  }

  /* --- Marcadores en el overlay SVG (nunca canvas) --- */
  const SVGNS = "http://www.w3.org/2000/svg";
  function svgEl(nombre, atributos) {
    const n = document.createElementNS(SVGNS, nombre);
    for (const k in atributos) {
      if (Object.prototype.hasOwnProperty.call(atributos, k)) n.setAttribute(k, atributos[k]);
    }
    return n;
  }

  /* --- Desapilado de marcadores ---
     Hay racimos anatómicos (patas de gallo, cola de ceja) cuyos puntos caen a
     6–8 px unos de otros con la lámina ajustada a pantalla: los discos se
     taparían y el número de abajo sería ilegible. Acá se calcula, para cada
     punto, un centro de disco apartado lo justo; el punto anatómico exacto no
     se mueve y queda unido al disco por una línea fina. El reparto es
     determinista: mismo orden de puntos, mismo dibujo. */
  function desapilarMarcadores(centros, radio) {
    const sep = radio * 2 + Math.max(2, radio * 0.28);
    const tope = radio * 2.6;
    const pos = centros.map((c, i) => ({ id: c.id, ax: c.x, ay: c.y, x: c.x, y: c.y, i: i }));
    const n = pos.length;
    if (n < 2) return pos.map((q) => Object.assign(q, { apartado: false }));

    for (let vuelta = 0; vuelta < 90; vuelta++) {
      let mayor = 0;
      for (let i = 0; i < n; i++) {
        for (let j = i + 1; j < n; j++) {
          const a = pos[i], b = pos[j];
          let dx = b.x - a.x, dy = b.y - a.y;
          let d = Math.hypot(dx, dy);
          if (d >= sep) continue;
          if (d < 0.001) {                          // puntos calcados: se abren en abanico
            const ang = (i * 2.399963) + j * 0.7;
            dx = Math.cos(ang); dy = Math.sin(ang); d = 1;
          }
          const empuje = ((sep - d) / 2) * 0.55;
          const ux = dx / d, uy = dy / d;
          a.x -= ux * empuje; a.y -= uy * empuje;
          b.x += ux * empuje; b.y += uy * empuje;
          if (empuje > mayor) mayor = empuje;
        }
      }
      // Cada vuelta tira un poco de vuelta hacia la posición anatómica.
      for (let i = 0; i < n; i++) {
        const q = pos[i];
        const acercar = vuelta < 60 ? 0.06 : 0;
        q.x += (q.ax - q.x) * acercar;
        q.y += (q.ay - q.y) * acercar;
        const dx = q.x - q.ax, dy = q.y - q.ay, d = Math.hypot(dx, dy);
        if (d > tope) { q.x = q.ax + (dx / d) * tope; q.y = q.ay + (dy / d) * tope; }
      }
      if (mayor < 0.08) break;
    }
    return pos.map((q) => Object.assign(q, { apartado: Math.hypot(q.x - q.ax, q.y - q.ay) > 1 }));
  }

  /* Posiciones de disco vigentes en pantalla; las usa el ratón para saber qué
     marcador se pinchó sin depender de quién se dibujó encima. */
  let discosEnPantalla = [];

  function renderMarcadores() {
    const capa = nodos.capaPuntos;
    capa.textContent = "";
    const r = estado.ui.tamMarcador;
    const colocados = desapilarMarcadores(estado.sesion.puntos.map((p) => {
      const q = normalizadaAPantalla(p.x, p.y);
      return { id: p.id, x: q.px, y: q.py };
    }), r);
    discosEnPantalla = colocados;

    // Primero las guías, para que ninguna línea cruce por encima de un disco.
    colocados.forEach((c) => {
      if (!c.apartado) return;
      capa.appendChild(svgEl("line", { "class": "inf-guia-marcador", x1: c.ax, y1: c.ay, x2: c.x, y2: c.y }));
      capa.appendChild(svgEl("circle", {
        "class": "inf-ancla-marcador", cx: c.ax, cy: c.ay,
        r: Math.max(1.6, r * 0.16), fill: colorDePunto(puntoPorId(c.id))
      }));
    });

    estado.sesion.puntos.forEach((p, i) => {
      const c = colocados[i];
      const g = svgEl("g", {
        "class": "inf-marcador" + (p.id === estado.ui.seleccionId ? " inf-seleccionado" : "") +
                 (tieneDosis(p) ? "" : " inf-sin-dosis") +
                 (arrastre.activo && arrastre.id === p.id ? " inf-arrastrando" : ""),
        "transform": "translate(" + c.x + "," + c.y + ")",
        "data-inf-id": p.id
      });
      if (p.id === estado.ui.seleccionId) g.appendChild(svgEl("circle", { "class": "inf-anillo", r: r + 4 }));
      const color = colorDePunto(p);
      g.appendChild(svgEl("circle", { "class": "inf-toque", r: Math.max(r + 8, 18) }));  // clic generoso
      g.appendChild(svgEl("circle", { "class": "inf-disco", r: r, fill: color }));
      // Con radio < 7 el número ya no entra adentro del disco: sale afuera con
      // halo (y ahí va siempre oscuro, porque el fondo es la lámina).
      const num = r >= 7
        ? svgEl("text", {
            "class": "inf-numero" + (numeroOscuro(color) ? " inf-numero-oscuro" : ""),
            "font-size": Math.round(r * 1.15)
          })
        : svgEl("text", { "class": "inf-numero inf-fuera", x: r + 2, y: -(r + 2), "font-size": 10 });
      num.textContent = String(p.orden);
      g.appendChild(num);
      if (estado.ui.mostrarDosis && dosisRellenada(p)) {
        const et = svgEl("text", {
          "class": "inf-etiqueta-dosis",
          y: -(r + (r >= 7 ? 6 : 15)),
          "font-size": Math.max(11, Math.round(r * 0.95))
        });
        et.textContent = textoDosis(p);
        g.appendChild(et);
      }
      capa.appendChild(g);
    });
    // El marcador seleccionado se dibuja el último: su número nunca queda tapado.
    const sel = capa.querySelector(".inf-marcador.inf-seleccionado");
    if (sel) capa.appendChild(sel);
  }

  /* Color del disco: el de su producto y, si ese producto ya no existe, el token. */
  function colorDePunto(p) {
    const prod = p ? productoPorId(p.productoId) : null;
    return (prod && prod.color) || colorDeToken("--inf-sin-producto");
  }

  /* --- El número del marcador, en blanco o en oscuro según el contraste ---
     Los colores de producto son DATOS: vienen del catálogo del servidor y el
     médico puede poner el que quiera desde Ajustes. Con un naranja claro el
     número blanco se queda en 3:1 y deja de leerse, así que acá se mide y se
     elige, que es exactamente lo que hace el PDF del servidor (contrato §4:
     «su número adentro en blanco o negro según el contraste»). Pantalla y
     papel deciden igual, y ningún color que elija el médico puede dejar un
     punto sin número legible. */
  function luminancia(hex) {
    const m = /^#?([0-9a-fA-F]{6})$/.exec(String(hex || "").trim());
    if (!m) return 0;
    const canal = (i) => {
      const v = parseInt(m[1].substr(i * 2, 2), 16) / 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * canal(0) + 0.7152 * canal(1) + 0.0722 * canal(2);
  }
  function contraste(a, b) {
    const la = luminancia(a), lb = luminancia(b);
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
  }
  /* ¿El número de este disco tiene que ir oscuro? Solo si el blanco no llega
     al 4,5:1 que pide un texto chico y el oscuro contrasta mejor que él. */
  function numeroOscuro(colorDisco) {
    const conBlanco = contraste(colorDisco, "#FFFFFF");
    if (conBlanco >= 4.5) return false;
    return contraste(colorDisco, colorDeToken("--texto") || "#1F2937") > conBlanco;
  }

  function colorDeToken(nombre) {
    const panel = document.getElementById("panel-infiltraciones") || document.documentElement;
    return getComputedStyle(panel).getPropertyValue(nombre).trim() || "#1F2937";
  }

  /* Marcador cuyo disco cae más cerca del puntero. Al no depender del orden de
     dibujo, en un racimo se puede agarrar cualquiera y no solo el de encima. */
  function marcadorEnPunto(px, py) {
    const alcance = Math.max(estado.ui.tamMarcador + 8, 18);
    let mejor = null, mejorD = Infinity;
    discosEnPantalla.forEach((c) => {
      const d = Math.hypot(px - c.x, py - c.y);
      if (d <= alcance && d < mejorD) { mejorD = d; mejor = c; }
    });
    return mejor;
  }

  /* Zoom y desplazamiento: la imagen y la capa de marcadores llevan
     exactamente la misma transformación, así los puntos siguen clavados. */
  function aplicarTransformacion() {
    const z = estado.ui.zoom || 1;
    nodos.lamina.style.transform =
      "translate(" + estado.ui.pan.x + "px," + estado.ui.pan.y + "px) scale(" + z + ")";
    nodos.capaZoom.setAttribute("transform",
      "translate(" + estado.ui.pan.x + "," + estado.ui.pan.y + ") scale(" + z + ")");
    nodos.marco.classList.toggle("inf-desplazable", z > 1 || estado.ui.espacioPulsado);
  }

  /* Sesión anterior de referencia: mismos puntos en gris translúcido, debajo.
     Se pasan por su propio marco facial y se devuelven con el marco de hoy,
     porque se guardaron con SU lámina y SU calibración. */
  function renderReferencia() {
    const capa = nodos.capaReferencia;
    capa.textContent = "";
    const ref = estado.ui.sesionReferencia;
    if (!ref || !estado.ui.refVisible) return;
    const r = Math.max(3, estado.ui.tamMarcador - 2);
    const marcoRef = marcoFacial(vistaPorId(ref.vista), ref.calibracion);
    const marcoHoy = marcoFacial();
    (ref.puntos || []).forEach((p) => {
      let x = p.x, y = p.y;
      if (marcoRef && marcoHoy) {
        const f = normalizadaAFacial(p.x, p.y, marcoRef);
        const n = facialANormalizada(f.u, f.v, marcoHoy);
        x = n.x; y = n.y;
      }
      const pos = normalizadaAPantalla(x, y);
      const g = svgEl("g", { "class": "inf-marcador-ref", transform: "translate(" + pos.px + "," + pos.py + ")" });
      g.appendChild(svgEl("circle", { "class": "inf-disco", r: r }));
      // En la capa translúcida un número adentro de un disco chiquito no se lee.
      if (r >= 7) {
        const num = svgEl("text", {
          "class": "inf-numero", "font-size": Math.round(r * 1.05),
          "text-anchor": "middle", "dominant-baseline": "central"
        });
        num.textContent = String(p.orden);
        g.appendChild(num);
      }
      capa.appendChild(g);
    });
  }

  /* Asistente de calibración: previsualización de los 35 puntos y las tres
     referencias arrastrables. */
  const ROTULOS_CALIB = ["Pupila izquierda", "Pupila derecha", "Punta del mentón"];

  function renderCalibracion() {
    const capa = nodos.capaCalibracion;
    capa.textContent = "";
    const mc = estado.ui.modoCalibracion;
    nodos.marco.classList.toggle("inf-calibrando", !!mc);
    nodos.barraCalibracion.hidden = !mc;
    if (!mc) return;

    // Con las tres referencias puestas ya se puede previsualizar.
    if (mc.refs.length === 3) {
      const m = marcoFacial(vistaActual(), calibracionDeRefs(mc.refs));
      if (m) {
        cat.puntos.forEach((def) => {
          const n = facialANormalizada(def.u, def.v, m);
          const pos = normalizadaAPantalla(n.x, n.y);
          capa.appendChild(svgEl("circle", { "class": "inf-punto-previo", cx: pos.px, cy: pos.py, r: 5 }));
        });
      }
    }

    mc.refs.forEach((ref, i) => {
      const pos = normalizadaAPantalla(ref[0], ref[1]);
      const g = svgEl("g", {
        "class": "inf-ref-calib",
        transform: "translate(" + pos.px + "," + pos.py + ")",
        "data-inf-ref": String(i)
      });
      g.appendChild(svgEl("circle", { "class": "inf-toque", r: 20 }));
      g.appendChild(svgEl("circle", { "class": "inf-aro", r: 9 }));
      g.appendChild(svgEl("line", { "class": "inf-cruz", x1: -14, y1: 0, x2: 14, y2: 0 }));
      g.appendChild(svgEl("line", { "class": "inf-cruz", x1: 0, y1: -14, x2: 0, y2: 14 }));
      const t = svgEl("text", { "class": "inf-rotulo", x: 16, y: -12, "font-size": 13 });
      t.textContent = ROTULOS_CALIB[i];
      g.appendChild(t);
      capa.appendChild(g);
    });

    nodos.calibPaso.textContent = mc.refs.length < 3 ? "Paso " + (mc.refs.length + 1) + " de 3" : "Comprobá y guardá";
    nodos.calibInstruccion.textContent = mc.refs.length < 3
      ? "Hacé clic en: " + ROTULOS_CALIB[mc.refs.length].toLowerCase() + "."
      : "Arrastrá las tres marcas hasta que los puntos previos encajen con la anatomía.";
    nodos.calibAceptar.disabled = mc.refs.length < 3;
  }

  function calibracionDeRefs(refs) {
    return {
      pupilaIzq: [refs[0][0], refs[0][1]],
      pupilaDer: [refs[1][0], refs[1][1]],
      menton: [refs[2][0], refs[2][1]]
    };
  }

  /* Dos preguntas distintas:
       dosisRellenada -> ¿el médico escribió una dosis? (un 0 a propósito cuenta)
       tieneDosis     -> ¿esa dosis es mayor que cero? (decide el dibujo)
     «Borrar los puntos sin dosis» usa la primera: un 0 anotado es un dato. */
  function dosisRellenada(p) {
    return p.dosis !== null && p.dosis !== undefined && p.dosis !== "" && Number.isFinite(Number(p.dosis));
  }
  function tieneDosis(p) { return dosisRellenada(p) && Number(p.dosis) > 0; }
  function textoDosis(p) {
    const prod = productoPorId(p.productoId);
    return String(p.dosis) + (prod ? " " + prod.unidad : "");
  }

  /* --- Leyenda de productos usados --- */
  function renderLeyenda() {
    const cont = nodos.leyenda;
    cont.textContent = "";
    const usados = estado.sesion.productos.filter(
      (pr) => estado.sesion.puntos.some((p) => p.productoId === pr.id)
    );
    if (!usados.length) {
      const vacio = document.createElement("span");
      vacio.textContent = "Sin puntos: la leyenda aparece al agregar el primero.";
      cont.appendChild(vacio);
      return;
    }
    usados.forEach((pr) => {
      const chip = document.createElement("span");
      chip.className = "inf-chip-leyenda";
      const bola = document.createElement("span");
      bola.className = "inf-chip-color";
      bola.style.background = pr.color;
      const txt = document.createElement("span");
      txt.textContent = pr.nombre + " (" + pr.unidad + ")";
      chip.appendChild(bola);
      chip.appendChild(txt);
      cont.appendChild(chip);
    });
  }

  /* --- Tabla del panel derecho --- */
  /* Los grupos TAL COMO ESTÁN DIBUJADOS ahora mismo: qué región, con qué
     puntos y con qué botón de cabecera. Lo llena `renderTabla()` y lo lee
     `refrescarPorDosis()` para recalcular subtotales sin reconstruir las filas
     (reconstruirlas le sacaría el cursor de la casilla al médico a mitad de un
     número). Se guardan los IDS y no los puntos: así el subtotal sale siempre
     de la dosis de AHORA, y la cabecera resume exactamente las filas que están
     debajo de ella, incluso si el grupo está plegado. */
  let gruposDibujados = [];

  function renderTabla() {
    const cuerpo = nodos.cuerpoTabla;
    const foco = recordarFoco();
    cuerpo.textContent = "";
    nodos.sinPuntos.hidden = estado.sesion.puntos.length > 0;
    gruposDibujados = [];

    gruposDePuntos().forEach((g) => {
      const tr = filaDeGrupo(g);
      cuerpo.appendChild(tr);
      gruposDibujados.push({
        region: g.region,
        etiqueta: g.etiqueta,
        ids: g.puntos.map((p) => p.id),
        boton: tr.querySelector(".inf-cabecera-grupo")
      });
      if (estado.ui.gruposPlegados[g.region]) return;
      g.puntos.forEach((p) => cuerpo.appendChild(filaDePunto(p)));
    });
    restaurarFoco(foco);
  }

  /* ------------------------------------------------------------------
     PRUEBA DE HUMO de `refrescarPorDosis()` — el invariante que se rompió.

     INVARIANTE: en una herramienta que registra dosis nunca pueden convivir
     en la pantalla dos cifras distintas de la misma dosis. El subtotal de la
     cabecera de región se tiene que mover con la MISMA tecla con la que se
     mueve el total por producto de abajo.

     Se toca UNA sola cosa: la casilla «Dosis» de una fila (cada tecla, sin
     salir del campo). Se tienen que mover, en el acto y todas juntas:
       1. el subtotal de la cabecera de SU región      («▾ Frente (8) 16 U»)
       2. los totales por producto de abajo            («… · 16 U · 35 puntos»)
       3. el contador de «sin dosis» del pie de la tabla
       4. el marcador en el mapa: deja de estar hueco (`.inf-sin-dosis`) en
          cuanto la dosis pasa de vacía a mayor que cero
       5. la etiqueta de dosis sobre el marcador, si «Dosis en el mapa» está
          tildado

     Cómo se rompió: la escritura en caliente repintaba (2), (3), (4) y (5)
     —`renderMarcadores()` + `renderTotales()`— pero la cabecera del grupo solo
     se escribía al reconstruir la tabla entera, o sea al salir del campo. Con
     cinco dosis escritas de a una la cabecera quedaba mostrando la primera.
     Por eso ahora hay un solo camino y no dos: todo lo que depende de la dosis
     se refresca desde acá, y `pintarCabeceraGrupo()` es el único lugar donde
     se escribe el texto de una cabecera, la dibuje quien la dibuje.
     ------------------------------------------------------------------ */
  function refrescarPorDosis() {
    renderMarcadores();          // huecos/llenos y etiquetas de dosis
    renderSubtotalesDeGrupos();  // cabeceras de región
    renderTotales();             // totales por producto y contador de «sin dosis»
  }

  /* Reescribe el texto de las cabeceras que ya están en pantalla, sin tocar
     ninguna fila. */
  function renderSubtotalesDeGrupos() {
    gruposDibujados.forEach((g) => {
      if (!g.boton || !g.boton.isConnected) return;
      const puntos = g.ids.map(puntoPorId).filter(Boolean);
      pintarCabeceraGrupo(g.boton, g.etiqueta, puntos, !!estado.ui.gruposPlegados[g.region]);
    });
  }

  /* Puntos repartidos por región en el orden de REGIONES. */
  function gruposDePuntos() {
    const porRegion = {};
    estado.sesion.puntos.forEach((p) => {
      const r = regionDeZona(p.zona);
      if (!porRegion[r]) porRegion[r] = [];
      porRegion[r].push(p);
    });
    const orden = REGIONES.map((r) => r.id);
    Object.keys(porRegion).forEach((k) => { if (orden.indexOf(k) < 0) orden.push(k); });
    /* No se devuelve el subtotal ya calculado a propósito: lo saca
       `pintarCabeceraGrupo()` de los puntos, y así hay una sola cuenta.
       Un subtotal guardado acá sería una segunda copia de la misma cifra, que
       es exactamente de donde salió el defecto de la cabecera vieja. */
    return orden.filter((id) => porRegion[id]).map((id) => ({
      region: id,
      etiqueta: id === "otras" ? "Otras / sin zona" : etiquetaRegion(id),
      puntos: porRegion[id]
    }));
  }

  function subtotalesDe(puntos) {
    const res = [];
    estado.sesion.productos.forEach((pr) => {
      const suyos = puntos.filter((p) => p.productoId === pr.id);
      if (!suyos.length) return;
      res.push({
        producto: pr,
        total: suyos.reduce((s, p) => s + (Number(p.dosis) || 0), 0),
        puntos: suyos.length
      });
    });
    return res;
  }

  function textoSubtotal(subtotales) {
    return subtotales.filter((s) => s.total > 0)
      .map((s) => redondear(s.total) + " " + s.producto.unidad)
      .join(" · ");
  }

  function filaDeGrupo(g) {
    const tr = document.createElement("tr");
    tr.className = "inf-fila-grupo";
    const td = document.createElement("td");
    td.colSpan = 7;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "inf-cabecera-grupo";
    btn.dataset.infAccion = "plegar";
    btn.dataset.infRegion = g.region;

    // Los cuatro huecos se crean vacíos y los llena `pintarCabeceraGrupo()`,
    // que es la MISMA función que después los actualiza en caliente.
    ["inf-flecha", "inf-nombre-grupo", "inf-cuantos", "inf-subtotal"].forEach((clase) => {
      const s = document.createElement("span");
      s.className = clase;
      if (clase === "inf-flecha") s.setAttribute("aria-hidden", "true");
      btn.appendChild(s);
    });
    pintarCabeceraGrupo(btn, g.etiqueta, g.puntos, !!estado.ui.gruposPlegados[g.region]);

    td.appendChild(btn);
    tr.appendChild(td);
    return tr;
  }

  /* EL único lugar donde se escribe el texto de una cabecera de región. La
     usan tanto el dibujo completo de la tabla como el refresco en caliente:
     mientras siga siendo una sola, las dos cifras no se pueden separar. */
  function pintarCabeceraGrupo(btn, etiqueta, puntos, plegado) {
    btn.setAttribute("aria-expanded", String(!plegado));
    btn.title = (plegado ? "Desplegar" : "Plegar") + " el grupo " + etiqueta;
    btn.querySelector(".inf-flecha").textContent = plegado ? "▸" : "▾";
    btn.querySelector(".inf-nombre-grupo").textContent = etiqueta;
    btn.querySelector(".inf-cuantos").textContent = "(" + puntos.length + ")";
    btn.querySelector(".inf-subtotal").textContent =
      textoSubtotal(subtotalesDe(puntos)) || "sin dosis";
  }

  function filaDePunto(p) {
    const prod = productoPorId(p.productoId);
    const tr = document.createElement("tr");
    tr.id = "inf-fila-" + p.id;
    tr.dataset.infId = p.id;
    if (p.id === estado.ui.seleccionId) tr.classList.add("inf-seleccionada");

    // N.º + color del producto
    const tdNum = document.createElement("td");
    tdNum.className = "inf-celda-num inf-col-num";
    const bola = document.createElement("span");
    bola.className = "inf-punto-color";
    bola.style.background = colorDePunto(p);
    tdNum.appendChild(bola);
    tdNum.appendChild(document.createTextNode(String(p.orden)));
    tr.appendChild(tdNum);

    // Lado (deducido, editable)
    const tdLado = document.createElement("td");
    tdLado.className = "inf-col-lado";
    const selLado = document.createElement("select");
    selLado.className = "inf-control";
    selLado.dataset.infCampo = "lado";
    selLado.title = TITULO_LADO;
    [["I", "Izquierdo del paciente"], ["D", "Derecho del paciente"], ["C", "Central / línea media"]]
      .forEach((par) => {
        const o = document.createElement("option");
        o.value = par[0]; o.textContent = par[0]; o.title = par[1];
        selLado.appendChild(o);
      });
    selLado.value = p.lado || "C";
    tdLado.appendChild(selLado);
    tr.appendChild(tdLado);

    // Zona (desplegable con búsqueda: input + datalist)
    const tdZona = document.createElement("td");
    const inZona = document.createElement("input");
    inZona.type = "text";
    inZona.className = "inf-control";
    inZona.setAttribute("list", "inf-lista-zonas");
    inZona.setAttribute("maxlength", "80");
    inZona.dataset.infCampo = "zona";
    inZona.value = p.zona || "";
    inZona.placeholder = "Zona anatómica";
    inZona.title = p.zona || "Zona anatómica (escribí para buscar en el catálogo)";
    tdZona.appendChild(inZona);
    tr.appendChild(tdZona);

    // Producto
    const tdProd = document.createElement("td");
    tdProd.className = "inf-col-producto";
    const selProd = document.createElement("select");
    selProd.className = "inf-control";
    selProd.dataset.infCampo = "productoId";
    estado.sesion.productos.forEach((pr) => {
      const o = document.createElement("option");
      o.value = pr.id; o.textContent = pr.nombre;
      selProd.appendChild(o);
    });
    selProd.value = p.productoId || "";
    selProd.title = prod ? prod.nombre : "";
    tdProd.appendChild(selProd);
    tr.appendChild(tdProd);

    // Dosis + unidad del producto (la unidad la fija el producto)
    const tdDosis = document.createElement("td");
    tdDosis.className = "inf-col-dosis";
    const caja = document.createElement("div");
    caja.className = "inf-caja-dosis";
    const inDosis = document.createElement("input");
    inDosis.type = "number";
    inDosis.className = "inf-control";
    inDosis.min = "0";
    inDosis.max = String(MAX_DOSIS);
    inDosis.step = "0.5";
    inDosis.dataset.infCampo = "dosis";
    inDosis.value = (p.dosis === null || p.dosis === undefined) ? "" : String(p.dosis);
    const unidad = document.createElement("span");
    unidad.className = "inf-unidad";
    unidad.textContent = prod ? prod.unidad : "";
    caja.appendChild(inDosis);
    caja.appendChild(unidad);
    tdDosis.appendChild(caja);
    tr.appendChild(tdDosis);

    // Notas
    const tdNotas = document.createElement("td");
    tdNotas.className = "inf-col-notas";
    const inNotas = document.createElement("input");
    inNotas.type = "text";
    inNotas.className = "inf-control";
    inNotas.dataset.infCampo = "notas";
    inNotas.maxLength = 60;
    inNotas.value = p.notas || "";
    inNotas.title = p.notas || "Nota breve";
    tdNotas.appendChild(inNotas);
    tr.appendChild(tdNotas);

    // Borrar
    const tdBorrar = document.createElement("td");
    tdBorrar.className = "inf-col-borrar";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "inf-boton-icono";
    btn.dataset.infAccion = "borrar";
    btn.title = "Borrar el punto " + p.orden;
    btn.setAttribute("aria-label", "Borrar el punto " + p.orden);
    btn.textContent = "✕";
    tdBorrar.appendChild(btn);
    tr.appendChild(tdBorrar);

    return tr;
  }

  /* Recuerda qué celda tenía el foco para devolverlo tras reconstruir la tabla. */
  function recordarFoco() {
    const a = document.activeElement;
    if (!a || !a.closest) return null;
    const tr = a.closest("#inf-cuerpo-tabla tr");
    if (!tr) return null;
    return {
      id: tr.dataset.infId,
      campo: a.dataset.infCampo || null,
      inicio: a.selectionStart,
      fin: a.selectionEnd
    };
  }
  function restaurarFoco(f) {
    if (!f || !f.campo || !f.id) return;
    const nodo = document.querySelector(
      "#inf-fila-" + CSS.escape(f.id) + ' [data-inf-campo="' + f.campo + '"]'
    );
    if (!nodo) return;
    nodo.focus();
    if (typeof nodo.setSelectionRange === "function" && f.inicio !== null && f.inicio !== undefined && nodo.type !== "number") {
      try { nodo.setSelectionRange(f.inicio, f.fin); } catch (e) { /* campos sin selección */ }
    }
  }

  /* --- Totales en vivo por producto --- */
  function renderTotales() {
    const cont = nodos.listaTotales;
    cont.textContent = "";
    let algo = false;
    estado.sesion.productos.forEach((pr) => {
      const puntos = estado.sesion.puntos.filter((p) => p.productoId === pr.id);
      if (!puntos.length) return;
      algo = true;
      const total = puntos.reduce((s, p) => s + (Number(p.dosis) || 0), 0);
      const fila = document.createElement("div");
      fila.className = "inf-fila-total";
      const bola = document.createElement("span");
      bola.className = "inf-chip-color";
      bola.style.background = pr.color;
      const nombre = document.createElement("span");
      nombre.className = "inf-nombre";
      nombre.textContent = pr.nombre;
      const valor = document.createElement("span");
      valor.className = "inf-valor";
      valor.textContent = redondear(total) + " " + pr.unidad + " · " +
        puntos.length + (puntos.length === 1 ? " punto" : " puntos");
      fila.appendChild(bola);
      fila.appendChild(nombre);
      fila.appendChild(valor);
      cont.appendChild(fila);
    });
    if (!algo) {
      const p = document.createElement("div");
      p.className = "inf-nota";
      p.textContent = "Sin dosis registradas.";
      cont.appendChild(p);
    }
    const n = estado.sesion.puntos.length;
    const sinDosis = estado.sesion.puntos.filter((p) => !dosisRellenada(p)).length;
    nodos.totalPuntos.textContent = n + (n === 1 ? " punto" : " puntos") +
      (sinDosis ? " · " + sinDosis + " sin dosis" : "");
  }

  /* --- Sesiones anteriores del paciente --- */
  function renderSesiones() {
    nodos.sesionesFlecha.textContent = estado.ui.sesionesAbiertas ? "▾" : "▸";
    nodos.sesionesPlegar.setAttribute("aria-expanded", String(estado.ui.sesionesAbiertas));
    nodos.sesionesCuerpo.hidden = !estado.ui.sesionesAbiertas;
    nodos.sesionesCuantas.textContent =
      listaSesiones.estado === "listo" ? "(" + listaSesiones.filas.length + ")" : "";

    if (listaSesiones.estado === "pidiendo") {
      nodos.sesionesEstado.hidden = false;
      nodos.sesionesEstado.textContent = "Cargando…";
    } else if (listaSesiones.estado === "error") {
      nodos.sesionesEstado.hidden = false;
      nodos.sesionesEstado.textContent = listaSesiones.error;
    } else if (listaSesiones.estado === "listo" && !listaSesiones.filas.length) {
      nodos.sesionesEstado.hidden = false;
      nodos.sesionesEstado.textContent = "Este paciente todavía no tiene mapas guardados.";
    } else {
      nodos.sesionesEstado.hidden = true;
    }

    const ul = nodos.listaSesiones;
    ul.textContent = "";
    listaSesiones.filas.forEach((f) => {
      const li = document.createElement("li");
      if (String(f.id) === String(estado.sesionId)) li.classList.add("inf-sesion-abierta");

      const cont = document.createElement("span");
      cont.className = "inf-sesion-texto";
      const fecha = document.createElement("span");
      fecha.className = "inf-sesion-fecha";
      fecha.textContent = fechaLegible(f.fecha);
      cont.appendChild(fecha);
      const detalle = document.createElement("span");
      detalle.className = "inf-sesion-detalle";
      const trozos = [];
      if (Number.isFinite(Number(f.puntos))) trozos.push(Number(f.puntos) + " puntos");
      if (texto(f.vista)) trozos.push(texto(f.vista));
      detalle.textContent = trozos.length ? " · " + trozos.join(" · ") : "";
      cont.appendChild(detalle);
      if (f.anulado) {
        const an = document.createElement("span");
        an.className = "inf-sesion-anulada";
        an.textContent = " · anulada";
        cont.appendChild(an);
      }
      li.appendChild(cont);

      li.appendChild(botonSesion("Abrir", "Reabrir este mapa para corregirlo", () => abrirSesionGuardada(f.id)));
      li.appendChild(botonSesion("Abrir PDF", "Abrir el PDF guardado en el visor", (b) => abrirPdfDeSesion(f.id, b)));
      li.appendChild(botonSesion("Referencia", "Dibujarlo en gris debajo del mapa de hoy", () => usarComoReferencia(f.id)));

      ul.appendChild(li);
    });
  }

  function botonSesion(rotulo, titulo, alPulsar) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "inf-boton inf-boton-chico";
    b.textContent = rotulo;
    b.title = titulo;
    b.addEventListener("click", () => alPulsar(b));
    return b;
  }

  /* --- Aviso breve (no bloqueante) --- */
  let temporizadorAviso = null;
  function avisar(t) {
    if (!nodos.aviso) return;
    nodos.aviso.textContent = t;
    nodos.aviso.hidden = false;
    clearTimeout(temporizadorAviso);
    temporizadorAviso = setTimeout(() => { nodos.aviso.hidden = true; }, 4000);
  }

  function mostrarError(t) {
    nodos.error.textContent = t;
    nodos.error.hidden = false;
    nodos.exito.hidden = true;
  }
  function mostrarExito(t) {
    nodos.exito.textContent = t;
    nodos.exito.hidden = false;
    nodos.error.hidden = true;
  }
  function limpiarMensajes() {
    nodos.error.hidden = true;
    nodos.exito.hidden = true;
  }

  /* ============================================================
     F. EVENTOS
     ============================================================ */

  function numeroSiguienteDeId() {
    let max = 0;
    estado.sesion.puntos.forEach((p) => {
      const n = parseInt(String(p.id).replace(/^\D+/, ""), 10);
      if (!isNaN(n) && n > max) max = n;
    });
    return max + 1;
  }
  function nuevoIdPunto() { return "n" + numeroSiguienteDeId(); }
  function renumerar() { estado.sesion.puntos.forEach((p, i) => { p.orden = i + 1; }); }

  function crearPunto(x, y) {
    if (estado.sesion.puntos.length >= MAX_PUNTOS) {
      avisar("Una sesión admite hasta " + MAX_PUNTOS + " puntos.");
      return;
    }
    const p = {
      id: nuevoIdPunto(),
      orden: estado.sesion.puntos.length + 1,
      x: redondear5(x),
      y: redondear5(y),
      lado: ladoDesdeNormalizada(x, y),
      zona: "",
      productoId: productoParaPuntoNuevo(),
      dosis: null,
      notas: "",
      plantillaId: null,
      manual: true
    };
    estado.sesion.puntos.push(p);
    renumerar();
    estado.ui.seleccionId = p.id;
    desplegarGrupoDe(p.id);
    registrar();
    render();
    enfocarDosis(p.id);
  }

  /* Si el punto vive en un grupo plegado no habría fila que enfocar: se despliega. */
  function desplegarGrupoDe(id) {
    const p = puntoPorId(id);
    if (!p) return;
    const region = regionDeZona(p.zona);
    if (estado.ui.gruposPlegados[region]) estado.ui.gruposPlegados[region] = false;
  }

  function enfocarDosis(id) {
    const nodo = document.querySelector("#inf-fila-" + CSS.escape(id) + ' [data-inf-campo="dosis"]');
    if (nodo) { nodo.focus(); nodo.select(); }
  }

  function seleccionar(id, desplazar) {
    estado.ui.seleccionId = id;
    if (id) desplegarGrupoDe(id);
    render();
    if (desplazar && id) {
      const tr = document.getElementById("inf-fila-" + id);
      if (tr) tr.scrollIntoView({ block: "nearest" });
    }
  }

  function borrarPunto(id) {
    const i = estado.sesion.puntos.findIndex((p) => p.id === id);
    if (i < 0) return;
    estado.sesion.puntos.splice(i, 1);
    renumerar();
    if (estado.ui.seleccionId === id) estado.ui.seleccionId = null;
    registrar();
    render();
  }

  function borrarPuntosSinDosis() {
    const antes = estado.sesion.puntos.length;
    // Solo se van los que nadie rellenó: un 0 escrito a mano es un dato registrado.
    estado.sesion.puntos = estado.sesion.puntos.filter((p) => dosisRellenada(p));
    const quitados = antes - estado.sesion.puntos.length;
    if (!quitados) { avisar("No hay puntos sin dosis."); return; }
    renumerar();
    if (!puntoPorId(estado.ui.seleccionId)) estado.ui.seleccionId = null;
    registrar();
    render();
    avisar(quitados + (quitados === 1 ? " punto borrado." : " puntos borrados."));
  }

  /* ---- Interacción con el lienzo (pointer events) ----
     Tres tipos de arrastre: 'punto' (mover un marcador), 'pan' (desplazar la
     lámina con el botón central o con espacio pulsado) y 'ref' (mover una de
     las tres referencias de calibración). */
  const arrastre = {
    activo: false, id: null, movido: false, x0: 0, y0: 0,
    tipo: null, ref: -1, pan0: null, desfase: { x: 0, y: 0 }
  };
  let selloPuntero = 0;
  let observadorLienzo = null;

  function conectarLienzo() {
    const marco = nodos.marco;

    marco.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 && e.button !== 1) return;
      selloPuntero = Date.now();
      arrastre.movido = false;
      arrastre.x0 = e.clientX; arrastre.y0 = e.clientY;
      arrastre.tipo = null; arrastre.ref = -1;

      // Desplazar: botón central o espacio mantenido.
      if (e.button === 1 || estado.ui.espacioPulsado) {
        e.preventDefault();
        arrastre.activo = true; arrastre.tipo = "pan";
        arrastre.pan0 = { x: estado.ui.pan.x, y: estado.ui.pan.y };
        marco.classList.add("inf-desplazando");
        capturar(marco, e);
        return;
      }

      // Calibrando: solo se arrastran las tres referencias.
      if (estado.ui.modoCalibracion) {
        const r = e.target.closest ? e.target.closest(".inf-ref-calib") : null;
        if (r) {
          arrastre.activo = true; arrastre.tipo = "ref"; arrastre.ref = Number(r.dataset.infRef);
          capturar(marco, e);
        }
        return;
      }

      const c = marcadorDeEvento(e);
      if (c) {
        arrastre.activo = true;
        arrastre.tipo = "punto";
        arrastre.id = c.id;
        // Se guarda la distancia entre el puntero y el punto: al arrastrar no
        // da un salto, ni siquiera con el disco apartado de su anatomía.
        const p = puntoPorId(c.id);
        const n = coordenadasDeEvento(e);
        arrastre.desfase = p ? { x: p.x - n.x, y: p.y - n.y } : { x: 0, y: 0 };
        capturar(marco, e);
        if (estado.ui.seleccionId !== arrastre.id) seleccionar(arrastre.id, true);
        // seleccionar() repinta el overlay: hay que volver a buscar el nodo.
        const nodo = nodos.capaPuntos.querySelector('[data-inf-id="' + CSS.escape(arrastre.id) + '"]');
        if (nodo) nodo.classList.add("inf-arrastrando");
      } else {
        arrastre.activo = false;
        arrastre.id = null;
      }
    });

    marco.addEventListener("pointermove", (e) => {
      if (!arrastre.activo) return;
      if (Math.abs(e.clientX - arrastre.x0) + Math.abs(e.clientY - arrastre.y0) > 3) arrastre.movido = true;
      if (!arrastre.movido) return;

      if (arrastre.tipo === "pan") {
        estado.ui.pan.x = arrastre.pan0.x + (e.clientX - arrastre.x0);
        estado.ui.pan.y = arrastre.pan0.y + (e.clientY - arrastre.y0);
        limitarPan();
        aplicarTransformacion();
        return;
      }
      if (arrastre.tipo === "ref" && estado.ui.modoCalibracion) {
        const c = coordenadasDeEvento(e);
        estado.ui.modoCalibracion.refs[arrastre.ref] = [redondear5(c.x), redondear5(c.y)];
        renderCalibracion();
        return;
      }
      if (arrastre.tipo === "punto") {
        const p = puntoPorId(arrastre.id);
        if (!p) return;
        const n = coordenadasDeEvento(e);
        const d = arrastre.desfase || { x: 0, y: 0 };
        const c = { x: Math.min(1, Math.max(0, n.x + d.x)), y: Math.min(1, Math.max(0, n.y + d.y)) };
        p.x = redondear5(c.x); p.y = redondear5(c.y);
        p.lado = ladoDesdeNormalizada(p.x, p.y);
        p.manual = true;                        // la posición manual manda sobre la plantilla
        renderMarcadores();                     // durante el arrastre solo se repinta el mapa
      }
    });

    marco.addEventListener("pointerup", (e) => {
      selloPuntero = Date.now();
      try {
        if (marco.hasPointerCapture && marco.hasPointerCapture(e.pointerId)) marco.releasePointerCapture(e.pointerId);
      } catch (err) { /* nada que liberar */ }
      marco.classList.remove("inf-desplazando");
      const g = nodos.capaPuntos.querySelector(".inf-arrastrando");
      if (g) g.classList.remove("inf-arrastrando");

      const tipo = arrastre.tipo, movido = arrastre.movido, id = arrastre.id;
      arrastre.activo = false; arrastre.tipo = null; arrastre.id = null; arrastre.ref = -1;

      if (tipo === "pan") return;

      // Calibrando: cada clic sin arrastre coloca la siguiente referencia.
      if (estado.ui.modoCalibracion) {
        if (!movido && tipo !== "ref" && estado.ui.modoCalibracion.refs.length < 3) {
          const c = coordenadasDeEvento(e);
          estado.ui.modoCalibracion.refs.push([redondear5(c.x), redondear5(c.y)]);
          renderCalibracion();
        }
        return;
      }

      if (tipo === "punto" && id) {
        if (movido) { registrar(); render(); }
        return;
      }
      // Clic en zona vacía de la lámina = punto nuevo.
      if (!movido && !marcadorDeEvento(e)) {
        const c = coordenadasDeEvento(e);
        crearPunto(c.x, c.y);
      }
    });

    marco.addEventListener("pointercancel", () => {
      arrastre.activo = false; arrastre.id = null; arrastre.movido = false; arrastre.tipo = null;
      marco.classList.remove("inf-desplazando");
    });
    marco.addEventListener("auxclick", (e) => { if (e.button === 1) e.preventDefault(); });

    // Respaldo para entornos que solo emiten eventos de ratón.
    marco.addEventListener("click", (e) => {
      if (Date.now() - selloPuntero < 800) return;
      if (estado.ui.modoCalibracion) {
        if (estado.ui.modoCalibracion.refs.length < 3) {
          const cc = coordenadasDeEvento(e);
          estado.ui.modoCalibracion.refs.push([redondear5(cc.x), redondear5(cc.y)]);
          renderCalibracion();
        }
        return;
      }
      const c0 = marcadorDeEvento(e);
      if (c0) { seleccionar(c0.id, true); return; }
      const c = coordenadasDeEvento(e);
      crearPunto(c.x, c.y);
    });

    // Rueda = zoom centrado en el cursor.
    marco.addEventListener("wheel", (e) => {
      e.preventDefault();
      const r = marco.getBoundingClientRect();
      zoom(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top);
    }, { passive: false });

    // El marco se redimensiona con la ventana (y al abrirse la pestaña, que es
    // cuando pasa de 0 px a su tamaño real): recalcular y repintar.
    if (typeof ResizeObserver === "function") {
      // Se guarda la referencia a propósito: un observador sin nadie que lo
      // sostenga es carne de recolector de basura en algunos motores.
      observadorLienzo = new ResizeObserver(() => { ajustarMarco(); renderMapa(); });
      observadorLienzo.observe(nodos.areaLienzo);
    } else {
      window.addEventListener("resize", () => { ajustarMarco(); renderMapa(); });
    }

    // La lámina puede llegar después del primer render; y si el catálogo no
    // trajo las medidas nativas, se toman de la propia imagen.
    nodos.lamina.addEventListener("load", () => {
      const v = vistaActual();
      if (v && (!v.ancho || !v.alto) && nodos.lamina.naturalWidth) {
        v.ancho = nodos.lamina.naturalWidth;
        v.alto = nodos.lamina.naturalHeight;
      }
      ajustarMarco();
      renderMapa();
    });
    nodos.lamina.addEventListener("error", () => {
      const v = vistaActual();
      avisar("No se pudo cargar la lámina" + (v ? " «" + v.etiqueta + "»" : "") + ".");
    });
  }

  function capturar(nodo, e) {
    try { nodo.setPointerCapture(e.pointerId); } catch (err) { /* algunos entornos no lo permiten */ }
  }

  function marcadorDeEvento(e) {
    const r = nodos.marco.getBoundingClientRect();
    const z = estado.ui.zoom || 1;
    const px = (e.clientX - r.left - estado.ui.pan.x) / z;
    const py = (e.clientY - r.top - estado.ui.pan.y) / z;
    return marcadorEnPunto(px, py);
  }

  function coordenadasDeEvento(e) {
    const r = nodos.marco.getBoundingClientRect();
    return marcoANormalizada(e.clientX - r.left, e.clientY - r.top);
  }

  /* ---- Tabla: edición y sincronización con el mapa (en los dos sentidos) ---- */
  function conectarTabla() {
    const cuerpo = nodos.cuerpoTabla;

    cuerpo.addEventListener("pointerdown", (e) => {
      const tr = e.target.closest("tr");
      if (!tr || !tr.dataset.infId) return;        // las cabeceras de grupo no seleccionan
      if (estado.ui.seleccionId !== tr.dataset.infId) {
        estado.ui.seleccionId = tr.dataset.infId;
        Array.prototype.forEach.call(cuerpo.querySelectorAll("tr"),
          (f) => f.classList.toggle("inf-seleccionada", f === tr));
        renderMarcadores();
        renderBarra();
      }
    });

    // Escritura: actualiza el modelo sin reconstruir la tabla (no se pierde el cursor)
    cuerpo.addEventListener("input", (e) => {
      const tr = e.target.closest("tr"); if (!tr) return;
      const p = puntoPorId(tr.dataset.infId); if (!p) return;
      const campo = e.target.dataset.infCampo;
      if (campo === "dosis") {
        const v = e.target.value;
        p.dosis = (v === "" ? null : Number(v));
        marcarCambios();
        // Un solo camino para TODO lo que depende de la dosis (ver la prueba
        // de humo arriba de `refrescarPorDosis`).
        refrescarPorDosis();
        return;
      }
      if (campo === "zona" || campo === "notas") {
        p[campo] = e.target.value;
        e.target.title = e.target.value;   // la columna es angosta: el texto entero, en el título
        marcarCambios();
        /* La zona decide en qué región cae el punto, pero reagrupar la tabla
           con cada tecla le sacaría el cursor al médico a mitad de palabra: el
           punto se muda de grupo al cerrar el campo (`change`), que es cuando
           la zona está escrita. Ninguna cifra de dosis depende de esto, así
           que el invariante de arriba no se toca. */
      }
    });

    // Cambios cerrados (select, blur de un número): un paso de deshacer
    cuerpo.addEventListener("change", (e) => {
      const tr = e.target.closest("tr"); if (!tr) return;
      const p = puntoPorId(tr.dataset.infId); if (!p) return;
      const campo = e.target.dataset.infCampo;
      if (campo === "lado") {
        p.lado = e.target.value;
      } else if (campo === "productoId") {
        p.productoId = e.target.value;
        estado.ui.productoId = e.target.value;   // los puntos nuevos heredan el último producto
      } else if (campo === "dosis") {
        const v = e.target.value;
        let d = v === "" ? null : Number(v);
        if (d !== null && Number.isFinite(d)) {
          // Los topes del contrato se respetan acá, no al mandar: el médico ve
          // en el acto qué quedó anotado.
          if (d < 0) d = 0;
          if (d > MAX_DOSIS) { d = MAX_DOSIS; avisar("La dosis máxima que admite el registro es " + MAX_DOSIS + "."); }
        }
        p.dosis = d;
      } else if (campo === "zona" || campo === "notas") {
        p[campo] = e.target.value;
      } else {
        return;
      }
      registrar();
      render();
    });

    cuerpo.addEventListener("click", (e) => {
      const plegar = e.target.closest('[data-inf-accion="plegar"]');
      if (plegar) {
        const r = plegar.dataset.infRegion;
        estado.ui.gruposPlegados[r] = !estado.ui.gruposPlegados[r];
        renderTabla();
        return;
      }
      const btn = e.target.closest('[data-inf-accion="borrar"]');
      if (!btn) return;
      const tr = btn.closest("tr");
      if (tr && tr.dataset.infId) borrarPunto(tr.dataset.infId);
    });
  }

  /* ---- Barras de botones ---- */
  function conectarBarras() {
    nodos.irHistoria.addEventListener("click", () => Recipes.irAPestana("panel-historia"));
    nodos.bandaCambiar.addEventListener("click", () => Recipes.irAPestana("panel-historia"));
    nodos.reintentar.addEventListener("click", () => { cat.estado = "vacio"; asegurarCatalogo(); });

    nodos.avisoPacienteCambiar.addEventListener("click", async () => {
      const pac = pacienteAbierto();
      if (!pac) { Recipes.irAPestana("panel-historia"); return; }
      const si = await confirmar(
        "El mapa que está en pantalla no se guardó todavía y se va a perder. ¿Cambiar a " +
        texto(pac.nombre) + "?", "Cambiar de paciente");
      if (!si) return;
      adoptarPaciente(pac);
    });

    nodos.fecha.addEventListener("input", () => { estado.sesion.fecha = nodos.fecha.value; marcarCambios(); });
    nodos.fecha.addEventListener("change", () => { estado.sesion.fecha = nodos.fecha.value; registrar(); render(); });

    nodos.observaciones.addEventListener("input", () => {
      estado.sesion.observaciones = nodos.observaciones.value;
      marcarCambios();
    });
    nodos.observaciones.addEventListener("change", () => {
      estado.sesion.observaciones = nodos.observaciones.value;
      registrar();
    });

    nodos.selVista.addEventListener("change", (e) => cambiarVista(e.target.value));

    nodos.selPlantilla.addEventListener("change", async (e) => {
      const id = e.target.value;
      e.target.value = "";
      if (!id) return;
      await aplicarPlantilla(id);
      // El foco sale del desplegable: así el mapa recibe Ctrl+Z, Supr y M.
      if (document.activeElement === e.target) e.target.blur();
    });

    nodos.selProducto.addEventListener("change", (e) => {
      estado.ui.productoId = e.target.value;
      avisar("Los puntos nuevos van a nacer con este producto.");
    });

    nodos.chkDosis.addEventListener("change", (e) => { estado.ui.mostrarDosis = e.target.checked; renderMapa(); });
    nodos.rngTam.addEventListener("input", (e) => { estado.ui.tamMarcador = Number(e.target.value); renderMapa(); });
    nodos.chkReferencia.addEventListener("change", (e) => { estado.ui.refVisible = e.target.checked; renderMapa(); });

    nodos.btnGuardarPlantilla.addEventListener("click", guardarComoPlantilla);
    nodos.btnAjustes.addEventListener("click", abrirAjustes);
    nodos.btnBorrarSinDosis.addEventListener("click", borrarPuntosSinDosis);
    nodos.btnNueva.addEventListener("click", nuevaSesion);
    nodos.btnGuardar.addEventListener("click", guardar);
    nodos.btnDeshacer.addEventListener("click", deshacer);
    nodos.btnRehacer.addEventListener("click", rehacer);
    nodos.btnEspejo.addEventListener("click", espejarSeleccion);
    nodos.btnZoomMas.addEventListener("click", () => zoom(1.2));
    nodos.btnZoomMenos.addEventListener("click", () => zoom(1 / 1.2));
    nodos.btnAjustar.addEventListener("click", ajustarAPantalla);

    nodos.sesionesPlegar.addEventListener("click", () => {
      estado.ui.sesionesAbiertas = !estado.ui.sesionesAbiertas;
      if (estado.ui.sesionesAbiertas && listaSesiones.estado === "vacio") cargarSesionesDelPaciente();
      renderSesiones();
    });

    // Barra del asistente de calibración
    nodos.calibRepetir.addEventListener("click", () => {
      if (estado.ui.modoCalibracion) { estado.ui.modoCalibracion.refs = []; renderCalibracion(); }
    });
    nodos.calibCancelar.addEventListener("click", cancelarCalibracion);
    nodos.calibAceptar.addEventListener("click", guardarCalibracion);

    nodos.archivoPlantillas.addEventListener("change", (e) => leerArchivo(e.target, recibirMisPlantillas));
  }

  /* Lee un archivo de texto elegido por el médico y limpia el input. */
  function leerArchivo(input, alTener) {
    const f = input.files && input.files[0];
    input.value = "";
    if (!f) return;
    const lector = new FileReader();
    lector.onload = () => alTener(String(lector.result || ""), f.name);
    lector.onerror = () => avisar("No pude leer «" + f.name + "».");
    lector.readAsText(f, "utf-8");
  }

  /* Cambio de lámina: los puntos sembrados por plantilla (no manuales) se
     reproyectan a la nueva calibración; los movidos a mano se quedan. */
  function cambiarVista(id) {
    const v = vistaPorId(id);
    if (!v) return;
    const marcoAntiguo = marcoFacial(vistaActual(), calibracionActual());
    // La calibración de la lámina que se deja se guarda como su calibración viva.
    sincronizarCalibracionViva();
    estado.ui.vistaId = v.id;
    estado.sesion.vista = v.id;
    const calNueva = calibracionDeVista(v.id);
    estado.sesion.calibracion = clon(calNueva);
    const marcoNuevo = marcoFacial(v, calNueva);
    let movidos = 0;
    if (marcoAntiguo && marcoNuevo) {
      estado.sesion.puntos.forEach((p) => {
        if (p.manual) return;
        const f = normalizadaAFacial(p.x, p.y, marcoAntiguo);
        const n = facialANormalizada(f.u, f.v, marcoNuevo);
        p.x = redondear5(n.x); p.y = redondear5(n.y);
        movidos++;
      });
    }
    registrar();
    render();
    if (movidos) avisar("Lámina cambiada: " + movidos + " puntos de plantilla reproyectados.");
  }

  /* ---- Teclado ----
     OJO: el listener es de `document` porque el lienzo no tiene el foco, pero
     TODO está condicionado a que la pestaña visible sea la de infiltraciones.
     Si no, Ctrl+Z, Supr, M y la barra espaciadora serían del resto de la app. */
  function conectarTeclado() {
    document.addEventListener("keydown", (e) => {
      if (!estaVisible()) return;
      const enCampo = e.target && /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName);
      const enDialogo = e.target && e.target.closest && e.target.closest("dialog");
      if (enDialogo) return;

      /* Deshacer sí funciona con el foco adentro de un control: tras aplicar
         una plantilla el foco queda en el desplegable y tras dar de alta un
         punto en su casilla de dosis, que son justo los dos momentos en los
         que se aprieta Ctrl+Z. Solo se respeta el deshacer nativo del
         navegador cuando se está escribiendo texto libre. */
      if ((e.ctrlKey || e.metaKey) && !enTextoLibre(e.target) && (e.key === "z" || e.key === "Z")) {
        e.preventDefault();
        if (e.shiftKey) rehacer(); else deshacer();
        return;
      }
      if ((e.ctrlKey || e.metaKey) && !enTextoLibre(e.target) && (e.key === "y" || e.key === "Y")) {
        e.preventDefault(); rehacer(); return;
      }
      if ((e.key === "Delete" || e.key === "Supr") && !enCampo && estado.ui.seleccionId) {
        e.preventDefault(); borrarPunto(estado.ui.seleccionId); return;
      }
      if (e.key === "Escape" && estado.ui.modoCalibracion) { cancelarCalibracion(); return; }
      if (e.key === "Escape" && !enCampo && estado.ui.seleccionId) {
        estado.ui.seleccionId = null; render(); return;
      }
      if ((e.key === "m" || e.key === "M") && !enCampo && !e.ctrlKey && !e.metaKey) {
        e.preventDefault(); espejarSeleccion(); return;
      }
      // Espacio mantenido = modo desplazar. Con el foco en un botón manda el
      // navegador: la barra espaciadora es cómo se acciona sin ratón.
      if (e.code === "Space" && !enCampo && !enBoton(e.target)) {
        if (!estado.ui.espacioPulsado) { estado.ui.espacioPulsado = true; aplicarTransformacion(); }
        e.preventDefault();
      }
    });
    document.addEventListener("keyup", (e) => {
      if (e.code === "Space" && estado.ui.espacioPulsado) {
        estado.ui.espacioPulsado = false;
        aplicarTransformacion();
      }
    });
    window.addEventListener("blur", () => {
      if (!estado.ui.espacioPulsado) return;
      estado.ui.espacioPulsado = false;
      aplicarTransformacion();
    });
  }

  function estaVisible() {
    return estado.montado && window.Recipes && Recipes.pestanaActiva === "panel-infiltraciones";
  }

  function enBoton(nodo) {
    if (!nodo || !nodo.closest) return false;
    return !!(nodo.closest("button") || nodo.closest('[role="button"]'));
  }
  function enTextoLibre(nodo) {
    if (!nodo || !nodo.tagName) return false;
    if (nodo.tagName === "TEXTAREA") return true;
    if (nodo.tagName !== "INPUT") return false;
    return /^(text|search|email|url|tel|password)$/.test((nodo.type || "text").toLowerCase());
  }

  /* ---- Confirmación y petición de texto (diálogos propios, nada de prompt) ---- */
  function confirmar(t, titulo) {
    return new Promise((resolver) => {
      const dlg = nodos.dlgConfirmar;
      nodos.dlgConfirmarTexto.textContent = t;
      nodos.dlgConfirmarTitulo.textContent = titulo || "Confirmar";
      const alCerrar = () => {
        dlg.removeEventListener("close", alCerrar);
        resolver(dlg.returnValue === "si");
      };
      dlg.addEventListener("close", alCerrar);
      dlg.returnValue = "no";
      if (typeof dlg.showModal === "function") dlg.showModal();
      else resolver(window.confirm(t));
    });
  }

  function pedirTexto(titulo, etiqueta, valorInicial, nota) {
    return new Promise((resolver) => {
      const dlg = nodos.dlgTexto;
      nodos.dlgTextoTitulo.textContent = titulo;
      nodos.dlgTextoEtiqueta.textContent = etiqueta;
      nodos.dlgTextoNota.textContent = nota || "";
      const campo = nodos.dlgTextoCampo;
      campo.value = valorInicial || "";
      const alCerrar = () => {
        dlg.removeEventListener("close", alCerrar);
        resolver(dlg.returnValue === "aceptar" && campo.value.trim() ? campo.value.trim() : null);
      };
      dlg.addEventListener("close", alCerrar);
      dlg.returnValue = "cancelar";
      if (typeof dlg.showModal === "function") { dlg.showModal(); campo.focus(); campo.select(); }
      else resolver(window.prompt(etiqueta, valorInicial || ""));
    });
  }

  /* Botones «Cancelar» que no son submit: cierran su diálogo con el valor dado. */
  function conectarDialogos() {
    document.addEventListener("click", (e) => {
      const b = e.target.closest ? e.target.closest("[data-inf-cerrar]") : null;
      if (!b) return;
      const d = b.closest("dialog");
      if (d && d.open) d.close(b.dataset.infCerrar);
    });
  }

  /* ---- Espejo: mismo producto y dosis al otro lado, con el eje de la calibración ---- */
  function espejarSeleccion() {
    const p = puntoPorId(estado.ui.seleccionId);
    if (!p) { avisar("Seleccioná antes el punto que querés reflejar."); return; }
    if (estado.sesion.puntos.length >= MAX_PUNTOS) {
      avisar("Una sesión admite hasta " + MAX_PUNTOS + " puntos.");
      return;
    }
    const m = marcoFacial();
    if (!m) { avisar("Sin calibración no hay eje para el espejo."); return; }
    const f = normalizadaAFacial(p.x, p.y, m);
    if (Math.abs(f.u) < 0.05) { avisar("Ese punto está sobre la línea media: su reflejo caería encima."); return; }
    const n = facialANormalizada(-f.u, f.v, m);
    const gemelo = {
      id: nuevoIdPunto(),
      orden: estado.sesion.puntos.length + 1,
      x: redondear5(n.x),
      y: redondear5(n.y),
      lado: p.lado === "I" ? "D" : (p.lado === "D" ? "I" : "C"),
      zona: p.zona,
      productoId: p.productoId,
      dosis: p.dosis,                 // mismo producto y misma dosis, como la lámina de papel
      notas: p.notas,
      plantillaId: null,
      manual: true
    };
    estado.sesion.puntos.push(gemelo);
    renumerar();
    estado.ui.seleccionId = gemelo.id;
    registrar();
    render();
    avisar("Punto reflejado al lado " +
      (gemelo.lado === "I" ? "izquierdo" : gemelo.lado === "D" ? "derecho" : "central") + ".");
  }

  /* ---- Zoom y desplazamiento ---- */
  const ZOOM_MIN = 1, ZOOM_MAX = 8;
  function zoom(factor, cx, cy) {
    const z0 = estado.ui.zoom || 1;
    const z = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z0 * (factor || 1)));
    if (z === z0) return;
    const w = estado.ui.lienzo.ancho, h = estado.ui.lienzo.alto;
    const px = (cx === null || cx === undefined ? w / 2 : cx);
    const py = (cy === null || cy === undefined ? h / 2 : cy);
    // El punto bajo el cursor se queda donde está: el zoom crece a su alrededor.
    estado.ui.pan.x = px - (px - estado.ui.pan.x) * (z / z0);
    estado.ui.pan.y = py - (py - estado.ui.pan.y) * (z / z0);
    estado.ui.zoom = z;
    limitarPan();
    renderMapa();
  }
  function ajustarAPantalla() {
    estado.ui.zoom = 1;
    estado.ui.pan = { x: 0, y: 0 };
    ajustarMarco();
    renderMapa();
  }

  /* ============================================================
     G. SESIÓN — todo contra la base, nada de archivos .json
     ============================================================ */

  function pacienteAbierto() {
    try { return (window.Recipes && Recipes.pacienteDeLaHistoria) || null; }
    catch (e) { return null; }
  }

  async function asegurarCatalogo() {
    if (cat.estado === "listo" || cat.estado === "pidiendo") return;
    cat.estado = "pidiendo";
    cat.error = "";
    render();
    try {
      const r = await fetch(RUTA_CATALOGO, { headers: { "Accept": "application/json" } });
      if (!r.ok) throw new Error(await Recipes.mensajeDeError(r, "No se pudo traer el catálogo de infiltraciones."));
      const datos = await Recipes.cuerpoJson(r);
      normalizarCatalogo(datos);
      if (!cat.vistas.length) throw new Error("El catálogo no trae ninguna lámina calibrada; no se puede dibujar el mapa.");
      cat.estado = "listo";
      // Con el catálogo en la mano ya hay sesión y desplegables.
      reiniciarSesion();
      poblarSelectores();
    } catch (err) {
      cat.estado = "error";
      cat.error = Recipes.motivoLegible(err,
        "No se pudo traer el catálogo de infiltraciones. Cerrá y volvé a abrir la app.");
    }
    render();
  }

  /* Deja la sesión en blanco para el paciente que esté puesto. */
  function reiniciarSesion() {
    estado.sesion = sesionVacia();
    estado.sesionId = null;
    estado.codigo = "";
    estado.ui.vistaId = estado.sesion.vista;
    estado.ui.seleccionId = null;
    estado.ui.zoom = 1;
    estado.ui.pan = { x: 0, y: 0 };
    estado.ui.gruposPlegados = {};
    estado.ui.modoCalibracion = null;
    estado.ui.productoId = (estado.sesion.productos[0] && estado.sesion.productos[0].id) || "";
    estado.ui.cambiosSinGuardar = false;
    sincronizarCalibracionViva();
    historialIniciar();
  }

  async function nuevaSesion() {
    if (estado.sesion.puntos.length || estado.ui.cambiosSinGuardar) {
      const si = await confirmar(
        "Se pierde lo que no esté guardado de este mapa. ¿Empezar una sesión nueva?", "Sesión nueva");
      if (!si) return;
    }
    const vistaPrevia = estado.ui.vistaId;
    reiniciarSesion();
    if (vistaPorId(vistaPrevia)) {
      estado.sesion.vista = vistaPrevia;
      estado.ui.vistaId = vistaPrevia;
      estado.sesion.calibracion = clon(calibracionDeVista(vistaPrevia));
      historialIniciar();
    }
    estado.ui.sesionReferencia = null;
    estado.ui.refVisible = false;
    estado.ui.refEtiqueta = "";
    limpiarMensajes();
    poblarSelectores();
    render();
    avisar("Sesión nueva preparada.");
  }

  /* --- El paciente sale de la Historia clínica --- */
  function sincronizarPaciente() {
    const pac = pacienteAbierto();

    if (!pac) {
      if (estado.pacienteId !== null && estado.ui.cambiosSinGuardar) {
        // Hay trabajo sin guardar: no se tira. Se avisa y se sigue.
        nodos.avisoPaciente.hidden = false;
        nodos.avisoPacienteTexto.textContent =
          "No hay ninguna historia clínica abierta, pero acá quedó el mapa sin guardar de " +
          texto((estado.paciente || {}).nombre) + ". Guardalo o descartalo antes de cambiar.";
        nodos.avisoPacienteCambiar.textContent = "Ir a la Historia clínica";
        render();
        return;
      }
      estado.pacienteId = null;
      estado.paciente = null;
      nodos.avisoPaciente.hidden = true;
      render();
      return;
    }

    if (estado.pacienteId === null) { adoptarPaciente(pac); return; }

    if (String(pac.id) === String(estado.pacienteId)) {
      estado.paciente = pac;                       // por si le corrigieron el nombre
      nodos.avisoPaciente.hidden = true;
      render();
      return;
    }

    // Cambió el paciente de la historia.
    if (estado.ui.cambiosSinGuardar) {
      nodos.avisoPaciente.hidden = false;
      nodos.avisoPacienteTexto.textContent =
        "La historia abierta ahora es la de " + texto(pac.nombre) + ", pero acá está el mapa sin guardar de " +
        texto((estado.paciente || {}).nombre) + ".";
      nodos.avisoPacienteCambiar.textContent = "Cambiar a " + texto(pac.nombre);
      render();
      return;
    }
    adoptarPaciente(pac);
  }

  function adoptarPaciente(pac) {
    estado.pacienteId = pac.id;
    estado.paciente = pac;
    nodos.avisoPaciente.hidden = true;
    reiniciarSesion();
    estado.ui.sesionReferencia = null;
    estado.ui.refVisible = false;
    estado.ui.refEtiqueta = "";
    listaSesiones.estado = "vacio";
    listaSesiones.filas = [];
    listaSesiones.error = "";
    limpiarMensajes();
    poblarSelectores();
    render();
    cargarSesionesDelPaciente();
  }

  /* --- Lista de sesiones anteriores --- */
  function filasDeRespuesta(cuerpo) {
    if (Array.isArray(cuerpo)) return cuerpo;
    if (!cuerpo || typeof cuerpo !== "object") return [];
    if (Array.isArray(cuerpo.resultados)) return cuerpo.resultados;
    if (Array.isArray(cuerpo.infiltraciones)) return cuerpo.infiltraciones;
    return [];
  }

  async function cargarSesionesDelPaciente() {
    if (estado.pacienteId === null) return;
    const cual = estado.pacienteId;
    listaSesiones.estado = "pidiendo";
    listaSesiones.error = "";
    renderSesiones();
    try {
      const cuerpo = await Recipes.pedirCuerpo(
        "api/pacientes/" + encodeURIComponent(cual) + "/infiltraciones", {});
      if (String(cual) !== String(estado.pacienteId)) return;   // ya cambió el paciente
      listaSesiones.filas = filasDeRespuesta(cuerpo).map((f) => ({
        id: f.id,
        fecha: texto(f.fecha),
        codigo: texto(f.codigo),
        vista: texto(f.vista),
        /* `rutas.py` manda la sesión entera en cada fila (`puntos` es el
           array) y además `cantidad_puntos` ya contado. Se acepta cualquiera
           de los dos, y también un `puntos` que fuera directamente el número. */
        puntos: Array.isArray(f.puntos) ? f.puntos.length
              : (Number.isFinite(Number(f.cantidad_puntos)) ? Number(f.cantidad_puntos)
              : (Number.isFinite(Number(f.puntos)) ? Number(f.puntos) : null)),
        anulado: !!f.anulado
      }));
      listaSesiones.estado = "listo";
    } catch (err) {
      if (String(cual) !== String(estado.pacienteId)) return;
      listaSesiones.estado = "error";
      listaSesiones.error = Recipes.motivoLegible(err,
        "No se pudieron traer los mapas anteriores de este paciente.");
    }
    renderSesiones();
  }

  /* Trae una sesión entera de la base. Devuelve el objeto o null. */
  async function traerSesion(id) {
    const cuerpo = await Recipes.pedirCuerpo("api/infiltraciones/" + encodeURIComponent(id), {});
    if (cuerpo && cuerpo.infiltracion && typeof cuerpo.infiltracion === "object") return cuerpo.infiltracion;
    return cuerpo;
  }

  /* Deja lo que venga de la base con la forma que espera el mapa. */
  function normalizarSesion(d) {
    const base = sesionVacia();
    const calArchivo = d && d.calibracion;
    const calOk = calibracionValida(calArchivo);
    const vista = (d && texto(d.vista)) || base.vista;

    /* Los productos de la sesión mandan; los del catálogo que no estén se
       suman al final, para que el desplegable de la tabla siga completo. */
    let productos = (Array.isArray(d && d.productos) ? d.productos : []).map(normalizarProducto);
    if (!productos.length) productos = clon(cat.productos);
    const ids = {};
    productos.forEach((p) => { ids[p.id] = true; });
    cat.productos.forEach((p) => { if (!ids[p.id]) { productos.push(clon(p)); ids[p.id] = true; } });

    const s = {
      fecha: (d && texto(d.fecha)) || base.fecha,
      vista: vista,
      calibracion: calOk
        ? {
            pupilaIzq: [Number(calArchivo.pupilaIzq[0]), Number(calArchivo.pupilaIzq[1])],
            pupilaDer: [Number(calArchivo.pupilaDer[0]), Number(calArchivo.pupilaDer[1])],
            menton: [Number(calArchivo.menton[0]), Number(calArchivo.menton[1])]
          }
        : clon(calibracionDeVista(vista)),
      productos: productos,
      puntos: [],
      observaciones: (d && texto(d.observaciones)) || ""
    };

    s.puntos = (Array.isArray(d && d.puntos) ? d.puntos : [])
      .filter((p) => p && Number.isFinite(Number(p.x)) && Number.isFinite(Number(p.y)))
      .slice(0, MAX_PUNTOS)
      .map((p, i) => ({
        id: texto(p.id) || ("n" + (i + 1)),
        orden: i + 1,
        x: Number(p.x),
        y: Number(p.y),
        lado: texto(p.lado) || "C",
        zona: texto(p.zona),
        productoId: ids[p.productoId] ? p.productoId : s.productos[0].id,
        dosis: (p.dosis === "" || p.dosis === null || p.dosis === undefined) ? null : Number(p.dosis),
        notas: texto(p.notas),
        plantillaId: p.plantillaId || null,
        manual: !!p.manual
      }));

    s.calibracionIncompleta = calArchivo !== null && calArchivo !== undefined && !calOk;
    return s;
  }

  /* Diálogo para elegir otra lámina cuando la de la sesión no existe acá. */
  function elegirVista(idQueFalta) {
    return new Promise((resolver) => {
      const dlg = nodos.dlgElegirVista;
      nodos.dlgVistaTexto.textContent =
        "Ese mapa se registró con la lámina «" + idQueFalta + "», que este catálogo no tiene. " +
        "Los puntos se conservan; elegí con qué lámina verlos.";
      const sel = nodos.dlgVistaSel;
      sel.textContent = "";
      cat.vistas.forEach((v) => {
        const o = document.createElement("option");
        o.value = v.id; o.textContent = v.etiqueta;
        sel.appendChild(o);
      });
      const alCerrar = () => {
        dlg.removeEventListener("close", alCerrar);
        resolver(sel.value || (cat.vistas[0] && cat.vistas[0].id) || "");
      };
      dlg.addEventListener("close", alCerrar);
      if (typeof dlg.showModal === "function") dlg.showModal();
      else resolver((cat.vistas[0] && cat.vistas[0].id) || "");
    });
  }

  async function abrirSesionGuardada(id) {
    if (estado.ui.cambiosSinGuardar) {
      const si = await confirmar(
        "El mapa que está en pantalla tiene cambios sin guardar y se van a perder. ¿Abrir el guardado igual?",
        "Abrir un mapa guardado");
      if (!si) return;
    }
    limpiarMensajes();
    try {
      const d = await traerSesion(id);
      const s = normalizarSesion(d);
      if (!vistaPorId(s.vista) || !cat.vistas.some((v) => v.id === s.vista)) {
        const elegida = await elegirVista(s.vista);
        if (!elegida) return;
        s.vista = elegida;
        s.calibracion = clon(calibracionDeVista(elegida));
      }
      const incompleta = s.calibracionIncompleta;
      delete s.calibracionIncompleta;

      estado.sesion = s;
      estado.sesionId = (d && d.id) || id;
      estado.codigo = texto(d && d.codigo);
      estado.ui.vistaId = s.vista;
      estado.ui.seleccionId = null;
      estado.ui.zoom = 1;
      estado.ui.pan = { x: 0, y: 0 };
      estado.ui.gruposPlegados = {};
      estado.ui.modoCalibracion = null;
      if (!s.productos.some((p) => p.id === estado.ui.productoId)) {
        estado.ui.productoId = s.productos[0].id;
      }
      sincronizarCalibracionViva();
      historialIniciar();
      estado.ui.cambiosSinGuardar = false;
      poblarSelectores();
      render();
      avisar("Mapa del " + fechaLegible(s.fecha) + " abierto: " + s.puntos.length + " puntos." +
        (incompleta ? " Ojo: la calibración guardada venía incompleta; se puso la de fábrica de esta lámina." : ""));
    } catch (err) {
      mostrarError(Recipes.motivoLegible(err, "No se pudo abrir ese mapa guardado."));
    }
  }

  async function usarComoReferencia(id) {
    try {
      const d = await traerSesion(id);
      const s = normalizarSesion(d);
      estado.ui.sesionReferencia = s;
      estado.ui.refVisible = true;
      estado.ui.refEtiqueta = fechaLegible(s.fecha);
      render();
      const otraLamina = s.vista && s.vista !== estado.sesion.vista;
      avisar("Referencia cargada: " + fechaLegible(s.fecha) + " · " + s.puntos.length + " puntos en gris." +
        (otraLamina ? " Venía de otra lámina: se reproyectó a la actual." : ""));
    } catch (err) {
      mostrarError(Recipes.motivoLegible(err, "No se pudo traer ese mapa como referencia."));
    }
  }

  async function abrirPdfDeSesion(id, boton) {
    const antes = boton.textContent;
    boton.disabled = true;
    boton.textContent = "Abriendo…";
    try {
      const r = await fetch("api/infiltraciones/" + encodeURIComponent(id) + "/abrir", {
        method: "POST",
        headers: { "Accept": "application/json" }
      });
      if (!r.ok) throw new Error(await Recipes.mensajeDeError(r, "No se pudo abrir el PDF de ese mapa."));
      avisar("Se abrió el PDF en el visor.");
    } catch (err) {
      mostrarError(Recipes.motivoLegible(err,
        "No se pudo abrir el PDF. Buscalo en la carpeta del paciente, en infiltraciones\\."));
    } finally {
      boton.disabled = false;
      boton.textContent = antes;
    }
  }

  /* --- Guardar: POST si es nueva, PUT si se está corrigiendo una guardada --- */

  /* Los productos que viajan son los que usa al menos un punto: son los que
     salen en la leyenda y en los totales del PDF (§4). Al reabrir la sesión,
     `normalizarSesion` vuelve a sumarle el catálogo entero. */
  function productosUsados() {
    return estado.sesion.productos.filter(
      (pr) => estado.sesion.puntos.some((p) => p.productoId === pr.id)
    );
  }

  function cuerpoSesion() {
    return {
      fecha: estado.sesion.fecha,
      vista: estado.sesion.vista,
      calibracion: estado.sesion.calibracion,
      productos: productosUsados().map((pr) => ({
        id: pr.id, nombre: pr.nombre, tipo: pr.tipo, unidad: pr.unidad,
        color: pr.color, lote: pr.lote, caducidad: pr.caducidad
      })),
      puntos: estado.sesion.puntos.map((p) => ({
        id: p.id,
        orden: p.orden,
        x: p.x,
        y: p.y,
        lado: p.lado,
        zona: p.zona,
        productoId: p.productoId,
        dosis: dosisRellenada(p) ? Number(p.dosis) : null,
        notas: p.notas,
        plantillaId: p.plantillaId,
        manual: !!p.manual
      })),
      observaciones: estado.sesion.observaciones
    };
  }

  /* Los mismos límites de la §5, comprobados acá para no mandar algo que el
     backend va a rechazar y para decirlo en castellano. */
  function queFaltaParaGuardar() {
    if (estado.pacienteId === null) return "No hay ningún paciente abierto en la Historia clínica.";
    if (!texto(estado.sesion.fecha)) return "Falta la fecha de la sesión.";
    if (!estado.sesion.puntos.length) return "No hay ningún punto en el mapa: no hay nada que registrar.";
    if (estado.sesion.puntos.length > MAX_PUNTOS) return "Una sesión admite hasta " + MAX_PUNTOS + " puntos.";
    if (productosUsados().length > MAX_PRODUCTOS) return "Una sesión admite hasta " + MAX_PRODUCTOS + " productos.";
    const fuera = estado.sesion.puntos.filter(
      (p) => !(p.x >= 0 && p.x <= 1 && p.y >= 0 && p.y <= 1));
    if (fuera.length) return "Hay " + fuera.length + " puntos fuera de la lámina. Recolocalos antes de guardar.";
    const dosisMala = estado.sesion.puntos.filter(
      (p) => dosisRellenada(p) && (Number(p.dosis) < 0 || Number(p.dosis) > MAX_DOSIS));
    if (dosisMala.length) return "Hay dosis fuera de rango (0 a " + MAX_DOSIS + ").";
    if (!calibracionValida(estado.sesion.calibracion)) {
      return "Esta lámina no tiene una calibración utilizable. Recalibrala desde Ajustes.";
    }
    return "";
  }

  async function guardar() {
    if (estado.ui.guardando) return;
    const falta = queFaltaParaGuardar();
    if (falta) { mostrarError(falta); return; }

    estado.ui.guardando = true;
    limpiarMensajes();
    renderBarra();

    const corrigiendo = estado.sesionId !== null && estado.sesionId !== undefined;
    const ruta = corrigiendo
      ? "api/infiltraciones/" + encodeURIComponent(estado.sesionId)
      : "api/pacientes/" + encodeURIComponent(estado.pacienteId) + "/infiltraciones";

    try {
      const r = await fetch(ruta, {
        method: corrigiendo ? "PUT" : "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify(cuerpoSesion())
      });
      if (!r.ok) {
        throw new Error(await Recipes.mensajeDeError(r,
          corrigiendo ? "No se pudieron guardar los cambios del mapa."
                      : "No se pudo guardar el mapa. Volvé a intentar."));
      }
      const datos = await Recipes.cuerpoJson(r);
      if (datos && datos.id !== undefined && datos.id !== null) estado.sesionId = datos.id;
      if (datos && datos.codigo) estado.codigo = texto(datos.codigo);
      // El historial NO se reinicia: guardar no es cerrar el mapa, y el médico
      // tiene que poder deshacer lo último aunque acabe de guardar (después
      // vuelve a guardar y el PUT rehace el PDF).
      estado.ui.cambiosSinGuardar = false;

      const aviso = texto(datos && datos.aviso);
      mostrarExito(
        (corrigiendo ? "Mapa corregido" : "Mapa guardado") +
        (estado.codigo ? " · " + estado.codigo : "") +
        (corrigiendo ? ". El PDF se rehízo y se abrió en el visor."
                     : ". Se generó el PDF y se abrió en el visor.") +
        (aviso ? " " + aviso : ""));
      cargarSesionesDelPaciente();
    } catch (err) {
      mostrarError(Recipes.motivoLegible(err,
        "No se pudo guardar el mapa. Fijate que la app siga andando y volvé a intentar."));
    } finally {
      estado.ui.guardando = false;
      render();
    }
  }

  /* ============================================================
     H. AJUSTES  (productos, zonas propias, mis plantillas, calibración)
     Del panel de Ajustes del programa suelto se borraron los datos del centro
     y del profesional: eso vive en la pestaña Configuración de esta app.
     ============================================================ */

  let ajustesBorrador = null;

  function abrirAjustes() {
    ajustesBorrador = {
      productos: clon(estado.sesion.productos),
      zonas: estado.zonasPropias.join("\n")
    };
    pintarAjustes();
    if (typeof nodos.dlgAjustes.showModal === "function") nodos.dlgAjustes.showModal();
  }

  function pintarAjustes() {
    nodos.ajZonas.value = ajustesBorrador.zonas || "";
    pintarProductosAjustes();
    pintarPlantillasAjustes();
  }

  function celdaCon(nodo) { const td = document.createElement("td"); td.appendChild(nodo); return td; }
  function campoTexto(campo, valor) {
    const i = document.createElement("input");
    i.type = "text"; i.className = "inf-control"; i.value = valor || "";
    i.dataset.infCampo = campo; i.autocomplete = "off";
    return i;
  }
  function campoSelect(campo, opciones, valor) {
    const s = document.createElement("select");
    s.className = "inf-control";
    s.dataset.infCampo = campo;
    opciones.forEach((o) => {
      const op = document.createElement("option");
      op.value = o; op.textContent = o;
      s.appendChild(op);
    });
    s.value = valor || opciones[0];
    return s;
  }

  function pintarProductosAjustes() {
    const cuerpo = nodos.ajCuerpoProductos;
    cuerpo.textContent = "";
    ajustesBorrador.productos.forEach((pr, i) => {
      const tr = document.createElement("tr");
      tr.dataset.infIndice = String(i);

      tr.appendChild(celdaCon(campoTexto("nombre", pr.nombre)));
      tr.appendChild(celdaCon(campoSelect("tipo", TIPOS_PRODUCTO, pr.tipo)));
      tr.appendChild(celdaCon(campoSelect("unidad", UNIDADES, pr.unidad)));

      const color = document.createElement("input");
      color.type = "color";
      color.value = pr.color || COLOR_PRODUCTO_NUEVO;
      color.dataset.infCampo = "color";
      color.title = "Color del marcador de este producto";
      tr.appendChild(celdaCon(color));

      tr.appendChild(celdaCon(campoTexto("lote", pr.lote)));

      const cad = document.createElement("input");
      cad.type = "date";
      cad.className = "inf-control";
      cad.value = pr.caducidad || "";
      cad.dataset.infCampo = "caducidad";
      tr.appendChild(celdaCon(cad));

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "inf-boton-icono";
      btn.dataset.infAccion = "quitar-producto";
      btn.textContent = "✕";
      btn.title = "Quitar el producto " + pr.nombre;
      btn.setAttribute("aria-label", btn.title);
      const td = celdaCon(btn);
      td.className = "inf-aj-col-acciones";
      tr.appendChild(td);

      cuerpo.appendChild(tr);
    });
  }

  function pintarPlantillasAjustes() {
    const ul = nodos.ajListaPlantillas;
    ul.textContent = "";
    if (!estado.misPlantillas.length) {
      const li = document.createElement("li");
      li.className = "inf-nota";
      li.textContent = "Todavía no hay plantillas propias. Se crean con «Guardar plantilla».";
      ul.appendChild(li);
      return;
    }
    estado.misPlantillas.forEach((p) => {
      const li = document.createElement("li");
      const n = document.createElement("span");
      n.className = "inf-nombre";
      n.textContent = p.nombre + " — " + ((p.puntos || []).length) + " puntos";
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "inf-boton-icono";
      btn.dataset.infAccion = "quitar-plantilla";
      btn.dataset.infId = p.id;
      btn.textContent = "✕";
      btn.title = "Borrar la plantilla " + p.nombre;
      btn.setAttribute("aria-label", btn.title);
      li.appendChild(n);
      li.appendChild(btn);
      ul.appendChild(li);
    });
  }

  function conectarAjustes() {
    const anotar = (e) => {
      const tr = e.target.closest("tr"); if (!tr || !ajustesBorrador) return;
      const pr = ajustesBorrador.productos[Number(tr.dataset.infIndice)];
      const campo = e.target.dataset.infCampo;
      if (pr && campo) pr[campo] = e.target.value;
    };
    nodos.ajCuerpoProductos.addEventListener("input", anotar);
    nodos.ajCuerpoProductos.addEventListener("change", anotar);

    nodos.ajCuerpoProductos.addEventListener("click", (e) => {
      const btn = e.target.closest('[data-inf-accion="quitar-producto"]');
      if (!btn || !ajustesBorrador) return;
      const tr = btn.closest("tr");
      const i = Number(tr.dataset.infIndice);
      const pr = ajustesBorrador.productos[i];
      if (estado.sesion.puntos.some((p) => p.productoId === pr.id)) {
        avisar("No se puede quitar «" + pr.nombre + "»: hay puntos que lo usan.");
        return;
      }
      if (ajustesBorrador.productos.length <= 1) { avisar("Tiene que quedar al menos un producto."); return; }
      ajustesBorrador.productos.splice(i, 1);
      pintarProductosAjustes();
    });

    nodos.ajBtnProducto.addEventListener("click", () => {
      if (!ajustesBorrador) return;
      if (ajustesBorrador.productos.length >= MAX_PRODUCTOS) {
        avisar("Una sesión admite hasta " + MAX_PRODUCTOS + " productos.");
        return;
      }
      let n = 1;
      const usados = {};
      ajustesBorrador.productos.forEach((p) => { usados[p.id] = true; });
      while (usados["p" + n]) n++;
      ajustesBorrador.productos.push({
        id: "p" + n, nombre: "Producto nuevo", tipo: "otro", unidad: "U",
        color: COLOR_PRODUCTO_NUEVO, lote: "", caducidad: ""
      });
      pintarProductosAjustes();
    });

    nodos.ajListaPlantillas.addEventListener("click", (e) => {
      const btn = e.target.closest('[data-inf-accion="quitar-plantilla"]');
      if (!btn) return;
      borrarMiPlantilla(btn.dataset.infId);
      pintarPlantillasAjustes();
    });
    nodos.ajExportar.addEventListener("click", exportarMisPlantillas);
    nodos.ajImportar.addEventListener("click", importarMisPlantillas);

    // Se cierra guardando lo escrito: nadie pierde un lote por ir a calibrar.
    nodos.ajCalibrar.addEventListener("click", () => {
      nodos.dlgAjustes.close("aceptar");
      abrirCalibracion();
    });
    nodos.ajCalibFabrica.addEventListener("click", async () => {
      const si = await confirmar(
        "Se recupera la calibración de fábrica de esta lámina. ¿Continuar?", "Calibración de fábrica");
      if (!si) return;
      const v = vistaActual();
      if (!v) return;
      const fabrica = CALIBRACION_FABRICA[v.id] || v.calibracion;
      fijarCalibracionVista(v.id, fabrica);
      estado.sesion.calibracion = clon(fabrica);
      registrar();
      render();
      avisar("Calibración de fábrica restablecida.");
    });

    nodos.dlgAjustes.addEventListener("close", () => {
      if (nodos.dlgAjustes.returnValue !== "aceptar" || !ajustesBorrador) { ajustesBorrador = null; return; }
      guardarAjustes();
    });
  }

  function guardarAjustes() {
    const b = ajustesBorrador;
    b.zonas = nodos.ajZonas.value;

    // Productos: se conservan los ids, así los puntos siguen apuntando al suyo.
    estado.sesion.productos = b.productos.slice(0, MAX_PRODUCTOS).map((p) => ({
      id: p.id,
      nombre: texto(p.nombre) || "Producto",
      tipo: TIPOS_PRODUCTO.indexOf(p.tipo) >= 0 ? p.tipo : "otro",
      unidad: UNIDADES.indexOf(p.unidad) >= 0 ? p.unidad : "U",
      color: /^#[0-9a-fA-F]{6}$/.test(p.color || "") ? p.color : COLOR_PRODUCTO_NUEVO,
      lote: texto(p.lote),
      caducidad: texto(p.caducidad)
    }));
    if (!estado.sesion.productos.some((p) => p.id === estado.ui.productoId)) {
      estado.ui.productoId = estado.sesion.productos[0].id;
    }

    estado.zonasPropias = String(b.zonas || "").split("\n").map((s) => s.trim()).filter(Boolean);

    ajustesBorrador = null;
    registrar();
    poblarSelectores();
    render();
    avisar("Ajustes aplicados a esta sesión.");
  }

  /* ---- Asistente de calibración de 3 clics ---- */
  function abrirCalibracion() {
    const d = nodos.dlgCalibracion;
    const alCerrar = () => {
      d.removeEventListener("close", alCerrar);
      if (d.returnValue !== "empezar") return;
      empezarCalibracion();
    };
    d.addEventListener("close", alCerrar);
    d.returnValue = "cancelar";
    if (typeof d.showModal === "function") d.showModal(); else empezarCalibracion();
  }
  function empezarCalibracion() {
    estado.ui.modoCalibracion = { refs: [] };
    estado.ui.seleccionId = null;
    render();
    avisar("Calibrando: hacé clic en la pupila izquierda, la derecha y la punta del mentón.");
  }
  function cancelarCalibracion() {
    estado.ui.modoCalibracion = null;
    render();
  }
  function guardarCalibracion() {
    const mc = estado.ui.modoCalibracion;
    if (!mc || mc.refs.length < 3) return;
    const nueva = calibracionDeRefs(mc.refs);
    if (!calibracionValida(nueva)) {
      avisar("Esas tres marcas no forman una calibración válida: las dos pupilas no pueden estar en el mismo punto.");
      return;
    }
    const v = vistaActual();
    if (v) fijarCalibracionVista(v.id, nueva);
    estado.sesion.calibracion = clon(nueva);
    estado.ui.modoCalibracion = null;
    registrar();
    render();
    avisar("Calibración guardada. Viaja con esta sesión.");
  }

  /* ============================================================
     I. ARRANQUE Y REGISTRO
     ============================================================ */

  function poblarSelectores() {
    if (!estado.montado) return;

    const selVista = nodos.selVista;
    selVista.textContent = "";
    cat.vistas.forEach((v) => {
      const o = document.createElement("option");
      o.value = v.id; o.textContent = v.etiqueta;
      selVista.appendChild(o);
    });
    selVista.value = estado.ui.vistaId || "";

    const selPlant = nodos.selPlantilla;
    selPlant.textContent = "";
    const vacia = document.createElement("option");
    vacia.value = ""; vacia.textContent = "Aplicar plantilla…";
    selPlant.appendChild(vacia);
    listaPlantillas().forEach((p) => {
      const o = document.createElement("option");
      o.value = p.id; o.textContent = p.nombre + (p.propia ? " (mía)" : "");
      selPlant.appendChild(o);
    });
    selPlant.value = "";

    const selProd = nodos.selProducto;
    selProd.textContent = "";
    estado.sesion.productos.forEach((pr) => {
      const o = document.createElement("option");
      o.value = pr.id; o.textContent = pr.nombre;
      selProd.appendChild(o);
    });
    selProd.value = productoParaPuntoNuevo();

    const lista = nodos.listaZonas;
    lista.textContent = "";
    cat.zonas.forEach((g) => {
      g.zonas.forEach((z) => {
        const o = document.createElement("option");
        o.value = z; o.label = g.grupo;
        lista.appendChild(o);
      });
    });
    estado.zonasPropias.forEach((z) => {
      const o = document.createElement("option");
      o.value = z; o.label = "Zonas propias";
      lista.appendChild(o);
    });
  }

  /* Corre una sola vez, al arrancar la app. Acá NO se pide nada al servidor:
     quien solo emite récipes no espera nunca por algo que no pidió. */
  function montarInfiltraciones() {
    if (!tomarNodos()) {
      console.error("Infiltraciones: falta el HTML del panel (#inf-mesa). La pestaña queda inerte.");
      return;
    }
    estado.montado = true;
    conectarLienzo();
    conectarTabla();
    conectarBarras();
    conectarAjustes();
    conectarDialogos();
    conectarTeclado();
    historialIniciar();
    render();
  }

  /* Corre cada vez que el médico entra a la pestaña. */
  async function alAbrirInfiltraciones() {
    if (!estado.montado) return;
    /* `irAPestana` no espera a esta promesa: si algo reventara acá, el fallo
       saldría como un rechazo sin dueño y el médico solo vería una pestaña
       en blanco. Se atrapa y se dice. */
    try {
      await asegurarCatalogo();
      if (cat.estado !== "listo") return;
      sincronizarPaciente();
      // El área del lienzo acaba de pasar de 0 px a su tamaño real.
      ajustarMarco();
      renderMapa();
    } catch (err) {
      console.error("Infiltraciones: fallo al abrir la pestaña:", err);
      mostrarError("Algo falló al abrir el mapa de infiltraciones. Volvé a entrar a la pestaña.");
    }
  }

  Recipes.registrar({
    nombre: "Infiltraciones",
    panel: "panel-infiltraciones",
    montar: montarInfiltraciones,
    alAbrir: alAbrirInfiltraciones
  });
})();
