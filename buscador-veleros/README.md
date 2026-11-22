# Buscador diario de veleros de ocasión (España · Francia · Países Bajos)

Programa en Python que cada día:

1. **Busca** veleros en venta en portales de España, Francia y Países Bajos.
2. **Filtra**: se queda con los de **7 a 10 m de eslora** y **10.000 € o menos**. Descarta los **modelos muy antiguos** y los que **no tienen marcado CE**. También descarta motoras, neumáticas, anuncios de "busco", alquileres y duplicados.
3. **Traduce** al español los anuncios en francés y neerlandés.
4. **Detecta puntos débiles** (motor averiado, reparaciones pendientes, ósmosis, vías de agua, jarcia o velas viejas, falta de papeles…) y **puntos fuertes** (antifouling o varada reciente, jarcia o velas nuevas, grifos de fondo cambiados, radar, plotter, WC marino, depósito de aguas negras, IVA pagado, motor revisado, piloto automático, remolque…), en el texto original y en la traducción.
5. **Estima el coste total**: precio, ITP, impuesto de matriculación (IEDMT), tasas de abanderamiento **en España** y **con bandera polaca**, gestoría, traducciones, seguro, peritaje y **traslado por carretera** hasta su puerto.
6. **Clasifica** los anuncios y genera un **informe HTML** con las **15 mejores ofertas de cada país**. Cada oferta incluye **todas las fotos publicadas** (galería ampliable), el anuncio traducido y el desglose de costes.

## Instalación

Requiere Python 3.10 o superior.

```bash
cd buscador-veleros
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

```bash
python -m veleros demo --abrir          # informe de ejemplo con anuncios ficticios (no necesita Internet)
python -m veleros ejecutar --abrir      # búsqueda real del día
python -m veleros ejecutar --ia         # igual, pero la traducción y el análisis los hace Claude (de pago, más preciso)
python -m veleros ejecutar --solo leboncoin,marktplaats
python -m veleros probar leboncoin      # diagnostica un portal: muestra lo que extrae y por qué descarta
```

El informe se guarda en `informes/veleros-AAAA-MM-DD.html`. El último informe también se copia a `informes/ultimo.html`, y los datos van en un `.json` del mismo nombre. El histórico se guarda en `datos/veleros.db`, lo que permite marcar los anuncios **NUEVOS HOY** y detectar **bajadas de precio**.

### Ejecución diaria automática

**Linux / macOS (cron)**: `crontab -e` y añada, por ejemplo, para las 7:30 cada día:

```
30 7 * * * /ruta/a/buscador-veleros/ejecutar_diario.sh
```

**Windows**: abra el Programador de tareas, cree una tarea básica diaria y elija como acción `ejecutar_diario.bat`.

## Configuración (`config.yaml`)

Todo se ajusta sin tocar el código:

| Sección | Qué controla |
|---|---|
| `filtros` | Eslora mín./máx., precio máximo, año mínimo, exigencia de CE, palabras que excluyen un anuncio |
| `informe` | Nº de mejores ofertas por país (15), descarga local de fotos (`descargar_fotos: true` las conserva aunque se retire el anuncio) |
| `traduccion` | `google` (gratis), `claude` o `ninguno` |
| `ia` | Análisis con Claude (modelo, esfuerzo). Necesita `ANTHROPIC_API_KEY` |
| `costes` | **Puerto de destino**, tipo de ITP de **su comunidad autónoma**, IEDMT, tasas, gestoría, transporte (€/km, grúas, mástil, permisos)… |
| `sitios` | Portales activos, términos de búsqueda y URLs de listado |

### Criterio de antigüedad y marcado CE

El marcado CE es obligatorio para los barcos comercializados desde el **16/06/1998** (Directiva 94/25/CE) y era voluntario desde 1996. Por defecto:

- se descartan los barcos anteriores a **1996** (`anio_minimo`);
- los de 1996-1997 solo pasan si el anuncio menciona CE o una categoría de diseño (A/B/C/D);
- se descartan los anuncios que dicen expresamente "sin CE" y los que no indican ni el año ni el CE.

### Cómo se calcula el coste (estimación)

- **Abanderar en España** (barco con bandera francesa, holandesa, polaca, etc.):
  - ITP (modelo 620) si el vendedor es particular;
  - IEDMT del 12 % (modelo 576) si la eslora supera 8 m;
  - tasas de Capitanía, inspección inicial (ECI), gestoría, traducción jurada y baja en el registro de origen;
  - evaluación posconstrucción si no hay declaración CE;
  - seguro de responsabilidad civil.

  Si el barco ya es español, solo se calcula el cambio de titularidad.
- **Bandera polaca**: inscripción en el registro polaco (o cambio de propietario si ya es polaco), gestor, traducción jurada y seguro. El impuesto polaco PCC es opcional. El informe advierte de que un residente en España que usa el barco de forma habitual en aguas españolas puede tener que pagar el IEDMT de todos modos.
- **Traslado**: distancia por carretera estimada hasta el puerto de destino. El precio por km es mayor si el barco necesita transporte especial (manga de más de 2,55 m). Se suman grúas en origen y destino, desarbolado y cuna. Si el barco se vende con remolque, se calcula el remolcado con vehículo propio.
- **Avisos**: el informe recuerda pedir la **Declaración de Conformidad CE** y la **prueba del IVA UE pagado** (si no la hay, Hacienda puede reclamar el 21 %).

> Son **estimaciones orientativas**. Los tipos y las tasas cambian y dependen de la comunidad autónoma y de la documentación del barco. Confírmelos con una gestoría náutica antes de comprar.

### Puntuación (0-100)

La puntuación parte de 45 puntos:

- **Puntos fuertes**: suman como máximo 35 puntos. Cada uno vale más si es reciente (por ejemplo, un antifouling de este año o del anterior).
- **Puntos débiles**: restan sin límite inferior. Un motor averiado resta 18 puntos.
- **Otros factores**: también cuentan los €/metro, el año, el número de fotos, la calidad del anuncio y el coste total estimado.

Los pesos de cada rasgo están en `veleros/analisis.py`.

## Portales incluidos

| País | Portales |
|---|---|
| España | Wallapop, Milanuncios, Cosas de Barcos (Boat24 desactivado por defecto) |
| Francia | Leboncoin, Band of Boats, Youboat |
| Países Bajos | Marktplaats, Botentekoop |

Para añadir un portal sin programar, añada en `sitios` un bloque como este:

```yaml
nuevo_portal:
  tipo: generico
  pais: FR
  idioma: fr
  listados: ["https://www.ejemplo.fr/voiliers?prix_max={precio_max}&page={pagina}"]
  patron_enlace: "/annonce/\\d+"
```

El extractor genérico abre cada anuncio y lee el JSON-LD, la ficha técnica y todas las imágenes de la galería.

**Avisos importantes sobre los portales:**

- **Sus webs cambian a menudo.** Si un portal deja de dar resultados, ejecute `python -m veleros probar <portal>` y ajuste la URL o el `patron_enlace`.
- **Algunos tienen protección anti-bots** (Leboncoin y Milanuncios, sobre todo) y pueden bloquear la búsqueda. El programa sigue con los demás portales e indica el bloqueo en el *Resumen del día* del informe.
- **Uso responsable.** El programa respeta `robots.txt`, hace pausas de 2 a 5 s entre peticiones y está pensado para **uso personal**. Revise las condiciones de uso de cada portal.

## Tests

```bash
python -m pytest -q
```
