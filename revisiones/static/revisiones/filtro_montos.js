/* Lista de importes de Pago técnico. No cambia el orden ni el guardado de filas. */
(function () {
  "use strict";
  const lista = document.getElementById("listaMontos");
  if (!lista) return;
  const opciones = Array.from(lista.querySelectorAll("input[name=monto]"));
  const resumen = document.getElementById("montosResumen");
  function actualizar() {
    const seleccionados = opciones.filter(el => el.checked);
    resumen.textContent = seleccionados.length === opciones.length ? "Todos los montos"
      : seleccionados.length === 0 ? "Ningún monto seleccionado"
      : seleccionados.length === 1 ? seleccionados[0].closest("label").textContent.trim()
      : `${seleccionados.length} montos seleccionados`;
    document.getElementById("cantidadMontos").textContent = `${seleccionados.length} seleccionados`;
  }
  lista.addEventListener("change", actualizar);
  for (const [id, marcado] of [["todosMontos", true], ["limpiarMontos", false]]) {
    document.getElementById(id).addEventListener("click", function () {
      opciones.forEach(el => { el.checked = marcado; });
      actualizar();
    });
  }
  document.getElementById("buscarMonto").addEventListener("input", function () {
    const normalizar = texto => texto.replace(/[\s.$,]/g, "");
    const buscar = normalizar(this.value);
    opciones.forEach(el => {
      el.closest("label").style.display = normalizar(el.closest("label").textContent).includes(buscar) ? "" : "none";
    });
  });
  // Todos significa sin restricción, también al cambiar fechas/servicios.
  document.querySelector("form.filters").addEventListener("formdata", function (event) {
    if (opciones.length && opciones.every(el => el.checked)) {
      event.formData.delete("monto");
      event.formData.delete("montos_filtrados");
    }
  });
  actualizar();
})();
