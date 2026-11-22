"""Línea de órdenes.

  python -m veleros ejecutar            búsqueda diaria completa + informe
  python -m veleros ejecutar --ia       igual, con análisis y traducción por Claude
  python -m veleros demo                informe de ejemplo con anuncios ficticios
  python -m veleros probar leboncoin    diagnostica un portal (muestra lo que extrae)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
import webbrowser
from pathlib import Path

import requests
import yaml

from . import parsing
from .filtros import motivo_descarte
from .informe import generar
from .models import Anuncio
from .procesar import casi_por_pais, descargar_fotos, ejecutar, exportar_descartados, exportar_json, mejores_por_pais
from .scrapers import TIPOS, Http

BASE = Path(__file__).resolve().parent.parent


def cargar_config(ruta: Path) -> dict:
    with open(ruta, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _informe(cfg: dict, res, base: Path, fecha: str, abrir: bool) -> Path:
    icfg = cfg.get("informe", {})
    top = mejores_por_pais(res, icfg.get("n_mejores", 15))
    casi = casi_por_pais(res, cfg.get("casi", {}).get("n_por_pais", 5))
    carpeta = base / icfg.get("carpeta", "informes")
    exportar_descartados(res, carpeta / f"descartados-{fecha}.csv")
    if icfg.get("descargar_fotos"):
        s = requests.Session()
        s.headers["User-Agent"] = "Mozilla/5.0"
        for lista in list(top.values()) + list(casi.values()):
            for a in lista:
                descargar_fotos(a, carpeta / "fotos" / f"{a.sitio}-{a.id_sitio}", s, icfg.get("max_fotos", 60))
    exportar_json(top, carpeta / f"veleros-{fecha}.json")
    ruta = generar(res, top, cfg, carpeta, fecha, casi)
    print(f"\nInforme: {ruta}")
    for p, lista in top.items():
        print(f"  {p}: {len(lista)} ofertas" + (f" · mejor: {lista[0].titulo_es or lista[0].titulo} ({lista[0].precio:.0f} €, {lista[0].puntuacion:.0f} pts)" if lista else ""))
    n_casi = sum(len(v) for v in casi.values())
    if n_casi:
        print(f"  Casi (fuera de límites por poco): {n_casi}")
    print(f"  Descartados: {sum(res.descartes.values())} (detalle en descartados-{fecha}.csv)")
    print("  Portales: " + ", ".join(f"{n}={e['encontrados']}{'' if e['estado'] == 'ok' else ' (' + e['estado'][:40] + ')'}" for n, e in res.por_portal.items()))
    if abrir:
        webbrowser.open(ruta.as_uri())
    return ruta


def cmd_ejecutar(args, cfg):
    if args.ia:
        cfg.setdefault("ia", {})["activar"] = True
    if args.sin_traduccion:
        cfg["traduccion"]["motor"] = "ninguno"
    if args.solo:
        elegidos = set(args.solo.split(","))
        for n, s in cfg["sitios"].items():
            s["activo"] = n in elegidos
    fecha = dt.date.today().isoformat()
    res = ejecutar(cfg, BASE, hoy=fecha)
    _informe(cfg, res, BASE, fecha, args.abrir)


def cmd_demo(args, cfg):
    datos = json.loads((BASE / "demo" / "anuncios_demo.json").read_text("utf-8"))
    anuncios = []
    for d in datos:
        d["fotos"] = [str((BASE / "demo" / f).resolve()) if not f.startswith("http") else f for f in d.get("fotos", [])]
        anuncios.append(Anuncio(**d))
    cfg["carpeta_datos"] = "demo/datos"
    cfg["informe"]["carpeta"] = "demo/informe"
    cfg["costes"]["geocodificar_online"] = False
    cfg.setdefault("correo", {})["activar"] = False
    if not args.ia:
        cfg["traduccion"]["motor"] = cfg["traduccion"].get("motor") if args.traducir else "ninguno"
    else:
        cfg.setdefault("ia", {})["activar"] = True
    fecha = dt.date.today().isoformat()
    # fotos locales de la demo: rutas relativas al informe
    res = ejecutar(cfg, BASE, anuncios_entrada=anuncios, hoy=fecha)
    for a in res.analizados + res.casi:
        a.fotos_locales, a.fotos = list(a.fotos), a.fotos
    _informe(cfg, res, BASE, fecha, args.abrir)


def cmd_probar(args, cfg):
    scfg = cfg["sitios"].get(args.portal)
    if not scfg:
        sys.exit(f"Portal desconocido. Disponibles: {', '.join(cfg['sitios'])}")
    scfg = {**scfg, "max_anuncios": args.n}
    sc = TIPOS[scfg.get("tipo", "generico")](args.portal, scfg, Http(cfg.get("red", {})), cfg["filtros"])
    n = 0
    for a in sc.buscar():
        parsing.completar(a)
        n += 1
        motivo = motivo_descarte(a, cfg["filtros"])
        print(f"\n[{n}] {a.titulo[:90]}\n    {a.url}\n    precio={a.precio} eslora={a.eslora_m} año={a.anio} CE={a.ce} "
              f"bandera={a.bandera} fotos={len(a.fotos)} texto={len(a.descripcion)} car.\n    "
              + (f"DESCARTADO: {motivo}" if motivo else "PASA LOS FILTROS"))
    print(f"\n{n} anuncios extraídos de {args.portal}." if n else "\nNo se extrajo ningún anuncio: revise la URL/patrón en config.yaml.")


def cmd_probar_correo(args, cfg):
    from .correo import LectorAlertas
    ccfg = {**cfg.get("correo", {}), "dias_atras": args.dias}
    try:
        lector = LectorAlertas(ccfg, BASE)
    except (FileNotFoundError, ValueError) as e:
        sys.exit(str(e))
    n = 0
    try:
        for a in lector.buscar():
            parsing.completar(a)
            n += 1
            print(f"[{n}] {a.sitio}: {a.titulo[:80]} · {a.precio} € · {a.ubicacion}\n     {a.url}  ({len(a.fotos)} fotos)")
    except Exception as e:  # noqa: BLE001
        sys.exit(f"No se pudo leer el correo: {e}\nRevise servidor, usuario y contraseña de aplicación en correo_privado.yaml.")
    for portal, e in lector.estado.items():
        print(f"{portal}: {e['correos']} correos, {e['encontrados']} anuncios")
    if not lector.estado:
        print(f"Conexión correcta, pero no hay alertas de portales en los últimos {args.dias} días.")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="veleros", description="Buscador diario de veleros de ocasión (ES, FR, NL)")
    ap.add_argument("--config", default=str(BASE / "config.yaml"))
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="orden", required=True)
    e = sub.add_parser("ejecutar", help="búsqueda completa y genera el informe del día")
    e.add_argument("--ia", action="store_true", help="análisis y traducción con Claude")
    e.add_argument("--sin-traduccion", action="store_true")
    e.add_argument("--solo", help="portales separados por comas, p. ej. leboncoin,marktplaats")
    e.add_argument("--abrir", action="store_true", help="abre el informe en el navegador")
    d = sub.add_parser("demo", help="informe de ejemplo con anuncios ficticios (sin conexión)")
    d.add_argument("--ia", action="store_true")
    d.add_argument("--traducir", action="store_true", help="traduce los textos de la demo (necesita Internet)")
    d.add_argument("--abrir", action="store_true")
    p = sub.add_parser("probar", help="diagnostica un portal")
    p.add_argument("portal")
    p.add_argument("-n", type=int, default=5)
    c = sub.add_parser("probar-correo", help="comprueba la lectura de las alertas por correo")
    c.add_argument("--dias", type=int, default=7)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    cfg = cargar_config(Path(args.config))
    {"ejecutar": cmd_ejecutar, "demo": cmd_demo, "probar": cmd_probar, "probar-correo": cmd_probar_correo}[args.orden](args, cfg)
