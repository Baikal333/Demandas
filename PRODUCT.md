# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Abogados y personal del despacho. Lo usan en su propio ordenador, en mitad del trabajo de un expediente, cuando tienen que sacar un documento del entorno del despacho (demanda, sentencia, contrato, hoja de cálculo, presentación) sin que salgan con él datos personales de clientes o de terceros.

## Product Purpose

Anonimizador local de documentos (`anonimizador.html`). Sustituye los datos personales por datos ficticios que se reconocen a simple vista y devuelve el documento en el mismo formato. Usos principales, todos confirmados:

- subir escritos a herramientas de IA (ChatGPT, Claude…) sin exponer datos personales (RGPD);
- compartirlos con terceros: peritos, colaboradores, otros despachos, o usarlos como modelo o plantilla;
- publicarlos: formación, artículos, blog, jurisprudencia propia.

Hay éxito cuando el documento descargado no contiene ningún dato identificativo, conserva su formato y su sentido jurídico, y el abogado lo ha revisado con confianza en poco tiempo.

## Positioning

El documento nunca sale del equipo. Todo se procesa en el navegador, en un único archivo HTML que funciona sin conexión. La política `connect-src 'none'` impide cualquier petición de red y las pruebas automáticas lo comprueban. Los sustitutos se ven falsos a simple vista (Fulano de Tal Ejemplo, 00000001R, dominio `.invalid`) y son coherentes en todo el documento: la misma persona recibe siempre el mismo nombre ficticio.

## Operating Context

- Se abre con doble clic en Chrome, Edge, Firefox o Safari recientes; no requiere instalación ni Internet.
- Flujo: arrastrar el documento o pegar el texto → revisar la lista de datos detectados (desmarcar, editar sustitutos, seleccionar texto en la vista previa para añadir lo que falte) → descargar `nombre_ANONIMIZADO.ext`.
- Opcionalmente se descarga la tabla de correspondencias (CSV), que contiene los datos reales y se guarda aparte.
- Interfaz y documentos en español de España; terminología jurídica española (DNI/NIE/CIF, NSS, n.º de procedimiento, D./Dña.).

## Capabilities and Constraints

- Entrada y salida: Word, Excel y PowerPoint (`.docx`, `.xlsx`, `.pptx`) y OpenDocument (`.odt`, `.ods`, `.odp`), conservando el diseño; PDF con texto → `.docx`; texto plano y formatos de texto (`.txt`, `.csv`, `.md`, `.json`, `.xml`, `.html`, `.srt`…). Los formatos antiguos (`.doc`, `.xls`, `.rtf`) no se admiten.
- Detecta personas, empresas, DNI/NIE/CIF/pasaporte, correo, teléfono, IBAN/CCC/tarjeta, NSS, direcciones, códigos postales, matrículas, IP y fechas de nacimiento. Opcionales: todas las fechas, números de procedimiento y términos propios. Alternativa: estilo etiquetas (`[PERSONA A]`).
- Limpia los metadatos y puede sustituir las imágenes por recuadros en blanco.
- Restricción dura: un solo archivo autocontenido, sin recursos externos, sin red (ni fuentes ni CDN). Se genera con `node build.mjs` a partir de `src/`; pdf.js 3.11.174 va incrustado desde `vendor/pdfjs/`.
- La detección es automática y puede fallar: la interfaz tiene que llevar al abogado a revisar el resultado, no darle una falsa sensación de seguridad.

## Brand Commitments

Decisión abierta. Ahora mismo la herramienta es neutra, sin nombre ni logo del despacho. En el cuestionario de init se marcaron a la vez «sin marca» y «marca del despacho», y no hay nombre, logo ni colores confirmados. Hasta que se confirme, no se añade identidad del despacho ni se inventa.

## Evidence on Hand

- Documento de muestra: `tests/muestra.txt`. Generador de documentos de prueba: `tests/make_fixtures.py`. Prueba en navegador: `tests/e2e.cjs`.
- No hay testimonios, cifras de uso, clientes ni certificaciones. No deben inventarse.

## Product Principles

1. La privacidad se demuestra, no se promete: nada en la herramienta puede hacer una conexión de red ni necesitar una.
2. La revisión humana es el paso central. Lo detectado, lo sustituido y lo que puede faltar tiene que leerse de un vistazo.
3. El documento de salida debe ser útil: mismo formato, mismo sentido, sustitutos coherentes y evidentemente falsos.
4. Cero fricción para un abogado no técnico: doble clic, arrastrar, revisar, descargar.
