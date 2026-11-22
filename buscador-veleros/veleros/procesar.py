"""Proceso diario completo: buscar → filtrar → traducir → analizar → costes → clasificar → informe."""
from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
import logging
from pathlib import Path

import requests

from . import analisis, costes, parsing
from .db import BaseDatos
from .filtros import motivo_descarte
from .models import Anuncio
from .scrapers import TIPOS, Bloqueado, Http
from .traduccion import Traductor

log = logging.getLogger(__name__)
PAISES = {"ES": "España", "FR": "Francia", "NL": "Países Bajos"}


class Resultado:
    def __init__(self):
        self.analizados: list[Anuncio] = []
        self.descartes: collections.Counter = collections.Counter()
        self.por_portal: dict[str, dict] = {}
        self.inicio = dt.datetime.now()


def _clave_duplicado(a: Anuncio) -> str:
    t = parsing.normalizar(a.titulo)
    t = "".join(c for c in t if c.isalnum())[:40]
    return f"{t}|{round(a.precio or 0, -1)}|{a.eslora_m}"


def _agrupar_motivo(m: str) -> str:
    if m.startswith("eslora "):
        return "eslora fuera de rango"
    if m.startswith("anterior a"):
        return m.split(" (")[0] + " sin marcado CE acreditado"
    if m.startswith("modelo muy antiguo"):
        return "modelo muy antiguo"
    if m.startswith("no es un velero"):
        return "no es un velero completo (motora, neumática, solo accesorios...)"
    return m


def descargar_fotos(a: Anuncio, carpeta: Path, http: requests.Session, maximo: int) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    locales = []
    for i, url in enumerate(a.fotos[:maximo]):
        ext = (url.split("?")[0].rsplit(".", 1)[-1] or "jpg").lower()
        ext = ext if ext in ("jpg", "jpeg", "png", "webp") else "jpg"
        nombre = f"{hashlib.sha1(url.encode()).hexdigest()[:16]}.{ext}"
        destino = carpeta / nombre
        if not destino.exists():
            try:
                r = http.get(url, timeout=30)
                if not r.ok or not r.headers.get("content-type", "image").startswith("image"):
                    continue
                destino.write_bytes(r.content)
            except requests.RequestException:
                continue
        locales.append(str(destino))
    a.fotos_locales = locales


def analizar_anuncio(a: Anuncio, cfg: dict, traductor: Traductor, ia, geo: costes.Geocodificador) -> None:
    usado_ia = False
    if ia is not None:
        usado_ia = ia.analizar(a)
    if not usado_ia:
        a.titulo_es = traductor.traducir(a.titulo, a.idioma)
        a.descripcion_es = traductor.traducir(a.descripcion, a.idioma)
    analisis.detectar_rasgos(a)
    if usado_ia:
        from .ia import fusionar_rasgos
        fusionar_rasgos(a)
    if not a.resumen_es:
        a.resumen_es = analisis.resumen(a)
    a.costes = costes.estimar(a, geo, cfg)
    for e in a.costes["escenarios"]:
        for aviso in e["avisos"]:
            if aviso not in a.avisos:
                a.avisos.append(aviso)


def ejecutar(cfg: dict, base: Path, anuncios_entrada: list[Anuncio] | None = None, hoy: str | None = None) -> Resultado:
    hoy = hoy or dt.date.today().isoformat()
    datos_dir = base / cfg.get("carpeta_datos", "datos")
    db = BaseDatos(datos_dir / "veleros.db")
    res = Resultado()
    filtros = cfg["filtros"]

    motor = cfg.get("traduccion", {}).get("motor", "google")
    traductor = Traductor("ninguno" if motor == "claude" else motor, db)
    ia = None
    if motor == "claude" or cfg.get("ia", {}).get("activar"):
        try:
            from .ia import AnalizadorClaude
            ia = AnalizadorClaude(cfg.get("ia", {}), db)
        except Exception as e:  # noqa: BLE001
            log.warning("No se pudo iniciar el análisis con Claude (%s). Se usa traducción gratuita y palabras clave.", e)
            traductor = Traductor("google", db)
    geo = costes.Geocodificador(cfg["costes"], datos_dir / "geocache.json")
    http = Http(cfg.get("red", {}))

    def fuentes():
        if anuncios_entrada is not None:
            res.por_portal["demo"] = {"estado": "ok", "encontrados": len(anuncios_entrada)}
            yield from anuncios_entrada
            return
        for nombre, scfg in cfg["sitios"].items():
            if not scfg.get("activo", True):
                continue
            clase = TIPOS.get(scfg.get("tipo", "generico"))
            if clase is None:
                log.error("Tipo de portal desconocido: %s", scfg.get("tipo"))
                continue
            estado = {"estado": "ok", "encontrados": 0}
            res.por_portal[nombre] = estado
            log.info("== %s (%s) ==", nombre, scfg["pais"])
            try:
                for a in clase(nombre, scfg, http, filtros).buscar():
                    estado["encontrados"] += 1
                    yield a
            except Bloqueado as e:
                estado["estado"] = f"bloqueado: {e}"
                log.warning("%s bloqueado: %s", nombre, e)
            except Exception as e:  # noqa: BLE001 - un portal roto no debe parar el resto
                estado["estado"] = f"error: {type(e).__name__}: {e}"
                log.exception("Error en %s", nombre)

    vistos: set[str] = set()
    for a in fuentes():
        parsing.completar(a)
        motivo = motivo_descarte(a, filtros)
        if motivo:
            res.descartes[_agrupar_motivo(motivo)] += 1
            continue
        clave = _clave_duplicado(a)
        if clave in vistos:
            res.descartes["duplicado en otro portal"] += 1
            continue
        vistos.add(clave)
        try:
            analizar_anuncio(a, cfg, traductor, ia, geo)
        except Exception:  # noqa: BLE001
            log.exception("Error analizando %s", a.url)
            continue
        a.nuevo, precio_ant = db.registrar(a, hoy)
        if precio_ant and a.precio and a.precio < precio_ant:
            a.avisos.insert(0, f"Ha bajado de precio: antes {precio_ant:,.0f} €".replace(",", "."))
            a.puntos_fuertes.append(analisis.Rasgo("bajada", "Bajada de precio reciente", 3, f"{precio_ant:.0f} € → {a.precio:.0f} €"))
        analisis.puntuar(a, cfg)
        db.registrar(a, hoy)
        res.analizados.append(a)
    return res


def mejores_por_pais(res: Resultado, n: int) -> dict[str, list[Anuncio]]:
    grupos: dict[str, list[Anuncio]] = {p: [] for p in PAISES}
    for a in res.analizados:
        grupos.setdefault(a.pais, []).append(a)
    return {p: sorted(lst, key=lambda a: (-a.puntuacion, a.costes.get("mejor_total") or 1e9))[:n] for p, lst in grupos.items()}


def exportar_json(top: dict[str, list[Anuncio]], ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({p: [a.to_dict() for a in lst] for p, lst in top.items()}, ensure_ascii=False, indent=1), "utf-8")
