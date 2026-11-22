"""Extracción de datos (precio, eslora, año, CE, bandera, IVA...) de textos en ES/FR/NL/EN."""
from __future__ import annotations

import datetime as _dt
import re
import unicodedata

PIE_A_METRO = 0.3048
ANIO_ACTUAL = _dt.date.today().year


def normalizar(texto: str) -> str:
    """Minúsculas y sin acentos, para comparar patrones."""
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower()


def _num(s: str) -> float | None:
    """Convierte '8.500', '8 500', '8,5', '8.50', '8,500.00' en número."""
    s = s.strip().replace("\u00a0", " ").replace("\u202f", " ")
    s = re.sub(r"[,\-]+$", "", s).strip()          # '8.500,-' (estilo holandés)
    s = s.replace(" ", "").replace("'", "")
    if not s:
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif re.fullmatch(r"\d{1,3}(?:,\d{3})+", s):
        s = s.replace(",", "")                       # 8,500  -> 8500
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", s):
        s = s.replace(".", "")                       # 8.500  -> 8500
    elif "," in s:
        s = s.replace(",", ".")                      # 8,5    -> 8.5
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------------------------------------- precio
_RE_PRECIO = [
    re.compile(r"(?:€|\beur(?:os?)?\b)\s*([0-9][0-9 .,\u00a0\u202f]{0,12}[0-9](?:,-)?)", re.I),
    re.compile(r"([0-9][0-9 .,\u00a0\u202f]{0,12}[0-9])(?:,-)?\s*(?:€|\beur(?:os?)?\b)", re.I),
]


def parse_precio(texto: str | None) -> float | None:
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        return float(texto)
    t = str(texto)
    for rx in _RE_PRECIO:
        m = rx.search(t)
        if m:
            v = _num(m.group(1))
            if v is not None and v > 0:
                return v
    if re.fullmatch(r"\s*[0-9][0-9 .,]*\s*", t):
        return _num(t)
    return None


# ---------------------------------------------------------------- eslora
_ETIQ_ESLORA = r"(?:eslora(?:\s+total)?|loa|l\.?o\.?a\.?|longueur(?:\s+(?:hors\s+tout|coque))?|lengte(?:\s+over\s+alles)?|length(?:\s+overall)?|lunghezza|lange)"
_RE_ESLORA_ETIQ_M = re.compile(_ETIQ_ESLORA + r"\s*[:=\-]?\s*(?:\(m\)\s*)?([0-9]{1,2}(?:[.,][0-9]{1,2})?)\s*(?:m\b|mt|metros?|meters?|metres?|mètres?)?", re.I)
_RE_ESLORA_ETIQ_FT = re.compile(_ETIQ_ESLORA + r"\s*[:=\-]?\s*([0-9]{2}(?:[.,][0-9])?)\s*(?:ft|feet|pies|'|pieds|voet)", re.I)
_RE_M = re.compile(r"\b([0-9]{1,2}[.,][0-9]{1,2}|[0-9]{1,2})\s*(?:m|mt|metros|meters|metres|mètres|meter)\b(?!\s*[²2³3])", re.I)
_RE_FT = re.compile(r"\b([2-4][0-9](?:[.,][0-9])?)\s*(?:ft|feet|pies|pieds|voet)\b|\b([2-4][0-9])'(?!')", re.I)
_RE_DIM = re.compile(r"\b([0-9]{1,2}[.,][0-9]{1,2})\s*[x×]\s*([0-9][.,][0-9]{1,2})\s*m?\b", re.I)


def parse_eslora(texto: str) -> float | None:
    """Devuelve la eslora en metros (prioriza valores etiquetados)."""
    if not texto:
        return None
    for rx, factor in ((_RE_ESLORA_ETIQ_FT, PIE_A_METRO), (_RE_ESLORA_ETIQ_M, 1.0)):
        m = rx.search(texto)
        if m:
            v = _num(m.group(1))
            if v:
                v *= factor
                if 3 <= v <= 30:
                    return round(v, 2)
    m = _RE_DIM.search(texto)
    if m:
        v = _num(m.group(1))
        if v and 3 <= v <= 30:
            return round(v, 2)
    for m in _RE_M.finditer(texto):
        v = _num(m.group(1))
        if v and 4 <= v <= 20:
            return round(v, 2)
    m = _RE_FT.search(texto)
    if m:
        v = _num(m.group(1) or m.group(2))
        if v:
            return round(v * PIE_A_METRO, 2)
    return None


