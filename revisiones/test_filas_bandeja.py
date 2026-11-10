from datetime import date
from django.test import TestCase
from .consultas.filas_bandeja import paginar_filas, cargar_complementos
from .presentacion.filas_bandeja import preparar_filas
from .facturacion_models import FacturacionContratista, FacturacionODT, PeriodoFacturacion
from .models import ODT, CatalogoCuenta, Revision, CorreccionODT


class FilasBandejaTests(TestCase):
    def setUp(self):
        ODT.objects.bulk_create([
            ODT(numero=n, cuenta_completa="FIR-1 - Cuenta", contratista="Prueba",
                servicio="MANTENCION CORRECTIVA CON COBRO", valor_pago_tecnico=100)
            for n in range(1, 61)
        ])
        CatalogoCuenta.objects.create(codigo_cuenta="FIR-1", tipo_cliente="B2B",
                                     ceco="50-01-01", requiere_revision_ceco=False)

    def datos_coordinadores(self, filas, disponible=True, identificado=True):
        return {o.numero:{"usuario":"jtapia" if identificado else None,
                "nombre":"Responsable" if identificado else "No disponible",
                "identificado":identificado,"disponible":disponible} for o in filas}

    def test_limite_50_y_desempate_por_numero_descendente(self):
        pagina=paginar_filas(ODT.objects.all(),"1")
        self.assertEqual(len(pagina.object_list),50)
        self.assertEqual([o.numero for o in pagina.object_list],list(range(60,10,-1)))
        self.assertEqual(pagina.paginator.count,60)
        segunda=paginar_filas(ODT.objects.all(),"2")
        self.assertEqual([o.numero for o in segunda.object_list],list(range(10,0,-1)))

    def test_no_recupera_odt_fuera_del_queryset_autorizado(self):
        pagina=paginar_filas(ODT.objects.filter(numero__lte=3),"1")
        self.assertEqual([o.numero for o in pagina.object_list],[3,2,1])
        self.assertEqual(pagina.paginator.count,3)

    def test_pagina_invalida_y_fuera_de_rango_conservan_get_page(self):
        self.assertEqual(paginar_filas(ODT.objects.all(),"incorrecta").number,1)
        self.assertEqual(paginar_filas(ODT.objects.all(),"999").number,2)

    def test_pagina_vacia_sin_consultas_de_complementos(self):
        pagina=paginar_filas(ODT.objects.none(),"1")
        with self.assertNumQueries(0):
            datos=cargar_complementos(pagina.object_list)
            self.assertEqual(preparar_filas([],coordinadores_pagina={},facturadas=datos.facturadas,
                catalogo=datos.catalogo,puede_procesar=False,puede_asignar=False),[])

    def test_presupuesto_lectura_independiente_de_cantidad_de_filas(self):
        for cantidad in (1,50):
            with self.subTest(cantidad=cantidad):
                with self.assertNumQueries(4):
                    pagina=paginar_filas(ODT.objects.filter(numero__lte=cantidad),"1")
                with self.assertNumQueries(2):
                    cargar_complementos(pagina.object_list)

    def test_presentacion_precargada_no_consulta_base_y_conserva_bloqueos(self):
        Revision.objects.create(odt=ODT.objects.get(numero=60),estado="RECHAZADA")
        periodo=PeriodoFacturacion.objects.create(fecha_desde=date(2026,10,21),fecha_hasta=date(2026,11,20))
        factura=FacturacionContratista.objects.create(periodo=periodo,contratista="Prueba")
        FacturacionODT.objects.create(facturacion=factura,odt=ODT.objects.get(numero=59),
                                     servicio_facturado="Servicio",monto_facturado=100)
        ODT.objects.filter(numero=58).update(valor_pago_editado=0)
        pagina=paginar_filas(ODT.objects.all(),"1")
        datos=cargar_complementos(pagina.object_list)
        with self.assertNumQueries(0):
            filas=preparar_filas(pagina.object_list,
                coordinadores_pagina=self.datos_coordinadores(pagina.object_list),
                facturadas=datos.facturadas,catalogo=datos.catalogo,
                puede_procesar=True,puede_asignar=True)
        por_numero={o.numero:o for o in filas}
        self.assertTrue(por_numero[60].esta_rechazada)
        self.assertTrue(por_numero[60].esta_bloqueada)
        self.assertTrue(por_numero[59].esta_facturada)
        self.assertTrue(por_numero[59].esta_bloqueada)
        self.assertFalse(por_numero[58].esta_bloqueada)
        self.assertEqual(por_numero[58].estado_modificacion,"PENDIENTE")
        self.assertTrue(por_numero[58].puede_procesar_modificacion)
        self.assertEqual(por_numero[58].valor_pago_editado,0)
        self.assertEqual(por_numero[58].tipo_cliente_catalogo,"B2B")
        self.assertEqual(por_numero[58].ceco_catalogo,"50-01-01")
        self.assertFalse(por_numero[58].permite_asignar_coordinador)

    def test_no_permite_asignar_si_verificacion_no_disponible(self):
        pagina=paginar_filas(ODT.objects.filter(numero=1),"1")
        datos=cargar_complementos(pagina.object_list)
        filas=preparar_filas(pagina.object_list,
            coordinadores_pagina=self.datos_coordinadores(pagina.object_list,False,False),
            facturadas=datos.facturadas,catalogo=datos.catalogo,puede_procesar=False,puede_asignar=True)
        self.assertFalse(filas[0].permite_asignar_coordinador)

    def test_catalogo_ausente_aplica_b2c_y_no_inventa_ceco(self):
        pagina=paginar_filas(ODT.objects.filter(numero=1),"1")
        filas=preparar_filas(pagina.object_list,
            coordinadores_pagina=self.datos_coordinadores(pagina.object_list),
            facturadas=frozenset(),catalogo={},puede_procesar=False,puede_asignar=False)
        self.assertEqual(filas[0].tipo_cliente_catalogo,"B2C")
        self.assertEqual(filas[0].ceco_catalogo,"")
        self.assertFalse(filas[0].cuenta_en_catalogo)


    def test_correcciones_primero_antes_de_paginar_y_conserva_total(self):
        CorreccionODT.objects.create(odt=ODT.objects.get(numero=1), estado="PENDIENTE", corrige_monto=True)
        CorreccionODT.objects.create(odt=ODT.objects.get(numero=2), estado="EN_PROCESO", corrige_servicio=True)
        CorreccionODT.objects.create(odt=ODT.objects.get(numero=3), estado="ACTUALIZADA", corrige_monto=True)
        ODT.objects.filter(numero=3).update(valor_pago_editado=25)
        primera = paginar_filas(ODT.objects.all(), "1")
        segunda = paginar_filas(ODT.objects.all(), "2")
        numeros = [o.numero for o in primera] + [o.numero for o in segunda]
        self.assertEqual(numeros, [1, 2] + list(range(60, 2, -1)))
        self.assertEqual(primera.paginator.count, 60)
        self.assertEqual(len(set(numeros)), 60)

    def test_ediciones_antiguas_sin_seguimiento_tambien_primero(self):
        ODT.objects.filter(numero=1).update(valor_pago_editado=0)
        ODT.objects.filter(numero=2).update(servicio_editado="")
        pagina = paginar_filas(ODT.objects.all(), "1")
        self.assertEqual([o.numero for o in pagina][:3], [2, 1, 60])

    def test_prioridad_no_amplia_alcance_autorizado_y_respeta_orden_interno(self):
        for numero in (1, 2, 3):
            CorreccionODT.objects.create(odt=ODT.objects.get(numero=numero), estado="PENDIENTE", corrige_monto=True)
        pagina = paginar_filas(ODT.objects.filter(numero__in=[2, 3, 60]), "1")
        self.assertEqual([o.numero for o in pagina], [3, 2, 60])
        self.assertEqual(pagina.paginator.count, 3)

    def test_mas_de_una_pagina_de_pendientes_se_muestran_antes_del_resto(self):
        CorreccionODT.objects.bulk_create([
            CorreccionODT(odt=o, estado="PENDIENTE", corrige_servicio=True)
            for o in ODT.objects.filter(numero__lte=55)
        ])
        primera = paginar_filas(ODT.objects.all(), "1")
        segunda = paginar_filas(ODT.objects.all(), "2")
        self.assertEqual([o.numero for o in primera], list(range(55, 5, -1)))
        self.assertEqual([o.numero for o in segunda], [5, 4, 3, 2, 1, 60, 59, 58, 57, 56])


    def test_monto_cero_segun_valor_efectivo_sin_consultas_adicionales(self):
        ODT.objects.filter(numero=1).update(valor_pago_tecnico=0)
        ODT.objects.filter(numero=2).update(valor_pago_tecnico=100, valor_pago_editado=0)
        ODT.objects.filter(numero=3).update(valor_pago_tecnico=0, valor_pago_editado=200)
        pagina = paginar_filas(ODT.objects.filter(numero__lte=4), "1")
        datos = cargar_complementos(pagina.object_list)
        with self.assertNumQueries(0):
            filas = preparar_filas(pagina.object_list,
                coordinadores_pagina=self.datos_coordinadores(pagina.object_list),
                facturadas=datos.facturadas, catalogo=datos.catalogo,
                puede_procesar=True, puede_asignar=False)
        self.assertEqual({o.numero:o.monto_cero for o in filas}, {1:True, 2:True, 3:False, 4:False})

    def test_bandeja_resalta_fila_cero_y_la_identifica_con_texto(self):
        from types import SimpleNamespace
        from django.contrib.auth.models import AnonymousUser
        from django.template.loader import render_to_string
        ODT.objects.filter(numero=1).update(valor_pago_tecnico=0)
        pagina = paginar_filas(ODT.objects.filter(numero__lte=2), "1")
        datos = cargar_complementos(pagina.object_list)
        filas = preparar_filas(pagina.object_list, coordinadores_pagina=self.datos_coordinadores(pagina.object_list),
            facturadas=datos.facturadas, catalogo=datos.catalogo, puede_procesar=False, puede_asignar=False)
        html = render_to_string("revisiones/bandeja.html", {
            "request":SimpleNamespace(user=AnonymousUser()), "bandeja_url":"bandeja", "filtros":{},
            "registros":filas, "pagina":pagina, "querystring":"", "destacar_monto_cero":True,
        })
        self.assertEqual(html.count('class=" odt-monto-cero"'), 1)
        self.assertIn('class="monto-cero-marca">Monto $0</span>', html)

    def test_localiza_odt_guardada_aunque_cambie_de_pagina(self):
        self.assertEqual(paginar_filas(ODT.objects.all(), 1, 1).number, 2)
        CorreccionODT.objects.create(odt=ODT.objects.get(numero=1), estado="PENDIENTE", corrige_monto=True)
        pagina = paginar_filas(ODT.objects.all(), 2, 1)
        self.assertEqual(pagina.number, 1)
        self.assertEqual(pagina.object_list[0].numero, 1)

    def test_localizacion_respeta_filtros_y_no_expone_odt_ajena(self):
        pagina = paginar_filas(ODT.objects.filter(numero__gte=20), 1, 1)
        self.assertEqual(pagina.paginator.count, 41)
        self.assertNotIn(1, [o.numero for o in pagina])
        for numero in ("invalida", "1 OR 1=1", "9"*100, None):
            self.assertEqual(paginar_filas(ODT.objects.all(), 1, numero).number, 1)

    def test_vista_ubica_odt_y_limpia_parametro_de_la_paginacion(self):
        from unittest.mock import patch
        from django.contrib.auth.models import User
        from django.test import RequestFactory
        from .vistas.bandeja import bandeja
        usuario = User.objects.create_superuser("admin", password="prueba")
        request = RequestFactory().get("/", {"page":"1", "ubicar_odt":"1", "estado":"",
                                              "fecha_desde":"", "fecha_hasta":""})
        request.user = usuario
        with patch("revisiones.vistas.bandeja.coordinadores_para_mostrar",
                   side_effect=lambda r, numeros: {n:{"nombre":"Responsable", "usuario":"jtapia", "identificado":True} for n in numeros}), \
             patch("revisiones.vistas.bandeja.render", side_effect=lambda r, t, contexto: contexto):
            contexto = bandeja(request)
        self.assertEqual(contexto["pagina"].number, 2)
        self.assertIn(1, [o.numero for o in contexto["registros"]])
        self.assertNotIn("ubicar_odt", contexto["querystring"])

    def test_servicio_editado_muestra_original_y_coordinador_tiene_boton_calendario(self):
        from types import SimpleNamespace
        from django.contrib.auth.models import AnonymousUser
        from django.template.loader import render_to_string
        from django.urls import reverse
        original = 'SERVICIO ANTERIOR <script>no ejecutar</script>'
        ODT.objects.filter(numero=1).update(servicio=original, servicio_editado="MANTENIMIENTO PREVENTIVO")
        pagina = paginar_filas(ODT.objects.filter(numero=1), 1)
        datos = cargar_complementos(pagina.object_list)
        filas = preparar_filas(pagina.object_list, coordinadores_pagina=self.datos_coordinadores(pagina.object_list),
            facturadas=datos.facturadas, catalogo=datos.catalogo, puede_procesar=True, puede_asignar=False)
        html = render_to_string("revisiones/bandeja.html", {
            "request":SimpleNamespace(user=AnonymousUser()), "bandeja_url":"bandeja", "filtros":{},
            "registros":filas, "pagina":pagina, "querystring":"", "es_coordinador":True,
        })
        self.assertIn("Servicio editado · Original: SERVICIO ANTERIOR &lt;script&gt;", html)
        self.assertNotIn("<script>no ejecutar</script>", html)
        self.assertIn(f'href="{reverse("calendario_servicios")}"', html)
        self.assertNotIn('>Seguimiento de cambios</a>', html)
