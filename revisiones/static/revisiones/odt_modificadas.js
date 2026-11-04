document.addEventListener("DOMContentLoaded", () => {
  "use strict";
  const limpiarNumeroODT = valor => String(valor ?? "").replace(/[\s.\u00A0\u202F]/g, "").trim();
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