_RE_MANGA = re.compile(r"(?:manga|largeur|breedte|beam|width)\s*[:=\-]?\s*([0-9](?:[.,][0-9]{1,2})?)\s*(?:m\b|metros?|meters?|mètres?)?", re.I)


def parse_manga(texto: str) -> float | None:
    m = _RE_MANGA.search(texto or "")
    if m:
        v = _num(m.group(1))
        if v and 1.2 <= v <= 6:
            return v
    m = _RE_DIM.search(texto or "")
    if m:
        v = _num(m.group(2))
        if v and 1.2 <= v <= 6:
            return v
    return None


# ---------------------------------------------------------------- año
_RE_ANIO_ETIQ = re.compile(
    r"(?:a[nñ]o(?:\s+de)?(?:\s+construcci[oó]n|\s+fabricaci[oó]n)?|ann[ée]e(?:\s+de\s+construction)?|"
    r"bouwjaar|year(?:\s+built)?|built(?:\s+in)?|construit\s+en|construido\s+en|de\s+l'ann[ée]e|baujahr|"
    r"fabricado\s+en|matriculado\s+en)\s*[:=\-]?\s*((?:19|20)[0-9]{2})", re.I)
_RE_ANIO = re.compile(r"\b((?:19[5-9]|20[0-4])[0-9])\b")


def parse_anio(texto: str) -> int | None:
    if not texto:
        return None
    m = _RE_ANIO_ETIQ.search(texto)
    if m:
        a = int(m.group(1))
        if 1950 <= a <= ANIO_ACTUAL:
            return a
    candidatos = [int(x) for x in _RE_ANIO.findall(texto) if 1950 <= int(x) <= ANIO_ACTUAL]
    # El primer año que aparece suele ser el de construcción (en título o ficha).
    return candidatos[0] if candidatos else None


# ---------------------------------------------------------------- CE
_CE_NEG = re.compile(
    r"\b(?:sin|no\s+tiene|no\s+dispone\s+de|sans|pas\s+de|geen|zonder|no|without|pre)[\s\-]*"
    r"(?:marcado\s+|marquage\s+|markering\s+|marking\s+)?c\.?e\b", re.I)
_CE_POS = re.compile(
    r"(?:marcado|marca|marquage|norme|normes|homologad[oa]|homologu[ée]e?|conforme|certificad[oa]|"
    r"markering|gemarkeerd|keurmerk|marked|marking|certified|declaraci[oó]n\s+de\s+conformidad)[\s:\-]*c\.?e\b|"
    r"\bc\.?e[\s\-]*(?:markering|gemarkeerd|marking|marked|categor(?:y|ie|[ií]a)|cat\.?|[aA-dD]\b|certif|norm)|"
    r"\bc\.?e[\s\-]+(?:marcado|marquage)|\bcat[ée]gor(?:ie|[ií]a)\s+(?:de\s+(?:conception|dise[nñ]o)\s+)?[abcd]\b|"
    r"\bontwerpcategorie\s+[abcd]\b|\bdesign\s+category\s+[abcd]\b|\brcd\b", re.I)


def detectar_ce(texto: str) -> str:
    t = texto or ""
    if _CE_NEG.search(t):
        return "no"
    if _CE_POS.search(t):
        return "si"
    return "desconocido"


# ---------------------------------------------------------------- bandera
_BANDERAS = {
    "PL": r"bandera\s+polaca|pabell[oó]n\s+polaco|pavillon\s+polonais|poolse\s+vlag|polish\s+flag|registro\s+polaco|matr[ií]cula\s+polaca|\bpzz\b|pzż",
    "FR": r"bandera\s+francesa|pabell[oó]n\s+franc[eé]s|pavillon\s+fran[cç]ais|francis[ée]e?\b|francisation|acte\s+de\s+francisation|franse\s+vlag|french\s+flag",
    "ES": r"bandera\s+espa[nñ]ola|pabell[oó]n\s+espa[nñ]ol|matr[ií]cula\s+espa[nñ]ola|lista\s+(?:7|s[eé]ptima)|7[ªa]\s+lista|pavillon\s+espagnol|spaanse\s+vlag|spanish\s+flag",
    "NL": r"bandera\s+holandesa|pavillon\s+n[ée]erlandais|nederlandse\s+vlag|dutch\s+flag|\bicp\b|kadaster|teboekgesteld",
    "BE": r"pavillon\s+belge|belgische\s+vlag|bandera\s+belga",
    "DE": r"bandera\s+alemana|pavillon\s+allemand|duitse\s+vlag|german\s+flag",
    "GB": r"bandera\s+brit[aá]nica|pavillon\s+britannique|britse\s+vlag|british\s+flag|\bssr\b|part\s+1\s+regist",
}


