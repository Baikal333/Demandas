"""Traducción + análisis con Claude (opcional, requiere ANTHROPIC_API_KEY o `ant auth login`).

Una sola llamada por anuncio devuelve la traducción al español y los puntos
fuertes/débiles en JSON validado por esquema. Los resultados se guardan en caché
para no pagar dos veces el mismo anuncio.
"""
from __future__ import annotations

import hashlib
import json
import logging

from .analisis import DEBILES, FUERTES
from .db import BaseDatos
from .models import Anuncio, Rasgo

log = logging.getLogger(__name__)

_PESOS_F = {p.clave: (p.etiqueta, p.peso) for p in FUERTES}
_PESOS_D = {p.clave: (p.etiqueta, p.peso) for p in DEBILES}

_RASGO = {
    "type": "object",
    "properties": {
        "clave": {"type": "string"},
        "etiqueta": {"type": "string"},
        "evidencia": {"type": "string"},
    },
    "required": ["clave", "etiqueta", "evidencia"],
    "additionalProperties": False,
}

ESQUEMA = {
    "type": "object",
    "properties": {
        "titulo_es": {"type": "string"},
        "descripcion_es": {"type": "string"},
        "resumen_es": {"type": "string"},
        "eslora_m": {"type": ["number", "null"]},
        "anio": {"type": ["integer", "null"]},
        "bandera": {"type": ["string", "null"]},
        "ce": {"type": "string", "enum": ["si", "no", "desconocido"]},
        "iva_pagado": {"type": ["boolean", "null"]},
        "vendedor_profesional": {"type": ["boolean", "null"]},
        "puntos_fuertes": {"type": "array", "items": _RASGO},
        "puntos_debiles": {"type": "array", "items": _RASGO},
    },
    "required": ["titulo_es", "descripcion_es", "resumen_es", "eslora_m", "anio", "bandera", "ce",
                 "iva_pagado", "vendedor_profesional", "puntos_fuertes", "puntos_debiles"],
    "additionalProperties": False,
}

SISTEMA = f"""Eres un perito náutico que ayuda a un comprador español a evaluar veleros de segunda mano.
Recibirás un anuncio (en español, francés, neerlandés o inglés). Debes:
1. Traducirlo fielmente al español (titulo_es, descripcion_es). Conserva cifras, marcas y modelos.
2. Escribir resumen_es: 2-3 frases sobre estado real, equipamiento y riesgos.
3. Extraer eslora total en metros (convierte pies), año de construcción, bandera (código ISO de 2 letras, p. ej. FR, PL, ES, NL; null si no consta),
   si consta marcado CE o categoría de diseño ("si"), si se dice que no tiene ("no") o no consta ("desconocido"),
   si el IVA/TVA/BTW está pagado, y si el vendedor parece profesional.
4. Listar puntos fuertes y débiles SOLO si el anuncio los menciona (evidencia = cita breve traducida).
   Usa estas claves cuando encajen; si no encaja ninguna usa "otro".
   Claves de puntos fuertes: {", ".join(_PESOS_F)}.
   Claves de puntos débiles: {", ".join(_PESOS_D)}.
   Una negación ("sin ósmosis") NO es un punto débil. No inventes datos que no aparezcan."""


