/* Fijar filtros efectivos antes de guardar posición o seleccionar exportaciones. */
(() => {
  'use strict';
  const valor=document.body.dataset.urlConsulta;
  if(!valor)return;
  const actual=new URL(window.location.href), consulta=new URL(valor,actual.href);
  if(consulta.origin!==actual.origin||consulta.pathname!==actual.pathname)return;
  consulta.hash=actual.hash;
  if(consulta.href!==actual.href)window.history.replaceState(null,'',consulta.href);
})();
