"""Criterios de descarte: eslora, precio, antigüedad, marcado CE y tipo de barco."""
from __future__ import annotations

import re

from .models import Anuncio
from .parsing import normalizar


def motivo_descarte(a: Anuncio, f: dict) -> str | None:
    """Devuelve el motivo por el que se descarta el anuncio, o None si pasa los filtros."""
    texto = normalizar(a.titulo + " " + a.descripcion[:600])
    for palabra in f.get("excluir_palabras", []):
        if re.search(r"\b" + re.escape(normalizar(palabra)), texto):
            return f"no es un velero completo ('{palabra}')"

    if a.precio is None:
        if f.get("descartar_sin_precio", True):
            return "sin precio"
    elif a.precio > f["precio_max"]:
        return f"precio superior a {f['precio_max']:,.0f} €".replace(",", ".")
    elif a.precio < f.get("precio_min", 0):
        return "precio simbólico o 'a consultar'"

    if a.eslora_m is None:
        if f.get("descartar_sin_eslora", True):
            return "eslora no indicada"
    elif not (f["eslora_min"] <= a.eslora_m <= f["eslora_max"]):
        return f"eslora {a.eslora_m:.2f} m fuera de {f['eslora_min']}-{f['eslora_max']} m"

    anio_min = f.get("anio_minimo", 1990)
    anio_ce = f.get("anio_ce_obligatorio", 1998)
    if a.ce == "no":
        return "el anuncio indica que no tiene marcado CE"
    if a.anio is None:
        if f.get("descartar_sin_anio", False) and a.ce != "si":
            return "año no indicado y sin mención de CE"
    else:
        if a.anio < anio_min:
            return f"modelo muy antiguo ({a.anio})"
        if f.get("exigir_ce", True) and a.anio < anio_ce and a.ce != "si":
            return f"anterior a {anio_ce} ({a.anio}) sin marcado CE acreditado"
    if f.get("exigir_palabra_vela") and f.get("palabras_vela"):
        texto_total = normalizar(a.texto_completo)
        if not any(normalizar(p) in texto_total for p in f["palabras_vela"]):
            return "no parece un velero"
    return None
