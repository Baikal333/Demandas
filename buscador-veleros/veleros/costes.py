"""Estimación del coste total de compra: precio + impuestos + abanderamiento + traslado.

IMPORTANTE: son estimaciones orientativas con parámetros editables en config.yaml.
Los tipos impositivos y tasas cambian y dependen de la comunidad autónoma, del
vendedor (particular / profesional) y de la documentación del barco. Confírmense
siempre con una gestoría náutica antes de comprar.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import requests

from .models import Anuncio
from .parsing import normalizar

# Coordenadas aproximadas de puertos/ciudades frecuentes (lat, lon).
LUGARES: dict[str, tuple[float, float]] = {
    # España
    "barcelona": (41.38, 2.18), "tarragona": (41.12, 1.25), "girona": (41.98, 2.82), "roses": (42.26, 3.18), "palamos": (41.85, 3.13),
    "valencia": (39.46, -0.33), "alicante": (38.34, -0.48), "denia": (38.84, 0.11), "castellon": (39.97, -0.03), "murcia": (37.98, -1.13),
    "cartagena": (37.6, -0.98), "almeria": (36.83, -2.46), "malaga": (36.72, -4.42), "cadiz": (36.53, -6.29), "huelva": (37.26, -6.95),
    "sevilla": (37.39, -5.98), "palma": (39.57, 2.65), "mallorca": (39.6, 2.9), "ibiza": (38.91, 1.43), "menorca": (39.95, 4.1),
    "bilbao": (43.26, -2.93), "santander": (43.46, -3.81), "gijon": (43.54, -5.66), "coruna": (43.37, -8.4), "vigo": (42.24, -8.72),
    "san sebastian": (43.32, -1.98), "donostia": (43.32, -1.98), "madrid": (40.42, -3.7), "zaragoza": (41.65, -0.88),
    # Francia
    "brest": (48.39, -4.49), "lorient": (47.75, -3.37), "vannes": (47.66, -2.76), "la trinite": (47.59, -3.03), "saint-malo": (48.65, -2.0),
    "saint malo": (48.65, -2.0), "cherbourg": (49.64, -1.62), "le havre": (49.49, 0.11), "caen": (49.18, -0.37), "nantes": (47.22, -1.55),
    "pornic": (47.11, -2.1), "la rochelle": (46.16, -1.15), "les sables": (46.5, -1.78), "royan": (45.62, -1.03), "arcachon": (44.66, -1.17),
    "bordeaux": (44.84, -0.58), "biarritz": (43.48, -1.56), "hendaye": (43.36, -1.77), "bayonne": (43.49, -1.47), "port-vendres": (42.52, 3.11),
    "perpignan": (42.7, 2.9), "canet": (42.7, 3.03), "leucate": (42.91, 3.03), "port-la-nouvelle": (43.02, 3.04), "narbonne": (43.18, 3.0),
    "sete": (43.4, 3.69), "montpellier": (43.61, 3.88), "la grande-motte": (43.56, 4.08), "marseille": (43.3, 5.37), "toulon": (43.12, 5.93),
    "hyeres": (43.12, 6.13), "saint-tropez": (43.27, 6.64), "cannes": (43.55, 7.01), "antibes": (43.58, 7.12), "nice": (43.7, 7.27),
    "ajaccio": (41.92, 8.74), "bastia": (42.7, 9.45), "corse": (42.15, 9.1), "bretagne": (48.0, -3.2), "normandie": (49.1, -0.4),
    "vendee": (46.7, -1.4), "charente": (45.9, -1.0), "gironde": (44.8, -0.6), "occitanie": (43.6, 3.0), "provence": (43.5, 5.8),
    "paris": (48.86, 2.35), "lyon": (45.76, 4.84), "lille": (50.63, 3.06), "dunkerque": (51.03, 2.38), "boulogne": (50.73, 1.61),
    # Países Bajos
    "amsterdam": (52.37, 4.9), "rotterdam": (51.92, 4.48), "lelystad": (52.52, 5.47), "enkhuizen": (52.7, 5.29), "hoorn": (52.64, 5.06),
    "den helder": (52.96, 4.76), "harlingen": (53.17, 5.42), "makkum": (53.06, 5.4), "lemmer": (52.84, 5.71), "sneek": (53.03, 5.66),
    "heeg": (52.97, 5.6), "workum": (52.98, 5.45), "stavoren": (52.88, 5.36), "muiden": (52.33, 5.07), "huizen": (52.3, 5.24),
    "hellevoetsluis": (51.82, 4.13), "bruinisse": (51.66, 4.09), "vlissingen": (51.44, 3.57), "middelburg": (51.5, 3.61), "zeeland": (51.5, 3.8),
    "friesland": (53.1, 5.8), "noord-holland": (52.6, 4.9), "flevoland": (52.5, 5.6), "groningen": (53.22, 6.57), "utrecht": (52.09, 5.12),
    "den haag": (52.07, 4.3), "scheveningen": (52.1, 4.27), "ijmuiden": (52.46, 4.6), "monnickendam": (52.46, 5.04), "roermond": (51.19, 5.99),
    # Polonia (por si el barco se registra/lleva allí)
    "gdansk": (54.35, 18.65), "gdynia": (54.52, 18.53), "szczecin": (53.43, 14.55),
}
CENTRO_PAIS = {"ES": (40.4, -3.7), "FR": (46.6, 2.4), "NL": (52.3, 5.3), "PL": (52.2, 19.1), "BE": (50.8, 4.4), "DE": (51.2, 10.4)}
_FACTOR_CARRETERA = 1.3


def _haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371.0
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


class Geocodificador:
    """Tabla interna + (opcional) Nominatim/OpenStreetMap con caché en disco."""

    def __init__(self, cfg: dict, cache_path: Path):
        self.online = cfg.get("geocodificar_online", True)
        self.cache_path = cache_path
        try:
            self.cache = json.loads(cache_path.read_text("utf-8"))
        except (OSError, ValueError):
            self.cache = {}
        self._ultimo = 0.0

    def _guardar(self):
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False), "utf-8")
        except OSError:
            pass

    def buscar(self, lugar: str, pais: str) -> tuple[tuple[float, float], str]:
        """Devuelve ((lat, lon), precisión)."""
        n = normalizar(lugar)
        for nombre in sorted(LUGARES, key=len, reverse=True):
            if nombre in n:
                return LUGARES[nombre], nombre
        clave = f"{pais}|{n}"
        if n and clave in self.cache:
            c = self.cache[clave]
            if c:
                return (c[0], c[1]), "osm"
        elif n and self.online:
            try:
                espera = 1.1 - (time.time() - self._ultimo)
                if espera > 0:
                    time.sleep(espera)
                self._ultimo = time.time()
                r = requests.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": lugar, "countrycodes": pais.lower(), "format": "json", "limit": 1},
                    headers={"User-Agent": "buscador-veleros/1.0 (uso personal)"},
                    timeout=15,
                )
                datos = r.json() if r.ok else []
                self.cache[clave] = [float(datos[0]["lat"]), float(datos[0]["lon"])] if datos else None
                self._guardar()
                if datos:
                    return (float(datos[0]["lat"]), float(datos[0]["lon"])), "osm"
            except (requests.RequestException, ValueError, KeyError, IndexError):
                pass
        return CENTRO_PAIS.get(pais, CENTRO_PAIS["FR"]), "centro del país"


# ------------------------------------------------------------------ cálculos
def _valor_fiscal(precio: float, anio: int | None, cfg_fiscal: dict) -> float:
    """Base imponible: el mayor entre el precio y un valor de tablas aproximado.

    Hacienda publica cada año (Orden HFP de precios medios) los valores de
    embarcaciones; aquí se aproxima con el precio declarado como mínimo.
    """
    minimo = cfg_fiscal.get("base_minima_eur", 0)
    return max(precio, minimo)


def transporte(anuncio: Anuncio, geo: Geocodificador, cfg: dict) -> dict:
    t = cfg["traslado"]
    destino = cfg.get("destino", {})
    dest_coord = (destino.get("lat", 39.46), destino.get("lon", -0.33))
    origen, precision = geo.buscar(anuncio.ubicacion or "", anuncio.pais)
    km = round(_haversine(origen, dest_coord) * _FACTOR_CARRETERA)
    eslora = anuncio.eslora_m or 8.5
    manga = anuncio.manga_m or (2.5 + (eslora - 7) * 0.25)
    especial = manga > t.get("manga_max_sin_permiso_m", 2.55) or eslora > t.get("eslora_transporte_especial_m", 8.5)
    eur_km = t["eur_km_especial"] if especial else t["eur_km_normal"]
    tiene_remolque = any(r.clave == "remolque" for r in anuncio.puntos_fuertes)
    partidas = {
        "camión (%d km × %.2f €/km)" % (km, eur_km): km * eur_km,
        "grúa/varada origen y destino": 0 if tiene_remolque else t["grua_origen"] + t["grua_destino"],
        "desarbolado y arbolado del mástil": t["mastil"],
        "cuna de transporte / calzos": 0 if tiene_remolque else t["cuna"],
    }
    if especial:
        partidas["permiso de transporte especial / escolta"] = t["permiso_especial"]
    if tiene_remolque:
        partidas["remolcado con el propio remolque (vehículo propio, combustible y peajes)"] = km * t.get("eur_km_remolque_propio", 0.45)
        partidas = {k: v for k, v in partidas.items() if not k.startswith("camión")}
    total = sum(partidas.values())
    return {
        "km": km, "precision_origen": precision, "transporte_especial": especial,
        "partidas": {k: round(v) for k, v in partidas.items() if v}, "total": round(total),
    }


def escenario_espana(anuncio: Anuncio, cfg: dict) -> dict:
    f = cfg["fiscalidad_espana"]
    a = cfg["abanderamiento_espana"]
    precio = anuncio.precio or 0
    base = _valor_fiscal(precio, anuncio.anio, f)
    partidas: dict[str, float] = {}
    avisos: list[str] = []
    profesional_con_iva = bool(anuncio.vendedor_profesional) and f.get("vendedor_profesional_factura_iva", True)
    if profesional_con_iva:
        avisos.append("Vendedor profesional: normalmente factura con IVA incluido y no hay ITP.")
    else:
        partidas[f"ITP (modelo 620) {f['itp_tipo'] * 100:.1f} % ({f.get('itp_comunidad', 'CCAA')})"] = base * f["itp_tipo"]

    ya_espanol = (anuncio.bandera == "ES") or (anuncio.bandera is None and anuncio.pais == "ES")
    eslora = anuncio.eslora_m or 0
    if not ya_espanol:
        if eslora > f.get("iedmt_eslora_umbral_m", 8):
            partidas[f"Impuesto de matriculación IEDMT (modelo 576) {f['iedmt_tipo'] * 100:.0f} %"] = base * f["iedmt_tipo"]
        else:
            avisos.append(f"Eslora ≤ {f.get('iedmt_eslora_umbral_m', 8)} m: no sujeta al impuesto de matriculación (IEDMT).")
        partidas["Tasas Capitanía Marítima (abanderamiento y matrícula)"] = a["tasas_capitania"]
        partidas["Inspección inicial / certificado de navegabilidad (ECI)"] = a["inspeccion_eci"]
        partidas["Gestoría náutica"] = a["gestoria"]
        partidas["Traducción jurada de documentos"] = 0 if anuncio.pais == "ES" else a["traduccion_jurada"]
        partidas["Baja en el registro de origen"] = a.get("baja_origen", {}).get(anuncio.bandera or anuncio.pais, 0)
        if anuncio.ce != "si":
            if (anuncio.anio or 0) >= 1998:
                avisos.append("Pida la Declaración de Conformidad CE al vendedor: es imprescindible para matricular en España.")
            else:
                partidas["Evaluación posconstrucción CE (PCA) si no hay declaración CE"] = a["evaluacion_posconstruccion_ce"]
                avisos.append("Sin declaración CE, matricular en España exige una evaluación posconstrucción (cara y lenta).")
        if anuncio.iva_pagado is not True:
            avisos.append("Pida prueba de IVA UE pagado (factura original o antigüedad anterior a 1985 en la UE). "
                          "Sin ella Hacienda puede reclamar el IVA (21 %).")
    else:
        partidas["Cambio de titularidad (tasas Capitanía + gestoría)"] = a["cambio_titularidad"]
        avisos.append("El barco ya tiene bandera española: solo cambio de titularidad (sin IEDMT).")
    partidas["Seguro obligatorio RC (1 año)"] = a["seguro_rc_anual"]
    total = sum(partidas.values())
    return {"nombre": "Abanderar en España", "partidas": {k: round(v) for k, v in partidas.items() if v},
            "impuestos_y_tramites": round(total), "avisos": avisos}


def escenario_polonia(anuncio: Anuncio, cfg: dict) -> dict:
    p = cfg["abanderamiento_polonia"]
    precio = anuncio.precio or 0
    partidas: dict[str, float] = {}
    avisos = [
        "Residente en España con bandera polaca: Hacienda puede exigir el IEDMT si el barco se usa de forma "
        "habitual en aguas españolas (art. 65.1.d Ley 38/1992). Consúltelo con un asesor.",
    ]
    if anuncio.bandera == "PL":
        partidas["Cambio de propietario en registro polaco"] = p["cambio_propietario"]
    else:
        partidas["Inscripción en registro polaco de embarcaciones (tasa)"] = p["tasa_registro"]
        partidas["Gestoría / representante en Polonia"] = p["gestoria"]
        partidas["Traducción jurada al polaco"] = p["traduccion_jurada"]
        partidas["Baja en el registro de origen"] = cfg["abanderamiento_espana"].get("baja_origen", {}).get(anuncio.bandera or anuncio.pais, 0)
    if p.get("pcc_tipo"):
        partidas[f"PCC polaco {p['pcc_tipo'] * 100:.0f} % (si el contrato se firma en Polonia)"] = precio * p["pcc_tipo"]
    partidas["Seguro RC (1 año)"] = p["seguro_rc_anual"]
    if anuncio.iva_pagado is not True:
        avisos.append("Conserve prueba del IVA UE pagado: también la piden en Polonia.")
    total = sum(partidas.values())
    return {"nombre": "Bandera polaca", "partidas": {k: round(v) for k, v in partidas.items() if v},
            "impuestos_y_tramites": round(total), "avisos": avisos}


def estimar(anuncio: Anuncio, geo: Geocodificador, cfg: dict) -> dict:
    ccfg = cfg["costes"]
    precio = anuncio.precio or 0
    tr = transporte(anuncio, geo, ccfg)
    inspeccion = ccfg.get("inspeccion_previa", {})
    otros = {"Peritaje antes de comprar": inspeccion.get("peritaje", 0),
             "Viaje para ver el barco": inspeccion.get("viaje", 0) if anuncio.pais != "ES" else inspeccion.get("viaje_nacional", 0)}
    otros = {k: v for k, v in otros.items() if v}
    escenarios = [escenario_espana(anuncio, ccfg)]
    if ccfg.get("calcular_bandera_polaca", True) and not (anuncio.bandera == "ES" or (anuncio.bandera is None and anuncio.pais == "ES")):
        escenarios.append(escenario_polonia(anuncio, ccfg))
    elif anuncio.bandera == "PL":
        escenarios.append(escenario_polonia(anuncio, ccfg))
    for e in escenarios:
        e["total"] = round(precio + e["impuestos_y_tramites"] + tr["total"] + sum(otros.values()))
    mejor = min(escenarios, key=lambda e: e["total"])
    return {"precio": precio, "traslado": tr, "otros": otros, "escenarios": escenarios,
            "mejor_total": mejor["total"], "mejor_escenario": mejor["nombre"],
            "destino": ccfg.get("destino", {}).get("nombre", "")}
