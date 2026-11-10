const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[2], 'utf8');
function barra(datos={}) {
  return {...datos, scrollLeft:0, callbacks:{}, addEventListener(n,f){this.callbacks[n]=f}};
}
const superior=barra({firstElementChild:{style:{}}});
const tabla={};
const contenido=barra({scrollWidth:2400,clientWidth:900,querySelector:()=>tabla});
const bloque={querySelector:s=>s==='[data-scroll-superior]'?superior:contenido};
let redimensionar;
vm.runInNewContext(source,{
  document:{querySelectorAll:()=>[bloque]},
  window:{addEventListener:(n,f)=>redimensionar=f},
});
assert.equal(superior.firstElementChild.style.width,'2400px');
assert.equal(superior.hidden,false);
superior.scrollLeft=450;superior.callbacks.scroll();assert.equal(contenido.scrollLeft,450);
contenido.scrollLeft=150;contenido.callbacks.scroll();assert.equal(superior.scrollLeft,150);
contenido.clientWidth=390;redimensionar();assert.equal(superior.hidden,false);
contenido.clientWidth=2500;redimensionar();assert.equal(superior.hidden,true);
contenido.clientWidth=900;contenido.scrollWidth=3000;redimensionar();
assert.equal(superior.firstElementChild.style.width,'3000px');assert.equal(superior.hidden,false);
console.log('Tablas: sincronización bidireccional y adaptación al ancho disponible.');
