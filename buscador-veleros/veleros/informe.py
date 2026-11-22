"""Generación del informe HTML diario."""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .procesar import PAISES, Resultado

_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
_BANDERAS = {"ES": "🇪🇸", "FR": "🇫🇷", "NL": "🇳🇱", "PL": "🇵🇱"}


def eur(v) -> str:
    if v is None:
        return "—"
    return f"{v:,.0f} €".replace(",", ".")


def generar(res: Resultado, top: dict, cfg: dict, carpeta: Path, fecha: str, casi: dict | None = None) -> Path:
    env = Environment(loader=FileSystemLoader(Path(__file__).parent / "plantillas"), autoescape=select_autoescape(["html"]))
    d = dt.date.fromisoformat(fecha)
    # rutas de fotos locales relativas a la carpeta del informe
    casi = casi or {p: [] for p in PAISES}
    for lista in list(top.values()) + list(casi.values()):
        for a in lista:
            a.fotos_locales = [os.path.relpath(p, carpeta) for p in a.fotos_locales]
    html = env.get_template("informe.html").render(
        fecha=fecha, fecha_larga=f"{d.day} de {_MESES[d.month - 1]} de {d.year}", f=cfg["filtros"], top=top, paises=PAISES,
        eur=eur, bandera=lambda p: _BANDERAS.get(p, ""), destino=cfg["costes"].get("destino", {}).get("nombre", ""),
        casi=casi, casi_cfg=cfg.get("casi", {}), csv_descartados=f"descartados-{fecha}.csv",
        total_analizados=len(res.analizados), total_vistos=len(res.analizados) + sum(res.descartes.values()),
        portales=res.por_portal, descartes=res.descartes, generado=dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
    )
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"veleros-{fecha}.html"
    ruta.write_text(html, "utf-8")
    (carpeta / "ultimo.html").write_text(html, "utf-8")
    return ruta
