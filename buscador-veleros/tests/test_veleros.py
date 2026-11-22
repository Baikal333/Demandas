import copy
import json
from pathlib import Path

import pytest
import yaml

from veleros import analisis, costes, parsing
from veleros.filtros import motivo_descarte
from veleros.models import Anuncio
from veleros.scrapers import portales
from veleros.scrapers.base import ficha_generica

BASE = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((BASE / "config.yaml").read_text("utf-8"))


def anuncio(**kw):
    d = dict(sitio="t", pais="FR", id_sitio="1", url="https://x/1", titulo="Voilier", descripcion="")
    d.update(kw)
    a = Anuncio(**d)
    parsing.completar(a)
    return a


# ------------------------------------------------------------------ parsing
@pytest.mark.parametrize("txt,esperado", [
    ("8.500 €", 8500), ("8 500 €", 8500), ("€ 8.750,-", 8750), ("Prix : 9500€", 9500), ("EUR 7,900", 7900),
    ("9.900,00 €", 9900), ("Prijs 8.750,- euro", 8750),
])
def test_precio(txt, esperado):
    assert parsing.parse_precio(txt) == esperado


@pytest.mark.parametrize("txt,esperado", [
    ("Eslora: 8,50 m", 8.5), ("longueur 7.65 m, largeur 2,9 m", 7.65), ("lengte 9,45 m", 9.45),
    ("LOA 28 ft", 8.53), ("Dufour 29, 8,90 x 2,95 m", 8.9), ("bateau de 9 m", 9.0), ("Length overall: 9.99m", 9.99),
])
def test_eslora(txt, esperado):
    assert parsing.parse_eslora(txt) == pytest.approx(esperado, abs=0.01)


def test_anio_y_ce():
    assert parsing.parse_anio("Bouwjaar: 2001, gereviseerd 2023") == 2001
    assert parsing.parse_anio("Voilier First 27.7 de 2000") == 2000
    assert parsing.detectar_ce("CE categorie C") == "si"
    assert parsing.detectar_ce("catégorie de conception B") == "si"
    assert parsing.detectar_ce("bateau sans CE") == "no"
    assert parsing.detectar_ce("bonito velero") == "desconocido"


def test_bandera_e_iva():
    assert parsing.detectar_bandera("Bateau francisé") == "FR"
    assert parsing.detectar_bandera("con bandera polaca") == "PL"
    assert parsing.detectar_bandera("matrícula española, lista 7ª") == "ES"
    assert parsing.detectar_iva("TVA payée") is True
    assert parsing.detectar_iva("BTW betaald") is True
    assert parsing.detectar_iva("hola") is None


def test_idioma():
    assert parsing.detectar_idioma("Te koop mooie zeilboot met motor in zeer goede staat") == "nl"
    assert parsing.detectar_idioma("Vends voilier avec moteur en très bon état pour la saison") == "fr"


# ------------------------------------------------------------------ filtros
def test_filtros():
    f = CFG["filtros"]
    ok = anuncio(descripcion="Voilier longueur 8,2 m, année 2001, CE catégorie C. Prix 9000 €")
    assert motivo_descarte(ok, f) is None
    assert "precio" in motivo_descarte(anuncio(descripcion="Voilier 8,2 m 2001 CE 12.000 €"), f)
    assert "eslora" in motivo_descarte(anuncio(descripcion="Voilier 11 m, année 2001, CE, 9000 €"), f)
    assert "antiguo" in motivo_descarte(anuncio(descripcion="Voilier 8 m, année 1985, 6000 €"), f)
    assert "CE" in motivo_descarte(anuncio(descripcion="Voilier 8 m, année 1997, 6000 €"), f)
    assert motivo_descarte(anuncio(descripcion="Voilier 8 m, année 1997, marquage CE, 6000 €"), f) is None
    assert "velero" in motivo_descarte(anuncio(titulo="Semi-rigide", descripcion="pneumatique 7 m 2005 CE 9000 €"), f)


