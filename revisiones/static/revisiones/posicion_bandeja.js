/* Retorno a la ODT guardada; no guarda información de pagos ni cambia filtros. */
(() => {
  "use strict";
  const CLAVE = "sstt_posicion_bandeja_v2";
  const numeroValido = numero => /^[0-9]{1,10}$/.test(String(numero || ""));
  const tabla = () => document.getElementById("tablaScrollPrincipal");
  function contexto(url) {
    const copia = new URL(url.href);
    copia.searchParams.delete("page");
    copia.searchParams.delete("ubicar_odt");
    copia.searchParams.delete("filas_guardadas");
    copia.searchParams.sort();
    return copia.pathname + "?" + copia.searchParams.toString();
  }
  function mensaje(texto) {
    const estado = document.getElementById("estadoPosicionBandeja");
    if (estado) estado.textContent = texto;
  }
  function marcar(fila) {
    if (!fila) return;
    document.querySelectorAll("tr.odt-reciente").forEach(otra => otra.classList.remove("odt-reciente"));
    fila.classList.add("odt-reciente");
    mensaje(`ODT ${fila.dataset.numero} guardada.`);
  }
  function recargar(fila) {
    const url = new URL(window.location.href);
    if (!fila || !numeroValido(fila.dataset.numero)) {
      window.location.reload();
      return;
    }
    const posicion = {
      contexto: contexto(url), numero: fila.dataset.numero, fecha: Date.now(),
      horizontal: tabla()?.scrollLeft || 0,
      vertical: window.scrollY, paginaX: window.scrollX,
      desplazamientoFila: fila.getBoundingClientRect().top
    };
    try { sessionStorage.setItem(CLAVE, JSON.stringify(posicion)); } catch (_) { /* Guardar sigue funcionando sin almacenamiento. */ }
    const pagina = document.body.dataset.paginaActual;
    if (/^[1-9][0-9]*$/.test(pagina || "")) url.searchParams.set("page", pagina);
    const numeros = [...(tabla()?.querySelectorAll("tr[data-numero]") || [])]
      .map(elemento => elemento.dataset.numero).filter(numeroValido);
    if (numeros.length && numeros.length <= 50 && numeros.includes(posicion.numero)) {
      url.searchParams.set("filas_guardadas", numeros.join(","));
    }
    url.searchParams.set("ubicar_odt", posicion.numero);
    window.location.assign(url.href);
  }
  function restaurar() {
    const url = new URL(window.location.href);
    // La ubicación es de un solo uso; la siguiente navegación usa la página real.
    if (url.searchParams.has("ubicar_odt")) {
      url.searchParams.delete("ubicar_odt");
      url.searchParams.delete("filas_guardadas");
      const pagina = document.body.dataset.paginaActual;
      if (/^[1-9][0-9]*$/.test(pagina || "")) url.searchParams.set("page", pagina);
      window.history.replaceState(null, "", url.href);
    }
    let posicion;
    try {
      const guardado = sessionStorage.getItem(CLAVE);
      sessionStorage.removeItem(CLAVE);
      posicion = JSON.parse(guardado || "null");
    } catch (_) { return; }
    if (!posicion || posicion.contexto !== contexto(url) || !numeroValido(posicion.numero)
        || !Number.isFinite(posicion.fecha) || Date.now() - posicion.fecha > 120000) return;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const contenedor = tabla();
      if (!contenedor) return;
      const fila = [...contenedor.querySelectorAll("tr[data-numero]")]
        .find(elemento => elemento.dataset.numero === posicion.numero);
      contenedor.scrollLeft = Number(posicion.horizontal) || 0;
      const superior = document.getElementById("tablaScrollSuperior");
      if (superior) superior.scrollLeft = contenedor.scrollLeft;
      if (fila) {
        marcar(fila);
        const destino = window.scrollY + fila.getBoundingClientRect().top - (Number(posicion.desplazamientoFila) || 0);
        window.scrollTo(Number(posicion.paginaX) || 0, Math.max(0, destino));
      } else {
        window.scrollTo(Number(posicion.paginaX) || 0, Number(posicion.vertical) || 0);
        mensaje(`ODT ${posicion.numero} guardada. Ya no aparece con los filtros actuales.`);
      }
    }));
  }
  window.SSTTPosicionBandeja = {recargar, marcar};
  if (document.readyState === "complete") restaurar();
  else window.addEventListener("load", restaurar, {once:true});
})();
