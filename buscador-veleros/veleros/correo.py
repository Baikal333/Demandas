"""Lectura de las alertas por correo de los portales (Leboncoin, Marktplaats, Youboat...).

Los portales que bloquean las búsquedas automáticas permiten guardar una
búsqueda y recibir cada día un correo con los anuncios nuevos. Este módulo se
conecta al buzón por IMAP en modo SOLO LECTURA (no borra, no mueve y no marca
como leído ningún correo), localiza esos avisos y extrae de cada uno los
anuncios: enlace, título, precio, foto y, si aparece, la población.
"""
from __future__ import annotations

import datetime as dt
import email
import imaplib
import logging
import re
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parseaddr
from pathlib import Path
from typing import Callable, Iterator
from urllib.parse import urlparse

import requests
import yaml
from bs4 import BeautifulSoup

from .models import Anuncio
from .parsing import parse_precio

log = logging.getLogger(__name__)

# remitente (dominio) -> portal, país, idioma, dominio de los anuncios
PORTALES_ALERTA = {
    "leboncoin": {"pais": "FR", "idioma": "fr", "dominios": ["leboncoin.fr"]},
    "marktplaats": {"pais": "NL", "idioma": "nl", "dominios": ["marktplaats.nl"]},
    "youboat": {"pais": "FR", "idioma": "fr", "dominios": ["youboat.com", "youboat.fr"]},
    "botentekoop": {"pais": "NL", "idioma": "nl", "dominios": ["botentekoop.nl"]},
    "bandofboats": {"pais": "FR", "idioma": "fr", "dominios": ["bandofboats.com"]},
    "boat24": {"pais": None, "idioma": None, "dominios": ["boat24.com", "boat24.ch"]},
    "milanuncios": {"pais": "ES", "idioma": "es", "dominios": ["milanuncios.com"]},
    "cosasdebarcos": {"pais": "ES", "idioma": "es", "dominios": ["cosasdebarcos.com"]},
}
_CP = re.compile(r"\b\d{5}\b|\b\d{4}\s?[A-Z]{2}\b")
_PAIS_URL = {"/fr/": ("FR", "fr"), "/nl/": ("NL", "nl"), "/es/": ("ES", "es")}


def cargar_credenciales(base: Path, cfg: dict) -> dict:
    """Lee el archivo privado con usuario y contraseña (no se sube a GitHub)."""
    ruta = base / cfg.get("archivo_credenciales", "correo_privado.yaml")
    if not ruta.exists():
        raise FileNotFoundError(
            f"Falta {ruta.name}. Copie correo_privado.ejemplo.yaml como {ruta.name} y rellene su correo y contraseña de aplicación.")
    datos = yaml.safe_load(ruta.read_text("utf-8")) or {}
    for campo in ("servidor", "usuario", "contrasena"):
        if not datos.get(campo):
            raise ValueError(f"En {ruta.name} falta el campo '{campo}'.")
    return datos


def _texto_cabecera(v: str | None) -> str:
    try:
        return str(make_header(decode_header(v or "")))
    except Exception:  # noqa: BLE001
        return v or ""


def _html_del_mensaje(msg: Message) -> str:
    partes_html, partes_txt = [], []
    for parte in msg.walk():
        tipo = parte.get_content_type()
        if parte.get_content_maintype() == "multipart" or parte.get("Content-Disposition", "").startswith("attachment"):
            continue
        try:
            contenido = parte.get_payload(decode=True)
            if contenido is None:
                continue
            texto = contenido.decode(parte.get_content_charset() or "utf-8", errors="replace")
        except (LookupError, AttributeError):
            continue
        (partes_html if tipo == "text/html" else partes_txt if tipo == "text/plain" else []).append(texto)
    if partes_html:
        return "\n".join(partes_html)
    # sin HTML: convertir texto plano con enlaces
    txt = "\n".join(partes_txt)
    return "<br>".join(re.sub(r"(https?://\S+)", r'<a href="\1">\1</a>', linea) for linea in txt.splitlines())


def portal_del_remitente(remitente: str, asunto: str, portales: dict) -> str | None:
    dominio = parseaddr(remitente)[1].lower().rsplit("@", 1)[-1]
    for nombre, p in portales.items():
        if any(d.split(".")[0] in dominio for d in p["dominios"]) or nombre in dominio:
            return nombre
    texto = (remitente + " " + asunto).lower()
    for nombre in portales:
        if nombre in texto:
            return nombre
    return None


def _resolver_redireccion(url: str, sesion: requests.Session) -> str:
    """Sigue los enlaces de seguimiento del correo hasta la URL real del anuncio."""
    try:
        r = sesion.get(url, allow_redirects=True, timeout=15, stream=True)
        final = r.url
        r.close()
        return final
    except requests.RequestException:
        return url


def _bloque(a) -> object:
    """Sube por el HTML hasta el bloque (celda/tabla/div) que contiene precio y no es enorme."""
    nodo = a
    for _ in range(8):
        padre = nodo.parent
        if padre is None or padre.name in ("body", "html", "[document]"):
            break
        texto = padre.get_text(" ", strip=True)
        if len(texto) > 600:
            break
        nodo = padre
        if parse_precio(texto) is not None and len(texto) > 15:
            return nodo
    return nodo


