"""
Conector de facturas recibidas en PDF -> Contasimple.

Lee los PDF de la carpeta de entrada, reconoce al proveedor con su plantilla
(proveedores.json), extrae los datos de la factura, se los muestra para que
los confirme o corrija, la registra en Contasimple como factura recibida con
el PDF adjunto y mueve el PDF a la carpeta de facturas gestionadas.

Uso (desde la carpeta del conector):
    python facturas_contasimple.py procesar     -> procesa la carpeta de entrada
    python facturas_contasimple.py probar       -> comprueba la conexión y lista las cuentas de gasto
    python facturas_contasimple.py texto X.pdf  -> muestra el texto de un PDF (para crear plantillas)
    python facturas_contasimple.py nuevo-proveedor X.pdf  -> crea la plantilla de un proveedor a partir de una factura
    python facturas_contasimple.py probar-plantilla X.pdf -> extrae datos sin registrar nada
"""

import json
import os
import re
import shutil
import sys
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

try:
    import pdfplumber
    import requests
except ImportError:
    print("Faltan librerías. Ejecute primero instalar.bat (o: pip install -r requirements.txt)")
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
PROVEEDORES_FILE = BASE_DIR / "proveedores.json"
LOG_FILE = BASE_DIR / "registro.log"

API_URL = "https://api.contasimple.com/api/v2"


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------

def log(msg):
    linea = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(linea + "\n")


def cargar_json(ruta, obligatorio=True):
    if not ruta.exists():
        if obligatorio:
            print(f"No encuentro {ruta.name}. Copie el archivo de ejemplo y rellénelo (vea LEEME.md).")
            sys.exit(1)
        return None
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def importe(texto):
    """Convierte '1.234,56 €' o '1234.56' en 1234.56."""
    if texto is None:
        return None
    t = re.sub(r"[^\d,.\-]", "", str(texto))
    if not t:
        return None
    if "," in t and "." in t:
        # el separador que aparece el último es el decimal
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    elif t.count(".") > 1:
        t = t.replace(".", "")
    try:
        return round(float(t), 2)
    except ValueError:
        return None


MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
         "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}


