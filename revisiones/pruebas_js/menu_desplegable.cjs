const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[2], 'utf8');
function grupo() {
  return {open:false,events:{},addEventListener(n,f){this.events[n]=f},querySelector(){return {focus:()=>this.enfocado=true}}};
}
const a=grupo(), b=grupo(), events={};
const menu={querySelectorAll:()=>[a,b],contains:t=>t.interno};
vm.runInNewContext(source,{document:{querySelector:()=>menu,addEventListener:(n,f)=>events[n]=f},Array});
a.open=true;a.events.toggle();assert.equal(b.open,false);
b.open=true;b.events.toggle();assert.equal(a.open,false);
let prevenido=false;
b.events.keydown({key:'Escape',preventDefault:()=>prevenido=true});
assert.equal(b.open,false);assert.equal(b.enfocado,true);assert.equal(prevenido,true);
a.open=true;events.click({target:{interno:false}});assert.equal(a.open,false);
a.open=true;events.focusin({target:{interno:true,closest:()=>b}});assert.equal(a.open,false);
b.open=true;events.focusin({target:{interno:false}});assert.equal(b.open,false);
a.open=true;events.click({target:{interno:true,closest:()=>a}});assert.equal(a.open,true);
console.log('Desplegables: un grupo abierto, cierre exterior y Escape con foco recuperado.');
