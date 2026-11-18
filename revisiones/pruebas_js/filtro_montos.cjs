const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const elemento = () => ({textContent:'', value:'', handlers:{}, style:{},
  addEventListener(event, fn) { this.handlers[event]=fn; }});
const ids = Object.fromEntries(['listaMontos','montosResumen','cantidadMontos','todosMontos',
  'limpiarMontos','buscarMonto'].map(id=>[id,elemento()]));
const opciones = ['$0', '$2', '$25.000,50'].map(texto=>{
  const label = elemento(); label.textContent=texto;
  return {checked:true, closest:()=>label};
});
ids.listaMontos.querySelectorAll=()=>opciones;
const form=elemento();
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'), {
  document:{getElementById:id=>ids[id],querySelector:()=>form}
});
assert.equal(ids.montosResumen.textContent,'Todos los montos');
const datos = new Map([['monto','0.00'],['montos_filtrados','1']]);
form.handlers.formdata({formData:datos});
assert.equal(datos.size,0);
ids.limpiarMontos.handlers.click();
assert.ok(opciones.every(o=>!o.checked));
assert.equal(ids.montosResumen.textContent,'Ningún monto seleccionado');
datos.set('montos_filtrados','1');
form.handlers.formdata({formData:datos});
assert.equal(datos.get('montos_filtrados'),'1');
opciones[1].checked=true; ids.listaMontos.handlers.change();
assert.equal(ids.montosResumen.textContent,'$2');
opciones[2].checked=true; ids.listaMontos.handlers.change();
assert.equal(ids.montosResumen.textContent,'2 montos seleccionados');
ids.buscarMonto.value='25.000,50';
ids.buscarMonto.handlers.input.call(ids.buscarMonto);
assert.equal(opciones[0].closest().style.display,'none');
assert.equal(opciones[2].closest().style.display,'');
assert.ok(opciones[1].checked); // Buscar no modifica la selección.
ids.todosMontos.handlers.click();
assert.ok(opciones.every(o=>o.checked));
console.log('Casillas, búsqueda, resumen y envío verificados.');