def fecha(texto):
    """Admite 05/03/2026, 5-3-26, 2026-03-05 y '5 de marzo de 2026'."""
    if not texto:
        return None
    t = texto.strip().lower()
    m = re.search(r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+(?:de\s+)?(\d{4})", t)
    if m and m.group(2) in MESES:
        return datetime(int(m.group(3)), MESES[m.group(2)], int(m.group(1)))
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d.%m.%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(t, fmt)
        except ValueError:
            pass
    return None


def periodo(f, formato):
    trimestre = (f.month - 1) // 3 + 1
    return formato.format(anio=f.year, trimestre=trimestre)


def texto_pdf(ruta):
    with pdfplumber.open(ruta) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def normaliza_nif(nif):
    return re.sub(r"[^A-Z0-9]", "", (nif or "").upper())


# --------------------------------------------------------------------------
# Extracción con plantillas
# --------------------------------------------------------------------------

def buscar_plantilla(texto, proveedores):
    texto_nif = normaliza_nif(texto)
    texto_min = texto.lower()
    for p in proveedores:
        claves = p.get("reconocer_por") or [p["nif"]]
        for clave in claves:
            if normaliza_nif(clave) and normaliza_nif(clave) in texto_nif and len(normaliza_nif(clave)) >= 8:
                return p
            if clave.lower() in texto_min:
                return p
    return None


def campo(texto, patron):
    if not patron:
        return None
    m = re.search(patron, texto, re.IGNORECASE | re.MULTILINE)
    if not m:
        return None
    return (m.group(1) if m.groups() else m.group(0)).strip()


def extraer(texto, plantilla, config):
    pat = plantilla.get("patrones", {})
    datos = {
        "proveedor": plantilla["nombre"],
        "nif": plantilla["nif"],
        "numero": campo(texto, pat.get("numero")),
        "fecha": fecha(campo(texto, pat.get("fecha"))),
        "base": importe(campo(texto, pat.get("base"))),
        "iva_pct": plantilla.get("iva_pct", 21),
        "irpf_pct": plantilla.get("irpf_pct", 0),
        "total": importe(campo(texto, pat.get("total"))),
        "concepto": plantilla.get("concepto") or f"Factura {plantilla['nombre']}",
        "cuenta_gasto": plantilla.get("cuenta_gasto", config.get("cuenta_gasto_defecto", 629)),
        "tipo_operacion": plantilla.get("tipo_operacion", "Nacional"),
        "imputacion": plantilla.get("imputacion_pct", 100),
        "imputacion_iva": plantilla.get("imputacion_iva_pct", 100),
    }
    if pat.get("iva_pct"):
        v = importe(campo(texto, pat["iva_pct"]))
        if v is not None:
            datos["iva_pct"] = v
    if pat.get("irpf_pct"):
        v = importe(campo(texto, pat["irpf_pct"]))
        if v is not None:
            datos["irpf_pct"] = v
    # Si falta la base pero hay total, se calcula
    if datos["base"] is None and datos["total"] is not None:
        divisor = 1 + datos["iva_pct"] / 100 - datos["irpf_pct"] / 100
        datos["base"] = round(datos["total"] / divisor, 2)
    return datos


def redondea(x):
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def calcula(d):
    base = d["base"] or 0
    d["cuota_iva"] = redondea(Decimal(str(base)) * Decimal(str(d["iva_pct"])) / 100)
    d["cuota_irpf"] = redondea(Decimal(str(base)) * Decimal(str(d["irpf_pct"])) / 100)
    d["total_calculado"] = redondea(Decimal(str(base)) + Decimal(str(d["cuota_iva"])) - Decimal(str(d["cuota_irpf"])))
    return d


def avisos(d):
    a = []
    for k, nombre in (("numero", "número de factura"), ("fecha", "fecha"), ("base", "base imponible")):
        if not d.get(k):
            a.append(f"No he encontrado la {nombre}.")
    if d.get("total") is not None and d.get("base") is not None:
        if abs(d["total"] - d["total_calculado"]) > 0.02:
            a.append(f"El total del PDF ({d['total']:.2f}) no cuadra con base + IVA - IRPF "
                     f"({d['total_calculado']:.2f}).")
    return a


# --------------------------------------------------------------------------
# Revisión en pantalla
# --------------------------------------------------------------------------

CAMPOS_EDITABLES = [
    ("numero", "Número de factura", str),
    ("fecha", "Fecha (dd/mm/aaaa)", fecha),
    ("proveedor", "Proveedor", str),
    ("nif", "NIF proveedor", str),
    ("concepto", "Concepto", str),
    ("base", "Base imponible", importe),
    ("iva_pct", "% IVA", importe),
    ("irpf_pct", "% IRPF", importe),
    ("cuenta_gasto", "Cuenta de gasto (p.ej. 629)", int),
]


def mostrar(d, nombre_pdf):
    calcula(d)
    f = d["fecha"].strftime("%d/%m/%Y") if d.get("fecha") else "¿?"
    print("\n" + "=" * 64)
    print(f" {nombre_pdf}")
    print("=" * 64)
    print(f"  Proveedor ...... {d['proveedor']}  (NIF {d['nif']})")
    print(f"  Nº factura ..... {d.get('numero') or '¿?'}")
    print(f"  Fecha .......... {f}")
    print(f"  Concepto ....... {d['concepto']}")
    base_txt = f"{d['base']:.2f}" if d["base"] is not None else "¿?"
    print(f"  Base ........... {base_txt:>10}")
    print(f"  IVA {d['iva_pct']:>5}% ..... {d['cuota_iva']:>10.2f}")
    if d["irpf_pct"]:
        print(f"  IRPF {d['irpf_pct']:>4}% ..... -{d['cuota_irpf']:>9.2f}")
    print(f"  TOTAL .......... {d['total_calculado']:>10.2f}"
          + (f"   (PDF: {d['total']:.2f})" if d.get("total") is not None else ""))
    print(f"  Cuenta gasto ... {d['cuenta_gasto']}   Operación: {d['tipo_operacion']}"
          f"   Imputación: {d['imputacion']}% / IVA {d['imputacion_iva']}%")
    for a in avisos(d):
        print(f"  ⚠  {a}")


def editar(d):
    for clave, etiqueta, conv in CAMPOS_EDITABLES:
        actual = d.get(clave)
        if isinstance(actual, datetime):
            actual = actual.strftime("%d/%m/%Y")
        nuevo = input(f"  {etiqueta} [{actual if actual is not None else ''}]: ").strip()
        if nuevo:
            valor = conv(nuevo)
            if valor is None:
                print("    Valor no válido, se mantiene el anterior.")
            else:
                d[clave] = valor
    return d


def datos_manual(nombre_pdf, config):
    print(f"\nNo hay plantilla para {nombre_pdf}. Introduzca los datos a mano.")
    d = {"proveedor": "", "nif": "", "numero": "", "fecha": None, "base": None, "iva_pct": 21.0,
         "irpf_pct": 0.0, "total": None, "concepto": "", "cuenta_gasto": config.get("cuenta_gasto_defecto", 629),
         "tipo_operacion": "Nacional", "imputacion": 100, "imputacion_iva": 100}
    editar(d)
    if not d["concepto"]:
        d["concepto"] = f"Factura {d['proveedor']}"
    return d


def revisar(d, nombre_pdf):
    """Devuelve 'si', 'omitir', 'revisar' o 'salir'."""
    while True:
        mostrar(d, nombre_pdf)
        if avisos(d):
            print("\n  Hay avisos: revise los datos antes de registrar.")
        r = input("\n  [S] Registrar  [E] Editar  [R] Enviar a 'Revisar'  [O] Omitir  [X] Salir: ").strip().lower()
        if r == "s":
            if not d.get("numero") or not d.get("fecha") or d.get("base") is None or not d.get("nif"):
                print("  Faltan datos obligatorios (número, fecha, base o NIF). Pulse E para completarlos.")
                continue
            return "si"
        if r == "e":
            editar(d)
        elif r == "r":
            return "revisar"
        elif r == "o":
            return "omitir"
        elif r == "x":
            return "salir"


# --------------------------------------------------------------------------
# API de Contasimple
# --------------------------------------------------------------------------

class Contasimple:
    def __init__(self, clave, client_id=None):
        if not clave or "PEGUE" in clave:
            print("Falta la clave de API de Contasimple en config.json (o en la variable CONTASIMPLE_API_KEY).")
            sys.exit(1)
        datos = {"grant_type": "authentication_key", "key": clave}
        if client_id:
            datos["client_id"] = client_id
        r = requests.post(f"{API_URL}/oauth/token", data=datos, timeout=30)
        if r.status_code != 200:
            print(f"Contasimple rechazó la clave de API ({r.status_code}): {r.text[:300]}\n"
                  "Compruebe que ha copiado la clave completa y que está activa en Contasimple.")
            sys.exit(1)
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}",
                               "Accept-Language": "es-ES"})

    def _ok(self, r, que):
        if r.status_code >= 400:
            raise RuntimeError(f"Error al {que} ({r.status_code}): {r.text[:500]}")
        return r.json() if r.content else {}

    def cuentas_gasto(self):
        return self._ok(self.s.get(f"{API_URL}/configuration/invoiceClasses/received", timeout=30),
                        "leer las cuentas de gasto").get("data", [])

    def proveedor(self, nif, nombre):
        r = self.s.get(f"{API_URL}/entities/providers/search/nif",
                       params={"query": nif, "exactMatch": "true"}, timeout=30)
        encontrados = self._ok(r, "buscar el proveedor").get("data") or []
        for e in encontrados:
            if normaliza_nif(e.get("nif")) == normaliza_nif(nif):
                return e["id"]
        if encontrados:
            return encontrados[0]["id"]
        log(f"  Proveedor {nombre} ({nif}) no existe en Contasimple: lo doy de alta.")
        r = self.s.post(f"{API_URL}/entities/providers",
                        json={"type": "Issuer", "organization": nombre, "nif": nif}, timeout=30)
        return self._ok(r, "crear el proveedor")["data"]["id"]

    def ya_existe(self, per, numero, nif):
        r = self.s.get(f"{API_URL}/accounting/{per}/invoices/received",
                       params={"number": numero, "nif": nif}, timeout=30)
        if r.status_code >= 400:
            return False
        return bool(r.json().get("data"))

    def registrar(self, d, per, ruta_pdf):
        proveedor_id = self.proveedor(d["nif"], d["proveedor"])
        if self.ya_existe(per, d["numero"], d["nif"]):
            raise RuntimeError(f"La factura {d['numero']} de {d['proveedor']} ya está en Contasimple.")
        cuerpo = {
            "issuerEntityId": proveedor_id,
            "number": d["numero"],
            "date": d["fecha"].strftime("%Y-%m-%dT00:00:00"),
            "invoiceClass": int(d["cuenta_gasto"]),
            "imputation": int(d["imputacion"]),
            "vatImputation": int(d["imputacion_iva"]),
            "retentionPercentage": d["irpf_pct"],
            "operationType": d["tipo_operacion"],
            "notes": f"Importada automáticamente desde {ruta_pdf.name}",
            "lines": [{
                "concept": d["concepto"],
                "unitAmount": d["base"],
                "quantity": 1,
                "vatPercentage": d["iva_pct"],
                "vatAmount": d["cuota_iva"],
                "totalTaxableAmount": d["base"],
            }],
        }
        r = self.s.post(f"{API_URL}/accounting/{per}/invoices/received", json=cuerpo, timeout=60)
        factura = self._ok(r, "crear la factura")["data"]
        factura_id = factura["id"]
        try:
            with open(ruta_pdf, "rb") as f:
                r = self.s.post(f"{API_URL}/accounting/{per}/invoices/received/{factura_id}/attach",
                                files={"file": (ruta_pdf.name, f, "application/pdf")}, timeout=120)
            self._ok(r, "adjuntar el PDF")
        except Exception as e:  # la factura ya está creada; solo avisamos
            log(f"  ⚠  Factura creada, pero no se pudo adjuntar el PDF: {e}")
        return factura_id


