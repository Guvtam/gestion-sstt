const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[2], 'utf8');
function entorno({guardado=null, href='http://localhost/?servicios=A&servicios=B&page=2', numero='10', top=200, bloquear=false, pagina='1'}={}) {
  const datos = new Map(guardado ? [['sstt_posicion_bandeja_v2', JSON.stringify(guardado)]] : []);
  const clases = new Set();
  const fila = {dataset:{numero},getBoundingClientRect:()=>({top}),classList:{add:x=>clases.add(x),remove:x=>clases.delete(x)}};
  const tabla = {scrollLeft:300,querySelectorAll:()=>numero ? [fila] : []};
  const superior = {scrollLeft:0}; const mensaje={textContent:''};
  const callbacks={}; const llamadas={};
  const window={scrollY:1000,scrollX:0,location:{href,reload:()=>llamadas.reload=true,assign:url=>llamadas.url=url},history:{replaceState:(_,__,url)=>llamadas.canonica=url},addEventListener:(n,f)=>callbacks[n]=f,scrollTo:(x,y)=>llamadas.scroll=[x,y]};
  const document={readyState:'loading',body:{dataset:{paginaActual:pagina}},getElementById:id=>({tablaScrollPrincipal:tabla,tablaScrollSuperior:superior,estadoPosicionBandeja:mensaje})[id],querySelectorAll:()=>[]};
  const sessionStorage={setItem:(k,v)=>{if(bloquear)throw Error();datos.set(k,v)},getItem:k=>{if(bloquear)throw Error();return datos.get(k)},removeItem:k=>datos.delete(k)};
  vm.runInNewContext(source,{window,document,sessionStorage,URL,Date,Number,Math,JSON,requestAnimationFrame:f=>f()});
  return {window,datos,fila,tabla,superior,mensaje,clases,llamadas,cargar:()=>callbacks.load()};
}
let e=entorno();e.window.SSTTPosicionBandeja.recargar(e.fila);
let url=new URL(e.llamadas.url);
assert.deepEqual(url.searchParams.getAll('servicios'),['A','B']);assert.equal(url.searchParams.get('ubicar_odt'),'10');
const guardado=JSON.parse(e.datos.get('sstt_posicion_bandeja_v2'));
e=entorno({guardado,href:url.href,top:400});e.cargar();
assert.deepEqual(e.llamadas.scroll,[0,1200]);assert.equal(e.superior.scrollLeft,300);assert(e.clases.has('odt-reciente'));assert.equal(e.datos.size,0);
assert.equal(new URL(e.llamadas.canonica).searchParams.get('page'),'1');assert.equal(new URL(e.llamadas.canonica).searchParams.has('ubicar_odt'),false);
e=entorno({guardado,numero:''});e.cargar();assert(e.mensaje.textContent.includes('filtros actuales'));assert.deepEqual(e.llamadas.scroll,[0,1000]);
e=entorno({guardado,href:'http://localhost/?servicios=C'});e.cargar();assert.equal(e.llamadas.scroll,undefined);
e=entorno({guardado:{...guardado,fecha:Date.now()-130000}});e.cargar();assert.equal(e.llamadas.scroll,undefined);
e=entorno({bloquear:true});e.window.SSTTPosicionBandeja.recargar(e.fila);assert(e.llamadas.url.includes('ubicar_odt=10'));e.cargar();
e=entorno();e.datos.set('sstt_posicion_bandeja_v2','{invalido');e.cargar();assert.equal(e.llamadas.scroll,undefined);
e=entorno();e.window.SSTTPosicionBandeja.marcar(e.fila);assert(e.mensaje.textContent.includes('10 guardada'));assert(e.clases.has('odt-reciente'));
console.log('Posición de bandeja: todas las comprobaciones correctas.');

for (const pagina of ['2','3']) {
  const href='http://localhost/odt-por-creacion/?servicios=A&servicios=B&page='+pagina;
  e=entorno({href,pagina});e.window.SSTTPosicionBandeja.recargar(e.fila);
  const destino=new URL(e.llamadas.url);
  assert.equal(destino.pathname,'/odt-por-creacion/');
  assert.equal(destino.searchParams.get('page'),pagina);
  assert.deepEqual(destino.searchParams.getAll('servicios'),['A','B']);
  const posicion=JSON.parse(e.datos.get('sstt_posicion_bandeja_v2'));
  e=entorno({href:destino.href,pagina,guardado:posicion,top:400});e.cargar();
  assert.equal(new URL(e.llamadas.canonica).searchParams.get('page'),pagina);
  assert.deepEqual(e.llamadas.scroll,[0,1200]);
  assert.equal(e.superior.scrollLeft,300);
}
console.log('ODT por creación: página, filtros y posición conservados en páginas 2 y 3.');
