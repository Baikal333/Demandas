# Demandas
Expedientes

> **Nuevo:** [`buscador-veleros/`](buscador-veleros/README.md) — búsqueda diaria de veleros de ocasión en España, Francia y Países Bajos con análisis de estado, costes de abanderamiento y traslado, e informe de las mejores ofertas.

## Anonimizador local de documentos

`anonimizador.html` es una aplicación web en **un solo archivo** que sustituye los datos personales de un documento por datos ficticios que se reconocen a simple vista. **El archivo nunca sale del equipo**: todo se procesa en el navegador.

### Cómo usarlo

1. Descargue `anonimizador.html` y ábralo con doble clic (Chrome, Edge, Firefox o Safari recientes). Funciona sin conexión a Internet.
2. Arrastre el documento a la página (o pegue el texto).
3. Revise la lista de datos detectados: desmarque lo que no deba cambiarse, edite los sustitutos o seleccione texto en la vista previa para añadir lo que falte.
4. Pulse **Descargar documento anonimizado**. Se descarga `nombre_ANONIMIZADO.ext` en el mismo formato.

### Formatos

| Entrada | Salida |
|---|---|
| Word `.docx`, Excel `.xlsx`, PowerPoint `.pptx` | Mismo formato, se conserva el diseño |
| OpenDocument `.odt`, `.ods`, `.odp` | Mismo formato, se conserva el diseño |
| PDF con texto | `.docx` con el texto (los PDF no se pueden reescribir conservando el diseño; los escaneados necesitan OCR antes) |
| `.txt`, `.csv`, `.md`, `.json`, `.xml`, `.html`, `.srt`… | Mismo formato |

Los `.doc`, `.xls`, `.rtf` antiguos hay que guardarlos antes como `.docx` / `.xlsx`.

### Qué detecta y por qué se sustituye

| Dato | Ejemplo de sustituto (evidentemente falso) |
|---|---|
| Nombres de personas (tras D., Dña., Sr., Sra.… o por diccionario de nombres y apellidos) | Fulano de Tal Ejemplo, Mengana Ficción |
| Empresas (S.L., S.A., S.L.U., S. Coop.…) | Empresa Ficticia Alfa, S.L. |
| DNI / NIE (con letra de control válida) / CIF / pasaporte | 00000001R · X0000001R · B00000001 |
| Correo electrónico | persona.ficticia1@ejemplo.invalid (dominio reservado) |
| Teléfono | 000 000 001 |
| IBAN / CCC / tarjeta | ES00 0000 0000 0000 0000 0001 |
| Nº Seguridad Social | 00/00000001/00 |
| Direcciones postales y códigos postales | Calle Ficticia Alfa, n.º 0 · 00000 |
| Matrículas, IP, fechas de nacimiento | 0001 FIC · 192.0.2.1 · 01/01/1900 |
| Opcional: todas las fechas, nº de procedimiento, términos propios | 0001/0000, «Dato Ficticio Alfa» |

- Las sustituciones son **coherentes**: la misma persona recibe siempre el mismo nombre ficticio, también cuando aparece solo con el apellido («el Sr. Pérez» → «el Sr. Ficción»).
- Alternativa: estilo **etiquetas** (`[PERSONA A]`, `[DNI 1]`…).
- También limpia los **metadatos** (autor, último en modificar, empresa, autores de comentarios y control de cambios, miniatura de la primera página) y, opcionalmente, sustituye las imágenes por recuadros en blanco.
- Se puede descargar la **tabla de correspondencias** (CSV) para revertir. Contiene los datos reales: guárdela aparte.

> La detección es automática y puede fallar. Revise siempre el resultado antes de compartirlo.

### Garantía de privacidad

- No hay servidor: todo el código está dentro del HTML (incluido el lector de PDF, pdf.js de Mozilla, licencia Apache 2.0, en `vendor/pdfjs/`).
- La página declara una política de seguridad `connect-src 'none'` que **impide al navegador cualquier conexión de red** desde ella.
- Las pruebas automáticas (`tests/e2e.cjs`) comprueban que no se realiza ninguna petición de red.

### Desarrollo

```
src/            código fuente (index.html, styles.css, zip.js, detector.js, formats.js, app.js)
vendor/pdfjs/   pdf.js 3.11.174
build.mjs       genera anonimizador.html incrustando todo:  node build.mjs
tests/          documentos de prueba (make_fixtures.py) y prueba en navegador (e2e.cjs)
```