# --------------------------------------------------------------------------
# Creación automática de plantillas
# --------------------------------------------------------------------------

RE_FECHA = r"\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{1,2}\s+de\s+[A-Za-záéíóú]+\s+(?:de\s+)?\d{4}"
RE_IMPORTE = r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d{1,3}(?:,\d{3})*\.\d{2}|-?\d+(?:[.,]\d{1,2})?"
CAPTURA = {
    "numero": r"([A-Za-z0-9][A-Za-z0-9\-/\.]*)",
    "fecha": "(" + RE_FECHA + ")",
    "base": "(" + RE_IMPORTE + ")",
    "total": "(" + RE_IMPORTE + ")",
}
PALABRAS = {"numero": ("factura", "n", "num", "nº"), "fecha": ("fecha",),
            "base": ("base", "imponible", "subtotal"), "total": ("total",)}
LETRA = r"[A-Za-zÁÉÍÓÚáéíóúñÑ]"


def _etiquetas(texto, inicio):
    """Posibles etiquetas del valor: lo que tiene delante en su línea, o la cabecera de la línea anterior
    (facturas en forma de tabla). Devuelve (etiqueta, columna) con columna=None si está en la misma línea."""
    ini_linea = texto.rfind("\n", 0, inicio) + 1
    antes = texto[ini_linea:inicio]
    res = []
    m = re.search(r"([^\d\n]{2,40}?)[\s:.\-€]*$", antes)
    if m and re.search(LETRA, m.group(1)):
        res.append((re.sub(r"[\s:.\-€(]+$", "", m.group(1)).strip(), None))
    if ini_linea > 0:
        ant_ini = texto.rfind("\n", 0, ini_linea - 1) + 1
        anterior = texto[ant_ini:ini_linea - 1]
        palabras = [w for w in anterior.split()[:3]]
        while palabras and not re.search(LETRA, palabras[-1]):
            palabras.pop()
        if palabras:
            columna = len(antes.split())
            res.append((" ".join(palabras), columna))
    return res