# ------------------------------------------------------------------ rasgos
def test_rasgos_multilingues():
    a = anuncio(pais="NL", descripcion="Motor Volvo Penta 2002 werkt niet. Nieuwe zeilen. Geen osmose. Radar: nee. Kaartplotter. BTW betaald.")
    analisis.detectar_rasgos(a)
    f = {r.clave for r in a.puntos_fuertes}
    d = {r.clave for r in a.puntos_debiles}
    assert "motor_averiado" in d
    assert "osmosis" not in d and "osmosis" in f      # negación → punto fuerte
    assert "radar" not in f                           # "Radar: nee"
    assert {"velas", "plotter", "iva"} <= f

    b = anuncio(pais="ES", descripcion="Motor Yanmar en perfecto estado. Antifouling 2026. Grifos de fondo cambiados. WC marino con depósito de aguas negras.")
    analisis.detectar_rasgos(b)
    assert {"motor_ok", "antifouling", "grifos", "wc", "aguas_negras"} <= {r.clave for r in b.puntos_fuertes}
    assert not b.puntos_debiles


def test_puntuacion_ordena():
    bueno = anuncio(descripcion="Voilier 8 m 2002 CE. Moteur révisé, voiles neuves, antifouling 2026, gréement neuf. 9000 €", fotos=["a"] * 10)
    malo = anuncio(descripcion="Voilier 8 m 2002 CE. Moteur en panne, travaux à prévoir, osmose. 9000 €")
    for a in (bueno, malo):
        analisis.detectar_rasgos(a)
        analisis.puntuar(a, CFG)
    assert bueno.puntuacion > malo.puntuacion + 30


# ------------------------------------------------------------------ costes
def test_costes(tmp_path):
    cfg = copy.deepcopy(CFG)
    cfg["costes"]["geocodificar_online"] = False
    geo = costes.Geocodificador(cfg["costes"], tmp_path / "g.json")
    a = anuncio(descripcion="Voilier 9 m, 2001, CE, pavillon français", precio=9000, ubicacion="La Rochelle")
    analisis.detectar_rasgos(a)
    c = costes.estimar(a, geo, cfg)
    esp = c["escenarios"][0]
    assert any("IEDMT" in k for k in esp["partidas"])              # > 8 m
    assert esp["partidas"][next(k for k in esp["partidas"] if "IEDMT" in k)] == 1080
    assert any("ITP" in k for k in esp["partidas"])
    assert len(c["escenarios"]) == 2 and c["escenarios"][1]["nombre"] == "Bandera polaca"
    assert 800 < c["traslado"]["km"] < 1200
    assert c["mejor_total"] == min(e["total"] for e in c["escenarios"])

    corto = anuncio(descripcion="Voilier 7,5 m, 2001, CE", precio=9000, ubicacion="Brest")
    c2 = costes.estimar(corto, geo, cfg)
    assert not any("IEDMT" in k for k in c2["escenarios"][0]["partidas"])

    espanol = anuncio(pais="ES", descripcion="Velero 9 m, 2001, CE, bandera española", precio=9000, ubicacion="Dénia")
    c3 = costes.estimar(espanol, geo, cfg)
    assert len(c3["escenarios"]) == 1
    assert any("titularidad" in k for k in c3["escenarios"][0]["partidas"])


# ------------------------------------------------------------------ extractores (respuestas simuladas)
class HttpFalso:
    def __init__(self, respuestas):
        self.respuestas = respuestas

    def get(self, url, json_resp=False, **kw):
        for patron, resp in self.respuestas.items():
            if patron in url:
                return resp
        raise portales.Bloqueado(url)


FICHA = """<html><head><title>Voilier</title>
<script type="application/ld+json">{"@type":"Product","name":"Dufour 29","description":"Dufour 29 de 1998, marquage CE.",
"image":["https://img/1.jpg","https://img/2.jpg"],"offers":{"price":"6500","priceCurrency":"EUR"}}</script></head>
<body><dl><dt>Longueur</dt><dd>8,90 m</dd><dt>Année</dt><dd>1998</dd><dt>Localisation</dt><dd>Port-Vendres</dd></dl>
<div class="gallery"><img src="https://img/3.jpg"><img src="/static/logo.png"></div>
<a href="https://img/2.jpg?w=200">x</a></body></html>"""


