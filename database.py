"""
Memoria persistente del sistema (Sección 6 del TP).

Implementa, sobre SQLite:
- Historial de usuarios (personas registradas, roles, lista negra)
- Decisiones anteriores / logs de acceso (Historial_Accesos)
- Resultados obtenidos (para el módulo de reportes)
- Reglas simples derivadas del historial (ej: 3 rechazos -> lista negra)
"""
import sqlite3
import datetime
import time
import hashlib
from contextlib import contextmanager



import config


def _connect():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS personas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label_lbph INTEGER UNIQUE,        -- id numérico usado por el modelo LBPH
            dni TEXT UNIQUE,
            nombre TEXT NOT NULL,
            apellido TEXT NOT NULL,
            categoria TEXT NOT NULL,          -- administrador | propietario | inquilino | visita_frecuente
            depto TEXT,
            email TEXT,                       -- para notificar visitas (Camino C)
            tipo_acceso TEXT DEFAULT 'permanente',  -- temporal | permanente | residente
            pin TEXT,                         -- código alternativo (Camino B)
            lista_negra INTEGER DEFAULT 0,
            fecha_alta TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Migración: si la DB ya existía de una versión anterior sin "email",
        # se agrega la columna sin perder los datos cargados.
        columnas = [row["name"] for row in conn.execute("PRAGMA table_info(personas)")]
        if "email" not in columnas:
            conn.execute("ALTER TABLE personas ADD COLUMN email TEXT")
        if "telefono" not in columnas:
            conn.execute("ALTER TABLE personas ADD COLUMN telefono TEXT")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS usuarios_app (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nombre TEXT NOT NULL,
            fecha_alta TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)


        conn.execute("""
        CREATE TABLE IF NOT EXISTS logs_acceso (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            persona_id INTEGER,
            dni_declarado TEXT,
            depto_destino TEXT,
            camino TEXT,               -- A | B | C
            resultado TEXT,            -- permitido | denegado | abandono
            score REAL,
            detalle TEXT,
            FOREIGN KEY(persona_id) REFERENCES personas(id)
        );
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS rechazos_visita (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            depto_destino TEXT,
            foto_path TEXT
        );
        """)


# ---------------- Personas ----------------

def siguiente_label_lbph():
    with get_conn() as conn:
        row = conn.execute("SELECT MAX(label_lbph) AS m FROM personas").fetchone()
        return 1 if row["m"] is None else row["m"] + 1


def _normalizar_depto(depto):
    """Los deptos se guardan siempre en mayúsculas y sin espacios extra,
    para que coincidan con lo que extrae el asistente conversacional
    (que también normaliza así), sin importar cómo se haya tipeado."""
    return (depto or "").strip().upper()


def alta_persona(dni, nombre, apellido, categoria, depto, tipo_acceso="permanente", pin=None, email=None, telefono=None):
    label = siguiente_label_lbph()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO personas (label_lbph, dni, nombre, apellido, categoria, depto, tipo_acceso, pin, email, telefono)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (label, dni, nombre, apellido, categoria, _normalizar_depto(depto), tipo_acceso, pin, email, telefono))
    return label


def get_persona_by_label(label):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM personas WHERE label_lbph = ?", (label,)).fetchone()


def get_persona_by_pin(depto, pin):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM personas WHERE depto = ? AND pin = ?", (_normalizar_depto(depto), pin)
        ).fetchone()


def esta_en_lista_negra(label):
    with get_conn() as conn:
        row = conn.execute("SELECT lista_negra FROM personas WHERE label_lbph = ?", (label,)).fetchone()
        return bool(row and row["lista_negra"])


def marcar_lista_negra(label):
    with get_conn() as conn:
        conn.execute("UPDATE personas SET lista_negra = 1 WHERE label_lbph = ?", (label,))


