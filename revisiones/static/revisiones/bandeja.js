
document.addEventListener("DOMContentLoaded", () => {
  "use strict";

  // =====================================================
  // FORMATO DE MONEDA CHILENA
  // =====================================================

  const dinero = valor =>
    new Intl.NumberFormat("es-CL", {
      style: "currency",
      currency: "CLP",
      minimumFractionDigits: 0,
      maximumFractionDigits: 2
    }).format(valor);

  // Convierte formatos CLP sin confundir 2.00 con 200.
  // 2, 2.00, 2,00 -> 2; 2.000 -> 2000; 20.000,50 -> 20000.50.
  const montoPlano = texto => {
    let valor = String(texto ?? "")
      .trim()
      .replace(/[\s\u00A0\u202F$]/g, "");

    if (!valor) return "";
    if (!/^[0-9.,]+$/.test(valor)) return "";

    const ultimaComa = valor.lastIndexOf(",");
    const ultimoPunto = valor.lastIndexOf(".");

    if (ultimaComa !== -1 && ultimoPunto !== -1) {
      const separadorDecimal = ultimaComa > ultimoPunto ? "," : ".";
      const indice = Math.max(ultimaComa, ultimoPunto);
      const enteros = valor.slice(0, indice).replace(/[.,]/g, "");
      const decimales = valor.slice(indice + 1);
      return /^[0-9]{1,2}$/.test(decimales)
        ? `${enteros}.${decimales}` : "";
    }

    if (ultimaComa !== -1) {
      if ((valor.match(/,/g) || []).length > 1) return "";
      return valor.replace(",", ".");
    }

    if (ultimoPunto !== -1) {
      const partes = valor.split(".");
      if (partes.length > 2) {
        return partes.slice(1).every(parte => /^\d{3}$/.test(parte))
          ? partes.join("") : "";
      }
      // Tres dígitos después del punto: separador de miles CLP.
      if (/^\d{3}$/.test(partes[1])) return partes.join("");
    }
    return valor;
  };

  const montoValido = texto =>
    /^\d+(?:\.\d{1,2})?$/.test(texto);

  const montoNumero = texto => {
    const plano = montoPlano(texto);
    return montoValido(plano) ? Number(plano) : NaN;
  };

  // Eliminar separadores visuales del número de ODT.
  // Ejemplos: 77 527, 77.527 -> 77527
  const limpiarNumeroODT = valor =>
    String(valor ?? "")
      .replace(/[\s.\u00A0\u202F]/g, "")
      .trim();

  document.querySelectorAll(
    ".money-kpi, .money-original"
  ).forEach(elemento => {
    const valor = Number(elemento.dataset.amount);

    elemento.textContent = Number.isFinite(valor)
      ? dinero(valor)
      : "$0";
  });

  // =====================================================
  // FORMATO DE DURACIÓN SLA
  // =====================================================

  document.querySelectorAll(".sla-tiempo").forEach(elemento => {
    const segundos = Number(elemento.dataset.segundos);

    if (!Number.isFinite(segundos) || segundos < 0) {
      elemento.textContent = "";
      return;
    }

    const horas = Math.floor(segundos / 3600);
    const minutos = Math.floor((segundos % 3600) / 60);

    elemento.textContent = `${horas} h ${minutos} min`;
  });

  // =====================================================
  // FILTRO MÚLTIPLE DE SERVICIOS
  // =====================================================

  const dropdown = document.getElementById("serviciosDropdown");
  const buscador = document.getElementById("buscarServicio");
  const listaServicios = document.getElementById("listaServicios");

  if (listaServicios) {
    const opciones = [
      ...listaServicios.querySelectorAll(".multi-option")
    ];

    const checksServicio = [
      ...listaServicios.querySelectorAll(
        'input[type="checkbox"][name="servicios"]'
      )
    ];

    function resumenServicios() {
      const resumen = document.getElementById("serviciosResumen");
      const contador = document.getElementById("cantidadServicios");

      const seleccionados = listaServicios.querySelectorAll(
        'input[name="servicios"]:checked'
      );

      const cantidad = seleccionados.length;

      if (resumen) {
        if (cantidad === 0) {
          resumen.textContent = "Todos los servicios";
        } else if (cantidad === 1) {
          resumen.textContent = seleccionados[0].value;
        } else {
          resumen.textContent =
            `${cantidad} servicios seleccionados`;
        }
      }

      if (contador) {
        contador.textContent =
          `${cantidad} seleccionado${cantidad === 1 ? "" : "s"}`;
      }
    }

    listaServicios.addEventListener(
      "change",
      resumenServicios
    );

    if (buscador) {
      buscador.addEventListener("input", () => {
        const texto = buscador.value
          .toLocaleLowerCase("es")
          .normalize("NFD")
          .replace(/[\u0300-\u036f]/g, "");

        opciones.forEach(opcion => {
          const nombre = opcion.textContent
            .toLocaleLowerCase("es")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "");

          opcion.style.display = nombre.includes(texto)
            ? ""
            : "none";
        });
      });
    }

    const limpiarServicios =
      document.getElementById("limpiarServicios");

    if (limpiarServicios) {
      limpiarServicios.addEventListener("click", () => {
        checksServicio.forEach(check => {
          check.checked = false;
        });

        resumenServicios();
      });
    }

    if (dropdown) {
      document.addEventListener("click", evento => {
        if (!dropdown.contains(evento.target)) {
          dropdown.open = false;
        }
      });
    }

    resumenServicios();
  }

  // =====================================================
  // VENTANA DE CONFIRMACIÓN DE MONTO
  // =====================================================

  const dialog = document.getElementById("confirmarMonto");
  let resolverConfirmacion = null;

  function cerrarConfirmacion(aceptado) {
    if (dialog && dialog.open) {
      dialog.close();
    }

    if (resolverConfirmacion) {
      resolverConfirmacion(aceptado);
      resolverConfirmacion = null;
    }
  }

  const cancelarMonto = document.getElementById("cancelarMonto");
  const aceptarMonto = document.getElementById("aceptarMonto");

  if (cancelarMonto) {
    cancelarMonto.addEventListener("click", () => {
      cerrarConfirmacion(false);
    });
  }

  if (aceptarMonto) {
    aceptarMonto.addEventListener("click", () => {
      cerrarConfirmacion(true);
    });
  }

  if (dialog) {
    dialog.addEventListener("cancel", evento => {
      evento.preventDefault();
      cerrarConfirmacion(false);
    });

    dialog.addEventListener("close", () => {
      if (resolverConfirmacion) {
        resolverConfirmacion(false);
        resolverConfirmacion = null;
      }
    });
  }

  function confirmarCambio(numero, anterior, nuevo) {
    return new Promise(resolve => {
      if (!dialog) {
        resolve(false);
        return;
      }

      resolverConfirmacion = resolve;

      const numeroElemento =
        document.getElementById("dialogODT");

      const anteriorElemento =
        document.getElementById("dialogAnterior");

      const nuevoElemento =
        document.getElementById("dialogNuevo");

      const diferenciaElemento =
        document.getElementById("dialogDiferencia");

      if (numeroElemento) {
        numeroElemento.textContent = numero;
      }

      if (anteriorElemento) {
        anteriorElemento.textContent = dinero(anterior);
      }

      if (nuevoElemento) {
        nuevoElemento.textContent = dinero(nuevo);
      }

      if (diferenciaElemento) {
        diferenciaElemento.textContent =
          dinero(nuevo - anterior);
      }

      dialog.showModal();
    });
  }

  // =====================================================
  // TOKEN CSRF Y PETICIONES AL SERVIDOR
  // =====================================================

  const token = document.querySelector(
    "#csrf-container input[name=csrfmiddlewaretoken]"
  )?.value || "";

  async function enviarCambio(url, datos) {
    if (!url) {
      throw new Error(
        "No tienes permiso para realizar esta operación."
      );
    }

    const respuesta = await fetch(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": token,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
      },
      credentials: "same-origin",
      body: new URLSearchParams(datos).toString()
    });

    const tipoContenido =
      respuesta.headers.get("content-type") || "";

    if (!tipoContenido.includes("application/json")) {
      throw new Error(
        `El servidor devolvió una respuesta inesperada (${respuesta.status}).`
      );
    }

    const resultado = await respuesta.json();

    if (!respuesta.ok || !resultado.ok) {
      throw new Error(
        resultado.error || "No se pudo guardar el cambio."
      );
    }

    return resultado;
  }

  // =====================================================
  // PERMISOS GENERALES
  // =====================================================

  const puedeEditar =
    document.body.dataset.puedeEditar === "1";

  const puedeRevisar =
    document.body.dataset.puedeRevisar === "1";


  
  // =====================================================
  // CONSERVAR POSICIÓN DE LA TABLA AL GUARDAR
  // =====================================================

  function recargarTrasGuardar(fila) {
    if (window.SSTTPosicionBandeja) {
      window.SSTTPosicionBandeja.recargar(fila);
    } else {
      window.location.reload();
    }
  }

  // =====================================================
  // EDICIÓN INDIVIDUAL DE ODT
  // =====================================================

  document.querySelectorAll("tr[data-numero]").forEach(fila => {
    const servicio = fila.querySelector(".service-input");
    const monto = fila.querySelector(".amount-input");
    const estado = fila.querySelector(".review-select");
    const informe = fila.querySelector(".report-select");
    const editar = fila.querySelector(".edit-row");
    const guardar = fila.querySelector(".save-row");
    const cancelar = fila.querySelector(".cancel-row");
    const error = fila.querySelector(".error-row");

    // Validar elementos antes de utilizarlos.
    if (
      !servicio || !monto || !estado || !informe ||
      !editar || !guardar || !cancelar || !error
    ) {
      return;
    }

    const numeroODT = limpiarNumeroODT(
      fila.dataset.numero
    );

    const estaBloqueada =
      fila.dataset.bloqueada === "1";

    // Guardar permisos originales del HTML.
    // No debemos habilitar un informe sin autorización.
    const puedeCambiarInforme = !informe.disabled;

    // =================================================
    // PROTECCIÓN VISUAL DE ODT BLOQUEADAS
    // =================================================

    if (estaBloqueada) {
      servicio.disabled = true;
      monto.disabled = true;
      estado.disabled = true;
      informe.disabled = true;

      editar.disabled = true;
      guardar.disabled = true;
      cancelar.disabled = true;

      editar.title =
        "ODT bloqueada: no permite modificaciones";

      // El historial funciona con otro controlador.
      // No agregamos eventos de edición a esta fila.
      return;
    }

    // =================================================
    // PERMISOS DE EDICIÓN
    // =================================================

    if (!puedeEditar) {
      servicio.disabled = true;
      monto.disabled = true;

      editar.disabled = true;
      guardar.disabled = true;
      cancelar.disabled = true;
    }

    if (!puedeRevisar) {
      estado.disabled = true;
    }

    if (!puedeCambiarInforme) {
      informe.disabled = true;
    }

    // =================================================
    // GUARDAR ESTADO DE REVISIÓN
    // =================================================

    if (puedeRevisar) {
      estado.addEventListener("change", async () => {
        const anterior = estado.dataset.saved;
        const nuevo = estado.value;

        if (nuevo === anterior) return;

        let comentario = "";

        if (
          nuevo === "RECHAZADA" ||
          nuevo === "EN_REVISION"
        ) {
          const accion = nuevo === "RECHAZADA"
            ? "rechazo"
            : "cambio a En revisión";

          const motivo = prompt(
            `Indica el motivo del ${accion} de la ODT ${numeroODT}:`
          );

          if (!motivo || !motivo.trim()) {
            estado.value = anterior;
            return;
          }

          comentario = motivo.trim();
        }

        estado.disabled = true;
        error.textContent = "";

        try {
          await enviarCambio(
            document.body.dataset.revisionUrl,
            {
              numero: numeroODT,
              estado: nuevo,
              comentario: comentario
            }
          );

          estado.dataset.saved = nuevo;

          // Actualizar indicadores y bloqueos.
          recargarTrasGuardar(fila);

        } catch (ex) {
          estado.value = anterior;
          error.textContent = ex.message;
          estado.disabled = false;
        }
      });
    }

    // =================================================
    // GUARDAR ESTADO DE INFORME
    // =================================================

    if (puedeCambiarInforme) {
      informe.addEventListener("change", async () => {
        const anterior = informe.dataset.saved;
        const nuevo = informe.value;

        if (nuevo === anterior) return;

        informe.disabled = true;
        error.textContent = "";

        try {
          await enviarCambio(
            document.body.dataset.informeUrl,
            {
              numero: numeroODT,
              estado: nuevo
            }
          );

          informe.dataset.saved = nuevo;
          window.SSTTPosicionBandeja?.marcar(fila);

        } catch (ex) {
          informe.value = anterior;
          error.textContent = ex.message;

        } finally {
          informe.disabled = false;
        }
      });
    }

    // =================================================
    // VALORES INICIALES
    // =================================================

    const servicioInicial = servicio.value;

    // Leer el monto antes de aplicarle formato.
    const montoInicial = montoNumero(monto.value);

    if (Number.isFinite(montoInicial)) {
      monto.value = dinero(montoInicial);
    }

    function pintarCambios() {
      servicio.classList.toggle(
        "changed",
        servicio.value !== servicioInicial
      );

      const actual = montoNumero(monto.value);

      monto.classList.toggle(
        "changed",
        Number.isFinite(actual) &&
        actual !== montoInicial
      );
    }

    function activarEdicion() {
      if (estaBloqueada || !puedeEditar) return;

      fila.classList.add("editing");

      servicio.disabled = false;
      monto.disabled = false;

      editar.hidden = true;
      guardar.hidden = false;
      cancelar.hidden = false;

      error.textContent = "";
      servicio.focus();
    }

    function desactivarEdicion() {
      fila.classList.remove("editing");

      servicio.disabled = true;
      monto.disabled = true;

      editar.hidden = false;
      guardar.hidden = true;
      cancelar.hidden = true;

      servicio.classList.remove("changed");
      monto.classList.remove("changed");
    }

    // =================================================
    // BOTÓN EDITAR
    // =================================================

    if (puedeEditar) {
      editar.addEventListener("click", () => {
        activarEdicion();
      });
    }

    // =================================================
    // BOTÓN CANCELAR
    // =================================================

    cancelar.addEventListener("click", () => {
      servicio.value = servicioInicial;
      monto.value = dinero(montoInicial);

      error.textContent = "";
      desactivarEdicion();
    });

    // =================================================
    // FORMATO DEL MONTO
    // =================================================

    monto.addEventListener("focus", () => {
      if (monto.disabled) return;

      monto.value = montoPlano(monto.value);
      monto.select();
    });

    monto.addEventListener("blur", () => {
      if (monto.disabled) return;

      const plano = montoPlano(monto.value);

      if (
        montoValido(plano) &&
        Number.isFinite(Number(plano))
      ) {
        monto.value = dinero(Number(plano));
      }

      pintarCambios();
    });

    servicio.addEventListener("input", pintarCambios);
    monto.addEventListener("input", pintarCambios);

    // =================================================
    // BOTÓN GUARDAR
    // =================================================

    if (puedeEditar) {
      guardar.addEventListener("click", async () => {
        if (estaBloqueada) return;

        error.textContent = "";

        const plano = montoPlano(monto.value);
        const valor = Number(plano);
        const anterior = montoInicial;

        if (!servicio.value.trim()) {
          alert("Debes indicar un servicio.");
          servicio.focus();
          return;
        }

        if (
          !montoValido(plano) ||
          !Number.isFinite(valor) ||
          valor < 0 ||
          valor > 999999999999.99
        ) {
          alert(
            "Ingresa un monto válido con máximo 2 decimales."
          );
          monto.focus();
          return;
        }

        const cambioMonto = valor !== anterior;

        const cambioServicio =
          servicio.value.trim() !== servicioInicial;

        if (!cambioMonto && !cambioServicio) {
          desactivarEdicion();
          return;
        }

        if (cambioMonto) {
          const confirmado = await confirmarCambio(
            numeroODT,
            anterior,
            valor
          );

          if (!confirmado) return;

        } else {
          const confirmado = confirm(
            `¿Guardar cambios de la ODT ${numeroODT}?`
          );

          if (!confirmado) return;
        }

        // El cambio de revisión se realiza únicamente
        // desde el selector de revisión.
        const datos = {
          numero: numeroODT,
          servicio: servicio.value.trim(),
          monto: plano,
          estado: estado.value,
          comentario: "",
          confirmar_monto: cambioMonto ? "SI" : "NO"
        };

        guardar.disabled = true;
        cancelar.disabled = true;
        guardar.textContent = "Guardando...";

        try {
          await enviarCambio(
            document.body.dataset.guardarUrl,
            datos
          );

          recargarTrasGuardar(fila);

        } catch (ex) {
          error.textContent = ex.message;

          guardar.disabled = false;
          cancelar.disabled = false;
          guardar.textContent = "Guardar";
        }
      });
    }
  });

  // =====================================================
  // SINCRONIZAR BARRAS HORIZONTALES
  // =====================================================

  const scrollSuperior =
    document.getElementById("tablaScrollSuperior");

  const scrollPrincipal =
    document.getElementById("tablaScrollPrincipal");

  const scrollAncho =
    document.getElementById("tablaScrollAncho");

  if (scrollSuperior && scrollPrincipal && scrollAncho) {
    const tabla = scrollPrincipal.querySelector("table");

    function actualizarAnchoScroll() {
      if (tabla) {
        scrollAncho.style.width =
          `${tabla.scrollWidth}px`;
      }
    }

    let sincronizando = false;

    scrollSuperior.addEventListener("scroll", () => {
      if (sincronizando) return;

      sincronizando = true;
      scrollPrincipal.scrollLeft =
        scrollSuperior.scrollLeft;
      sincronizando = false;
    });

    scrollPrincipal.addEventListener("scroll", () => {
      if (sincronizando) return;

      sincronizando = true;
      scrollSuperior.scrollLeft =
        scrollPrincipal.scrollLeft;
      sincronizando = false;
    });

    actualizarAnchoScroll();

    window.addEventListener(
      "resize",
      actualizarAnchoScroll
    );
  }

  // =====================================================
  // DESPLAZAMIENTO HORIZONTAL
  // =====================================================

  if (scrollPrincipal) {
    scrollPrincipal.addEventListener(
      "wheel",
      evento => {
        if (
          !evento.shiftKey ||
          scrollPrincipal.scrollWidth <=
            scrollPrincipal.clientWidth
        ) {
          return;
        }

        evento.preventDefault();

        scrollPrincipal.scrollLeft +=
          evento.deltaY || evento.deltaX;
      },
      { passive: false }
    );

    let arrastre = null;
    let evitarClick = false;

    const interactivo =
      "a, button, input, select, textarea, label, summary, " +
      "[contenteditable], .obs";

    scrollPrincipal.addEventListener(
      "pointerdown",
      evento => {
        if (
          evento.button !== 0 ||
          evento.pointerType === "touch" ||
          evento.target.closest(interactivo) ||
          !evento.target.closest("td, th") ||
          scrollPrincipal.scrollWidth <=
            scrollPrincipal.clientWidth
        ) {
          return;
        }

        arrastre = {
          x: evento.clientX,
          left: scrollPrincipal.scrollLeft,
          activo: false
        };
      }
    );

    scrollPrincipal.addEventListener(
      "pointermove",
      evento => {
        if (!arrastre || !(evento.buttons & 1)) return;

        const distancia =
          evento.clientX - arrastre.x;

        if (
          !arrastre.activo &&
          Math.abs(distancia) < 7
        ) {
          return;
        }

        if (!arrastre.activo) {
          arrastre.activo = true;

          scrollPrincipal.classList.add(
            "arrastrando-tabla"
          );

          scrollPrincipal.setPointerCapture(
            evento.pointerId
          );
        }

        scrollPrincipal.scrollLeft =
          arrastre.left - distancia;

        evento.preventDefault();
      }
    );

    const terminarArrastre = () => {
      if (arrastre?.activo) {
        evitarClick = true;

        setTimeout(() => {
          evitarClick = false;
        }, 0);
      }

      arrastre = null;

      scrollPrincipal.classList.remove(
        "arrastrando-tabla"
      );
    };

    scrollPrincipal.addEventListener(
      "pointerup",
      terminarArrastre
    );

    scrollPrincipal.addEventListener(
      "pointercancel",
      terminarArrastre
    );

    scrollPrincipal.addEventListener(
      "lostpointercapture",
      terminarArrastre
    );

    scrollPrincipal.addEventListener(
      "click",
      evento => {
        if (evitarClick) {
          evento.preventDefault();
          evento.stopPropagation();
        }
      },
      true
    );
  }

  // =====================================================
  // HISTORIAL DE MODIFICACIONES DE ODT
  // =====================================================

  const modalHistorial =
    document.getElementById("modalHistorial");

  const historialNumero =
    document.getElementById("historialNumero");

  const historialContenido =
    document.getElementById("historialContenido");

  const cerrarHistorial =
    document.getElementById("cerrarHistorial");

  // =====================================================
  // CREAR ELEMENTOS HTML DE FORMA SEGURA
  // =====================================================

  function crearElementoHistorial(etiqueta, clase, texto) {
    const elemento = document.createElement(etiqueta);

    if (clase) {
      elemento.className = clase;
    }

    if (texto !== undefined) {
      elemento.textContent = texto;
    }

    return elemento;
  }

  // =====================================================
  // MOSTRAR EVENTO DEL HISTORIAL
  // =====================================================

  function mostrarEventoHistorial(evento) {
    const tarjeta = crearElementoHistorial(
      "div",
      "historial-evento"
    );

    const cabecera = crearElementoHistorial(
      "div",
      "historial-evento-cabecera"
    );

    let fechaTexto = "Fecha no disponible";

    if (evento.fecha) {
      const fecha = new Date(evento.fecha);

      if (!Number.isNaN(fecha.getTime())) {
        fechaTexto = fecha.toLocaleString("es-CL", {
          day: "2-digit",
          month: "2-digit",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
          hour12: false
        });
      }
    }

    cabecera.appendChild(
      crearElementoHistorial(
        "span",
        "historial-fecha",
        fechaTexto
      )
    );

    cabecera.appendChild(
      crearElementoHistorial(
        "span",
        "historial-usuario",
        evento.usuario || "Usuario no identificado"
      )
    );

    tarjeta.appendChild(cabecera);

    tarjeta.appendChild(
      crearElementoHistorial(
        "div",
        "historial-estados",
        "Acción: " + (evento.accion || "Sin acción")
      )
    );

    // =================================================
    // OBSERVACIONES Y FIRMAS
    // =================================================

    const observaciones = crearElementoHistorial(
      "div",
      "historial-cambios"
    );

    const textoOriginal = evento.observacion || "";

    const patronImagen = /<img\b[^>]*>/gi;

    const etiquetasImagen =
      textoOriginal.match(patronImagen) || [];

    const textoLimpio = textoOriginal
      .replace(patronImagen, "")
      .trim();

    const observacion = crearElementoHistorial(
      "div",
      "historial-cambio",
      textoLimpio || (
        etiquetasImagen.length
          ? "Imagen adjunta:"
          : "Sin observaciones"
      )
    );

    observacion.style.whiteSpace = "pre-wrap";

    observaciones.appendChild(observacion);

    etiquetasImagen.forEach(etiqueta => {
      const coincidencia = etiqueta.match(
        /\bsrc\s*=\s*["']([^"']+)["']/i
      );

      if (!coincidencia) return;

      try {
        const url = new URL(coincidencia[1]);

        if (
          url.protocol !== "https:" ||
          url.hostname !== "cli.firstsecurity.cl" ||
          !url.pathname.startsWith(
            "/gallery/sharedimages/postimages/"
          )
        ) {
          return;
        }

        const imagen = document.createElement("img");

        imagen.src = url.href;
        imagen.alt =
          "Firma o imagen adjunta de SoftGuard";

        imagen.className = "historial-firma";
        imagen.loading = "lazy";
        imagen.referrerPolicy = "no-referrer";

        observaciones.appendChild(imagen);

      } catch (error) {
        console.warn(
          "URL de imagen no válida."
        );
      }
    });

    tarjeta.appendChild(observaciones);

    if (evento.correo_usuario) {
      tarjeta.appendChild(
        crearElementoHistorial(
          "div",
          "historial-usuario",
          "Correo: " + evento.correo_usuario
        )
      );
    }

    if (evento.correo_observacion) {
      tarjeta.appendChild(
        crearElementoHistorial(
          "div",
          "historial-usuario",
          "Correo en observación: " +
            evento.correo_observacion
        )
      );
    }

    return tarjeta;
  }

  // =====================================================
  // CONSULTAR HISTORIAL DE ODT
  // =====================================================

  async function abrirHistorialODT(numero, url) {
    if (
      !modalHistorial ||
      !historialNumero ||
      !historialContenido
    ) {
      return;
    }

    historialNumero.textContent = numero;

    historialContenido.replaceChildren(
      crearElementoHistorial(
        "p",
        "hint",
        "Cargando historial..."
      )
    );

    modalHistorial.showModal();

    try {
      const respuesta = await fetch(url, {
        method: "GET",
        headers: {
          "Accept": "application/json"
        },
        credentials: "same-origin"
      });

      if (!respuesta.ok) {
        throw new Error(
          "No se pudo consultar el historial de la ODT."
        );
      }

      const datos = await respuesta.json();

      if (!datos.ok) {
        throw new Error(
          "El servidor no pudo recuperar el historial."
        );
      }

      historialContenido.replaceChildren();

      if (
        !datos.eventos ||
        datos.eventos.length === 0
      ) {
        historialContenido.appendChild(
          crearElementoHistorial(
            "div",
            "historial-vacio",
            "Esta ODT todavía no tiene modificaciones registradas."
          )
        );

        return;
      }

      historialContenido.appendChild(
        crearElementoHistorial(
          "div",
          "historial-total",
          `${datos.total ?? datos.eventos.length} evento(s) registrado(s)`
        )
      );

      const lista = crearElementoHistorial(
        "div",
        "historial-lista"
      );

      datos.eventos.forEach(evento => {
        lista.appendChild(
          mostrarEventoHistorial(evento)
        );
      });

      historialContenido.appendChild(lista);

    } catch (error) {
      historialContenido.replaceChildren(
        crearElementoHistorial(
          "div",
          "historial-vacio",
          error.message
        )
      );
    }
  }

  // =====================================================
  // BOTONES DE HISTORIAL
  // =====================================================

  document.querySelectorAll(".history-row").forEach(boton => {
    boton.addEventListener("click", () => {
      const fila = boton.closest("tr[data-numero]");

      if (!fila) return;

      abrirHistorialODT(
        limpiarNumeroODT(fila.dataset.numero),
        boton.dataset.url
      );
    });
  });

  // =====================================================
  // CERRAR HISTORIAL
  // =====================================================

  if (cerrarHistorial && modalHistorial) {
    cerrarHistorial.addEventListener("click", () => {
      modalHistorial.close();
    });
  }

});