def test_ficha_generica():
    f = ficha_generica(FICHA, "https://exemple.fr/annonce/123456")
    assert f["titulo"] == "Dufour 29" and f["precio"] == 6500
    assert f["eslora_m"] == 8.9 and f["anio"] == 1998 and f["ubicacion"] == "Port-Vendres"
    assert "https://img/3.jpg" in f["fotos"] and not any("logo" in u for u in f["fotos"])
    assert len([u for u in f["fotos"] if "/2.jpg" in u]) == 1          # duplicado de distinto tamaño


def test_generico_y_marktplaats():
    listado = '<a href="/voiliers/dufour-29-123456">a</a><a href="/contact">b</a><a href="/voiliers/first-27-654321">c</a>'
    http = HttpFalso({"listado": listado, "123456": FICHA, "654321": FICHA})
    sc = portales.Generico("x", {"pais": "FR", "listados": ["https://exemple.fr/listado?p={pagina}"], "paginas": 1}, http, CFG["filtros"])
    res = list(sc.buscar())
    assert len(res) == 2 and res[0].precio == 6500 and len(res[0].fotos) >= 3

    api = {"listings": [{"itemId": "m1", "title": "Etap 26 zeilboot", "description": "lengte 7,9 m", "vipUrl": "/v/m1",
                         "priceInfo": {"priceCents": 990000}, "pictures": [{"extraExtraLargeUrl": "//img/x.jpg"}],
                         "location": {"cityName": "Lemmer"}},
                        {"itemId": "m2", "title": "Groot jacht", "description": "lengte 12 m", "vipUrl": "/v/m2",
                         "priceInfo": {"priceCents": 2000000}}]}
    http = HttpFalso({"lrp/api": api, "/v/m1": "<html></html>"})
    sc = portales.Marktplaats("marktplaats", {"pais": "NL", "terminos": ["zeilboot"], "paginas": 1}, http, CFG["filtros"])
    res = list(sc.buscar())
    assert [a.id_sitio for a in res] == ["m1"]
    assert res[0].precio == 9900 and res[0].fotos == ["https://img/x.jpg"]


def test_leboncoin_next_data():
    datos = {"props": {"pageProps": {"searchData": {"ads": [
        {"list_id": 42, "subject": "Voilier First 27.7", "body": "longueur 8,25 m", "price": [9500], "url": "https://lbc/42",
         "images": {"urls_large": ["https://img/a.jpg", "https://img/b.jpg"]}, "location": {"city": "La Rochelle"},
         "owner": {"type": "private"}, "attributes": []}]}}}}
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(datos)}</script>'
    sc = portales.Leboncoin("leboncoin", {"pais": "FR", "terminos": ["voilier"], "paginas": 1}, HttpFalso({"leboncoin": html}), CFG["filtros"])
    res = list(sc.buscar())
    assert len(res) == 1 and res[0].precio == 9500 and len(res[0].fotos) == 2 and res[0].ubicacion == "La Rochelle"


def test_demo_completa(tmp_path):
    from veleros.procesar import ejecutar, mejores_por_pais
    cfg = copy.deepcopy(CFG)
    cfg["carpeta_datos"] = str(tmp_path)
    cfg["traduccion"]["motor"] = "ninguno"
    cfg["costes"]["geocodificar_online"] = False
    datos = json.loads((BASE / "demo" / "anuncios_demo.json").read_text("utf-8"))
    res = ejecutar(cfg, tmp_path, anuncios_entrada=[Anuncio(**d) for d in datos])
    top = mejores_por_pais(res, 15)
    assert all(top[p] for p in ("ES", "FR", "NL"))
    for lista in top.values():
        assert [a.puntuacion for a in lista] == sorted((a.puntuacion for a in lista), reverse=True)
        for a in lista:
            assert 7 <= a.eslora_m <= 10 and a.precio <= 10000
    assert sum(res.descartes.values()) == 5