def detectar_bandera(texto: str) -> str | None:
    t = texto or ""
    for cod, pat in _BANDERAS.items():
        if re.search(pat, t, re.I):
            return cod
    return None


# ---------------------------------------------------------------- IVA
_IVA_SI = re.compile(
    r"iva\s+(?:pagado|incluido|liquidado|abonado)|tva\s+(?:pay[ée]e|acquitt[ée]e|r[ée]gl[ée]e|incluse)|"
    r"btw\s+(?:betaald|voldaan|inbegrepen)|incl\.?\s+btw|vat\s+(?:paid|included)|eu\s+vat\s+paid|"
    r"(?:ue|eu|ce)\s+(?:vat|tva|btw|iva)\s+(?:paid|pay[ée]e|betaald|pagado)", re.I)
_IVA_NO = re.compile(
    r"iva\s+no\s+pagado|sin\s+iva\s+pagado|tva\s+non\s+pay[ée]e|hors\s+tva\s+(?:ue|ce)|btw\s+niet\s+betaald|vat\s+not\s+paid|vat\s+unpaid", re.I)


def detectar_iva(texto: str) -> bool | None:
    t = texto or ""
    if _IVA_NO.search(t):
        return False
    if _IVA_SI.search(t):
        return True
    return None


# ---------------------------------------------------------------- vendedor
_PROF = re.compile(r"\b(?:concesionario|broker|bróker|chantier|courtier|concessionnaire|jachtmakelaar|makelaar|"
                   r"dealer|nuestra\s+empresa|notre\s+soci[ée]t[ée]|tva\s+r[ée]cup[ée]rable|factura\s+con\s+iva)\b", re.I)


def detectar_profesional(texto: str) -> bool | None:
    return True if _PROF.search(texto or "") else None


# ---------------------------------------------------------------- idioma
_STOP = {
    "es": {"el", "la", "de", "y", "con", "en", "barco", "velero", "motor", "muy", "para", "los", "del", "está", "nuevo"},
    "fr": {"le", "la", "de", "et", "avec", "en", "bateau", "voilier", "moteur", "très", "pour", "les", "du", "est", "neuf"},
    "nl": {"de", "het", "een", "en", "met", "in", "boot", "zeilboot", "motor", "zeer", "voor", "van", "is", "nieuw", "zeiljacht"},
    "en": {"the", "and", "with", "in", "boat", "sailboat", "engine", "very", "for", "of", "is", "new", "yacht"},
}


def detectar_idioma(texto: str, por_defecto: str | None = None) -> str | None:
    palabras = re.findall(r"[a-zàâçéèêëîïôûùüÿñæœ]+", (texto or "").lower())
    if len(palabras) < 4:
        return por_defecto
    puntos = {k: sum(1 for p in palabras if p in v) for k, v in _STOP.items()}
    mejor = max(puntos, key=puntos.get)
    return mejor if puntos[mejor] > 0 else por_defecto


def completar(anuncio) -> None:
    """Rellena los campos que falten a partir del texto del anuncio."""
    texto = anuncio.texto_completo
    if anuncio.precio is None:
        anuncio.precio = parse_precio(texto)
    if anuncio.eslora_m is None:
        anuncio.eslora_m = parse_eslora(texto)
    if anuncio.manga_m is None:
        anuncio.manga_m = parse_manga(texto)
    if anuncio.anio is None:
        anuncio.anio = parse_anio(texto)
    if anuncio.bandera is None:
        anuncio.bandera = detectar_bandera(texto)
    anuncio.ce = detectar_ce(texto)
    anuncio.iva_pagado = detectar_iva(texto)
    if anuncio.vendedor_profesional is None:
        anuncio.vendedor_profesional = detectar_profesional(texto)
    if not anuncio.idioma:
        anuncio.idioma = detectar_idioma(texto, {"ES": "es", "FR": "fr", "NL": "nl"}.get(anuncio.pais))
