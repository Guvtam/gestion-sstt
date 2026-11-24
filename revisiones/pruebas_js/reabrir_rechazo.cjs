const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const codigo = fs.readFileSync(process.argv[2], 'utf8');
const elementos = {};
function elemento(id) {
  return elementos[id] = {handlers:{},value:'',textContent:'',disabled:false,dataset:{},
    addEventListener(t,f){this.handlers[t]=f;},focus(){this.enfocado=true;}};
}
const dialog=elemento('confirmarReapertura');
dialog.dataset.url='/reabrir-rechazo/';dialog.abierto=false;
dialog.showModal=()=>{dialog.abierto=true;};dialog.close=()=>{dialog.abierto=false;};
for(const id of ['formReapertura','motivoReapertura','errorReapertura','aprobarReapertura','cancelarReapertura','numeroReapertura']) elemento(id);
const fila={dataset:{numero:'900'}};
const boton=elemento('boton');boton.dataset.numero='900';boton.closest=()=>fila;
let peticiones=[];let comportamiento;let recargada=null;
vm.runInNewContext(codigo, {
  URLSearchParams,
  document:{getElementById:id=>elementos[id],querySelectorAll:()=>[boton],querySelector:()=>({value:'csrf-prueba'})},
  fetch:async(url,opciones)=>{peticiones.push({url,opciones});return await comportamiento();},
  window:{SSTTPosicionBandeja:{recargar:f=>{recargada=f;}},location:{reload(){throw Error('Debe conservar la fila y posición');}}}
});
const submit=()=>elementos.formReapertura.handlers.submit({preventDefault(){}});
(async()=>{
  boton.handlers.click();
  assert.equal(dialog.abierto,true);assert.equal(elementos.numeroReapertura.textContent,'900');
  elementos.cancelarReapertura.handlers.click();assert.equal(dialog.abierto,false);assert.equal(peticiones.length,0);
  boton.handlers.click();elementos.motivoReapertura.value='  ';
  await submit();assert.equal(peticiones.length,0);assert.ok(elementos.errorReapertura.textContent);
  elementos.motivoReapertura.value=' Error corregido ';
  let terminar;comportamiento=()=>new Promise(resolve=>{terminar=resolve;});
  const pendiente=submit();await submit();
  assert.equal(peticiones.length,1);assert.equal(elementos.aprobarReapertura.disabled,true);
  elementos.cancelarReapertura.handlers.click();assert.equal(dialog.abierto,true);
  let cancelado=false;dialog.handlers.cancel({preventDefault(){cancelado=true;}});assert.equal(cancelado,true);
  const p=peticiones[0];assert.equal(p.url,'/reabrir-rechazo/');assert.equal(p.opciones.method,'POST');
  assert.equal(p.opciones.headers['X-CSRFToken'],'csrf-prueba');
  const datos=new URLSearchParams(p.opciones.body);
  assert.equal(datos.get('numero'),'900');assert.equal(datos.get('motivo'),'Error corregido');assert.equal(datos.has('monto'),false);
  terminar({ok:true,headers:{get:()=> 'application/json'},json:async()=>({ok:true,estado:'APROBADA'})});
  await pendiente;assert.equal(recargada,fila);assert.equal(dialog.abierto,false);
  boton.handlers.click();elementos.motivoReapertura.value='Reintento';
  comportamiento=async()=>({ok:false,headers:{get:()=> 'application/json'},json:async()=>({error:'La ODT ya está facturada'})});
  await submit();assert.equal(dialog.abierto,true);assert.equal(elementos.errorReapertura.textContent,'La ODT ya está facturada');
  assert.equal(elementos.aprobarReapertura.disabled,false);
  console.log('Confirmación, cancelación, motivo, CSRF, envío único, errores y conservación de posición: OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
