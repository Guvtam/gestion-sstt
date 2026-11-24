const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const codigo = fs.readFileSync(process.argv[2], 'utf8');
const handlers = {};
const selectores = [];
function enlace(href, attrs = {}, contexto = '') {
  const a = {attrs: {href, ...attrs}, contexto,
    getAttribute(k) { return this.attrs[k] ?? null; },
    hasAttribute(k) { return k in this.attrs; },
    setAttribute(k, v) { this.attrs[k] = v; },
    closest(selector) {
      if (selector === 'a[href]') return this;
      selectores.push(selector);
      return this.contexto && selector.split(',').includes(this.contexto) ? this : null;
    }};
  return a;
}
const odt = enlace('/calendario-servicios/odt/123/?volver=x');
const cuenta = enlace('/?numero_odt=123&estado=&fecha_desde=');
const pdf = enlace('/documento.pdf', {rel: 'nofollow', title: 'Ver informe'});
const externo = enlace('https://example.com/detalle');
const anclas = [odt, cuenta, pdf, externo];
const excluidos = [];
for (const selector of ['.btn', '.stats-btn', '.fact-secondary', '.hist-secondary', 'button', '[role="button"]',
  'nav', '[role="navigation"]', '.pagination', '.visita-leyenda', '.grafico-barra',
  '[data-sstt-volver]', '[data-sstt-destino]', '[download]', '[aria-disabled="true"]',
  '[data-sstt-misma-pestana]', '.kpi-card', '.stats-kpi']) {
  const a = enlace('/destino/', {}, selector); anclas.push(a); excluidos.push(a);
}
for (const href of ['#detalle', '', 'javascript:alert(1)', 'mailto:prueba@example.com',
 'tel:123', 'data:text/plain,abc', 'http://[invalida', '/actual/?q=uno#detalle']) {
  const a = enlace(href); anclas.push(a); excluidos.push(a);
}
const explicito = enlace('/misma/', {target: '_self'}); anclas.push(explicito);
vm.runInNewContext(codigo, {
  URL, Set, location: {href: 'https://sstt.example/actual/?q=uno'},
  document: {baseURI: 'https://sstt.example/actual/?q=uno',
    querySelectorAll: () => anclas,
    addEventListener(tipo, fn, capture) { assert.equal(capture, true); handlers[tipo] = fn; }}
});
for (const a of [odt, cuenta, pdf, externo]) {
  assert.equal(a.attrs.target, '_blank'); assert.ok(a.attrs.rel.split(' ').includes('noopener'));
}
assert.equal(pdf.attrs.title, 'Ver informe');
assert.equal(pdf.attrs.rel, 'nofollow noopener');
assert.equal(odt.attrs.href, '/calendario-servicios/odt/123/?volver=x');
for (const a of excluidos) assert.equal(a.attrs.target, undefined);
assert.equal(explicito.attrs.target, '_self');
for (const tipo of ['click','auxclick','contextmenu']) {
  const dinamico = enlace('/historial/123/');
  const hijo = {closest: () => dinamico};
  handlers[tipo]({target: hijo, preventDefault() { throw Error('No interceptar navegación'); }});
  assert.equal(dinamico.attrs.target, '_blank');
  handlers[tipo]({target: hijo});
  assert.equal(dinamico.attrs.rel, 'noopener');
  const control = enlace('/guardar/', {}, '.btn');
  handlers[tipo]({target: control});
  assert.equal(control.attrs.target, undefined);
}
handlers.click({target: {}});
assert.ok(selectores.length > 0);
console.log('Enlaces normales, dinámicos, controles, descargas, destinos y atributos: OK');
