const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[2], 'utf8');
const datos = new Map();
function cargar(href, usuario='1', bloquear=false) {
  const location = new URL(href);
  const attrs = {'aria-disabled':'true', tabindex:'-1'};
  const callbacks = {};
  const volver = {href:'/', removeAttribute:k=>delete attrs[k], getAttribute:k=>attrs[k], addEventListener:(n,f)=>callbacks[n]=f};
  const menu = {dataset:{usuario}, querySelector:()=>volver,
    querySelectorAll:()=>['/','/analisis-odt/','/calendario-servicios/','/odt-modificadas/estadisticas/'].map(p=>({href:location.origin+p}))};
  const sessionStorage = {getItem:k=>{if(bloquear)throw Error();return datos.get(k)},setItem:(k,v)=>datos.set(k,v)};
  vm.runInNewContext(source,{document:{querySelector:()=>menu},location,sessionStorage,URL,JSON,Set,Array});
  return {volver,attrs,click:(evento={})=>callbacks.click?.(evento)};
}
cargar('http://localhost/?servicios=A&servicios=B&page=4');
cargar('http://localhost/?servicios=A&servicios=B&page=5'); // filtro/página reemplaza el nivel actual
let e=cargar('http://localhost/analisis-odt/?desde=2026-10-21');
assert.equal(e.volver.href,'/?servicios=A&servicios=B&page=5');
assert.equal(e.attrs['aria-disabled'],undefined);
e=cargar('http://localhost/odt-modificadas/estadisticas/');
assert.equal(e.volver.href,'/analisis-odt/?desde=2026-10-21');
e.click();
e=cargar('http://localhost/analisis-odt/?desde=2026-10-21');
assert.equal(e.volver.href,'/?servicios=A&servicios=B&page=5');
e.click();
e=cargar('http://localhost/?servicios=A&servicios=B&page=5');
assert.equal(JSON.parse(datos.get('sstt:navegacion:1')).length,1);
e=cargar('http://localhost/calendario-servicios/','2');
assert.equal(JSON.parse(datos.get('sstt:navegacion:2')).length,1); // otro usuario no hereda regreso
datos.set('sstt:navegacion:3',JSON.stringify(['https://externo.cl/','//externo.cl/','/guardar-fila/','javascript:alert(1)']));
e=cargar('http://localhost/analisis-odt/','3');
assert.equal(JSON.parse(datos.get('sstt:navegacion:3')).length,1);
assert.equal(e.volver.href,'/');
e=cargar('http://localhost/analisis-odt/','4',true);
assert.equal(e.volver.href,'/'); // el enlace del servidor sigue disponible
datos.set('sstt:navegacion:5','{invalido');
cargar('http://localhost/analisis-odt/','5');
console.log('Regreso: conserva filtros, multiselección y página; aislado por usuario y sin destinos externos.');