def _patron(etiqueta, columna, tipo):
    pre = r"(?<![A-Za-zÁÉÍÓÚáéíóúñÑ])" + r"\s+".join(re.escape(p) for p in etiqueta.split())
    if columna is None:
        sep = r"[\s:.\-€]*"
    else:
        sep = r"[^\n]*\n\s*" + (r"(?:\S+\s+){%d}" % columna if columna else "")
    return pre + sep + CAPTURA[tipo]


def _candidatos(texto, tipo, valor):
    if tipo == "numero":
        return [m.start() for m in re.finditer(re.escape(str(valor)), texto)]
    if tipo == "fecha":
        return [m.start() for m in re.finditer(RE_FECHA, texto) if fecha(m.group(0)) == valor]
    return [m.start() for m in re.finditer(RE_IMPORTE, texto) if importe(m.group(0)) == valor]


def _coincide(tipo, extraido, valor):
    if tipo == "numero":
        return extraido == str(valor)
    if tipo == "fecha":
        return fecha(extraido) == valor
    return importe(extraido) == valor


def crear_patron(texto, tipo, valor):
    if valor in (None, ""):
        return None
    posiciones = _candidatos(texto, tipo, valor)
    # se prueban primero las apariciones con una etiqueta "típica" (Total, Base, Fecha...)
    opciones = []
    for pos in posiciones:
        for etiqueta, columna in _etiquetas(texto, pos):
            tipica = any(p in etiqueta.lower() for p in PALABRAS[tipo])
            opciones.append((not tipica, columna is not None, -pos if tipo == "total" else pos, etiqueta, columna))
    for *_, etiqueta, columna in sorted(opciones):
        patron = _patron(etiqueta, columna, tipo)
        extraido = campo(texto, patron)
        if extraido is not None and _coincide(tipo, extraido, valor):
            return patron
    return None