def extraer_anuncios(html: str, portal: str, portales: dict,
                     resolver: Callable[[str], str] | None = None) -> list[Anuncio]:
    """Extrae los anuncios de un correo de alerta."""
    p = portales[portal]
    soup = BeautifulSoup(html, "lxml")
    vistos: dict[str, Anuncio] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href.startswith("http"):
            continue
        bloque = _bloque(a)
        texto_bloque = bloque.get_text("\n", strip=True)
        precio = parse_precio(texto_bloque)
        tiene_img = a.find("img") is not None
        if precio is None and not tiene_img:
            continue
        if re.search(r"unsubscribe|desinscri|afmeld|uitschrijv|desuscrib|baja|preferen|instellingen|parametres|privacy|aide|help|contact|app-?store|google\.com/store|facebook|instagram|twitter",
                     href + " " + a.get_text(" ", strip=True), re.I):
            continue
        url = href
        if not any(d in urlparse(url).netloc for d in p["dominios"]) or not re.search(r"\d{5,}", url):
            url = resolver(href) if resolver else href
        if not any(d in urlparse(url).netloc for d in p["dominios"]):
            continue
        ids = re.findall(r"\d{5,}", urlparse(url).path)
        if not ids:
            continue
        id_sitio = ids[-1]
        url = url.split("?")[0] if portal not in ("boat24",) else url
        lineas = [l for l in texto_bloque.split("\n") if l.strip()]
        titulo = a.get_text(" ", strip=True)
        if not titulo or parse_precio(titulo) is not None or len(titulo) < 4:
            img = bloque.find("img", alt=True)
            titulo = (img["alt"] if img and len(img.get("alt", "")) > 3 else "") or next(
                (l for l in lineas if parse_precio(l) is None and len(l) > 4), "")
        ubicacion = next((l for l in lineas if _CP.search(l) and parse_precio(l) is None and l != titulo), "")
        fotos = [i["src"] for i in bloque.find_all("img", src=True)
                 if i["src"].startswith("http") and not re.search(r"logo|icon|pixel|spacer|tracking|open\?|badge", i["src"], re.I)
                 and not (i.get("width") and str(i.get("width")).isdigit() and int(i["width"]) < 60)]
        pais, idioma = p["pais"], p["idioma"]
        if pais is None:
            pais, idioma = next((v for k, v in _PAIS_URL.items() if k in url), ("FR", "fr"))
        if id_sitio in vistos:
            an = vistos[id_sitio]
            an.titulo = an.titulo or titulo
            an.precio = an.precio if an.precio is not None else precio
            an.fotos += [f for f in fotos if f not in an.fotos]
            continue
        vistos[id_sitio] = Anuncio(sitio=portal, pais=pais, id_sitio=id_sitio, url=url, titulo=titulo, precio=precio,
                                   descripcion=" · ".join(lineas)[:1000], ubicacion=ubicacion, fotos=fotos,
                                   idioma=idioma, origen="alerta")
    return list(vistos.values())


class LectorAlertas:
    def __init__(self, cfg: dict, base: Path):
        self.cfg = cfg
        self.cred = cargar_credenciales(base, cfg)
        self.portales = {k: v for k, v in PORTALES_ALERTA.items() if k in cfg.get("portales", PORTALES_ALERTA.keys())}
        self.sesion = requests.Session()
        self.sesion.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
        self.estado: dict[str, dict] = {}

    def _mensajes(self) -> Iterator[Message]:
        desde = (dt.date.today() - dt.timedelta(days=self.cfg.get("dias_atras", 2))).strftime("%d-%b-%Y")
        im = imaplib.IMAP4_SSL(self.cred["servidor"], int(self.cred.get("puerto", 993)))
        try:
            im.login(self.cred["usuario"], self.cred["contrasena"])
            for carpeta in self.cred.get("carpetas", ["INBOX"]):
                tipo, _ = im.select(f'"{carpeta}"', readonly=True)       # solo lectura
                if tipo != "OK":
                    log.warning("No existe la carpeta de correo '%s'", carpeta)
                    continue
                tipo, datos = im.search(None, f"(SINCE {desde})")
                ids = datos[0].split() if tipo == "OK" and datos and datos[0] else []
                log.info("Correo: %d mensajes desde %s en %s", len(ids), desde, carpeta)
                for num in ids:
                    tipo, partes = im.fetch(num, "(BODY.PEEK[])")              # PEEK: no lo marca como leído
                    if tipo == "OK" and partes and isinstance(partes[0], tuple):
                        yield email.message_from_bytes(partes[0][1])
        finally:
            try:
                im.logout()
            except Exception:  # noqa: BLE001
                pass

    def buscar(self) -> Iterator[Anuncio]:
        vistos: set[str] = set()
        for msg in self._mensajes():
            remitente, asunto = _texto_cabecera(msg.get("From")), _texto_cabecera(msg.get("Subject"))
            portal = portal_del_remitente(remitente, asunto, self.portales)
            if not portal:
                continue
            est = self.estado.setdefault(f"correo-{portal}", {"estado": "ok", "encontrados": 0, "correos": 0})
            est["correos"] += 1
            anuncios = extraer_anuncios(_html_del_mensaje(msg), portal, self.portales,
                                        resolver=lambda u: _resolver_redireccion(u, self.sesion))
            log.info("Alerta de %s («%s»): %d anuncios", portal, asunto[:60], len(anuncios))
            for a in anuncios:
                if a.id in vistos:
                    continue
                vistos.add(a.id)
                est["encontrados"] += 1
                yield a
