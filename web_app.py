"""
Servidor Backend Web (FastAPI) para el Sistema Inteligente de Acceso Residencial.

Permite ejecutar la aplicación en el navegador con acceso a la cámara web en vivo,
reconocimiento facial LBPH, enrolamiento de residentes, chatbot con IA y
panel administrativo.
"""
import os
import base64
import cv2
import numpy as np
from typing import List, Optional
from pydantic import BaseModel

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
import shutil
import urllib.parse

import config
import settings
import database
import recognizer
import chatbot
import agente_admin
import drive_sync
import reportes_excel

# Inicializar base de datos y modelo al arrancar
database.init_db()
os.makedirs(config.ROSTROS_DIR, exist_ok=True)
os.makedirs(config.REPORTES_DIR, exist_ok=True)

app = FastAPI(title="Sistema Inteligente de Acceso Residencial Web", version="2.0")

# Motor de reconocimiento facial
engine = recognizer.FaceEngine()
asistente_bot = chatbot.AsistenteConversacional()

# Servir archivos estáticos (HTML, CSS, JS)
STATIC_DIR = os.path.join(config.BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# --- Schemas Pydantic ---
class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    nombre: str

class RecognerRequest(BaseModel):
    image: str  # data:image/jpeg;base64,...

class EnrolarRequest(BaseModel):
    nombre: str
    apellido: str
    depto: str
    categoria: str = "propietario"
    tipo_acceso: str = "residente"
    pin: str = ""
    telefono: str = ""
    email: str = ""
    fotos_base64: List[str]

class AgregarFotosRequest(BaseModel):
    label: int
    fotos_base64: List[str]

class ListaNegraRequest(BaseModel):
    lista_negra: bool

class VisitaWhatsappRequest(BaseModel):
    depto: str
    nombre_visita: str

class ChatRequest(BaseModel):
    mensaje: str

class AdminQuestionRequest(BaseModel):
    pregunta: str



# --- Helper para decodificar base64 a imagen OpenCV ---
def decodificar_base64_a_cv2(b64_str: str) -> np.ndarray:
    if "," in b64_str:
        b64_str = b64_str.split(",")[1]
    img_data = base64.b64decode(b64_str)
    nparr = np.frombuffer(img_data, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    return frame


@app.get("/", response_class=HTMLResponse)
def index_page():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Sistema de Acceso Web iniciado. static/index.html no encontrado.</h1>"


@app.get("/api/auth/status")
def api_auth_status():
    total_users = database.contar_usuarios_app()
    return {"registrado": total_users > 0}


@app.post("/api/auth/register")
def api_auth_register(req: RegisterRequest):
    if not req.username.strip() or not req.password.strip():
        return {"exito": False, "mensaje": "Usuario y contraseña son obligatorios."}
    ok = database.crear_usuario_app(req.username, req.password, req.nombre)
    if ok:
        return {"exito": True, "mensaje": "Cuenta de administrador creada con éxito."}
    return {"exito": False, "mensaje": "El nombre de usuario ya existe."}


@app.post("/api/auth/login")
def api_auth_login(req: LoginRequest):
    usr = database.validar_usuario_app(req.username, req.password)
    if usr:
        return {"exito": True, "usuario": usr, "mensaje": "Inicio de sesión correcto."}
    return {"exito": False, "mensaje": "Usuario o contraseña incorrectos."}


@app.post("/api/reconocer")
def api_reconocer(req: RecognerRequest):
    """Procesa un fotograma de la webcam web y evalúa reconocimiento + liveness."""
    try:
        frame = decodificar_base64_a_cv2(req.image)
        if frame is None:
            raise HTTPException(status_code=400, detail="Imagen no válida")

        resultado = engine.evaluar_fotograma(frame)
        
        res_dict = {
            "estado": resultado.get("estado", "buscando"),
            "es_residente": resultado.get("es_residente", False),
            "nombre": resultado.get("nombre", ""),
            "depto": resultado.get("depto", ""),
            "score": round(resultado.get("score", 0), 1),
            "parpadeo_ok": resultado.get("parpadeo_ok", False),
            "camino": resultado.get("camino", ""),
            "mensaje": resultado.get("mensaje", "")
        }

        if res_dict["estado"] == "permitido":
            persona_id = resultado.get("persona_id")
            database.insertar_log(
                persona_id=persona_id,
                depto_destino=res_dict["depto"],
                camino="A",
                resultado="permitido",
                detalle=f"Reconocimiento facial en vivo (Confianza: {res_dict['score']}%)"
            )

        return res_dict
    except Exception as e:
        return {"estado": "error", "mensaje": str(e)}


@app.post("/api/enrolar")
def api_enrolar(req: EnrolarRequest):
    """Enrola a un nuevo usuario guardando sus fotos y reentrenando el modelo LBPH."""
    try:
        if not req.nombre.strip() or not req.apellido.strip():
            return {"exito": False, "mensaje": "Nombre y apellido son obligatorios."}

        # 1. Insertar persona en la base de datos
        persona_id = database.insertar_persona(
            nombre=req.nombre.strip(),
            apellido=req.apellido.strip(),
            depto=req.depto.strip().upper(),
            categoria=req.categoria,
            tipo_acceso=req.tipo_acceso,
            pin=req.pin.strip(),
            telefono=req.telefono.strip(),
            email=req.email.strip()
        )

        # 2. Guardar las fotos decodificadas usando el ID numérico como nombre de carpeta
        carpeta_persona = os.path.join(config.ROSTROS_DIR, str(persona_id))
        os.makedirs(carpeta_persona, exist_ok=True)


        contador = 0
        for b64 in req.fotos_base64:
            frame = decodificar_base64_a_cv2(b64)
            if frame is None or frame.size == 0:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = engine.detectar_rostros(gray)
            if len(faces) == 0:
                faces = engine.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(40, 40))

            if len(faces) > 0:
                (x, y, w, h) = faces[0]
                rostro_crop = cv2.resize(gray[y:y+h, x:x+w], (200, 200))
            else:
                # Recorte central garantizado
                h_f, w_f = gray.shape
                ch, cw = int(h_f * 0.6), int(w_f * 0.6)
                cy, cx = int((h_f - ch) / 2), int((w_f - cw) / 2)
                rostro_crop = cv2.resize(gray[cy:cy+ch, cx:cx+cw], (200, 200))

            contador += 1
            img_path = os.path.join(carpeta_persona, f"foto_{contador:03d}.jpg")
            cv2.imwrite(img_path, rostro_crop)

        if contador == 0:
            return {"exito": False, "mensaje": "No se pudieron procesar fotogramas para el enrolamiento."}

        # 3. Reentrenar el reconocedor LBPH
        engine.entrenar_modelo()

        return {
            "exito": True,
            "mensaje": f"Persona {req.nombre} {req.apellido} enrolada con éxito ({contador} fotos procesadas).",
            "persona_id": persona_id
        }

    except Exception as e:

        return {"exito": False, "mensaje": str(e)}


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    """Interactúa con el asistente virtual conversacional."""
    msg_bot, evento = asistente_bot.responder(req.mensaje)
    return {
        "respuesta": msg_bot,
        "estado_actual": asistente_bot.estado,
        "evento": evento
    }


@app.post("/api/chat/iniciar")
def api_chat_iniciar():
    msg = asistente_bot.iniciar()
    return {"respuesta": msg}


@app.get("/api/admin/stats")
def api_admin_stats():
    """Obtiene datos de resumen y anomalías para el panel administrativo."""
    personas = database.listar_personas()
    alertas = agente_admin.detectar_anomalias(horas=24)
    reporte_7dias = database.reporte_semanal()
    
    return {
        "total_personas": len(personas),
        "alertas": alertas,
        "resumen_semanal": reporte_7dias,
        "personas": [
            {
                "id": p["id"],
                "nombre": f"{p['nombre']} {p['apellido']}",
                "depto": p["depto"],
                "categoria": p["categoria"],
                "lista_negra": bool(p["lista_negra"])
            }
            for p in personas
        ]
    }


@app.post("/api/admin/pregunta")
def api_admin_pregunta(req: AdminQuestionRequest):
    """Responde consultas administrativas usando IA / Reglas."""
    respuesta = agente_admin.responder_pregunta(req.pregunta)
    return {"respuesta": respuesta}


# --- Gestor de Usuarios Enrolados (Módulos 3, 4 y 5) ---

@app.get("/api/usuarios")
def api_listar_usuarios():
    personas = database.listar_personas()
    res = []
    for p in personas:
        label = p["label_lbph"]
        carpeta = os.path.join(config.ROSTROS_DIR, str(label))
        cant_fotos = len([f for f in os.listdir(carpeta) if f.lower().endswith(('.jpg', '.png'))]) if os.path.exists(carpeta) else 0
        res.append({
            "id": p["id"],
            "label_lbph": label,
            "nombre": f"{p['nombre']} {p['apellido']}",
            "nombre_raw": p["nombre"],
            "apellido_raw": p["apellido"],
            "depto": p["depto"],
            "categoria": p["categoria"],
            "tipo_acceso": p["tipo_acceso"],
            "pin": p["pin"] or "",
            "email": p["email"] or "",
            "telefono": p["telefono"] or "",
            "lista_negra": bool(p["lista_negra"]),
            "cant_fotos": cant_fotos,
            "fecha_alta": p["fecha_alta"]
        })
    return res


@app.post("/api/usuarios/agregar-fotos")
def api_agregar_fotos_usuario(req: AgregarFotosRequest):
    """Módulo 3: Agregar fotos a usuario existente."""
    try:
        persona = database.get_persona_by_label(req.label)
        if not persona:
            return {"exito": False, "mensaje": "Usuario no encontrado."}

        carpeta_persona = os.path.join(config.ROSTROS_DIR, str(req.label))
        os.makedirs(carpeta_persona, exist_ok=True)
        existentes = len([f for f in os.listdir(carpeta_persona) if f.lower().endswith(('.jpg', '.png'))])

        contador = existentes
        for b64 in req.fotos_base64:
            frame = decodificar_base64_a_cv2(b64)
            if frame is None or frame.size == 0:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = engine.detectar_rostros(gray)
            if len(faces) == 0:
                faces = engine.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(40, 40))

            if len(faces) > 0:
                (x, y, w, h) = faces[0]
                rostro_crop = cv2.resize(gray[y:y+h, x:x+w], (200, 200))
            else:
                h_f, w_f = gray.shape
                ch, cw = int(h_f * 0.6), int(w_f * 0.6)
                cy, cx = int((h_f - ch) / 2), int((w_f - cw) / 2)
                rostro_crop = cv2.resize(gray[cy:cy+ch, cx:cx+cw], (200, 200))

            contador += 1
            img_path = os.path.join(carpeta_persona, f"foto_{contador:03d}.jpg")
            cv2.imwrite(img_path, rostro_crop)

        engine.entrenar_modelo()
        nuevas = contador - existentes
        return {"exito": True, "mensaje": f"Se agregaron {nuevas} fotos nuevas y se reentrenó el modelo LBPH."}
    except Exception as e:
        return {"exito": False, "mensaje": str(e)}


