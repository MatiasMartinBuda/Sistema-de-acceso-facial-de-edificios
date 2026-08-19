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

import zipfile
import io

def realizar_respaldo_drive():
    """Realiza una copia de seguridad hacia la ruta de Google Drive."""
    drive_dir = settings.get("GOOGLE_DRIVE_DIR") or config.GOOGLE_DRIVE_DIR
    if not drive_dir:
        drive_dir = os.path.join(config.BASE_DIR, "data", "cloud_backup")

    try:
        os.makedirs(drive_dir, exist_ok=True)

        # 1. Respaldar la base de datos SQLite y settings
        dest_db_dir = os.path.join(drive_dir, "data")
        os.makedirs(dest_db_dir, exist_ok=True)
        
        if os.path.exists(config.DB_PATH):
            shutil.copy2(config.DB_PATH, os.path.join(dest_db_dir, "acceso.sqlite3"))
        
        settings_file = getattr(config, "SETTINGS_PATH", os.path.join(config.DATA_DIR, "settings.json"))
        if os.path.exists(settings_file):
            shutil.copy2(settings_file, os.path.join(dest_db_dir, "settings.json"))


        # 2. Respaldar modelo LBPH
        if os.path.exists(config.MODELO_PATH):
            shutil.copy2(config.MODELO_PATH, os.path.join(dest_db_dir, "modelo_lbph.yml"))

        # 3. Respaldar reportes
        local_reportes = os.path.join(config.BASE_DIR, "reportes")
        drive_reportes = os.path.join(drive_dir, "reportes")
        if os.path.exists(local_reportes):
            shutil.copytree(local_reportes, drive_reportes, dirs_exist_ok=True)

        # 4. Respaldar capturas de rostros
        if os.path.exists(config.ROSTROS_DIR):
            drive_rostros = os.path.join(drive_dir, "data", "rostros")
            shutil.copytree(config.ROSTROS_DIR, drive_rostros, dirs_exist_ok=True)

        print(f"[Drive Sync] Respaldo completado en: {drive_dir}")
        return True, f"Respaldo sincronizado correctamente en {drive_dir}"
    except Exception as e:
        msg = f"Error al respaldar en Google Drive: {e}"
        print(f"[Drive Sync] {msg}")
        return False, msg


def restaurar_desde_drive_o_backup():
    """Restaura los datos desde la carpeta de Google Drive o copia persistente si la DB local está vacía o no existe."""
    drive_dir = settings.get("GOOGLE_DRIVE_DIR") or config.GOOGLE_DRIVE_DIR
    rutas_probables = [drive_dir, os.path.join(config.BASE_DIR, "data", "cloud_backup")]

    for r_dir in rutas_probables:
        if not r_dir or not os.path.exists(r_dir):
            continue
        
        db_remote = os.path.join(r_dir, "data", "acceso.sqlite3")
        if os.path.exists(db_remote):
            try:
                os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
                if not os.path.exists(config.DB_PATH) or os.path.getsize(config.DB_PATH) == 0:
                    shutil.copy2(db_remote, config.DB_PATH)
                    print(f"[Drive Restore] DB restaurada exitosamente desde {db_remote}")
                
                remote_rostros = os.path.join(r_dir, "data", "rostros")
                if os.path.exists(remote_rostros):
                    shutil.copytree(remote_rostros, config.ROSTROS_DIR, dirs_exist_ok=True)
                    print(f"[Drive Restore] Rostros restaurados exitosamente desde {remote_rostros}")
                return True
            except Exception as e:
                print(f"[Drive Restore Error] {e}")
    return False


def crear_backup_zip():
    """Genera un archivo .zip en memoria con la base de datos, rostros y configuración."""
    mem_zip = io.BytesIO()
    with zipfile.ZipFile(mem_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        if os.path.exists(config.DB_PATH):
            zf.write(config.DB_PATH, arcname="acceso.sqlite3")
        settings_file = getattr(config, "SETTINGS_PATH", os.path.join(config.DATA_DIR, "settings.json"))
        if os.path.exists(settings_file):
            zf.write(settings_file, arcname="settings.json")

        if os.path.exists(config.MODELO_PATH):
            zf.write(config.MODELO_PATH, arcname="modelo_lbph.yml")
        
        if os.path.exists(config.ROSTROS_DIR):
            for root, _, files in os.walk(config.ROSTROS_DIR):
                for f in files:
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, config.DATA_DIR)
                    zf.write(full_path, arcname=rel_path)

    mem_zip.seek(0)
    return mem_zip

