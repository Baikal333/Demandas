"""Extractores de cada portal.

Los portales cambian su HTML/API con frecuencia y varios usan protección
anti-bots. Cada extractor está escrito de forma defensiva (busca los datos en
JSON incrustado, JSON-LD y HTML) y, si un portal falla, el programa sigue con
los demás e informa en el resumen. Use `python -m veleros probar <portal>`
para diagnosticar uno concreto.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterator
from urllib.parse import urlencode, urljoin, urlparse

from ..models import Anuncio
from ..parsing import parse_eslora, parse_precio
from .base import Bloqueado, Scraper, ficha_generica, next_data, recorrer, sopa

log = logging.getLogger(__name__)


def _completar_desde_ficha(sc: Scraper, a: Anuncio) -> Anuncio:
    """Abre la página del anuncio para obtener descripción completa y todas las fotos."""
    try:
        html = sc.http.get(a.url)
    except Bloqueado as e:
        log.info("%s: ficha bloqueada (%s); se usan los datos del listado.", sc.nombre, e)
        return a
    except Exception as e:  # noqa: BLE001
        log.info("%s: error abriendo %s: %s", sc.nombre, a.url, e)
        return a
    f = ficha_generica(html, a.url)
    if len(f["descripcion"]) > len(a.descripcion):
        a.descripcion = f["descripcion"]
    a.titulo = a.titulo or f["titulo"]
    a.precio = a.precio if a.precio is not None else f["precio"]
    a.eslora_m = a.eslora_m or f["eslora_m"]
    a.anio = a.anio or f["anio"]
    a.ubicacion = a.ubicacion or f["ubicacion"]
    a.caracteristicas = {**f["caracteristicas"], **a.caracteristicas}
    vistos = set(a.fotos)
    a.fotos += [u for u in f["fotos"] if u not in vistos]
    return a


# ======================================================================= genérico
class Generico(Scraper):
    """Portal sin API: recorre páginas de listado, localiza enlaces a anuncios y abre cada ficha.

    Configuración (config.yaml):
      listados: ["https://.../veleros?pagina={pagina}", ...]
      paginas: 3
      patron_enlace: regex de la ruta de los anuncios (si se omite, se deduce)
    """

    _PALABRAS = re.compile(r"velero|vela|barco|voilier|bateau|zeil|boot|jacht|sail|yacht|boat|segel", re.I)

    def enlaces(self, html: str, base: str) -> list[str]:
        soup = sopa(html)
        patron = self.cfg.get("patron_enlace")
        dominio = urlparse(base).netloc
        vistos, salida = set(), []
        for a in soup.find_all("a", href=True):
            url = urljoin(base, a["href"]).split("#")[0]
            u = urlparse(url)
            if u.netloc and u.netloc != dominio:
                continue
            if patron:
                if not re.search(patron, u.path):
                    continue
            else:
                # Heurística: ruta con identificador numérico largo y palabra náutica
                if not (re.search(r"\d{5,}", u.path) and self._PALABRAS.search(u.path)):
                    continue
            if url not in vistos:
                vistos.add(url)
                salida.append(url)
        return salida

    def buscar(self) -> Iterator[Anuncio]:
        n = 0
        for plantilla in self.cfg.get("listados", []):
            for pagina in range(1, self.cfg.get("paginas", 2) + 1):
                url_listado = plantilla.format(pagina=pagina, precio_max=int(self.filtros["precio_max"]),
                                               eslora_min=self.filtros["eslora_min"], eslora_max=self.filtros["eslora_max"])
                html = self.http.get(url_listado)
                urls = self.enlaces(html, url_listado)
                log.info("%s: %d enlaces en %s", self.nombre, len(urls), url_listado)
                if not urls:
                    break
                for url in urls:
                    id_sitio = (re.findall(r"\d{5,}", url) or [url])[-1]
                    a = self.nuevo(id_sitio, url)
                    yield _completar_desde_ficha(self, a)
                    n += 1
                    if n >= self.max_anuncios:
                        return
                if "{pagina}" not in plantilla:
                    break


# ======================================================================= Wallapop (ES)
class Wallapop(Scraper):
    API = "https://api.wallapop.com/api/v3/search"

    def buscar(self) -> Iterator[Anuncio]:
        n = 0
        for termino in self.cfg.get("terminos", ["velero"]):
            params = {
                "keywords": termino, "source": "search_box", "order_by": "newest",
                "min_sale_price": int(self.filtros.get("precio_min", 0)), "max_sale_price": int(self.filtros["precio_max"]),
                "latitude": self.cfg.get("latitud", 40.4168), "longitude": self.cfg.get("longitud", -3.7038),
                "distance_in_km": self.cfg.get("distancia_km", 1500),
            }
            siguiente = None
            for _ in range(self.cfg.get("paginas", 3)):
                q = {**params, **({"next_page": siguiente} if siguiente else {})}
                datos = self.http.get(self.API + "?" + urlencode(q), json_resp=True,
                                      headers={"X-DeviceOS": "0", "Accept": "application/json"})
                items = [x for x in recorrer(datos) if isinstance(x, dict) and "web_slug" in x and "title" in x]
                for it in items:
                    precio = it.get("price")
                    precio = precio.get("amount") if isinstance(precio, dict) else precio
                    texto = f"{it.get('title', '')} {it.get('description', '')}"
                    if not self.pasa_prefiltro(precio, parse_eslora(texto)):
                        continue
                    fotos = []
                    for img in it.get("images") or []:
                        urls = img.get("urls") or {}
                        fotos.append(urls.get("big") or urls.get("medium") or img.get("original") or "")
                    loc = it.get("location") or {}
                    a = self.nuevo(it.get("id"), f"https://es.wallapop.com/item/{it['web_slug']}",
                                   titulo=it.get("title", ""), descripcion=it.get("description", ""), precio=precio,
                                   ubicacion=", ".join(x for x in (loc.get("city"), loc.get("region")) if x),
                                   fotos=[f for f in fotos if f], fecha_publicacion=str(it.get("created_at", "")))
                    yield a
                    n += 1
                    if n >= self.max_anuncios:
                        return
                siguiente = (datos.get("meta") or {}).get("next_page") if isinstance(datos, dict) else None
                if not siguiente or not items:
                    break


# ======================================================================= Milanuncios (ES)
class Milanuncios(Scraper):
    """Milanuncios incrusta los anuncios en `window.__INITIAL_PROPS__` (JSON escapado)."""

    def _json_incrustado(self, html: str) -> Any:
        m = re.search(r"window\.__INITIAL_PROPS__\s*=\s*JSON\.parse\((\".*?\")\)\s*;?\s*</script>", html, re.S)
        if m:
            try:
                return json.loads(json.loads(m.group(1)))
            except ValueError:
                pass
        return next_data(html)

    def buscar(self) -> Iterator[Anuncio]:
        n = 0
        for plantilla in self.cfg.get("listados", []):
            for pagina in range(1, self.cfg.get("paginas", 3) + 1):
                url = plantilla.format(pagina=pagina, precio_max=int(self.filtros["precio_max"]))
                html = self.http.get(url)
                datos = self._json_incrustado(html)
                ads = [x for x in recorrer(datos) if isinstance(x, dict) and "url" in x and ("title" in x or "titulo" in x)
                       and ("price" in x or "precio" in x)] if datos else []
                if not ads:  # plan B: enlaces del HTML
                    for url_ad in Generico(self.nombre, {**self.cfg, "patron_enlace": r"-\d{6,}\.htm"}, self.http, self.filtros).enlaces(html, url):
                        yield _completar_desde_ficha(self, self.nuevo(re.findall(r"\d{6,}", url_ad)[-1], url_ad))
                        n += 1
                        if n >= self.max_anuncios:
                            return
                    continue
                for ad in ads:
                    precio = ad.get("price") or ad.get("precio")
                    if isinstance(precio, dict):
                        precio = (precio.get("cashPrice") or {}).get("value") or precio.get("value") or precio.get("amount")
                    precio = parse_precio(str(precio)) if precio is not None else None
                    titulo = ad.get("title") or ad.get("titulo") or ""
                    desc = ad.get("description") or ad.get("descripcion") or ""
                    if not self.pasa_prefiltro(precio, parse_eslora(f"{titulo} {desc}")):
                        continue
                    fotos = []
                    for f in ad.get("images") or ad.get("photos") or []:
                        fotos.append(f if isinstance(f, str) else f.get("src") or f.get("url") or "")
                    a = self.nuevo(ad.get("id") or re.findall(r"\d{6,}", ad["url"])[-1], urljoin("https://www.milanuncios.com", ad["url"]),
                                   titulo=titulo, descripcion=desc, precio=precio,
                                   ubicacion=str((ad.get("location") or {}).get("city", {}).get("name", "") if isinstance(ad.get("location"), dict) else ad.get("location") or ""),
                                   fotos=[f for f in fotos if f])
                    yield _completar_desde_ficha(self, a) if self.cfg.get("abrir_fichas", True) else a
                    n += 1
                    if n >= self.max_anuncios:
                        return


# ======================================================================= Leboncoin (FR)
class Leboncoin(Scraper):
    """Leboncoin: página de resultados Next.js con los anuncios en __NEXT_DATA__."""

    def buscar(self) -> Iterator[Anuncio]:
        n = 0
        for termino in self.cfg.get("terminos", ["voilier"]):
            for pagina in range(1, self.cfg.get("paginas", 3) + 1):
                params = {"category": self.cfg.get("categoria", "7"), "text": termino,
                          "price": f"{int(self.filtros.get('precio_min', 0))}-{int(self.filtros['precio_max'])}", "page": pagina}
                url = "https://www.leboncoin.fr/recherche?" + urlencode(params)
                html = self.http.get(url)
                datos = next_data(html)
                ads = [x for x in recorrer(datos) if isinstance(x, dict) and "list_id" in x and "subject" in x] if datos else []
                if not ads:
                    break
                for ad in ads:
                    precio = (ad.get("price") or [None])[0] if isinstance(ad.get("price"), list) else ad.get("price")
                    attrs = {at.get("key_label") or at.get("key"): at.get("value_label") or at.get("value")
                             for at in ad.get("attributes") or [] if isinstance(at, dict)}
                    texto = f"{ad.get('subject', '')} {ad.get('body', '')} " + " ".join(f"{k} {v}" for k, v in attrs.items())
                    if not self.pasa_prefiltro(precio, parse_eslora(texto)):
                        continue
                    imgs = ad.get("images") or {}
                    fotos = imgs.get("urls_large") or imgs.get("urls") or ([imgs["thumb_url"]] if imgs.get("thumb_url") else [])
                    loc = ad.get("location") or {}
                    a = self.nuevo(ad["list_id"], ad.get("url") or f"https://www.leboncoin.fr/ad/nautisme/{ad['list_id']}",
                                   titulo=ad.get("subject", ""), descripcion=ad.get("body", ""), precio=precio,
                                   ubicacion=", ".join(x for x in (loc.get("city"), loc.get("department_name"), loc.get("region_name")) if x),
                                   fotos=list(fotos), caracteristicas={k: str(v) for k, v in attrs.items() if k},
                                   vendedor_profesional=(ad.get("owner") or {}).get("type") == "pro",
                                   fecha_publicacion=ad.get("first_publication_date"))
                    yield a
                    n += 1
                    if n >= self.max_anuncios:
                        return


# ======================================================================= Marktplaats (NL)
class Marktplaats(Scraper):
    API = "https://www.marktplaats.nl/lrp/api/search"

    def buscar(self) -> Iterator[Anuncio]:
        n = 0
        for termino in self.cfg.get("terminos", ["zeilboot"]):
            for pagina in range(self.cfg.get("paginas", 3)):
                params = {"query": termino, "limit": 100, "offset": pagina * 100, "sortBy": "SORT_INDEX", "sortOrder": "DECREASING",
                          "attributeRanges[]": f"PriceCents:{int(self.filtros.get('precio_min', 0)) * 100}:{int(self.filtros['precio_max']) * 100}"}
                if self.cfg.get("l1_categoria"):
                    params["l1CategoryId"] = self.cfg["l1_categoria"]
                datos = self.http.get(self.API + "?" + urlencode(params), json_resp=True, headers={"Accept": "application/json"})
                lst = datos.get("listings") or []
                if not lst:
                    break
                for it in lst:
                    pi = it.get("priceInfo") or {}
                    precio = pi.get("priceCents") / 100 if pi.get("priceCents") else None
                    attrs = {at.get("key"): at.get("value") for at in it.get("attributes") or [] if isinstance(at, dict)}
                    texto = f"{it.get('title', '')} {it.get('description', '')} {attrs}"
                    if not self.pasa_prefiltro(precio, parse_eslora(texto)):
                        continue
                    fotos = [p.get("extraExtraLargeUrl") or p.get("largeUrl") or p.get("mediumUrl") for p in it.get("pictures") or []]
                    fotos = [("https:" + f if f and f.startswith("//") else f) for f in fotos if f]
                    loc = it.get("location") or {}
                    a = self.nuevo(it.get("itemId"), urljoin("https://www.marktplaats.nl", it.get("vipUrl", "")),
                                   titulo=it.get("title", ""), descripcion=it.get("description", ""), precio=precio,
                                   ubicacion=loc.get("cityName", ""), fotos=fotos,
                                   caracteristicas={str(k): str(v) for k, v in attrs.items() if k},
                                   vendedor_profesional=bool((it.get("sellerInformation") or {}).get("showWebsiteUrl")) or None,
                                   fecha_publicacion=it.get("date"))
                    yield _completar_desde_ficha(self, a) if self.cfg.get("abrir_fichas", True) else a
                    n += 1
                    if n >= self.max_anuncios:
                        return


TIPOS = {
    "generico": Generico,
    "wallapop": Wallapop,
    "milanuncios": Milanuncios,
    "leboncoin": Leboncoin,
    "marktplaats": Marktplaats,
}
