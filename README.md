# Libro de Visitas · Despacho

Aplicación web de un solo archivo (`despacho.html`) para apuntar las visitas del despacho, controlar presupuestos y pagos a cuenta, programar avisos y emitir facturas.

## Cómo usarla
1. Descarga `despacho.html` y ábrelo con Chrome, Edge o Firefox (doble clic). No necesita instalación ni servidor.
2. En **Ajustes**, rellena los datos del despacho (nombre, NIF, dirección, IBAN), la serie y el siguiente número de factura.
3. Ábrelo siempre desde la misma ubicación y con el mismo navegador: los datos se guardan en ese navegador.

## Funciones
- **Visitas**: nombre, teléfono, email, fecha y hora, resumen del asunto, observaciones, presupuesto (base + IVA), estado, NIF y dirección para facturar. Búsqueda, filtro por estado y exportación a CSV.
- **Pagos a cuenta**: fecha, importe, forma de pago y concepto, con lo cobrado y lo pendiente frente al presupuesto.
- **Avisos**: fecha, hora y texto, con atajos (mañana, 1 semana, 15 días, 1 mes). Saltan en pantalla y como notificación del sistema mientras la página está abierta. Se exportan a Google Calendar, Outlook o Apple Calendar (.ics) para recibirlos también en el móvil.
- **Facturación**: numeración correlativa por serie y año, IVA, retención de IRPF opcional (cliente empresa o profesional) y descuento de las provisiones de fondos recibidas. Se imprimen o se guardan en PDF, se marcan como cobradas o se anulan. Incluye un resumen trimestral (base, IVA repercutido, IRPF retenido) y un libro de facturas en CSV.

## Copias de seguridad
Los datos no salen de tu ordenador. Descarga una copia `.json` desde **Ajustes** con regularidad. Esa copia sirve también para pasar los datos a otro equipo.
