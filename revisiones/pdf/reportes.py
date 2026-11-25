"""Reportes de consulta: datos explícitos, escapados y sin consultas adicionales."""
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape
from django.http import HttpResponse, HttpResponseBadRequest
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle
from .marca import LOGO, NARANJA, NEGRO, encabezado


def texto(valor):
    if valor is None: return '—'
    if isinstance(valor,datetime):
        if timezone.is_naive(valor): valor=timezone.make_aware(valor)
        return valor.astimezone(ZoneInfo('America/Santiago')).strftime('%d/%m/%Y %H:%M')
    if isinstance(valor,date): return valor.strftime('%d/%m/%Y')
    return str(valor)


def pagina(canvas,doc):
    encabezado(canvas,doc)
    canvas.saveState();canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#666666'))
    canvas.drawString(14*mm,10*mm,'First Security · Área Mantenimiento · '+texto(timezone.now()))
    canvas.drawRightString(doc.pagesize[0]-14*mm,10*mm,'Página '+str(doc.page));canvas.restoreState()


def filtros_texto(parametros):
    excluidos={'page','page_detalle','formato','exportar','seleccion','seleccion_periodos','ubicar_odt','filas_guardadas'}
    return '; '.join(f'{clave}: {", ".join(parametros.getlist(clave)) or "Todos"}'
        for clave in sorted(parametros) if clave not in excluidos) or 'Filtros predeterminados de la pantalla'


def pdf_reporte(titulo, secciones, filtros='', nombre='informe_sstt.pdf'):
    buffer=BytesIO();ancho,alto=landscape(A4);util=ancho-28*mm
    doc=SimpleDocTemplate(buffer,pagesize=(ancho,alto),leftMargin=14*mm,rightMargin=14*mm,
        topMargin=36*mm,bottomMargin=18*mm,title=titulo,author='First Security · Área Mantenimiento')
    normal=ParagraphStyle('reporte_normal',fontName='Helvetica',fontSize=7,leading=10,textColor=NEGRO)
    header=ParagraphStyle('reporte_cabecera',parent=normal,fontName='Helvetica-Bold',textColor=colors.white)
    title=ParagraphStyle('reporte_titulo',parent=normal,fontName='Helvetica-Bold',fontSize=15,leading=19,spaceAfter=8)
    sub=ParagraphStyle('reporte_seccion',parent=normal,fontName='Helvetica-Bold',fontSize=10,leading=14,spaceAfter=7,spaceBefore=10)
    def p(valor,estilo=normal):return Paragraph(escape(texto(valor)).replace('\n','<br/>'),estilo)
    story=[p(titulo,title),p(filtros),Spacer(1,8)]
    for seccion in secciones:
        etiqueta,cabeceras,filas=seccion[:3]
        pesos=seccion[3] if len(seccion)>3 else [1]*len(cabeceras)
        story.append(p(etiqueta,sub))
        datos=[[p(c,header) for c in cabeceras]]
        datos.extend([[p(c) for c in fila] for fila in filas])
        if len(datos)==1:datos.append([p('Sin registros')]+[p('') for _ in cabeceras[1:]])
        tabla=LongTable(datos,colWidths=[util*peso/sum(pesos) for peso in pesos],repeatRows=1,splitInRow=1)
        tabla.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NARANJA),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f5f5f5')]),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.25,colors.HexColor('#dddddd')),
            ('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),
            ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        story.append(tabla)
    doc.build(story,onFirstPage=pagina,onLaterPages=pagina)
    respuesta=HttpResponse(buffer.getvalue(),content_type='application/pdf')
    respuesta['Content-Disposition']=f'attachment; filename="{nombre}"'
    respuesta['Cache-Control']='private, no-store'
    return respuesta


def xlsx_reporte(cabeceras,filas,filtros=''):
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    filas=list(filas)
    if any(isinstance(v,str) and (len(v)>32767 or ILLEGAL_CHARACTERS_RE.search(v)) for fila in filas for v in fila):
        return HttpResponseBadRequest('Una observación excede los límites de Excel o contiene caracteres no admitidos. Exporta en PDF para conservar el contenido.', content_type='text/plain; charset=utf-8')
    wb=Workbook();ws=wb.active;ws.title='ODT seleccionadas'
    logo=Image(str(LOGO));logo.width=190;logo.height=60;ws.add_image(logo,'A1');ws.row_dimensions[1].height=48
    ws.cell(3,1,'First Security · Área Mantenimiento · '+texto(timezone.now()))
    ws.cell(4,1,filtros).data_type='s'
    for i,c in enumerate(cabeceras,1):
        celda=ws.cell(6,i,c);celda.font=Font(bold=True,color='FFFFFF');celda.fill=PatternFill('solid',fgColor='C63B00')
    for n,fila in enumerate(filas,7):
        for i,valor in enumerate(fila,1):
            if isinstance(valor,(date,datetime)):valor=texto(valor)
            celda=ws.cell(n,i,valor)
            if isinstance(valor,str):celda.data_type='s'  # No ejecutar fórmulas del origen.
            if isinstance(valor,(Decimal,float)):celda.number_format='#,##0.00'
            celda.alignment=Alignment(vertical='top',wrap_text=True)
    from openpyxl.utils import get_column_letter
    for i in range(1,len(cabeceras)+1):ws.column_dimensions[get_column_letter(i)].width=24
    ws.freeze_panes='C7';ws.auto_filter.ref=f'A6:{get_column_letter(len(cabeceras))}{max(6,ws.max_row)}'
    buffer=BytesIO();wb.save(buffer)
    respuesta=HttpResponse(buffer.getvalue(),content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    respuesta['Content-Disposition']='attachment; filename="ODT_seleccionadas.xlsx"'
    respuesta['Cache-Control']='private, no-store'
    return respuesta