class AnalizadorClaude:
    def __init__(self, cfg: dict, db: BaseDatos):
        import anthropic  # importación diferida: solo si se usa

        self.anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.modelo = cfg.get("modelo", "claude-opus-5-5")
        self.esfuerzo = cfg.get("esfuerzo", "low")
        self.db = db

    def _llamar(self, contenido: str) -> dict | None:
        resp = self.client.beta.messages.create(
            model=self.modelo,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SISTEMA,
            output_config={"effort": self.esfuerzo, "format": {"type": "json_schema", "schema": ESQUEMA}},
            messages=[{"role": "user", "content": contenido}],
        )
        if resp.stop_reason == "refusal":
            log.warning("Claude declinó analizar un anuncio; se usa el análisis por palabras clave.")
            return None
        if resp.stop_reason == "max_tokens":
            log.warning("Respuesta truncada (max_tokens); se usa el análisis por palabras clave.")
            return None
        texto = next((b.text for b in resp.content if b.type == "text"), None)
        return json.loads(texto) if texto else None

    def analizar(self, a: Anuncio) -> bool:
        """Aplica traducción y análisis al anuncio. Devuelve False si no se pudo."""
        contenido = (f"Portal: {a.sitio} ({a.pais})\nTítulo: {a.titulo}\nPrecio: {a.precio} {a.moneda}\n"
                     f"Ubicación: {a.ubicacion}\nCaracterísticas: {json.dumps(a.caracteristicas, ensure_ascii=False)}\n\n"
                     f"Descripción:\n{a.descripcion}")
        clave = hashlib.sha1((self.modelo + contenido).encode("utf-8")).hexdigest()
        datos = self.db.ia(clave)
        if datos is None:
            try:
                datos = self._llamar(contenido)
            except self.anthropic.RateLimitError:
                log.warning("Límite de peticiones de la API alcanzado; se omite el análisis con IA para este anuncio.")
                return False
            except self.anthropic.APIStatusError as e:
                log.warning("Error de la API de Claude (%s): %s", e.status_code, e.message)
                return False
            except self.anthropic.APIConnectionError:
                log.warning("Sin conexión con la API de Claude.")
                return False
            except json.JSONDecodeError:
                return False
            if datos is None:
                return False
            self.db.guardar_ia(clave, datos)
        a.titulo_es = datos["titulo_es"] or a.titulo
        a.descripcion_es = datos["descripcion_es"] or a.descripcion
        a.resumen_es = datos["resumen_es"]
        if datos["eslora_m"] and not a.eslora_m:
            a.eslora_m = float(datos["eslora_m"])
        if datos["anio"] and not a.anio:
            a.anio = int(datos["anio"])
        if datos["bandera"] and not a.bandera:
            a.bandera = datos["bandera"].upper()[:2]
        if datos["ce"] != "desconocido":
            a.ce = datos["ce"]
        if datos["iva_pagado"] is not None:
            a.iva_pagado = datos["iva_pagado"]
        if datos["vendedor_profesional"] is not None and a.vendedor_profesional is None:
            a.vendedor_profesional = datos["vendedor_profesional"]
        a.datos_ia = datos  # type: ignore[attr-defined]
        return True


def fusionar_rasgos(a: Anuncio) -> None:
    """Añade a los rasgos por palabras clave los que haya detectado Claude."""
    datos = getattr(a, "datos_ia", None)
    if not datos:
        return
    existentes_f = {r.clave for r in a.puntos_fuertes}
    existentes_d = {r.clave for r in a.puntos_debiles}
    for r in datos["puntos_fuertes"]:
        if r["clave"] in existentes_f:
            continue
        etiqueta, peso = _PESOS_F.get(r["clave"], (r["etiqueta"], 2))
        a.puntos_fuertes.append(Rasgo(r["clave"] if r["clave"] != "otro" else "otro_" + r["etiqueta"][:20], r["etiqueta"] or etiqueta, peso, r["evidencia"]))
    for r in datos["puntos_debiles"]:
        if r["clave"] in existentes_d:
            continue
        etiqueta, peso = _PESOS_D.get(r["clave"], (r["etiqueta"], 5))
        a.puntos_debiles.append(Rasgo(r["clave"] if r["clave"] != "otro" else "otro_" + r["etiqueta"][:20], r["etiqueta"] or etiqueta, peso, r["evidencia"]))
    if "motor_averiado" in {r.clave for r in a.puntos_debiles}:
        a.puntos_fuertes = [r for r in a.puntos_fuertes if r.clave != "motor_ok"]
    a.puntos_fuertes.sort(key=lambda r: -r.peso)
    a.puntos_debiles.sort(key=lambda r: -r.peso)
