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

## 4. Plantillas de proveedores (proveedores.json)

Cada proveedor habitual tiene una plantilla que dice cómo reconocer su factura y dónde están los datos:

```json
{
  "nombre": "Gestoría Ejemplo, S.L.",
  "nif": "B12345678",
  "reconocer_por": ["B12345678"],
  "concepto": "Honorarios asesoría",
  "cuenta_gasto": 623,
  "iva_pct": 21,
  "irpf_pct": 15,
  "patrones": {
    "numero": "Factura\\s+n[ºo°.]*\\s*([A-Z0-9\\-/]+)",
    "fecha":  "Fecha[:\\s]*(\\d{1,2}[/.\\-]\\d{1,2}[/.\\-]\\d{2,4})",
    "base":   "Base\\s+imponible[:\\s]*([\\d.,]+)",
    "total":  "Total\\s+a\\s+pagar[:\\s]*([\\d.,]+)"
  }
}
```

- `reconocer_por`: el NIF o un texto que solo aparece en las facturas de ese proveedor.
- `patrones`: expresiones regulares. Lo que va entre paréntesis es el dato que se extrae.
- Campos opcionales: `tipo_operacion` (`Nacional`, `Intracumunitaria`, `InversionSujetoPasivo`, `NacionalExenta`…), `imputacion_pct` e `imputacion_iva_pct` (p. ej. 50 para un vehículo de uso mixto), y los patrones `iva_pct` e `irpf_pct` si el tipo varía.

Para crear una plantilla nueva:

1. Vea el texto que contiene el PDF:
   `python facturas_contasimple.py texto "C:/Facturas/Recibidas/factura.pdf"`
2. Escriba los patrones a partir de ese texto. Si me pasa esa salida, se los preparo.
3. Compruebe la plantilla sin registrar nada:
   `python facturas_contasimple.py probar-plantilla "C:/Facturas/Recibidas/factura.pdf"`

## 5. Uso diario

Haga doble clic en **`procesar.bat`**. Para cada PDF de la carpeta de entrada:

1. Muestra los datos leídos (proveedor, número, fecha, base, IVA, IRPF, total y cuenta) y avisa si el total no cuadra o falta algo.
2. Usted elige:
   - **S**: registrar. Se da de alta el proveedor si no existe, se crea la factura, se adjunta el PDF y el archivo pasa a *Gestionadas*.
   - **E**: corregir datos.
   - **R**: mover a *Revisar*.
   - **O**: dejarla para otro momento.
   - **X**: salir.
3. Si un PDF no tiene plantilla, o es un escaneado sin texto, le pide los datos a mano.

Nada se registra sin su confirmación. Si Contasimple da un error, por ejemplo una factura duplicada, el PDF **se queda** en la carpeta de entrada y el motivo se anota en `registro.log`.

## Limitaciones

- Una línea por factura, con un solo tipo de IVA. Para facturas con varios tipos, regístrela a mano en Contasimple o pídame que lo amplíe.
- No lee PDF escaneados (imágenes). En ese caso pide los datos a mano.