def test_ia_simulada(tmp_path, monkeypatch):
    """Comprueba la integración con Claude sin llamar a la API (cliente simulado)."""
    from types import SimpleNamespace

    from veleros import ia
    from veleros.db import BaseDatos

    respuesta = {"titulo_es": "Velero Etap 26i", "descripcion_es": "Motor averiado. Velas nuevas.", "resumen_es": "Buen barco con motor averiado.",
                 "eslora_m": 7.9, "anio": 2001, "bandera": None, "ce": "si", "iva_pagado": True, "vendedor_profesional": False,
                 "puntos_fuertes": [{"clave": "velas", "etiqueta": "Velas nuevas", "evidencia": "Velas nuevas"},
                                    {"clave": "otro", "etiqueta": "Cuna de varada incluida", "evidencia": "cuna incluida"}],
                 "puntos_debiles": [{"clave": "motor_averiado", "etiqueta": "Motor averiado", "evidencia": "Motor averiado"}]}
    llamadas = []

    class Mensajes:
        def create(self, **kw):
            llamadas.append(kw)
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(respuesta))])

    an = ia.AnalizadorClaude.__new__(ia.AnalizadorClaude)
    an.client = SimpleNamespace(beta=SimpleNamespace(messages=Mensajes()))
    an.anthropic = __import__("anthropic")
    an.modelo, an.esfuerzo, an.db = "claude-opus-5-5", "low", BaseDatos(tmp_path / "db.sqlite")
    a = Anuncio(sitio="t", pais="NL", id_sitio="1", url="u", titulo="Etap 26i", descripcion="motor kapot, nieuwe zeilen")
    assert an.analizar(a) and an.analizar(a)
    assert len(llamadas) == 1                                   # la segunda vez sale de la caché
    assert llamadas[0]["output_config"]["format"]["type"] == "json_schema"
    analisis.detectar_rasgos(a)
    ia.fusionar_rasgos(a)
    assert a.titulo_es == "Velero Etap 26i" and a.iva_pagado is True and a.eslora_m == 7.9
    assert "motor_averiado" in {r.clave for r in a.puntos_debiles}
    assert any(r.etiqueta == "Cuna de varada incluida" for r in a.puntos_fuertes)


# ------------------------------------------------------------------ alertas por correo
ALERTA_LBC = """<html><body><table>
<tr><td><a href="https://www.leboncoin.fr/"><img src="https://static.lbc/logo.png" width="40"></a></td></tr>
<tr><td><a href="https://click.lbc-mail.fr/track/abc"><img src="https://img.lbc/ad1.jpg" alt="Voilier Sun Way 25"></a></td>
    <td><a href="https://click.lbc-mail.fr/track/abc">Voilier Sun Way 25</a><br>7 900 €<br>La Rochelle 17000</td></tr>
<tr><td><a href="https://www.leboncoin.fr/ad/nautisme/2876543210"><img src="https://img.lbc/ad2.jpg"></a></td>
    <td><a href="https://www.leboncoin.fr/ad/nautisme/2876543210">Bavaria 32 très bon état</a><br>14 500 €<br>Brest 29200</td></tr>
<tr><td><a href="https://www.leboncoin.fr/parametres/alertes">Gérer mes alertes</a> · <a href="https://lbc.fr/unsubscribe?x=1">Se désinscrire 0 €</a></td></tr>
</table></body></html>"""


def test_extraer_alerta_leboncoin():
    from veleros.correo import PORTALES_ALERTA, extraer_anuncios
    redir = {"https://click.lbc-mail.fr/track/abc": "https://www.leboncoin.fr/ad/nautisme/2871112223?utm_source=alerte"}
    ads = extraer_anuncios(ALERTA_LBC, "leboncoin", PORTALES_ALERTA, resolver=lambda u: redir.get(u, u))
    por_id = {a.id_sitio: a for a in ads}
    assert set(por_id) == {"2871112223", "2876543210"}
    a = por_id["2871112223"]
    assert a.url == "https://www.leboncoin.fr/ad/nautisme/2871112223"          # sin parámetros de seguimiento
    assert a.precio == 7900 and a.titulo == "Voilier Sun Way 25" and "17000" in a.ubicacion
    assert a.fotos == ["https://img.lbc/ad1.jpg"] and a.pais == "FR" and a.origen == "alerta"
    assert por_id["2876543210"].precio == 14500


