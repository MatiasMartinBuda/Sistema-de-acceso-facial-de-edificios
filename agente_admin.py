"""
Agente administrativo (Sección 6 del PDF: Módulo de Reportes + Alertas
de Seguridad).

Segundo "asistente" del sistema, pensado para administración/seguridad
en vez de para visitantes. Por los mismos motivos que el asistente de
recepción (chatbot.py), es un motor de reglas/consultas sobre la base
de datos — no un modelo de lenguaje externo, sin costo ni API.

Dos capacidades:
- responder_pregunta(texto): contesta preguntas en lenguaje natural
  sobre los registros de acceso (cuántos, quién, cuándo, etc.)
- detectar_anomalias(horas): escanea los logs recientes buscando
  patrones que ameriten revisión (rechazos repetidos, intentos de
  lista negra, fallos de prueba de vida).
"""
import re
import datetime

import database
try:
    import ia_service
except ImportError:
    ia_service = None



def _contiene(texto, palabras):
    return any(p in texto for p in palabras)


def _rango_hoy():
    hoy = datetime.date.today()
    inicio = datetime.datetime.combine(hoy, datetime.time.min)
    return inicio.isoformat()


def _rango_semana():
    limite = datetime.datetime.now() - datetime.timedelta(days=7)
    return limite.isoformat()


def _contar(where_extra="", params=()):
    with database.get_conn() as conn:
        row = conn.execute(f"SELECT COUNT(*) c FROM logs_acceso WHERE 1=1 {where_extra}", params).fetchone()
        return row["c"]


def responder_pregunta(texto):
    t = (texto or "").lower().strip()
    if not t:
        return "Decime qué querés saber sobre los accesos."

    # ---- último acceso / quién entró ----
    if _contiene(t, ["último acceso", "ultimo acceso", "quién entró", "quien entro",
                     "última persona", "ultima persona", "último evento", "ultimo evento"]):
        with database.get_conn() as conn:
            row = conn.execute("""
                SELECT l.timestamp, l.resultado, l.camino, l.depto_destino, p.nombre, p.apellido
                FROM logs_acceso l LEFT JOIN personas p ON p.id = l.persona_id
                ORDER BY l.timestamp DESC LIMIT 1
            """).fetchone()
        if not row:
            return "Todavía no hay ningún acceso registrado."
        if row["nombre"]:
            quien = f"{row['nombre']} {row['apellido']}"
        elif row["depto_destino"]:
            quien = f"una visita/PIN hacia el depto {row['depto_destino']}"
        else:
            quien = "una persona no identificada"
        return f"El último evento fue el {row['timestamp']}: {row['resultado']} ({quien}, camino {row['camino']})."

    # ---- lista negra ----
    if _contiene(t, ["lista negra"]):
        personas = [p for p in database.listar_personas() if p["lista_negra"]]
        if not personas:
            return "No hay nadie en la lista negra actualmente."
        nombres = ", ".join(f"{p['nombre']} {p['apellido']} (depto {p['depto']})" for p in personas)
        return f"Hay {len(personas)} persona(s) en lista negra: {nombres}."

    # ---- accesos de un depto específico ----
    m = re.search(r"dep(?:to|artamento)\s*([0-9]{1,3}\s?[a-zA-Z]?)", t)
    if m:
        depto = m.group(1).replace(" ", "").upper()
        with database.get_conn() as conn:
            filas = conn.execute("""
                SELECT timestamp, resultado, camino FROM logs_acceso
                WHERE depto_destino = ? ORDER BY timestamp DESC LIMIT 5
            """, (depto,)).fetchall()
        if not filas:
            return f"No encontré accesos registrados para el depto {depto}."
        detalle = "; ".join(f"{f['timestamp']}: {f['resultado']} ({f['camino']})" for f in filas)
        return f"Últimos accesos del depto {depto}: {detalle}."

    # ---- período mencionado ----
    periodo, desde = None, None
    if "hoy" in t:
        periodo, desde = "hoy", _rango_hoy()
    elif "semana" in t:
        periodo, desde = "en los últimos 7 días", _rango_semana()

    # ---- cuántos accesos totales ----
    if _contiene(t, ["cuántos acceso", "cuantos acceso", "cuántas entradas", "cuantas entradas",
                     "accesos hubo", "cuántos entraron", "cuantos entraron"]):
        desde = desde or _rango_semana()
        periodo = periodo or "en los últimos 7 días"
        total = _contar("AND timestamp >= ?", (desde,))
        permitidos = _contar("AND timestamp >= ? AND resultado='permitido'", (desde,))
        denegados = _contar("AND timestamp >= ? AND resultado='denegado'", (desde,))
        return f"Hubo {total} evento(s) {periodo}: {permitidos} permitido(s) y {denegados} denegado(s)."

    # ---- denegados ----
    if _contiene(t, ["denegad", "rechazad"]):
        desde = desde or _rango_semana()
        periodo = periodo or "en los últimos 7 días"
        denegados = _contar("AND timestamp >= ? AND resultado='denegado'", (desde,))
        return f"Se registraron {denegados} acceso(s) denegado(s) {periodo}."

    # ---- permitidos ----
    if _contiene(t, ["permitid", "concedid", "autorizad"]):
        desde = desde or _rango_semana()
        periodo = periodo or "en los últimos 7 días"
        permitidos = _contar("AND timestamp >= ? AND resultado='permitido'", (desde,))
        return f"Se registraron {permitidos} acceso(s) permitido(s) {periodo}."

    # ---- visitas ----
    if _contiene(t, ["visita"]):
        desde = desde or _rango_semana()
        periodo = periodo or "en los últimos 7 días"
        visitas = _contar("AND timestamp >= ? AND camino='C'", (desde,))
        return f"Hubo {visitas} evento(s) de visita (Camino C) {periodo}."

    # ---- personas registradas ----
    if _contiene(t, ["cuántas personas", "cuantas personas", "usuarios registrados", "personas registradas"]):
        n = len(database.listar_personas())
        return f"Hay {n} persona(s) registradas en el sistema."

    # ---- resumen general ----
    if _contiene(t, ["resumen", "reporte", "estado general", "cómo estamos", "como estamos"]):
        r = database.reporte_semanal()
        partes = ", ".join(f"camino {k}: {v}" for k, v in r["por_camino"].items()) or "sin datos"
        return (f"En los últimos 7 días hubo {r['total']} eventos: "
                f"{r['permitidos']} permitidos y {r['denegados']} denegados ({partes}).")

    if ia_service:
        # Darle a la IA el resumen semanal actual como contexto
        contexto = str(database.reporte_semanal())
        prompt_ia = (f"El administrador del edificio pregunta: '{t}'. "
                     f"Datos de accesos recientes en la base de datos: {contexto}. "
                     f"Respondé de forma profesional y precisa.")
        resp = ia_service.obtener_respuesta_ia(prompt_ia, "Sos un asistente de seguridad y administración de un edificio residencial.")
        if resp:
            return resp

    return ("No entendí bien esa consulta. Podés preguntarme cosas como: "
            "'¿cuántos accesos hubo hoy?', '¿quién entró último?', "
            "'accesos del depto 4B', '¿hay alguien en lista negra?' o 'dame un resumen'.")



