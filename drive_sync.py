"""
Módulo de respaldo y sincronización con Google Drive para Escritorio.

Copia automáticamente la base de datos `acceso.sqlite3`, la carpeta `rostros/`
y los reportes Excel generados hacia la unidad local de Google Drive
configurada en `GOOGLE_DRIVE_DIR`.
"""
import os
import shutil
import settings
import config

def realizar_respaldo_drive():
    """Realiza una copia de seguridad hacia la ruta de Google Drive."""
    if not settings.get("SINCRONIZAR_DRIVE"):
        return False, "La sincronización con Drive está desactivada en la configuración."

    drive_dir = settings.get("GOOGLE_DRIVE_DIR") or config.GOOGLE_DRIVE_DIR
    if not drive_dir:
        return False, "No se ha configurado ninguna ruta de Google Drive."

    try:
        os.makedirs(drive_dir, exist_ok=True)

        # 1. Respaldar la base de datos SQLite
        if os.path.exists(config.DB_PATH):
            dest_db_dir = os.path.join(drive_dir, "data")
            os.makedirs(dest_db_dir, exist_ok=True)
            shutil.copy2(config.DB_PATH, os.path.join(dest_db_dir, "acceso.sqlite3"))

        # 2. Respaldar reportes
        local_reportes = os.path.join(config.BASE_DIR, "reportes")
        drive_reportes = os.path.join(drive_dir, "reportes")
        if os.path.exists(local_reportes):
            shutil.copytree(local_reportes, drive_reportes, dirs_exist_ok=True)

        # 3. Respaldar capturas de rostros
        if os.path.exists(config.ROSTROS_DIR):
            drive_rostros = os.path.join(drive_dir, "data", "rostros")
            shutil.copytree(config.ROSTROS_DIR, drive_rostros, dirs_exist_ok=True)

        print(f"[Drive Sync] Respaldo completado en: {drive_dir}")
        return True, f"Respaldo sincronizado correctamente en {drive_dir}"
    except Exception as e:
        msg = f"Error al respaldar en Google Drive: {e}"
        print(f"[Drive Sync] {msg}")
        return False, msg
