const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const codigo=fs.readFileSync(process.argv[2],'utf8');
const almacen=new Map(), peticiones=[], descargas=[];
let responder=async()=>({ok:true,headers:{get:n=>n==='content-type'?'application/pdf':'attachment; filename="ODT.pdf"'},blob:async()=>({})});
function elemento(extra={}){return {handlers:{},dataset:{},checked:false,disabled:false,textContent:'',
  addEventListener(n,f){this.handlers[n]=f;},...extra};}
function pantalla({url='https://local/bandeja/?fecha_desde=2026-01-01&page=1',usuario='1',tipo='odt',ids=['1','2']}={}){
  const opciones=ids.map(value=>elemento({value})),pagina=elemento(),estado=elemento(),cantidad=elemento(),limpiar=elemento();
  const botones=['pdf',...(tipo==='odt'?['xlsx']:[])].map(f=>elemento({dataset:{descargar:f}}));
  const mapa={'[data-estado-exportacion]':estado,'[data-cantidad-seleccion]':cantidad,'[data-limpiar-seleccion]':limpiar,'[name=csrfmiddlewaretoken]':{value:'csrf-local'}};
  const panel={dataset:{tipo,url:'/descargar/'},querySelector:s=>mapa[s],querySelectorAll:()=>botones};
  class URLPrueba extends URL{} URLPrueba.createObjectURL=()=> 'blob:prueba';URLPrueba.revokeObjectURL=()=>{};
  vm.runInNewContext(codigo,{
    URL:URLPrueba,URLSearchParams,Set,JSON,
    window:{location:{href:url}},
    document:{querySelectorAll:s=>s==='[data-exportar-seleccion]'?[panel]:opciones,
      querySelector:s=>s==='[data-sstt-menu]'?{dataset:{usuario}}:pagina,
      body:{appendChild(){}},createElement:()=>({click(){descargas.push(this.download);},remove(){}})},
    sessionStorage:{getItem:k=>almacen.get(k),setItem:(k,v)=>almacen.set(k,v)},
    fetch:async(url,opciones)=>{peticiones.push({url,opciones});return responder();},setTimeout:f=>f()
  });
  return {opciones,pagina,estado,cantidad,limpiar,botones};
}
(async()=>{
  let p=pantalla();assert.equal(p.botones[0].disabled,true);
  p.opciones[0].checked=true;p.opciones[0].handlers.change();assert.equal(p.cantidad.textContent,'1');
  let p2=pantalla({url:'https://local/bandeja/?page=2&fecha_desde=2026-01-01',ids:['3','4']});
  assert.equal(p2.cantidad.textContent,'1');p2.pagina.checked=true;p2.pagina.handlers.change();assert.equal(p2.cantidad.textContent,'3');
  p=pantalla();assert.equal(p.opciones[0].checked,true);assert.equal(p.opciones[1].checked,false);assert.equal(p.pagina.indeterminate,true);
  assert.equal(pantalla({usuario:'2'}).cantidad.textContent,'0');
  assert.equal(pantalla({url:'https://local/bandeja/?fecha_desde=2026-02-01'}).cantidad.textContent,'0');
  assert.equal(pantalla({url:'https://local/otra/?fecha_desde=2026-01-01'}).cantidad.textContent,'0');
  let terminar;responder=()=>new Promise(r=>terminar=r);
  const pendiente=p.botones[0].handlers.click();await p.botones[0].handlers.click();assert.equal(peticiones.length,1);
  assert.equal(p.botones[0].disabled,true);assert.equal(peticiones[0].opciones.method,'POST');
  assert.equal(peticiones[0].opciones.headers['X-CSRFToken'],'csrf-local');
  const body=new URLSearchParams(peticiones[0].opciones.body);
  assert.equal(body.get('seleccion'),'1,3,4');assert.equal(body.get('formato'),'pdf');assert.equal(body.has('monto'),false);
  terminar({ok:true,headers:{get:n=>n==='content-type'?'application/pdf':'attachment; filename="ODT.pdf"'},blob:async()=>({})});
  await pendiente;assert.equal(descargas[0],'ODT.pdf');assert.equal(p.cantidad.textContent,'3');
  responder=async()=>({ok:true,headers:{get:()=> 'text/html'}});
  await p.botones[0].handlers.click();assert.match(p.estado.textContent,/sesión/);assert.equal(descargas.length,1);
  responder=async()=>({ok:false,headers:{get:()=> 'text/plain'},text:async()=> 'Selección fuera del alcance'});
  await p.botones[0].handlers.click();assert.equal(p.estado.textContent,'Selección fuera del alcance');assert.equal(p.botones[0].disabled,false);
  p.limpiar.handlers.click();assert.equal(p.cantidad.textContent,'0');assert.equal(pantalla().cantidad.textContent,'0');
  p=pantalla({tipo:'periodo',ids:['8'],url:'https://local/historial/?periodo=8'});
  p.pagina.checked=true;p.pagina.handlers.change();
  assert.equal(pantalla({tipo:'periodo',ids:['9'],url:'https://local/historial/?periodo=9'}).cantidad.textContent,'1');
  console.log('Selección entre páginas, aislamiento por usuario/filtros, períodos, CSRF, descarga única y errores: OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
