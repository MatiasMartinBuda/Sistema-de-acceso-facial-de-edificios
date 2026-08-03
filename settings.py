"""
Configuración editable en caliente desde la interfaz gráfica.

`config.py` tiene los valores por defecto (los que definieron en el TP).
Este módulo permite que la pantalla "Configuración" de la GUI los pise
sin tocar código: los guarda en data/settings.json y de ahí en más
todos los módulos (notificaciones, reconocimiento, enrolamiento) leen
los valores actuales llamando a settings.get("NOMBRE_CAMPO").
"""
import json
import os

import config

CAMPOS_EDITABLES = [
    "CAMERA_INDEX",
    "UMBRAL_CONFIANZA_RESIDENTE",
    "LIVENESS_REQUIERE_PARPADEO",
    "FOTOS_POR_ENROLAMIENTO",
    "IA_VOZ_HABILITADA",
    "DURACION_PUERTA_MS",
    "NOTIFICAR_VISITAS_POR_EMAIL",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_FROM_NAME",
    "USAR_IA_GENERATIVA",
    "IA_PROVIDER",
    "GEMINI_API_KEY",
    "OLLAMA_MODEL",
    "OLLAMA_HOST",
    "GOOGLE_DRIVE_DIR",
    "SINCRONIZAR_DRIVE",
]

_SETTINGS_PATH = os.path.join(config.DATA_DIR, "settings.json")
_cache = None


def _cargar():
    global _cache
    if _cache is not None:
        return _cache

    datos = {campo: getattr(config, campo) for campo in CAMPOS_EDITABLES}
    if os.path.exists(_SETTINGS_PATH):
        try:
            with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
                guardado = json.load(f)
            for k, v in guardado.items():
                if k in CAMPOS_EDITABLES:
                    datos[k] = v
        except Exception:
            pass  # si el JSON está corrupto, seguimos con los valores por defecto

    _cache = datos
    return _cache


def get(campo):
    return _cargar().get(campo, getattr(config, campo, None))


def get_all():
    return dict(_cargar())


def guardar(nuevos: dict):
    datos = _cargar()
    for k, v in nuevos.items():
        if k in CAMPOS_EDITABLES:
            datos[k] = v

    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)

    global _cache
    _cache = datos
