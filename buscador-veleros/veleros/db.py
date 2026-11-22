"""Persistencia en SQLite: histórico de anuncios vistos y caché de traducciones."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

from .models import Anuncio


class BaseDatos:
    def __init__(self, ruta: Path):
        ruta.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(ruta)
        self.con.executescript(
            """
            CREATE TABLE IF NOT EXISTS anuncios (
                id TEXT PRIMARY KEY, pais TEXT, primera_vez TEXT, ultima_vez TEXT,
                precio REAL, datos TEXT
            );
            CREATE TABLE IF NOT EXISTS traducciones (clave TEXT PRIMARY KEY, texto TEXT);
            CREATE TABLE IF NOT EXISTS ia (clave TEXT PRIMARY KEY, datos TEXT);
            """
        )

    # --------------------------------------------------------- anuncios
    def registrar(self, a: Anuncio, hoy: str | None = None) -> tuple[bool, float | None]:
        """Guarda el anuncio. Devuelve (es_nuevo, precio_anterior)."""
        hoy = hoy or dt.date.today().isoformat()
        fila = self.con.execute("SELECT primera_vez, precio FROM anuncios WHERE id=?", (a.id,)).fetchone()
        nuevo = fila is None or fila[0] == hoy
        precio_ant = fila[1] if fila else None
        self.con.execute(
            "INSERT INTO anuncios (id, pais, primera_vez, ultima_vez, precio, datos) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET ultima_vez=excluded.ultima_vez, precio=excluded.precio, datos=excluded.datos",
            (a.id, a.pais, hoy, hoy, a.precio, json.dumps(a.to_dict(), ensure_ascii=False)),
        )
        self.con.commit()
        return nuevo, precio_ant

    def anuncios_del_dia(self, dia: str) -> list[Anuncio]:
        filas = self.con.execute("SELECT datos FROM anuncios WHERE ultima_vez=?", (dia,)).fetchall()
        return [Anuncio.from_dict(json.loads(f[0])) for f in filas]

    # --------------------------------------------------------- cachés
    def traduccion(self, clave: str) -> str | None:
        f = self.con.execute("SELECT texto FROM traducciones WHERE clave=?", (clave,)).fetchone()
        return f[0] if f else None

    def guardar_traduccion(self, clave: str, texto: str) -> None:
        self.con.execute("INSERT OR REPLACE INTO traducciones VALUES (?,?)", (clave, texto))
        self.con.commit()

    def ia(self, clave: str) -> dict | None:
        f = self.con.execute("SELECT datos FROM ia WHERE clave=?", (clave,)).fetchone()
        return json.loads(f[0]) if f else None

    def guardar_ia(self, clave: str, datos: dict) -> None:
        self.con.execute("INSERT OR REPLACE INTO ia VALUES (?,?)", (clave, json.dumps(datos, ensure_ascii=False)))
        self.con.commit()
