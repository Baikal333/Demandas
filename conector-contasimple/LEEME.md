# Conector de facturas recibidas → Contasimple

Lee las facturas PDF de una carpeta, reconoce al proveedor, extrae los datos, se los enseña para que los confirme y los registra en Contasimple como **factura recibida**, con el PDF adjunto. Después mueve el PDF a la carpeta de **facturas gestionadas**.

La aplicación de Contasimple que tiene instalada en el ordenador trabaja sobre su cuenta en la nube. Por eso el conector usa la **API oficial de Contasimple** (`api.contasimple.com`): lo que registra aparece directamente en la aplicación.

## 1. Instalación (una vez)

1. Instale **Python 3** desde <https://www.python.org/downloads/>. En el instalador marque **"Add python.exe to PATH"**.
2. Copie la carpeta `conector-contasimple` a su ordenador, por ejemplo en `C:\Facturas\conector`.
3. Haga doble clic en **`instalar.bat`**. Instala las librerías y crea `config.json` y `proveedores.json`.

## 2. Clave de API de Contasimple

1. Entre en Contasimple y vaya a la configuración de su cuenta, al apartado de **API / claves de autenticación**.
2. Genere una clave y cópiela.
3. Abra `config.json` con el Bloc de notas y péguela en `clave_api_contasimple`.

Si no encuentra ese apartado, puede que su plan no incluya la API. En ese caso, pregunte a soporte de Contasimple.

La clave da acceso a su contabilidad. No la comparta, y no envíe el archivo `config.json` a nadie.

## 3. config.json

| Campo | Qué es |
|---|---|
| `carpeta_entrada` | Donde deja las facturas PDF pendientes |
| `carpeta_gestionadas` | Adonde se mueven las ya registradas (con subcarpeta por año si `subcarpeta_por_anio` es `true`) |
| `carpeta_revisar` | Adonde se mueven las que usted marque como "Revisar" |
| `cuenta_gasto_defecto` | Cuenta de gasto (grupo 6 del PGC) para facturas sin plantilla, p. ej. `629` |
| `formato_periodo` | Formato del trimestre que pide Contasimple. Por defecto `{anio}-{trimestre}T` (p. ej. `2026-4T`) |

Use barras normales en las rutas (`C:/Facturas/Recibidas`) o barras dobles (`C:\\Facturas\\Recibidas`).

Ejecute **`probar.bat`**. Comprueba la clave, lista las cuentas de gasto de su empresa y confirma que el formato de periodo es válido.

## 4. Dar de alta proveedores habituales

El programa reconoce a cada proveedor habitual por su NIF y sabe dónde están sus datos en el PDF. Ese "aprendizaje" se guarda en `proveedores.json` y se crea solo. Hay dos formas:

**A) Mientras procesa las facturas (lo más cómodo).** Cuando llegue la primera factura de un proveedor nuevo, el programa le pide los datos a mano. Después de registrarla, le pregunta:

> ¿Guardar a … como proveedor habitual para leer sus próximas facturas? [S/N]

Si responde **S**, las siguientes facturas de ese proveedor se leerán solas.

**B) Por adelantado, sin registrar nada.** Arrastre una factura PDF del proveedor y suéltela encima de **`nuevo_proveedor.bat`**. Le pedirá:

| Dato | Ejemplo | Consejo |
|---|---|---|
| Número de factura | `FE26-000981` | Cópielo tal cual aparece |
| Fecha | `03/11/2026` | |
| Proveedor | `Energía Sur, S.L.` | |
| NIF proveedor | `B87654321` | El del proveedor, no el suyo |
| Concepto | `Electricidad despacho` | Es el texto que verá en Contasimple |
| Base imponible | `84,30` | |
| % IVA | `21` | |
| % IRPF | `0`, `15` o `19` | `19` para alquileres, `15` para profesionales |
| Cuenta de gasto | `628` | Vea la lista con `probar.bat` |

Al terminar, le enseña cómo leerá las próximas facturas de ese proveedor, para que lo compruebe.

Si le avisa de que **no ha sabido localizar** algún dato (por ejemplo, la fecha), no pasa nada: ese dato se le pedirá en cada factura. Si un proveedor le da problemas, envíeme el PDF y ajusto la plantilla.

Para dar de alta otra vez un proveedor (porque ha cambiado el diseño de su factura), vuelva a usar `nuevo_proveedor.bat` con una factura nueva. Sustituye la plantilla anterior.

Para comprobar una plantilla sin registrar nada:
`python facturas_contasimple.py probar-plantilla "ruta/factura.pdf"`

## 5. Uso diario

Haga doble clic en **`procesar.bat`**. Para cada PDF de la carpeta de entrada:

1. Muestra los datos leídos (proveedor, número, fecha, base, IVA, IRPF, total y cuenta) y avisa si el total no cuadra o falta algo.
2. Usted elige:
   - **S**: registrar. Se da de alta el proveedor si no existe, se crea la factura, se adjunta el PDF y el archivo pasa a *Gestionadas*.
   - **E**: corregir datos.
   - **R**: mover a *Revisar*.
   - **O**: dejarla para otro momento.
   - **X**: salir.
3. Si un PDF es de un proveedor nuevo, o es un escaneado sin texto, le pide los datos a mano. Si es de un proveedor nuevo, después le ofrece guardarlo como habitual.

Nada se registra sin su confirmación. Si Contasimple da un error, por ejemplo una factura duplicada, el PDF **se queda** en la carpeta de entrada y el motivo se anota en `registro.log`.

## Limitaciones

- Una línea por factura, con un solo tipo de IVA. Para facturas con varios tipos, regístrela a mano en Contasimple o pídame que lo amplíe.
- No lee PDF escaneados (imágenes). En ese caso pide los datos a mano.
