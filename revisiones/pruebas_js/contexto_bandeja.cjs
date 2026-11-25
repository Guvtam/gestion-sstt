const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const codigo=fs.readFileSync(process.argv[2],'utf8');
function comprobar(actual,consulta){
 const cambios=[];
 vm.runInNewContext(codigo,{URL,document:{body:{dataset:{urlConsulta:consulta}}},
   window:{location:{href:actual},history:{replaceState:(s,t,u)=>cambios.push(u)}}});
 return cambios;
}
const filtros='?fecha_desde=2026-10-21&fecha_hasta=2026-11-20&orden=numero&direccion=desc';
let r=comprobar('https://local/', '/'+filtros);
assert.equal(r.length,1);assert.equal(new URL(r[0]).searchParams.get('fecha_hasta'),'2026-11-20');
r=comprobar('https://local/?page=3#tabla', '/'+filtros+'&page=3&ubicar_odt=78930&filas_guardadas=78930%2C1');
const u=new URL(r[0]);assert.equal(u.searchParams.get('page'),'3');assert.equal(u.hash,'#tabla');
assert.equal(u.searchParams.get('ubicar_odt'),'78930');assert.equal(u.searchParams.get('filas_guardadas'),'78930,1');
assert.equal(comprobar('https://local/'+filtros,'/'+filtros).length,0);
assert.equal(comprobar('https://local/','https://otro/').length,0);
assert.equal(comprobar('https://local/','/otra/').length,0);
assert.equal(comprobar('https://local/',null).length,0);
console.log('Filtros efectivos, período, orden, página, ancla y origen preservados: OK');
