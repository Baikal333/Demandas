"""Cliente HTTP educado y utilidades comunes de extracción."""
from __future__ import annotations

import json
import logging
import random
import re
import time
import urllib.robotparser
from typing import Any, Iterable, Iterator
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..models import Anuncio
from ..parsing import parse_anio, parse_eslora, parse_precio

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")


class Bloqueado(Exception):
    """El portal ha bloqueado la petición (anti-bot, captcha, 403...)."""


class Http:
    def __init__(self, cfg: dict):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": cfg.get("user_agent") or UA,
            "Accept-Language": "es-ES,es;q=0.9,fr;q=0.8,nl;q=0.7,en;q=0.6",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        })
        self.pausa = tuple(cfg.get("pausa_segundos", [2, 5]))
        self.respetar_robots = cfg.get("respetar_robots", True)
        self.timeout = cfg.get("timeout", 30)
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._ultima = 0.0

    def _permitido(self, url: str) -> bool:
        if not self.respetar_robots:
            return True
        base = "{0.scheme}://{0.netloc}".format(urlparse(url))
        if base not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.s.get(base + "/robots.txt", timeout=self.timeout)
                rp.parse(r.text.splitlines() if r.ok else [])
                self._robots[base] = rp
            except requests.RequestException:
                self._robots[base] = None
        rp = self._robots[base]
        return True if rp is None else rp.can_fetch(self.s.headers["User-Agent"], url)

    def get(self, url: str, *, json_resp: bool = False, **kw) -> Any:
        if not self._permitido(url):
            raise Bloqueado(f"robots.txt no permite {url}")
        metodo = kw.pop("method", "GET")
        espera = random.uniform(*self.pausa) - (time.time() - self._ultima)
        if espera > 0:
            time.sleep(espera)
        for intento in range(3):
            try:
                self._ultima = time.time()
                r = self.s.request(metodo, url, timeout=self.timeout, **kw)
            except requests.RequestException as e:
                if intento == 2:
                    raise
                log.debug("Reintento %s por %s", url, e)
                time.sleep(3 * (intento + 1))
                continue
            pequena = len(r.text) < 15000
            if r.status_code in (401, 403, 429) or (pequena and re.search(r"captcha|are you a robot|access denied", r.text, re.I)):
                if r.status_code == 429 and intento < 2:
                    time.sleep(20 * (intento + 1))
                    continue
                raise Bloqueado(f"{r.status_code} en {url} (protección anti-bots)")
            r.raise_for_status()
            return r.json() if json_resp else r.text
        raise Bloqueado(url)


class Scraper:
    """Clase base: cada portal implementa `buscar()` que produce anuncios."""

    nombre = "base"

    def __init__(self, nombre: str, cfg: dict, http: Http, filtros: dict):
        self.nombre = nombre
        self.cfg = cfg
        self.http = http
        self.filtros = filtros
        self.pais = cfg["pais"]
        self.idioma = cfg.get("idioma")
        self.max_anuncios = cfg.get("max_anuncios", 150)

    def buscar(self) -> Iterator[Anuncio]:  # pragma: no cover - interfaz
        raise NotImplementedError

    def nuevo(self, id_sitio: str, url: str, **kw) -> Anuncio:
        return Anuncio(sitio=self.nombre, pais=self.pais, id_sitio=str(id_sitio), url=url, idioma=self.idioma, **kw)

    # Prefiltro barato con los datos del listado, antes de abrir la ficha
    def pasa_prefiltro(self, precio: float | None, eslora: float | None) -> bool:
        f = self.filtros
        if precio is not None and precio > f["precio_max"]:
            return False
        if precio is not None and precio < f.get("precio_min", 0):
            return False
        if eslora is not None and not (f["eslora_min"] - 0.05 <= eslora <= f["eslora_max"] + 0.05):
            return False
        return True


