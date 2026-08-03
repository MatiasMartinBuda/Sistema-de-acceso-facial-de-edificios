"""
Configuración del Sistema Inteligente de Acceso Residencial
Basado en TP1 - UTN FRBA - IA Aplicada a Organizaciones
(Budassi, Paredes, Quiñones)

Todos los "parámetros de negocio" del documento están acá para
poder ajustarlos sin tocar el código.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Ruta de Google Drive para respaldos y reportes ---
GOOGLE_DRIVE_DIR = r"G:\Mi unidad\Proyecto\sistema_acceso_facial"
SINCRONIZAR_DRIVE = True

DATA_DIR = os.path.join(BASE_DIR, "data")
ROSTROS_DIR = os.path.join(DATA_DIR, "rostros")
CAPTURAS_VISITAS_DIR = os.path.join(DATA_DIR, "capturas_visitas")
MODELO_PATH = os.path.join(DATA_DIR, "modelo_lbph.yml")
DB_PATH = os.path.join(DATA_DIR, "acceso.sqlite3")

# Si la carpeta de Google Drive existe en la PC, guardar reportes directamente allí
if SINCRONIZAR_DRIVE and os.path.exists(os.path.dirname(GOOGLE_DRIVE_DIR)):
    REPORTES_DIR = os.path.join(GOOGLE_DRIVE_DIR, "reportes")
else:
    REPORTES_DIR = os.path.join(BASE_DIR, "reportes")

IMAGEN_PUERTA_ABIERTA = os.path.join(DATA_DIR, "assets", "puerta_abierta.png")


# --- Cámara ---
CAMERA_INDEX = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# --- Detección / Reconocimiento (Sección 5 y 7 del PDF) ---
# LBPH: a menor "confidence" mejor es el match (es una distancia, no un %).
# Lo convertimos a un score 0-100 para que se lea como "umbral de confianza".
UMBRAL_CONFIANZA_RESIDENTE = 60      # % mínimo para Camino A directo
UMBRAL_CONFIANZA_AREA_CRITICA = 75   # ej. sala de servidores / admin (no usado en demo pero configurable)
FRAMES_MINIMOS_ROSTRO_ESTABLE = 8    # frames seguidos con rostro detectado antes de evaluar
LBPH_CONFIDENCE_MAX = 130            # distancia LBPH que mapea a score = 0

# --- Prueba de vida (Anti-Spoofing simplificado con parpadeo) ---
LIVENESS_TIMEOUT_SEG = 4.0           # "esperar 4 segundos" (freno mencionado en el PDF)
LIVENESS_REQUIERE_PARPADEO = True

# --- Timeouts (Sección 7. Límites operativos) ---
TIMEOUT_BIOMETRICO_SEG = 2.5         # tiempo máx. de cómputo del reconocimiento
TIMEOUT_RESPUESTA_EXTERNA_SEG = 3.0  # timeout de "consulta a servidor" (simulado)
TIMEOUT_LLAMADA_VISITA_SEG = 15      # tiempo que "suena" la videollamada al depto (Camino C)
TIMEOUT_ABANDONO_SEG = 10            # si no hay respuesta, vuelve al estado de espera (Escenario D)

# --- Reglas de negocio (Sección 7 y 6. Memoria persistente) ---
MAX_REINTENTOS_FALLIDOS = 3          # bloqueo por reintentos fallidos
RECHAZOS_PARA_LISTA_NEGRA = 3        # "rechazado 3 veces en diferentes deptos" -> lista negra

# --- Enrolamiento ---
FOTOS_POR_ENROLAMIENTO = 20          # varias fotos para mejorar detección (Sección 8, aceleradores)

# --- Asistente conversacional (Camino B y C) ---
IA_VOZ_HABILITADA = True   # si está en False, el asistente solo usa texto
DURACION_PUERTA_MS = 6000  # cuánto tiempo queda visible el cartel de bienvenida

# --- Notificaciones por email (Agente de Intercomunicación y Notificaciones) ---
# Completá estos datos con una cuenta de correo propia para poder enviar
# notificaciones reales. Con Gmail necesitás generar una "contraseña de
# aplicación" (no la contraseña normal de la cuenta):
# https://myaccount.google.com/apppasswords
NOTIFICAR_VISITAS_POR_EMAIL = True   # poné False para desactivar el envío de mails

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "tu_correo@gmail.com"        # cuenta que envía la notificación
SMTP_PASSWORD = "tu_contraseña_de_app"    # contraseña de aplicación, no la normal
SMTP_FROM_NAME = "Sistema de Acceso - Edificio"

# --- IA Generativa (Google Gemini / Ollama) ---
USAR_IA_GENERATIVA = True               # Si se desactiva, usará únicamente reglas estáticas
IA_PROVIDER = "ollama"                  # "auto", "gemini" u "ollama"
GEMINI_API_KEY = ""                     # Podés pegar acá tu API Key de Google AI Studio o ingresarla por GUI
OLLAMA_MODEL = "mistral"                # Modelo local detectado en tu PC (mistral)
OLLAMA_HOST = "http://localhost:11434"


