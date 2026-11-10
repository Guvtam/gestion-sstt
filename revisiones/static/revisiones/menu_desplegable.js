/* Disclosure nativo: teclado y clic funcionan también sin JavaScript. */
(() => {
  const menu = document.querySelector('[data-sstt-menu]');
  if (!menu) return;
  const grupos = Array.from(menu.querySelectorAll('[data-sstt-grupo]'));
  const cerrar = excepto => grupos.forEach(grupo => { if (grupo !== excepto) grupo.open = false; });
  grupos.forEach(grupo => {
    grupo.addEventListener('toggle', () => { if (grupo.open) cerrar(grupo); });
    grupo.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        grupo.open = false;
        grupo.querySelector('summary').focus();
        event.preventDefault();
      }
    });
  });
  document.addEventListener('click', event => {
    if (!menu.contains(event.target) || !event.target.closest('[data-sstt-grupo]')) cerrar();
  });
  document.addEventListener('focusin', event => {
    if (!menu.contains(event.target)) cerrar();
    else cerrar(event.target.closest('[data-sstt-grupo]'));
  });
})();
