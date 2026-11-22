"""Traducción de anuncios al español con caché en SQLite.

Motores:
  - "google": deep-translator (Google Translate web, gratuito, sin clave).
  - "claude": se hace junto con el análisis en ia.py (una sola llamada).
  - "ninguno": no traduce.
"""
from __future__ import annotations

import hashlib
import logging

from .db import BaseDatos

log = logging.getLogger(__name__)
_MAX = 4500


def _trozos(texto: str) -> list[str]:
    trozos, actual = [], ""
    for parrafo in texto.split("\n"):
        while len(parrafo) > _MAX:
            corte = parrafo.rfind(". ", 0, _MAX) + 1 or _MAX
            trozos.append(parrafo[:corte])
            parrafo = parrafo[corte:]
        if len(actual) + len(parrafo) + 1 > _MAX:
            trozos.append(actual)
            actual = ""
        actual += parrafo + "\n"
    if actual.strip():
        trozos.append(actual)
    return trozos


class Traductor:
    def __init__(self, motor: str, db: BaseDatos):
        self.motor = motor
        self.db = db
        self._google = None
        if motor == "google":
            try:
                from deep_translator import GoogleTranslator
                self._google = GoogleTranslator(source="auto", target="es")
            except ImportError:
                log.warning("deep-translator no está instalado: pip install deep-translator. Se omite la traducción.")
                self.motor = "ninguno"

    def traducir(self, texto: str, idioma: str | None) -> str:
        if not texto or not texto.strip() or idioma == "es" or self.motor != "google":
            return texto
        clave = hashlib.sha1(texto.encode("utf-8")).hexdigest()
        cache = self.db.traduccion(clave)
        if cache is not None:
            return cache
        try:
            salida = "".join((self._google.translate(t) or "") + "\n" for t in _trozos(texto)).strip()
        except Exception as e:  # noqa: BLE001 - el servicio web puede fallar de muchas formas
            log.warning("Traducción fallida (%s); se deja el texto original.", e)
            return texto
        self.db.guardar_traduccion(clave, salida)
        return salida