def detectar_anomalias(horas=24):
    """Escanea los últimos `horas` en busca de patrones que ameriten
    revisión (Sección 6 y 8 del PDF: alertas de seguridad)."""
    alertas = []
    limite = (datetime.datetime.now() - datetime.timedelta(hours=horas)).isoformat()

    with database.get_conn() as conn:
        # muchos rechazos seguidos hacia el mismo depto
        filas = conn.execute("""
            SELECT depto_destino, COUNT(*) c FROM logs_acceso
            WHERE timestamp >= ? AND resultado = 'denegado' AND depto_destino IS NOT NULL AND depto_destino != ''
            GROUP BY depto_destino HAVING c >= 3
        """, (limite,)).fetchall()
        for f in filas:
            alertas.append(f"⚠️ El depto {f['depto_destino']} tuvo {f['c']} accesos denegados "
                            f"en las últimas {horas}hs.")

        # intentos de acceso de gente en lista negra
        intentos_ln = conn.execute("""
            SELECT COUNT(*) c FROM logs_acceso
            WHERE timestamp >= ? AND detalle LIKE '%Lista negra%'
        """, (limite,)).fetchone()["c"]
        if intentos_ln > 0:
            alertas.append(f"🚫 Se detectaron {intentos_ln} intento(s) de acceso de personas en lista negra.")

        # fallos de prueba de vida (posibles fotos/spoofing)
        liveness_fail = conn.execute("""
            SELECT COUNT(*) c FROM logs_acceso
            WHERE timestamp >= ? AND detalle LIKE '%Liveness%'
        """, (limite,)).fetchone()["c"]
        if liveness_fail >= 3:
            alertas.append(f"👁️ Hubo {liveness_fail} fallos de prueba de vida "
                            f"(posibles intentos con foto/pantalla).")

    if not alertas:
        alertas.append(f"✅ No se detectaron anomalías en las últimas {horas} horas.")
    return alertas