def emails_por_depto(depto):
    """Devuelve la lista de emails de todas las personas asociadas a un
    depto (puede haber propietario + inquilino, por ejemplo). Ignora
    registros sin email cargado."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT email FROM personas WHERE depto = ? AND email IS NOT NULL AND email != ''",
            (_normalizar_depto(depto),)
        ).fetchall()
        return [r["email"] for r in rows]


def actualizar_persona(label, **campos):
    """Actualiza uno o más campos de una persona ya registrada
    (ej: depto, email, pin, categoria, tipo_acceso). No toca la biometría."""
    permitidos = {"dni", "nombre", "apellido", "categoria", "depto",
                  "tipo_acceso", "pin", "email"}
    sets = {k: v for k, v in campos.items() if k in permitidos}
    if not sets:
        return False
    if "depto" in sets:
        sets["depto"] = _normalizar_depto(sets["depto"])
    columnas = ", ".join(f"{k} = ?" for k in sets)
    valores = list(sets.values()) + [label]
    with get_conn() as conn:
        conn.execute(f"UPDATE personas SET {columnas} WHERE label_lbph = ?", valores)
    return True


def eliminar_persona(label):
    """Borra a la persona de la base. Los logs históricos se conservan,
    pero quedan sin el vínculo a la persona (persona_id = NULL)."""
    persona = get_persona_by_label(label)
    if persona is None:
        return False
    with get_conn() as conn:
        conn.execute("UPDATE logs_acceso SET persona_id = NULL WHERE persona_id = ?", (persona["id"],))
        conn.execute("DELETE FROM personas WHERE id = ?", (persona["id"],))
    return True


def listar_logs_recientes(limite=500):
    with get_conn() as conn:
        return conn.execute("""
            SELECT l.timestamp, l.camino, l.resultado, l.score, l.depto_destino,
                   l.dni_declarado, l.detalle,
                   p.nombre, p.apellido
            FROM logs_acceso l
            LEFT JOIN personas p ON p.id = l.persona_id
            ORDER BY l.timestamp DESC
            LIMIT ?
        """, (limite,)).fetchall()


def listar_personas():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM personas ORDER BY apellido").fetchall()


# ---------------- Logs / auditoría ----------------

def log_evento(camino, resultado, persona_id=None, dni_declarado=None,
               depto_destino=None, score=None, detalle=""):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO logs_acceso (persona_id, dni_declarado, depto_destino, camino, resultado, score, detalle)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (persona_id, dni_declarado, depto_destino, camino, resultado, score, detalle))


def registrar_rechazo_visita(depto_destino, foto_path=None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO rechazos_visita (depto_destino, foto_path) VALUES (?, ?)",
            (_normalizar_depto(depto_destino), foto_path)
        )


def rechazos_recientes_por_depto(depto_destino, ventana_horas=24):
    """Cuenta cuántas veces fue rechazada una visita hacia ESE depto en
    particular en la última ventana de tiempo (aproximación al
    'rechazado 3 veces' de la Sección 6 del TP)."""
    limite = (datetime.datetime.now() - datetime.timedelta(hours=ventana_horas)).isoformat()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM rechazos_visita WHERE timestamp >= ? AND depto_destino = ?",
            (limite, _normalizar_depto(depto_destino))
        ).fetchone()
        return row["c"]


def reporte_semanal():
    """Módulo de Reportes (Sección 6): totales de la última semana."""
    limite = (datetime.datetime.now() - datetime.timedelta(days=7)).isoformat()
    with get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) c FROM logs_acceso WHERE timestamp >= ?", (limite,)
        ).fetchone()["c"]
        permitidos = conn.execute(
            "SELECT COUNT(*) c FROM logs_acceso WHERE timestamp >= ? AND resultado='permitido'", (limite,)
        ).fetchone()["c"]
        denegados = conn.execute(
            "SELECT COUNT(*) c FROM logs_acceso WHERE timestamp >= ? AND resultado='denegado'", (limite,)
        ).fetchone()["c"]
        por_camino = conn.execute(
            "SELECT camino, COUNT(*) c FROM logs_acceso WHERE timestamp >= ? GROUP BY camino", (limite,)
        ).fetchall()
        return {
            "total": total,
            "permitidos": permitidos,
            "denegados": denegados,
            "por_camino": {r["camino"]: r["c"] for r in por_camino},
        }


def insertar_persona(nombre, apellido, depto, categoria="propietario", tipo_acceso="permanente", pin="", dni=None, email=None, telefono=None):
    """Wrapper compatible con la API Web para insertar una persona en la base de datos."""
    if not dni:
        dni = f"WEB_{int(time.time() * 1000)}"
    return alta_persona(dni, nombre, apellido, categoria, depto, tipo_acceso, pin or None, email, telefono)


def insertar_log(persona_id=None, depto_destino=None, camino="A", resultado="permitido", score=None, detalle="", dni_declarado=None):
    """Wrapper compatible con la API Web para registrar eventos de acceso."""
    return log_evento(camino=camino, resultado=resultado, persona_id=persona_id, dni_declarado=dni_declarado, depto_destino=depto_destino, score=score, detalle=detalle)


# ---------------- Autenticación Usuarios App ----------------

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def crear_usuario_app(username, password, nombre):
    p_hash = hash_password(password)
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO usuarios_app (username, password_hash, nombre) VALUES (?, ?, ?)",
                (username.strip().lower(), p_hash, nombre.strip())
            )
        return True
    except sqlite3.IntegrityError:
        return False


def validar_usuario_app(username, password):
    p_hash = hash_password(password)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, username, nombre FROM usuarios_app WHERE username = ? AND password_hash = ?",
            (username.strip().lower(), p_hash)
        ).fetchone()
        if row:
            return dict(row)
    return None


def contar_usuarios_app():
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM usuarios_app").fetchone()
        return row["c"]


def cambiar_lista_negra(label, en_lista_negra: bool):
    with get_conn() as conn:
        val = 1 if en_lista_negra else 0
        conn.execute("UPDATE personas SET lista_negra = ? WHERE label_lbph = ?", (val, label))


def obtener_whatsapp_depto(depto):
    """Devuelve las personas con teléfono registrado asignadas a ese depto."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, nombre, apellido, depto, telefono FROM personas WHERE depto = ? AND telefono IS NOT NULL AND telefono != ''",
            (_normalizar_depto(depto),)
        ).fetchall()
        return [dict(r) for r in rows]


