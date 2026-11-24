/* Los enlaces de consulta usan navegación nativa; los controles permanecen. */
(() => {
  'use strict';
  const controles = [
    'button', '[role="button"]', '.btn', '.stats-btn', '.fact-secondary', '.hist-secondary',
    '[data-sstt-misma-pestana]', '[data-sstt-volver]', '[data-sstt-destino]',
    '[aria-disabled="true"]', '[download]', 'nav', '[role="navigation"]',
    '.pagination', '.paginacion', '.paginacion-enlaces', '.visita-leyenda',
    '.filtro-chip', '.leyenda-item', '.grafico-barra', '.tendencia-col',
    '.kpi-card', '.stats-kpi', '.modificadas-kpi'
  ].join(',');

  function preparar(enlace) {
    if (!enlace || enlace.closest(controles)) return;
    const href = (enlace.getAttribute('href') || '').trim();
    if (!href || href.startsWith('#')) return;
    const destinoExplicito = enlace.getAttribute('target');
    if (destinoExplicito && destinoExplicito !== '_blank') return;
    let destino;
    try { destino = new URL(href, document.baseURI); } catch (_) { return; }
    if (!['https:', 'http:'].includes(destino.protocol)) return;
    const actual = new URL(location.href);
    if (destino.hash && destino.origin === actual.origin &&
        destino.pathname === actual.pathname && destino.search === actual.search) return;
    enlace.setAttribute('target', '_blank');
    const rel = new Set((enlace.getAttribute('rel') || '').split(/\s+/).filter(Boolean));
    rel.add('noopener');
    enlace.setAttribute('rel', [...rel].join(' '));
    if (!enlace.hasAttribute('title')) enlace.setAttribute('title', 'Se abre en otra pestaña');
  }

  document.querySelectorAll('a[href]').forEach(preparar);
  // Preparar también enlaces añadidos después de cargar, antes de la acción nativa.
  for (const tipo of ['click', 'auxclick', 'contextmenu']) {
    document.addEventListener(tipo, evento => preparar(evento.target?.closest?.('a[href]')), true);
  }
})();