# ------------------------------------------------------------------ helpers HTML
def sopa(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def json_ld(soup: BeautifulSoup) -> list[dict]:
    salida: list[dict] = []
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(s.string or s.get_text() or "")
        except ValueError:
            continue
        pila = d if isinstance(d, list) else [d]
        while pila:
            x = pila.pop()
            if isinstance(x, dict):
                if "@graph" in x:
                    pila.extend(x["@graph"])
                salida.append(x)
            elif isinstance(x, list):
                pila.extend(x)
    return salida


def next_data(html: str) -> dict | None:
    m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except ValueError:
            return None
    return None


def recorrer(obj: Any) -> Iterable[Any]:
    """Recorre recursivamente un JSON."""
    pila = [obj]
    while pila:
        x = pila.pop()
        yield x
        if isinstance(x, dict):
            pila.extend(x.values())
        elif isinstance(x, list):
            pila.extend(x)


_IMG_EXT = re.compile(r"\.(?:jpe?g|png|webp)(?:\?|$)", re.I)
_IMG_RUIDO = re.compile(r"logo|icon|sprite|avatar|placeholder|banner|flag|pixel|badge|favicon|/ads?/|doubleclick|captcha|thumb_?\d{2}x", re.I)


def fotos_de_html(soup: BeautifulSoup, base_url: str, extra: Iterable[str] = ()) -> list[str]:
    """Todas las fotos del anuncio (galería), sin logos ni iconos y sin duplicados."""
    urls: list[str] = list(extra)
    for m in soup.find_all("meta", attrs={"property": "og:image"}):
        urls.append(m.get("content", ""))
    for img in soup.find_all(["img", "source", "a"]):
        for attr in ("data-src", "data-lazy", "data-original", "data-large", "data-full", "data-zoom-image", "href", "src", "srcset", "data-srcset"):
            v = img.get(attr)
            if not v:
                continue
            if "srcset" in attr:
                v = v.split(",")[-1].strip().split(" ")[0]
            if _IMG_EXT.search(v) and not _IMG_RUIDO.search(v):
                urls.append(v)
    vistos, salida = set(), []
    for u in urls:
        if not u or u.startswith("data:"):
            continue
        u = urljoin(base_url, u.strip())
        # misma foto en distintos tamaños: normalizar quitando parámetros de tamaño
        k = re.sub(r"(?:[?&](?:w|h|width|height|size|rule|resize)=[^&]*)|(?:_\d{2,4}x\d{2,4})|(?:/\d{2,4}x\d{2,4}/)", "", u)
        if k not in vistos:
            vistos.add(k)
            salida.append(u)
    return salida


_ETIQUETAS = re.compile(
    r"^(eslora|manga|calado|a[nñ]o|marca|modelo|astillero|motor|combustible|ubicaci[oó]n|bandera|material|"
    r"longueur|largeur|tirant|ann[ée]e|chantier|mod[eè]le|moteur|pavillon|localisation|lieu|"
    r"lengte|breedte|diepgang|bouwjaar|werf|merk|ligplaats|locatie|vlag|"
    r"length|beam|draft|year|builder|make|model|engine|location|flag|hull)", re.I)


def caracteristicas_de_html(soup: BeautifulSoup) -> dict[str, str]:
    """Pares etiqueta/valor de fichas técnicas (tablas, dl, listas)."""
    datos: dict[str, str] = {}
    for dt in soup.find_all(["dt", "th"]):
        dd = dt.find_next_sibling(["dd", "td"])
        if dd:
            k, v = dt.get_text(" ", strip=True), dd.get_text(" ", strip=True)
            if k and v and len(k) < 40 and len(v) < 120:
                datos[k] = v
    for li in soup.find_all(["li", "tr", "div"], limit=4000):
        hijos = [c for c in li.find_all(recursive=False)]
        if len(hijos) == 2:
            k, v = hijos[0].get_text(" ", strip=True), hijos[1].get_text(" ", strip=True)
            if k and v and _ETIQUETAS.match(k) and len(k) < 40 and len(v) < 120:
                datos.setdefault(k.rstrip(":"), v)
    return datos


def ficha_generica(html: str, url: str) -> dict[str, Any]:
    """Extrae título, descripción, precio, fotos y ficha técnica de cualquier página de anuncio."""
    soup = sopa(html)
    d: dict[str, Any] = {"titulo": "", "descripcion": "", "precio": None, "fotos": [], "caracteristicas": {}, "ubicacion": ""}
    extra_fotos: list[str] = []
    for x in json_ld(soup):
        tipo = x.get("@type")
        tipos = tipo if isinstance(tipo, list) else [tipo]
        if any(t in ("Product", "Vehicle", "Boat", "Offer", "Car", "IndividualProduct") for t in tipos):
            d["titulo"] = d["titulo"] or x.get("name", "")
            d["descripcion"] = d["descripcion"] or x.get("description", "")
            img = x.get("image")
            if isinstance(img, str):
                extra_fotos.append(img)
            elif isinstance(img, list):
                extra_fotos += [i if isinstance(i, str) else i.get("url", "") for i in img]
            elif isinstance(img, dict):
                extra_fotos.append(img.get("url", ""))
            ofertas = x.get("offers")
            if isinstance(ofertas, list) and ofertas:
                ofertas = ofertas[0]
            if isinstance(ofertas, dict) and d["precio"] is None:
                d["precio"] = parse_precio(str(ofertas.get("price", ""))) if ofertas.get("price") else None
                d["moneda"] = ofertas.get("priceCurrency", "EUR")
    if not d["titulo"]:
        og = soup.find("meta", attrs={"property": "og:title"})
        d["titulo"] = og["content"] if og and og.get("content") else (soup.title.get_text(strip=True) if soup.title else "")
    if not d["descripcion"] or len(d["descripcion"]) < 200:
        candidatos = []
        for sel in ['[itemprop="description"]', ".description", "#description", ".ad-description", ".descripcion",
                    '[class*="escription"]', '[class*="Description"]', '[data-testid*="description"]', "article"]:
            for el in soup.select(sel)[:3]:
                t = el.get_text("\n", strip=True)
                if len(t) > 80:
                    candidatos.append(t)
        if candidatos:
            mejor = max(candidatos, key=len)
            if len(mejor) > len(d["descripcion"]):
                d["descripcion"] = mejor[:8000]
    if not d["descripcion"]:
        og = soup.find("meta", attrs={"property": "og:description"}) or soup.find("meta", attrs={"name": "description"})
        d["descripcion"] = og.get("content", "") if og else ""
    d["caracteristicas"] = caracteristicas_de_html(soup)
    if d["precio"] is None:
        for sel in ['[itemprop="price"]', ".price", ".precio", ".prix", ".prijs", '[class*="rice"]', '[data-testid*="price"]']:
            el = soup.select_one(sel)
            if el:
                d["precio"] = parse_precio(el.get("content") or el.get_text(" ", strip=True))
                if d["precio"]:
                    break
    for k, v in d["caracteristicas"].items():
        if re.match(r"(ubicaci|localisation|lieu|ligplaats|locatie|location)", k, re.I):
            d["ubicacion"] = v
    d["fotos"] = fotos_de_html(soup, url, extra_fotos)
    texto = d["titulo"] + "\n" + " ".join(f"{k}: {v}" for k, v in d["caracteristicas"].items())
    d["eslora_m"] = parse_eslora(texto) or parse_eslora(d["descripcion"])
    d["anio"] = parse_anio(texto) or None
    return d
