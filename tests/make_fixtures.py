# Genera documentos de prueba con datos personales ficticios de ejemplo.
import sys, os
from docx import Document
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from pptx import Presentation

out = sys.argv[1]
os.makedirs(out, exist_ok=True)

d = Document()
d.core_properties.author = 'Laura Gómez Abogada'
d.core_properties.last_modified_by = 'Laura Gómez Abogada'
d.sections[0].header.paragraphs[0].text = 'Expediente de Juan Antonio Pérez Martínez'
p = d.add_paragraph()
p.add_run('DOÑA MARÍA JOSÉ ')
p.add_run('LÓPEZ').bold = True
p.add_run(' GARCÍA, Procuradora, en nombre de D. Juan Ant')
p.add_run('onio Pérez Martínez, con DNI 12.345.678-Z, domicilio en Calle Alcalá, 123, 4º B, 28009 Madrid.')
d.add_paragraph('Correo: juan.perez@gmail.com · Tel. 612 345 678 · IBAN ES91 2100 0418 4502 0005 1332')
t = d.add_table(rows=2, cols=2)
t.cell(0,0).text = 'Demandada'; t.cell(0,1).text = 'Dña. Lucía Fernández Sanz (NIE X1234567L)'
t.cell(1,0).text = 'Empresa'; t.cell(1,1).text = 'Construcciones Hermanos Ruiz, S.L. (CIF B12345674)'
d.add_paragraph('El Sr. Pérez y la Sra. Fernández comparecieron.')
d.save(f'{out}/demanda.docx')

wb = Workbook(); ws = wb.active
ws.append(['Nombre', 'DNI', 'Teléfono', 'Email'])
ws.append(['Pedro Sánchez Ruiz', '87654321X', 699112233, 'pedro.sanchez@hotmail.es'])
ws.append(['Ana Torres Vidal', '11111111H', 655443322, 'ana@empresa.com'])
ws.append(['Total', None, '=SUM(C2:C3)', None])
wb.properties.creator = 'Laura Gómez'
wb.save(f'{out}/clientes.xlsx')

c = canvas.Canvas(f'{out}/escrito.pdf', pagesize=A4)
c.setAuthor('Laura Gómez')
y = 800
for line in ['AL JUZGADO DE LO SOCIAL', 'D. Carlos Martín Navarro, con DNI 23456789D, vecino de Sevilla,',
             'con domicilio en Avenida de la Constitución 45, 41001 Sevilla,', 'telefono 954 123 456, interpone demanda contra',
             'Transportes Ibéricos, S.A. Correo: carlos.martin@yahoo.es']:
    c.drawString(60, y, line); y -= 18
c.showPage(); c.drawString(60, 800, 'Segunda página: el Sr. Martín reitera lo expuesto.'); c.save()

pr = Presentation(); s = pr.slides.add_slide(pr.slide_layouts[1])
s.shapes.title.text = 'Caso de Elena Ruiz Castro'
s.placeholders[1].text = 'Contacto: elena.ruiz@gmail.com, 600 112 233'
pr.save(f'{out}/caso.pptx')
