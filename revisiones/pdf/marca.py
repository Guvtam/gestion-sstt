"""Identidad visual compartida, sin acceso a datos ni servicios externos."""
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

LOGO = Path(__file__).resolve().parents[1] / 'static/revisiones/marca/logo_area.png'
NARANJA = colors.HexColor('#c63b00')
NEGRO = colors.HexColor('#252525')


def encabezado(canvas, doc):
    canvas.saveState()
    ancho, alto = doc.pagesize
    imagen=ImageReader(str(LOGO));w,h=imagen.getSize()
    canvas.drawImage(imagen,14*mm,alto-28*mm,width=66*mm,height=66*mm*h/w,mask='auto')
    canvas.setFillColor(NEGRO);canvas.setFont('Helvetica-Bold',9)
    canvas.drawRightString(ancho-14*mm,alto-18*mm,'ÁREA MANTENIMIENTO · SSTT')
    canvas.setStrokeColor(NARANJA);canvas.setLineWidth(1.4)
    canvas.line(14*mm,alto-31*mm,ancho-14*mm,alto-31*mm)
    canvas.restoreState()