def plantilla_desde_datos(texto, d):
    patrones, fallos = {}, []
    for tipo, nombre in (("numero", "número"), ("fecha", "fecha"), ("base", "base imponible"), ("total", "total")):
        valor = d.get("total_calculado") if tipo == "total" else d.get(tipo)
        p = crear_patron(texto, tipo, valor)
        if p:
            patrones[tipo] = p
        else:
            fallos.append(nombre)
    reconocer = [d["nif"]] if normaliza_nif(d["nif"]) in normaliza_nif(texto) else []
    if not reconocer and d["proveedor"] and d["proveedor"].lower() in texto.lower():
        reconocer = [d["proveedor"]]
    plantilla = {
        "nombre": d["proveedor"], "nif": d["nif"], "reconocer_por": reconocer,
        "concepto": d["concepto"], "cuenta_gasto": int(d["cuenta_gasto"]),
        "iva_pct": d["iva_pct"], "irpf_pct": d["irpf_pct"],
        "tipo_operacion": d.get("tipo_operacion", "Nacional"),
        "imputacion_pct": d.get("imputacion", 100), "imputacion_iva_pct": d.get("imputacion_iva", 100),
        "patrones": patrones,
    }
    return plantilla, fallos


def ofrecer_plantilla(texto, d, preguntar=True):
    """Crea la plantilla a partir de una factura ya revisada y la guarda si el usuario quiere."""
    if not texto.strip():
        return
    if preguntar:
        r = input(f"\n  ¿Guardar a {d['proveedor']} como proveedor habitual para leer sus próximas facturas? [S/N]: ")
        if r.strip().lower() != "s":
            return
    calcula(d)
    plantilla, fallos = plantilla_desde_datos(texto, d)
    if not plantilla["reconocer_por"]:
        print("  ✗ No encuentro ni el NIF ni el nombre del proveedor en el texto del PDF: no puedo crear la plantilla.")
        return
    if fallos:
        print(f"  ⚠  No he sabido localizar en el PDF: {', '.join(fallos)}. "
              "Esos datos se le pedirán o calcularán en cada factura.")
    proveedores = cargar_json(PROVEEDORES_FILE, obligatorio=False) or []
    proveedores = [p for p in proveedores if normaliza_nif(p.get("nif")) != normaliza_nif(d["nif"])]
    proveedores.append(plantilla)
    with open(PROVEEDORES_FILE, "w", encoding="utf-8") as f:
        json.dump(proveedores, f, ensure_ascii=False, indent=2)
    log(f"  ✓ Proveedor {d['proveedor']} guardado en proveedores.json.")


# --------------------------------------------------------------------------
# Órdenes
# --------------------------------------------------------------------------

def mover(ruta, destino, subcarpeta=None):
    carpeta = Path(destino) / subcarpeta if subcarpeta else Path(destino)
    carpeta.mkdir(parents=True, exist_ok=True)
    final = carpeta / ruta.name
    n = 1
    while final.exists():
        final = carpeta / f"{ruta.stem} ({n}){ruta.suffix}"
        n += 1
    shutil.move(str(ruta), str(final))
    return final


def clave_api(config):
    return os.environ.get("CONTASIMPLE_API_KEY") or config.get("clave_api_contasimple")


