/* Reabrir es una operación explícita: no habilita la edición de filas rechazadas. */
(() => {
  'use strict';
  const dialog = document.getElementById('confirmarReapertura');
  if (!dialog) return;
  const form = document.getElementById('formReapertura');
  const motivo = document.getElementById('motivoReapertura');
  const error = document.getElementById('errorReapertura');
  const confirmar = document.getElementById('aprobarReapertura');
  const cancelar = document.getElementById('cancelarReapertura');
  let fila = null;
  let numero = '';
  let guardando = false;
  document.querySelectorAll('.deshacer-rechazo').forEach(boton => {
    boton.addEventListener('click', () => {
      if (guardando) return;
      numero = boton.dataset.numero;
      fila = boton.closest('tr[data-numero]');
      document.getElementById('numeroReapertura').textContent = numero;
      motivo.value = '';
      error.textContent = '';
      dialog.showModal();
      motivo.focus();
    });
  });
  cancelar.addEventListener('click', () => { if (!guardando) dialog.close(); });
  dialog.addEventListener('cancel', e => { if (guardando) e.preventDefault(); });
  form.addEventListener('submit', async evento => {
    evento.preventDefault();
    if (guardando) return;
    if (!motivo.value.trim()) { error.textContent = 'Indica el motivo para deshacer el rechazo.'; return; }
    guardando = true;
    confirmar.disabled = cancelar.disabled = true;
    error.textContent = '';
    try {
      const respuesta = await fetch(dialog.dataset.url, {
        method: 'POST', credentials: 'same-origin',
        headers: {'X-CSRFToken': document.querySelector('#csrf-container input[name=csrfmiddlewaretoken]')?.value || '',
          'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'},
        body: new URLSearchParams({numero, motivo: motivo.value.trim()}).toString()
      });
      if (!respuesta.headers.get('content-type')?.includes('application/json')) throw Error('No se pudo deshacer el rechazo. Actualiza la pantalla.');
      const datos = await respuesta.json();
      if (!respuesta.ok || !datos.ok) throw Error(datos.error || 'No se pudo deshacer el rechazo.');
      dialog.close();
      if (window.SSTTPosicionBandeja?.recargar) window.SSTTPosicionBandeja.recargar(fila);
      else window.location.reload();
    } catch (e) {
      error.textContent = e.message;
    } finally {
      guardando = false;
      confirmar.disabled = cancelar.disabled = false;
    }
  });
})();
