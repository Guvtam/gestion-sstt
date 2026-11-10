/* Barras superior e inferior sincronizadas sin dependencias. */
document.querySelectorAll('[data-tabla-desplazable]').forEach(bloque => {
  const superior = bloque.querySelector('[data-scroll-superior]');
  const contenido = bloque.querySelector('[data-scroll-tabla]');
  const relleno = superior.firstElementChild;
  const tabla = contenido.querySelector('table');
  const medir = () => {
    relleno.style.width = contenido.scrollWidth + 'px';
    superior.hidden = contenido.scrollWidth <= contenido.clientWidth;
    superior.scrollLeft = contenido.scrollLeft;
  };
  superior.addEventListener('scroll', () => {
    if (contenido.scrollLeft !== superior.scrollLeft) contenido.scrollLeft = superior.scrollLeft;
  }, {passive:true});
  contenido.addEventListener('scroll', () => {
    if (superior.scrollLeft !== contenido.scrollLeft) superior.scrollLeft = contenido.scrollLeft;
  }, {passive:true});
  if (window.ResizeObserver) {
    const observador = new ResizeObserver(medir);
    observador.observe(contenido);
    observador.observe(tabla);
  }
  window.addEventListener('resize', medir);
  medir();
});
