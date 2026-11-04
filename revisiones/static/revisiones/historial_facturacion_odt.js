
document.addEventListener("DOMContentLoaded", () => {
    "use strict";

    const modal = document.getElementById("modalHistorial");
    const numeroTitulo = document.getElementById("historialNumero");
    const contenido = document.getElementById("historialContenido");
    const cerrar = document.getElementById("cerrarHistorial");

    if (!modal || !numeroTitulo || !contenido) return;

    function crearElemento(etiqueta, clase = "", texto) {
        const elemento = document.createElement(etiqueta);

        if (clase) elemento.className = clase;

        if (texto !== undefined) {
            elemento.textContent = String(texto);
        }

        return elemento;
    }

    function formatearFecha(valor) {
        if (!valor) return "Fecha no disponible";

        const fecha = new Date(valor);

        if (Number.isNaN(fecha.getTime())) {
            return "Fecha no disponible";
        }

        return fecha.toLocaleString("es-CL", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false
        });
    }

    function mostrarEvento(evento) {
        const tarjeta = crearElemento(
            "div",
            "historial-evento"
        );

        const cabecera = crearElemento(
            "div",
            "historial-evento-cabecera"
        );

        cabecera.appendChild(
            crearElemento(
                "span",
                "historial-fecha",
                formatearFecha(evento.fecha)
            )
        );

        cabecera.appendChild(
            crearElemento(
                "span",
                "historial-usuario",
                evento.usuario || "Usuario no identificado"
            )
        );

        tarjeta.appendChild(cabecera);

        tarjeta.appendChild(
            crearElemento(
                "div",
                "historial-estados",
                "Acción: " + (evento.accion || "Sin acción")
            )
        );

        const observaciones = crearElemento(
            "div",
            "historial-cambios"
        );

        const original = evento.observacion || "";
        const patronImagen = /<img\b[^>]*>/gi;

        const imagenes = original.match(patronImagen) || [];

        const texto = original
            .replace(patronImagen, "")
            .trim();

        const observacion = crearElemento(
            "div",
            "historial-cambio",
            texto || (
                imagenes.length
                    ? "Imagen adjunta:"
                    : "Sin observaciones"
            )
        );

        observacion.style.whiteSpace = "pre-wrap";
        observaciones.appendChild(observacion);

        imagenes.forEach(etiqueta => {
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
                imagen.alt = "Firma o imagen de SoftGuard";
                imagen.className = "historial-firma";
                imagen.loading = "lazy";
                imagen.referrerPolicy = "no-referrer";

                observaciones.appendChild(imagen);

            } catch (error) {
                console.warn("Imagen de historial no válida.");
            }
        });

        tarjeta.appendChild(observaciones);

        if (evento.correo_usuario) {
            tarjeta.appendChild(
                crearElemento(
                    "div",
                    "historial-usuario",
                    "Correo: " + evento.correo_usuario
                )
            );
        }

        if (evento.correo_observacion) {
            tarjeta.appendChild(
                crearElemento(
                    "div",
                    "historial-usuario",
                    "Correo en observación: " +
                        evento.correo_observacion
                )
            );
        }

        return tarjeta;
    }

    async function abrirHistorial(numero, url) {
        numeroTitulo.textContent = numero;

        contenido.replaceChildren(
            crearElemento(
                "p",
                "hint",
                "Cargando historial..."
            )
        );

        if (!modal.open) {
            modal.showModal();
        }

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
                    "No se pudo consultar el historial."
                );
            }

            const datos = await respuesta.json();

            if (!datos.ok) {
                throw new Error(
                    "El servidor no pudo recuperar el historial."
                );
            }

            contenido.replaceChildren();

            if (!datos.eventos || datos.eventos.length === 0) {
                contenido.appendChild(
                    crearElemento(
                        "div",
                        "historial-vacio",
                        "Esta ODT no tiene eventos registrados."
                    )
                );
                return;
            }

            contenido.appendChild(
                crearElemento(
                    "div",
                    "historial-total",
                    `${datos.total ?? datos.eventos.length} evento(s) registrado(s)`
                )
            );

            const lista = crearElemento(
                "div",
                "historial-lista"
            );

            datos.eventos.forEach(evento => {
                lista.appendChild(mostrarEvento(evento));
            });

            contenido.appendChild(lista);

        } catch (error) {
            contenido.replaceChildren(
                crearElemento(
                    "div",
                    "historial-vacio",
                    error.message
                )
            );
        }
    }

    document.querySelectorAll(
        ".btn-historial-odt"
    ).forEach(boton => {
        boton.addEventListener("click", () => {
            abrirHistorial(
                boton.dataset.numero,
                boton.dataset.url
            );
        });
    });

    if (cerrar) {
        cerrar.addEventListener("click", () => {
            modal.close();
        });
    }
});
