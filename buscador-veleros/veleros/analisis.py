"""Detección de puntos fuertes / débiles y puntuación de cada anuncio.

Los patrones se buscan tanto en el texto original (ES/FR/NL/EN) como en la
traducción al español, de modo que funcionan aunque la traducción falle.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .models import Anuncio, Rasgo
from .parsing import ANIO_ACTUAL, normalizar

# Palabras que niegan un defecto ("sin osmosis", "pas d'osmose", "geen osmose")
_NEGACION = re.compile(
    r"(?:\bsin\b|\bnada\s+de\b|\bningun[ao]?\b|\bnunca\b|\bsans\b|\bpas\s+d[e']|\baucune?\b|\bjamais\b|"
    r"\bgeen\b|\bzonder\b|\bnooit\b|\bno\b|\bnot?\b|\bfree\s+of\b|\bwithout\b|\bzero\b)[^.;\n]{0,18}$", re.I)


@dataclass
class Patron:
    clave: str
    etiqueta: str
    peso: float
    patrones: list[str]
    negable: bool = False          # si va precedido de negación, se ignora (o invierte)
    si_negado: tuple[str, float] | None = None   # (etiqueta, peso) como punto fuerte si se niega
    reciente: bool = False         # bonifica si menciona el año actual o el anterior


A = r"(?:20[0-9]{2})"
M = r"(?:\s+[\w./-]+,?){0,4}?\s+"   # hueco para marca/modelo: "motor Volvo MD2020 revisado"

FUERTES: list[Patron] = [
    Patron("antifouling", "Antifouling / varada reciente", 8, [
        r"antifouling", r"anti-?fouling", r"antiincrustante", r"patente\s+(?:nueva|reciente|hecha)",
        r"varad[ao]\s+(?:reciente|en\s+" + A + ")", r"carenad[oa]", r"car[eé]nage", r"onderwaterschip\s+(?:behandeld|geschilderd)",
        r"aangroeiwerende", r"antifoul", r"hull\s+(?:cleaned|painted)", r"bottom\s+paint",
    ], reciente=True),
    Patron("jarcia", "Jarcia nueva o en muy buen estado", 9, [
        r"jarcia\s+(?:firme\s+)?(?:nueva|cambiada|renovada|reciente|en\s+(?:muy\s+)?buen\s+estado|revisada)",
        r"(?:nueva|renovada)\s+jarcia", r"gr[ée]ement\s+(?:dormant\s+)?(?:neuf|r[ée]cent|chang[ée]|refait|remplac[ée]|en\s+(?:tr[eè]s\s+)?bon\s+[ée]tat)",
        r"staand\s+want\s+(?:nieuw|vernieuwd|vervangen)", r"(?:nieuw|vernieuwd)\s+staand\s+want", r"tuigage\s+(?:nieuw|vernieuwd)",
        r"(?:new|replaced)\s+(?:standing\s+)?rigging", r"rigging\s+(?:new|replaced|renewed)",
        r"haubans\s+(?:neufs|chang[ée]s|r[ée]cents)", r"obenques\s+(?:nuevos|cambiados)",
    ], reciente=True),
    Patron("velas", "Velas nuevas o en buen estado", 8, [
        r"velas?\s+(?:nuevas?|recientes?|en\s+(?:muy\s+)?buen\s+estado|seminuevas?)", r"(?:g[eé]nova|mayor|spi|spinnaker)\s+(?:nuev[oa]|de\s+" + A + ")",
        r"voiles?\s+(?:neuves?|r[ée]centes?|en\s+(?:tr[eè]s\s+)?bon\s+[ée]tat)", r"(?:g[ée]nois|grand[\s-]?voile)\s+(?:neuf|neuve|r[ée]cente?)",
        r"zeilen\s+(?:nieuw|zo\s+goed\s+als\s+nieuw|in\s+goede\s+staat)", r"(?:nieuw|nieuwe)\s+(?:grootzeil|fok|genua|zeilen)",
        r"(?:new|recent)\s+(?:sails?|main(?:sail)?|genoa|jib)", r"sails?\s+(?:new|in\s+(?:very\s+)?good\s+condition)",
    ], reciente=True),
    Patron("grifos", "Grifos de fondo cambiados", 7, [
        r"grifos?\s+(?:de\s+fondo|pasacascos?)\s+(?:nuevos?|cambiados?|renovados?|sustituidos?)", r"pasacascos?\s+(?:nuevos?|cambiados?)",
        r"(?:vannes?|passe-coques?)\s+(?:neuve?s?|chang[ée]e?s?|remplac[ée]e?s?)", r"(?:nouvelles?|nouveaux)\s+(?:vannes|passe-coques)",
        r"afsluiters\s+(?:nieuw|vervangen|vernieuwd)", r"(?:nieuwe)\s+(?:afsluiters|huiddoorvoeren)", r"huiddoorvoeren\s+(?:nieuw|vervangen)",
        r"(?:new|replaced)\s+(?:seacocks|thru-?hulls)", r"seacocks\s+(?:new|replaced)",
    ]),
    Patron("radar", "Radar", 5, [r"\bradar\b"]),
    Patron("plotter", "Plotter / GPS cartográfico", 5, [
        r"plotter", r"chart\s*plotter", r"traceur(?:\s+de\s+cartes)?", r"kaartplotter", r"\bgps\b", r"cartograf",
    ]),
    Patron("wc", "WC marino", 4, [
        r"\bw\.?c\.?\b(?:\s+marino)?", r"inodoro", r"v[aá]ter", r"toilettes?\s+marines?", r"toilette", r"\bwc\s+marin",
        r"scheepstoilet", r"\btoilet\b", r"marine\s+(?:toilet|head)",
    ]),
    Patron("aguas_negras", "Depósito de aguas negras", 6, [
        r"dep[oó]sito\s+de\s+aguas?\s+negras", r"tanque\s+de\s+aguas?\s+negras", r"aguas\s+negras",
        r"r[ée]servoir\s+(?:\w+\s+)?(?:eaux\s+noires|eaux\s+us[ée]es)", r"cuve\s+(?:\w+\s+)?(?:eaux\s+noires|[aà]\s+eaux\s+noires)", r"eaux\s+noires",
        r"vuilwatertank", r"septictank", r"fecali[eë]ntank", r"holding\s+tank", r"black\s*water\s+tank",
    ]),
    Patron("iva", "IVA pagado (UE)", 7, [
        r"iva\s+(?:pagado|incluido|liquidado)", r"tva\s+(?:pay[ée]e|acquitt[ée]e|incluse)", r"btw\s+(?:betaald|voldaan)",
        r"incl\.?\s+btw", r"vat\s+paid", r"eu\s+vat",
    ]),
    Patron("motor_ok", "Motor revisado / nuevo / pocas horas", 8, [
        r"motor" + M + r"(?:nuevo|revisado|reci[eé]n\s+revisado|en\s+perfecto\s+estado|perfecto|reconstruido|con\s+pocas\s+horas|funciona\s+(?:perfectamente|bien))",
        r"pocas\s+horas", r"moteur" + M + r"(?:neuf|r[ée]vis[ée]|r[ée]cent|refait|en\s+parfait\s+[ée]tat|fonctionne\s+parfaitement)", r"peu\s+d'heures",
        r"motor" + M + r"(?:gereviseerd|nieuw|in\s+(?:prima|goede|perfecte)\s+staat|loopt\s+(?:prima|goed|perfect))", r"weinig\s+(?:draai)?uren",
        r"(?:new|rebuilt|serviced)\s+engine", r"engine" + M + r"(?:serviced|rebuilt|new|runs\s+(?:well|perfectly))", r"low\s+hours",
    ]),
    Patron("piloto", "Piloto automático", 4, [r"piloto\s+autom[aá]tico", r"pilote\s+automatique", r"autopilot", r"stuurautomaat", r"tiller\s*pilot", r"raymarine\s+st\d"]),
    Patron("ais_vhf", "AIS / VHF", 2, [r"\bais\b", r"\bvhf\b", r"marifoon", r"\bdsc\b"]),
    Patron("enrollador", "Enrollador de génova", 2, [r"enrollador", r"enrouleur", r"rolfok", r"furler", r"furling"]),
    Patron("solar", "Panel solar / baterías nuevas", 2, [
        r"panel(?:es)?\s+solar", r"placas?\s+solar", r"panneaux?\s+solaires?", r"zonnepane", r"solar\s+panel",
        r"bater[ií]as?\s+nuevas?", r"batteries?\s+neuves?", r"nieuwe\s+accu", r"new\s+batter",
    ]),
    Patron("confort", "Equipamiento de confort (bimini, sprayhood, frigorífico, calefacción)", 2, [
        r"bimini", r"sprayhood", r"capota", r"frigor[ií]fico", r"nevera", r"r[ée]frig[ée]rateur", r"frigo", r"koelkast",
        r"calefacci[oó]n", r"chauffage", r"kachel", r"verwarming", r"webasto", r"ebersp[aä]cher",
    ]),
    Patron("remolque", "Incluye remolque (abarata el traslado)", 6, [
        r"remolque", r"\btr[aá]iler\b", r"remorque", r"trailer", r"aanhanger", r"boottrailer", r"bateau\s+[aà]\s+terre\s+sur\s+ber",
    ]),
    Patron("quilla_mov", "Quilla abatible / orzable (fácil de transportar)", 3, [
        r"orza\s+abatible", r"quilla\s+(?:abatible|retr[aá]ctil|elevable)", r"d[ée]riveur", r"quille\s+relevable", r"dériveur\s+lesté",
        r"kielmidzwaard", r"midzwaard", r"hefkiel", r"lifting\s+keel", r"swing\s+keel", r"centreboard",
    ]),
    Patron("papeles", "Documentación en regla", 3, [
        r"documentaci[oó]n\s+en\s+regla", r"papeles\s+en\s+regla", r"papiers\s+en\s+r[eè]gle", r"papieren\s+in\s+orde",
        r"itb\s+(?:en\s+vigor|pasada|al\s+d[ií]a)", r"inspecci[oó]n\s+(?:pasada|en\s+vigor)",
    ]),
    Patron("expertise", "Peritaje / inspección reciente disponible", 4, [
        r"peritaje", r"informe\s+pericial", r"expertise\s+(?:r[ée]cente|de\s+" + A + "|disponible)", r"keuring(?:srapport)?", r"survey(?:\s+report)?",
    ]),
]

DEBILES: list[Patron] = [
    Patron("motor_averiado", "Motor averiado o sin funcionar", 18, [
        r"motor" + M + r"(?:(?:que\s+)?necesita\s+(?:una\s+)?reparaci[oó]n|averiado|roto|gripado|estropeado|a\s+reparar|para\s+reparar|no\s+funciona|no\s+arranca|parado|fundido|sin\s+funcionar)",
        r"(?:aver[ií]a|aver[ií]as)\s+(?:de|en\s+el)\s+motor", r"motor\s+necesita\s+(?:reparaci[oó]n|revisi[oó]n)",
        r"moteur" + M + r"(?:en\s+panne|hs|h\.s\.|cass[ée]|gripp[ée]|[aà]\s+revoir|[aà]\s+refaire|ne\s+(?:d[ée]marre|fonctionne)\s+pas|non\s+fonctionnel|[aà]\s+r[ée]parer)",
        r"motor" + M + r"(?:defect|kapot|werkt\s+niet|start\s+niet|moet\s+gereviseerd|vast(?:gelopen)?)", r"motorpech",
        r"engine" + M + r"(?:not\s+working|broken|seized|needs\s+(?:work|repair|rebuild)|does\s+not\s+(?:start|run)|u/s)", r"non[\s-]?running\s+engine",
    ]),
    Patron("sin_motor", "Sin motor", 10, [r"sin\s+motor", r"sans\s+moteur", r"zonder\s+motor", r"geen\s+motor", r"no\s+engine", r"without\s+engine"]),
    Patron("reparaciones", "Necesita reparaciones / proyecto", 12, [
        r"necesita\s+(?:reparaci|arreglo|trabajo|mantenimiento|puesta\s+a\s+punto|algunos?\s+arreglos)", r"para\s+(?:restaurar|reformar|reparar|rehabilitar)",
        r"a\s+(?:restaurar|reparar)", r"proyecto\s+de\s+restauraci", r"requiere\s+(?:trabajo|reparaci)", r"(?:hay\s+que|a)\s+reparar",
        r"[aà]\s+(?:r[ée]nover|restaurer|r[ée]parer|refaire|pr[ée]voir)", r"travaux\s+[aà]\s+pr[ée]voir", r"pour\s+bricoleur", r"projet\s+(?:de\s+)?(?:restauration|r[ée]novation)", r"bateau[\s-]projet",
        r"opknapper", r"klusboot", r"moet\s+(?:opgeknapt|gerepareerd)", r"(?:wat\s+)?achterstallig\s+onderhoud", r"op\s+te\s+knappen",
        r"needs\s+(?:work|repair|tlc|restoration|refit)", r"project\s+boat", r"restoration\s+project", r"handyman",
    ]),
    Patron("osmosis", "Ósmosis", 12, [r"[oó]smosis", r"osmose", r"osmosis", r"blistering"], negable=True,
           si_negado=("Sin ósmosis declarada", 4)),
    Patron("humedad_casco", "Delaminación / casco o cubierta dañados / vía de agua", 14, [
        r"delamin", r"d[ée]lamin", r"v[ií]a\s+de\s+agua", r"voie\s+d'eau", r"lekkage", r"lekt\b", r"water\s+ingress", r"leak(?:s|ing)?\b",
        r"cubierta\s+(?:blanda|h[uú]meda)", r"pont\s+mou", r"zacht\s+dek", r"soft\s+deck", r"casco\s+da[nñ]ado", r"coque\s+(?:ab[iî]m[ée]e|endommag[ée]e)",
    ], negable=True),
    Patron("timon_quilla", "Daños en timón, quilla o pernos", 12, [
        r"tim[oó]n\s+(?:da[nñ]ado|roto|a\s+revisar)", r"pernos?\s+de\s+quilla\s+(?:a\s+revisar|oxidados?|corro)", r"quilla\s+(?:da[nñ]ada|golpeada|suelta)",
        r"safran\s+(?:ab[iî]m[ée]|cass[ée]|[aà]\s+refaire)", r"boulons?\s+de\s+quille\s+[aà]", r"quille\s+(?:ab[iî]m[ée]e|[aà]\s+revoir)",
        r"roer\s+(?:beschadigd|kapot)", r"kielbouten\s+(?:vervangen\s+nodig|roest)", r"(?:damaged|broken)\s+(?:rudder|keel)", r"keel\s+bolts?\s+(?:need|rust)",
    ], negable=True),
    Patron("mastil", "Mástil o jarcia en mal estado / a cambiar", 10, [
        r"(?:m[aá]stil|palo)\s+(?:da[nñ]ado|roto|doblado)", r"jarcia\s+(?:a\s+cambiar|vieja|antigua|original|para\s+cambiar)",
        r"m[aâ]t\s+(?:cass[ée]|tordu|[aà]\s+changer)", r"gr[ée]ement\s+(?:[aà]\s+(?:changer|refaire|revoir)|d'origine|ancien|vieux)",
        r"mast\s+(?:beschadigd|gebroken|krom)", r"want\s+(?:moet\s+vervangen|oud|origineel)", r"(?:broken|damaged)\s+mast", r"rigging\s+(?:needs|old|original)",
    ]),
    Patron("velas_mal", "Velas viejas / a cambiar", 5, [
        r"velas?\s+(?:viejas?|antiguas?|gastadas?|rotas?|a\s+cambiar)", r"voiles?\s+(?:anciennes?|us[ée]es|fatigu[ée]es|[aà]\s+changer)",
        r"zeilen\s+(?:oud|versleten|op)", r"(?:old|worn|tired)\s+sails",
    ]),
    Patron("sin_papeles", "Sin papeles / documentación incompleta", 14, [
        r"sin\s+(?:papeles|documentaci[oó]n)", r"sans\s+papiers", r"zonder\s+papieren", r"no\s+papers", r"without\s+(?:papers|documents)",
        r"documentaci[oó]n\s+(?:incompleta|caducada|pendiente)", r"papiers\s+[aà]\s+(?:refaire|faire)",
    ]),
    Patron("siniestro", "Hundido, incendio o siniestro previo", 16, [
        r"hundid[oa]", r"incendi", r"coul[ée]", r"incendie", r"gezonken", r"brandschade", r"sunk", r"fire\s+damage", r"siniestr",
    ], negable=True),
    Patron("electricidad", "Instalación eléctrica a revisar", 5, [
        r"(?:electricidad|instalaci[oó]n\s+el[eé]ctrica)\s+(?:a\s+revisar|a\s+rehacer|mal)", r"[ée]lectricit[ée]\s+[aà]\s+(?:revoir|refaire)",
        r"elektra\s+(?:moet|slecht)", r"wiring\s+(?:needs|poor)",
    ]),
    Patron("humedades", "Humedades / moho / interior deteriorado", 5, [
        r"humedad(?:es)?", r"moho", r"humidit[ée]", r"moisissure", r"vocht(?:ig)?", r"schimmel", r"\bdamp\b", r"\bmould|\bmold\b",
        r"interior\s+(?:a\s+reformar|deteriorado)", r"int[ée]rieur\s+[aà]\s+(?:refaire|r[ée]nover)", r"interieur\s+moet",
    ], negable=True),
    Patron("varado_mucho", "Lleva mucho tiempo varado sin uso", 6, [
        r"(?:varado|en\s+seco|parado)\s+(?:desde|hace)\s+(?:\d+|varios|muchos)\s+a[nñ]os", r"(?:au\s+sec|immobilis[ée]|stock[ée])\s+depuis\s+\d+\s+ans",
        r"(?:staat|ligt)\s+al\s+\d+\s+jaar\s+(?:op\s+de\s+kant|stil|droog)", r"(?:on\s+the\s+hard|laid\s+up)\s+(?:for|since)\s+\d+\s+years",
    ]),
]


def _contexto(texto: str, ini: int, fin: int, margen: int = 50) -> str:
    a, b = max(0, ini - margen), min(len(texto), fin + margen)
    return ("…" if a else "") + texto[a:b].replace("\n", " ").strip() + ("…" if b < len(texto) else "")


_NEG_DESPUES = re.compile(r"^\s*[:\-]?\s*(?:non|no|nee|niet|none|ninguno|aucun|absent|n/a)\b", re.I)


def _buscar(p: Patron, texto: str, texto_norm: str, negar_siempre: bool = False) -> tuple[bool, bool, str]:
    """Devuelve (encontrado, negado, evidencia)."""
    negado_ev = ""
    for pat in p.patrones:
        for m in re.finditer(pat, texto_norm, re.I):
            previo = texto_norm[max(0, m.start() - 25):m.start()]
            despues = texto_norm[m.end():m.end() + 12]
            if (p.negable or negar_siempre) and (_NEGACION.search(previo) or _NEG_DESPUES.search(despues)):
                negado_ev = negado_ev or _contexto(texto, m.start(), m.end())
                continue
            return True, False, _contexto(texto, m.start(), m.end())
    return False, bool(negado_ev), negado_ev


def _es_reciente(evidencia: str) -> bool:
    e = normalizar(evidencia)
    anios = [int(x) for x in re.findall(r"\b(20[0-9]{2})\b", e)]
    if any(a >= ANIO_ACTUAL - 1 for a in anios):
        return True
    return bool(re.search(r"recien|reciente|este\s+a[nñ]o|r[ée]cent|cette\s+ann[ée]e|dit\s+jaar|onlangs|recent|this\s+year|nuev|neu[fv]|nieuw|new", e))


def detectar_rasgos(anuncio: Anuncio) -> None:
    """Rellena puntos_fuertes y puntos_debiles del anuncio."""
    # Se analizan juntos el texto original y la traducción; la evidencia se toma del texto en español si existe.
    textos = [t for t in (anuncio.titulo_es + "\n" + anuncio.descripcion_es, anuncio.texto_completo) if t.strip()]
    fuertes: dict[str, Rasgo] = {}
    debiles: dict[str, Rasgo] = {}
    for texto in textos:
        tn = normalizar(texto)
        for p in FUERTES:
            if p.clave in fuertes:
                continue
            ok, _, ev = _buscar(p, texto, tn, negar_siempre=True)
            if ok:
                peso = p.peso
                if p.reciente and _es_reciente(ev):
                    peso *= 1.25
                fuertes[p.clave] = Rasgo(p.clave, p.etiqueta, round(peso, 1), ev)
        for p in DEBILES:
            if p.clave in debiles:
                continue
            ok, negado, ev = _buscar(p, texto, tn)
            if ok:
                debiles[p.clave] = Rasgo(p.clave, p.etiqueta, p.peso, ev)
            elif negado and p.si_negado and p.clave not in fuertes:
                fuertes[p.clave] = Rasgo(p.clave, p.si_negado[0], p.si_negado[1], ev)

    # Coherencias: un "motor averiado" anula "motor revisado"; "sin motor" también.
    if "motor_averiado" in debiles or "sin_motor" in debiles:
        fuertes.pop("motor_ok", None)
    if "mastil" in debiles:
        fuertes.pop("jarcia", None)
    if "velas_mal" in debiles:
        fuertes.pop("velas", None)
    if anuncio.iva_pagado is True and "iva" not in fuertes:
        fuertes["iva"] = Rasgo("iva", "IVA pagado (UE)", 7, "")
    if anuncio.ce == "si":
        fuertes["ce"] = Rasgo("ce", "Marcado CE / categoría de diseño indicada", 3, "")

    anuncio.puntos_fuertes = sorted(fuertes.values(), key=lambda r: -r.peso)
    anuncio.puntos_debiles = sorted(debiles.values(), key=lambda r: -r.peso)


def puntuar(anuncio: Anuncio, cfg: dict) -> float:
    """Puntuación 0-100: estado (rasgos) + relación precio/eslora + edad + calidad del anuncio."""
    pcfg = cfg.get("puntuacion", {})
    s = 45.0
    fuertes = sum(r.peso for r in anuncio.puntos_fuertes) * pcfg.get("factor_fuertes", 1.0)
    debiles = sum(r.peso for r in anuncio.puntos_debiles) * pcfg.get("factor_debiles", 1.0)
    s += 35 * (1 - math.exp(-fuertes / 35))      # rendimientos decrecientes: 35 puntos como máximo
    s -= min(50.0, debiles)                       # los defectos restan sin atenuar

    # Relación precio / eslora (más metros por euro = mejor)
    if anuncio.precio and anuncio.eslora_m:
        eur_m = anuncio.precio / anuncio.eslora_m
        ref = pcfg.get("euros_por_metro_referencia", 1000)
        s += max(-10, min(10, (ref - eur_m) / ref * 10))
    # Edad
    if anuncio.anio:
        s += max(-6, min(8, (anuncio.anio - 1998) * 0.6))
    else:
        s -= 4
    # Calidad del anuncio
    n = len(anuncio.fotos)
    s += 4 if n >= 10 else 2 if n >= 5 else -3 if n == 0 else 0
    if len(anuncio.descripcion) < 120:
        s -= 3
    if anuncio.eslora_m is None:
        s -= 3
    # Coste total estimado (más barato = mejor)
    total = (anuncio.costes or {}).get("mejor_total")
    if total:
        s += max(-6, min(6, (12000 - total) / 2000))
    if anuncio.nuevo:
        s += pcfg.get("bonus_nuevo", 1)
    anuncio.puntuacion = round(max(0.0, min(100.0, s)), 1)
    return anuncio.puntuacion


def resumen(anuncio: Anuncio) -> str:
    partes = []
    if anuncio.puntos_fuertes:
        partes.append("A favor: " + ", ".join(r.etiqueta.lower() for r in anuncio.puntos_fuertes[:6]) + ".")
    if anuncio.puntos_debiles:
        partes.append("En contra: " + ", ".join(r.etiqueta.lower() for r in anuncio.puntos_debiles[:6]) + ".")
    if not partes:
        partes.append("El anuncio no menciona ni equipamiento destacado ni defectos: conviene pedir más información.")
    return " ".join(partes)
