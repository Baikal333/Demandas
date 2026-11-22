"""Modelo de datos de un anuncio."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Rasgo:
    clave: str
    etiqueta: str
    peso: float
    evidencia: str = ""


@dataclass
class Anuncio:
    sitio: str
    pais: str                    # país del portal: ES, FR, NL
    id_sitio: str
    url: str
    titulo: str = ""
    descripcion: str = ""
    precio: float | None = None
    moneda: str = "EUR"
    eslora_m: float | None = None
    manga_m: float | None = None
    anio: int | None = None
    ubicacion: str = ""
    bandera: str | None = None   # ES, FR, NL, PL, ... (None = desconocida)
    fotos: list[str] = field(default_factory=list)
    idioma: str | None = None
    vendedor_profesional: bool | None = None
    fecha_publicacion: str | None = None
    caracteristicas: dict[str, str] = field(default_factory=dict)
    origen: str = "web"          # "web" (búsqueda en el portal) | "alerta" (correo de alerta)

    # --- resultados del análisis ---
    titulo_es: str = ""
    descripcion_es: str = ""
    resumen_es: str = ""
    puntos_fuertes: list[Rasgo] = field(default_factory=list)
    puntos_debiles: list[Rasgo] = field(default_factory=list)
    ce: str = "desconocido"      # "si" | "no" | "desconocido"
    iva_pagado: bool | None = None
    puntuacion: float = 0.0
    costes: dict[str, Any] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    descartado: str | None = None
    nuevo: bool = False
    fotos_locales: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"{self.sitio}:{self.id_sitio}"

    @property
    def texto_completo(self) -> str:
        extra = " ".join(f"{k}: {v}" for k, v in self.caracteristicas.items())
        return f"{self.titulo}\n{self.descripcion}\n{extra}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["id"] = self.id
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Anuncio":
        d = dict(d)
        d.pop("id", None)
        for k in ("puntos_fuertes", "puntos_debiles"):
            d[k] = [Rasgo(**r) if isinstance(r, dict) else r for r in d.get(k, [])]
        campos = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in d.items() if k in campos})
