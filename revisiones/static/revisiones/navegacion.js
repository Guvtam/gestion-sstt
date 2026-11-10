/* Regreso entre pantallas, por pestaña y usuario; no usa history.back tras POST. */
(() => {
  const menu = document.querySelector('[data-sstt-menu]');
  if (!menu) return;
  const volver = menu.querySelector('[data-sstt-volver]');
  const key = 'sstt:navegacion:' + menu.dataset.usuario;
  const actual = location.pathname + location.search;
  const permitidas = new Set(Array.from(menu.querySelectorAll('[data-sstt-destino]'), a => new URL(a.href).pathname));
  // Las pantallas de detalle tienen regreso propio; se visitan desde rutas internas.
  const interna = value => {
    try {
      const url = new URL(value, location.origin);
      return url.origin === location.origin && !url.hash && (permitidas.has(url.pathname) ||
        /^\/(?:facturacion\/\d+\/(?:odt|historial-requisicion)|contratistas\/\d+\/(?:editar|equivalencias)|contratistas\/(?:nuevo|vinculacion-softguard)|odt\/\d+)\/$/.test(url.pathname));
    } catch (_) { return false; }
  };
  try {
    const guardada = JSON.parse(sessionStorage.getItem(key) || '[]');
    const pila = (Array.isArray(guardada) ? guardada : []).filter(v => typeof v === 'string' && interna(v)).slice(-30);
    const ultima = pila[pila.length - 1];
    if (ultima && new URL(ultima, location.origin).pathname === location.pathname) pila[pila.length - 1] = actual;
    else pila.push(actual);
    if (pila.length > 1 && interna(pila[pila.length - 2])) {
      volver.href = pila[pila.length - 2];
      volver.removeAttribute('aria-disabled');
      volver.removeAttribute('tabindex');
    }
    sessionStorage.setItem(key, JSON.stringify(pila));
    volver.addEventListener('click', event => {
      if (event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      if (volver.getAttribute('aria-disabled') === 'true') { event.preventDefault(); return; }
      if (pila.length > 1) {
        pila.pop();
        sessionStorage.setItem(key, JSON.stringify(pila));
      }
    });
  } catch (_) { /* El enlace de regreso del servidor funciona sin almacenamiento. */ }
})();