@app.delete("/api/usuarios/{label}")
def api_eliminar_usuario(label: int):
    """Módulo 4: Borrar usuario."""
    try:
        ok = database.eliminar_persona(label)
        if not ok:
            return {"exito": False, "mensaje": "No se encontró el usuario a eliminar."}

        carpeta = os.path.join(config.ROSTROS_DIR, str(label))
        if os.path.exists(carpeta):
            shutil.rmtree(carpeta, ignore_errors=True)

        engine.entrenar_modelo()
        return {"exito": True, "mensaje": "Usuario eliminado correctamente."}
    except Exception as e:
        return {"exito": False, "mensaje": str(e)}


@app.post("/api/usuarios/{label}/lista-negra")
def api_cambiar_lista_negra(label: int, req: ListaNegraRequest):
    try:
        database.cambiar_lista_negra(label, req.lista_negra)
        estado_str = "agregado a" if req.lista_negra else "removido de"
        return {"exito": True, "mensaje": f"Usuario {estado_str} la lista negra."}
    except Exception as e:
        return {"exito": False, "mensaje": str(e)}


# --- Módulo 6: Generar y Descargar Reporte Excel (.xlsx) ---

@app.get("/api/reporte/excel")
def api_descargar_excel():
    try:
        ruta_archivo = reportes_excel.generar_reporte_xlsx()
        filename = os.path.basename(ruta_archivo)
        return FileResponse(
            path=ruta_archivo,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Notificaciones por WhatsApp para Visitas (Camino C) ---

@app.post("/api/visita/whatsapp")
def api_visita_whatsapp(req: VisitaWhatsappRequest):
    try:
        contactos = database.obtener_whatsapp_depto(req.depto)
        if not contactos:
            return {
                "exito": False,
                "mensaje": f"El departamento {req.depto} no tiene registrado ningún número de celular/WhatsApp."
            }

        resultados = []
        for c in contactos:
            raw_phone = c["telefono"].replace("+", "").replace(" ", "").replace("-", "")
            texto_msg = (
                f"🏢 *SISTEMA DE ACCESO EDIFICIO*\n\n"
                f"Hola {c['nombre']}, en la puerta del edificio se encuentra *{req.nombre_visita}* "
                f"solicitando ingresar al Depto *{req.depto}*.\n\n"
                f"¿Autoriza su ingreso? Responda SÍ o NO a esta recepción."
            )
            encoded_txt = urllib.parse.quote(texto_msg)
            url_wa = f"https://wa.me/{raw_phone}?text={encoded_txt}"
            resultados.append({
                "nombre": f"{c['nombre']} {c['apellido']}",
                "telefono": c["telefono"],
                "url": url_wa,
                "mensaje": texto_msg
            })

        return {"exito": True, "contactos": resultados}
    except Exception as e:
        return {"exito": False, "mensaje": str(e)}



@app.post("/api/drive/sync")
def api_drive_sync():
    """Ejecuta el respaldo en Google Drive."""
    ok, msg = drive_sync.realizar_respaldo_drive()
    return {"exito": ok, "mensaje": msg}


@app.get("/api/config")
def api_get_config():
    """Obtiene la configuración actual."""
    return settings.get_all()


@app.post("/api/config")
async def api_post_config(request: Request):
    """Guarda nuevos parámetros en caliente en data/settings.json."""
    try:
        nuevos_datos = await request.json()
        settings.guardar(nuevos_datos)
        return {"exito": True, "mensaje": "Configuración guardada correctamente."}
    except Exception as e:
        return {"exito": False, "mensaje": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_app:app", host="0.0.0.0", port=8000, reload=True)