def orden_procesar(config):
    proveedores = cargar_json(PROVEEDORES_FILE, obligatorio=False) or []
    entrada = Path(config["carpeta_entrada"])
    for c in ("carpeta_entrada", "carpeta_gestionadas", "carpeta_revisar"):
        Path(config[c]).mkdir(parents=True, exist_ok=True)
    pdfs = sorted(p for p in entrada.iterdir() if p.suffix.lower() == ".pdf")
    if not pdfs:
        print(f"No hay facturas PDF en {entrada}")
        return
    print(f"{len(pdfs)} factura(s) en {entrada}")
    cs = Contasimple(clave_api(config), config.get("client_id"))
    hechas = 0
    for ruta in pdfs:
        try:
            texto = texto_pdf(ruta)
        except Exception as e:
            log(f"{ruta.name}: no se puede leer el PDF ({e}).")
            continue
        if not texto.strip():
            print(f"\n{ruta.name}: el PDF no tiene texto (¿escaneado?). Introduzca los datos a mano.")
        plantilla = buscar_plantilla(texto, proveedores) if texto.strip() else None
        d = extraer(texto, plantilla, config) if plantilla else datos_manual(ruta.name, config)
        decision = revisar(d, ruta.name)
        if decision == "salir":
            break
        if decision == "omitir":
            continue
        if decision == "revisar":
            mover(ruta, config["carpeta_revisar"])
            log(f"{ruta.name}: enviada a Revisar.")
            continue
        per = periodo(d["fecha"], config.get("formato_periodo", "{anio}-{trimestre}T"))
        try:
            fid = cs.registrar(d, per, ruta)
        except Exception as e:
            log(f"{ruta.name}: NO registrada. {e}")
            print("  El PDF se queda en la carpeta de entrada.")
            continue
        sub = d["fecha"].strftime("%Y") if config.get("subcarpeta_por_anio", True) else None
        final = mover(ruta, config["carpeta_gestionadas"], sub)
        log(f"{ruta.name}: registrada en Contasimple (id {fid}, periodo {per}) y movida a {final}")
        hechas += 1
        if not plantilla and texto.strip():
            ofrecer_plantilla(texto, d)
            proveedores = cargar_json(PROVEEDORES_FILE, obligatorio=False) or []
    print(f"\nTerminado. Registradas: {hechas}.")


def orden_probar(config):
    cs = Contasimple(clave_api(config), config.get("client_id"))
    print("Conexión con Contasimple correcta.\n\nCuentas de gasto disponibles (use el número en 'cuenta_gasto'):")

    def pinta(items, nivel=0):
        for c in items:
            if c.get("enabled", True) and c.get("accountNumber"):
                print(f"  {'  ' * nivel}{c['accountNumber']:<8} {c.get('description') or c.get('name')}")
            pinta(c.get("subItems") or [], nivel + 1)
    pinta(cs.cuentas_gasto())
    per = periodo(datetime.now(), config.get("formato_periodo", "{anio}-{trimestre}T"))
    r = cs.s.get(f"{API_URL}/accounting/{per}/invoices/received", params={"numRows": 1}, timeout=30)
    if r.status_code < 400:
        print(f"\nFormato de periodo correcto ({per}).")
    else:
        print(f"\n⚠  Contasimple no acepta el periodo '{per}' ({r.status_code}): {r.text[:200]}\n"
              "   Cambie 'formato_periodo' en config.json (vea LEEME.md).")


def orden_texto(ruta):
    print(texto_pdf(Path(ruta)))


def orden_nuevo_proveedor(config, ruta):
    ruta = Path(ruta.strip('"'))
    texto = texto_pdf(ruta)
    if not texto.strip():
        print("Este PDF no tiene texto (es una imagen escaneada): no se puede crear una plantilla.")
        return
    print("Escriba los datos de ESTA factura tal como aparecen en el PDF.")
    d = datos_manual(ruta.name, config)
    calcula(d)
    ofrecer_plantilla(texto, d, preguntar=False)
    proveedores = cargar_json(PROVEEDORES_FILE, obligatorio=False) or []
    p = buscar_plantilla(texto, proveedores)
    if p:
        print("\nAsí leerá el programa las próximas facturas de este proveedor:")
        mostrar(extraer(texto, p, config), ruta.name)


def orden_probar_plantilla(config, ruta):
    proveedores = cargar_json(PROVEEDORES_FILE)
    texto = texto_pdf(Path(ruta))
    p = buscar_plantilla(texto, proveedores)
    if not p:
        print("Ninguna plantilla reconoce este PDF. Revise 'reconocer_por' en proveedores.json.")
        return
    d = extraer(texto, p, config)
    mostrar(d, Path(ruta).name)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("procesar", "probar", "texto", "probar-plantilla",
                                                "nuevo-proveedor"):
        print(__doc__)
        return
    orden = sys.argv[1]
    if orden == "texto":
        orden_texto(sys.argv[2])
        return
    config = cargar_json(CONFIG_FILE)
    if orden == "procesar":
        orden_procesar(config)
    elif orden == "probar":
        orden_probar(config)
    elif orden == "nuevo-proveedor":
        if len(sys.argv) < 3:
            print("Arrastre una factura PDF del proveedor sobre nuevo_proveedor.bat")
            return
        orden_nuevo_proveedor(config, sys.argv[2])
    elif orden == "probar-plantilla":
        orden_probar_plantilla(config, sys.argv[2])


if __name__ == "__main__":
    main()
