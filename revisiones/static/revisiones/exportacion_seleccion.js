/* Guarda solo identificadores por usuario, filtros y pantalla; el servidor revalida todo. */
(() => {
  'use strict';
  document.querySelectorAll('[data-exportar-seleccion]').forEach(panel => {
    const tipo=panel.dataset.tipo;
    const opciones=[...document.querySelectorAll(tipo==='odt'?'.seleccion-odt':'.seleccion-periodo')];
    const pagina=document.querySelector(`.seleccion-pagina[data-tipo="${tipo}"]`);
    const botones=[...panel.querySelectorAll('[data-descargar]')];
    const estado=panel.querySelector('[data-estado-exportacion]');
    const usuario=document.querySelector('[data-sstt-menu]')?.dataset.usuario || 'sin-usuario';
    const url=new URL(window.location.href);
    for(const k of ['page','ubicar_odt','filas_guardadas','formato'])url.searchParams.delete(k);
    url.searchParams.sort();
    const clave=`sstt_exportar_v1:${usuario}:${tipo}:${url.pathname}:${tipo==='odt'?url.searchParams.toString():''}`;
    const limite=tipo==='odt'?2000:120;
    const valido=id=>/^[1-9][0-9]{0,9}$/.test(String(id));
    let seleccion=new Set();let descargando=false;
    try{const datos=JSON.parse(sessionStorage.getItem(clave)||'[]');if(Array.isArray(datos))seleccion=new Set(datos.filter(valido).slice(0,limite).map(String));}catch(_){/* Sin almacenamiento también se puede exportar la página actual. */}
    function actualizar(){
      opciones.forEach(c=>{c.checked=seleccion.has(c.value)&&!c.disabled;});
      panel.querySelector('[data-cantidad-seleccion]').textContent=String(seleccion.size);
      botones.forEach(b=>{b.disabled=!seleccion.size||descargando;});
      if(pagina){const activas=opciones.filter(c=>!c.disabled);pagina.checked=!!activas.length&&activas.every(c=>c.checked);pagina.indeterminate=!pagina.checked&&activas.some(c=>c.checked);}
      try{sessionStorage.setItem(clave,JSON.stringify([...seleccion]));}catch(_){}
    }
    opciones.forEach(c=>c.addEventListener('change',()=>{
      if(c.checked){if(seleccion.size>=limite){c.checked=false;estado.textContent=`Máximo ${limite} registros por descarga.`;}else seleccion.add(c.value);}
      else seleccion.delete(c.value);
      actualizar();
    }));
    pagina?.addEventListener('change',()=>{
      for(const c of opciones.filter(c=>!c.disabled)){
        if(pagina.checked&&seleccion.size<limite)seleccion.add(c.value);
        else if(!pagina.checked)seleccion.delete(c.value);
      }actualizar();
    });
    panel.querySelector('[data-limpiar-seleccion]').addEventListener('click',()=>{seleccion.clear();estado.textContent='';actualizar();});
    botones.forEach(b=>b.addEventListener('click',async()=>{
      if(descargando||!seleccion.size)return;
      descargando=true;estado.textContent='Generando archivo…';actualizar();
      try{
        const respuesta=await fetch(panel.dataset.url,{method:'POST',credentials:'same-origin',headers:{
          'X-CSRFToken':panel.querySelector('[name=csrfmiddlewaretoken]')?.value||'',
          'Content-Type':'application/x-www-form-urlencoded'},
          body:new URLSearchParams({exportar:'seleccion',seleccion:[...seleccion].join(','),formato:b.dataset.descargar}).toString()});
        const mime=respuesta.headers.get('content-type')||'';
        if(!respuesta.ok){const texto=await respuesta.text();throw Error(mime.includes('text/plain')||!mime.includes('html')?texto.slice(0,400):'No se pudo generar el archivo. Revisa permisos y selección.');}
        if(!mime.includes('application/pdf')&&!mime.includes('spreadsheetml'))throw Error('La sesión pudo expirar. Actualiza la pantalla e intenta de nuevo.');
        const blob=await respuesta.blob();const enlace=document.createElement('a');const temporal=URL.createObjectURL(blob);
        enlace.href=temporal;enlace.download=(respuesta.headers.get('content-disposition')||'').match(/filename="([^"]+)"/)?.[1]||`Informe.${b.dataset.descargar}`;
        document.body.appendChild(enlace);enlace.click();enlace.remove();setTimeout(()=>URL.revokeObjectURL(temporal),5000);
        estado.textContent='Archivo descargado. Se conservó la selección.';
      }catch(e){estado.textContent=e.message;}finally{descargando=false;actualizar();}
    }));
    actualizar();
  });
})();
