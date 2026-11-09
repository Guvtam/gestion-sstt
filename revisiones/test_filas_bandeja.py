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