def test_remitente_portal():
    from veleros.correo import PORTALES_ALERTA, portal_del_remitente
    assert portal_del_remitente("Marktplaats <noreply@mail.marktplaats.nl>", "Nieuwe advertenties", PORTALES_ALERTA) == "marktplaats"
    assert portal_del_remitente('"leboncoin" <alertes@leboncoin.fr>', "Nouvelles annonces", PORTALES_ALERTA) == "leboncoin"
    assert portal_del_remitente("Banco <info@banco.es>", "Su extracto", PORTALES_ALERTA) is None


def test_lector_imap_simulado(tmp_path, monkeypatch):
    """Buzón IMAP falso: comprueba solo lectura (readonly + BODY.PEEK) y extracción."""
    from email.mime.text import MIMEText

    from veleros import correo

    html = """<table><tr><td><a href="https://www.marktplaats.nl/v/watersport-en-boten/zeilboten/m2112233445-etap-26">
      <img src="https://images.mp/etap.jpg"></a></td><td><a href="https://www.marktplaats.nl/v/watersport-en-boten/zeilboten/m2112233445-etap-26">Etap 26 zeilboot</a>
      € 8.950,-<br>Lemmer</td></tr></table>"""
    m1 = MIMEText(html, "html", "utf-8"); m1["From"] = "Marktplaats <noreply@marktplaats.nl>"; m1["Subject"] = "Nieuwe zoekresultaten"
    m2 = MIMEText("Hola", "plain", "utf-8"); m2["From"] = "Amigo <a@b.es>"; m2["Subject"] = "Cena"
    llamadas = []

    class ImapFalso:
        def __init__(self, servidor, puerto): llamadas.append(("conectar", servidor, puerto))
        def login(self, u, c): llamadas.append(("login", u))
        def select(self, carpeta, readonly=False): llamadas.append(("select", readonly)); return "OK", [b"2"]
        def search(self, charset, criterio): return "OK", [b"1 2"]
        def fetch(self, num, partes):
            llamadas.append(("fetch", partes))
            return "OK", [(b"x", (m1 if num == b"1" else m2).as_bytes())]
        def logout(self): pass

    monkeypatch.setattr(correo.imaplib, "IMAP4_SSL", ImapFalso)
    (tmp_path / "correo_privado.yaml").write_text("servidor: imap.test\nusuario: u@test\ncontrasena: x\n", "utf-8")
    lector = correo.LectorAlertas({"dias_atras": 2}, tmp_path)
    ads = list(lector.buscar())
    assert len(ads) == 1 and ads[0].sitio == "marktplaats" and ads[0].precio == 8950 and ads[0].pais == "NL"
    assert ("select", True) in llamadas and all(p == "(BODY.PEEK[])" for k, p, *_ in [c for c in llamadas if c[0] == "fetch"])
    assert lector.estado["correo-marktplaats"] == {"estado": "ok", "encontrados": 1, "correos": 1}


def test_alerta_sin_datos_no_se_descarta():
    f = CFG["filtros"]
    a = Anuncio(sitio="leboncoin", pais="FR", id_sitio="1", url="u", titulo="Voilier Sun Way 25", precio=7900, origen="alerta")
    parsing.completar(a)
    assert motivo_descarte(a, f) is None                                       # sin eslora ni año: se revisa a mano
    a.precio = 14500
    assert "precio" in motivo_descarte(a, f)
    b = Anuncio(sitio="leboncoin", pais="FR", id_sitio="2", url="u", titulo="Voilier 11 m", descripcion="longueur 11 m", precio=9000, origen="alerta")
    parsing.completar(b)
    assert "eslora" in motivo_descarte(b, f)
