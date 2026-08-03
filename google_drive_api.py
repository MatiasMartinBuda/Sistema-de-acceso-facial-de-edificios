"""
Módulo de integración con el SDK oficial de Google Workspace (Google Drive API v3).

Permite autenticarse mediante Service Account o OAuth 2.0 y subir fotos de
rostros capturados (o cualquier archivo) directamente a una carpeta específica
de Google Drive.

Dependencias necesarias:
    pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
"""
import os
from typing import Optional, Dict, Any

try:
    from google.oauth2 import service_account
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    _GOOGLE_SDK_DISPONIBLE = True
except ImportError:
    _GOOGLE_SDK_DISPONIBLE = False

# Alcance (Scope) necesario para administrar archivos creados en Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def obtener_servicio_drive(
    credentials_path: str = "credentials.json",
    token_path: str = "token.json"
):
    """Inicializa y retorna el cliente de la API v3 de Google Drive.

    Soporta dos métodos de autenticación:
    1. Service Account (`credentials.json` de tipo servicio).
    2. OAuth 2.0 para cuentas personales (`credentials.json` de aplicación de escritorio).
    """
    if not _GOOGLE_SDK_DISPONIBLE:
        raise ImportError(
            "Faltan las librerías del SDK de Google Workspace. "
            "Ejecutá: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        )

    if not os.path.exists(credentials_path):
        raise FileNotFoundError(
            f"No se encontró el archivo de credenciales en '{credentials_path}'. "
            "Descargalo desde Google Cloud Console y colócalo en la raíz del proyecto."
        )

    creds = None

    # Intentar como Service Account primero
    try:
        creds = service_account.Credentials.from_service_account_file(
            credentials_path, scopes=SCOPES
        )
    except Exception:
        # Si falla, intentar como OAuth 2.0 User Credentials
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)

            with open(token_path, 'w', encoding='utf-8') as token_file:
                token_file.write(creds.to_json())

    # Construir el cliente de la API v3 de Google Drive
    service = build('drive', 'v3', credentials=creds)
    return service


def subir_foto_a_drive(
    filepath: str,
    folder_id: Optional[str] = None,
    credentials_path: str = "credentials.json"
) -> Dict[str, Any]:
    """Suba una foto de rostro capturada a una carpeta específica de Google Drive.

    Parámetros:
        filepath: Ruta local del archivo de imagen (ej: 'data/rostros/residente_1.jpg').
        folder_id: (Opcional) ID de la carpeta destino en Google Drive.
        credentials_path: Ruta al archivo credentials.json de Google Cloud.

    Retorna:
        Dict con los datos del archivo subido ('id', 'name', 'webViewLink').
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"El archivo local '{filepath}' no existe.")

    service = obtener_servicio_drive(credentials_path=credentials_path)

    filename = os.path.basename(filepath)

    # Determinar el tipo MIME según la extensión
    ext = filename.lower().split('.')[-1]
    mimetype_map = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'webp': 'image/webp'
    }
    mimetype = mimetype_map.get(ext, 'image/jpeg')

    # Metadatos del archivo a crear en Drive
    file_metadata = {'name': filename}

    if folder_id:
        file_metadata['parents'] = [folder_id]

    media = MediaFileUpload(filepath, mimetype=mimetype, resumable=True)

    print(f"[Google Drive SDK] Subiendo '{filename}' a la carpeta '{folder_id or 'Raíz'}'...")

    # Ejecutar la subida del archivo
    archivo_subido = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, name, webViewLink'
    ).execute()

    print(f"[Google Drive SDK] Archivo subido con éxito. ID: {archivo_subido.get('id')}")

    return {
        "id": archivo_subido.get("id"),
        "nombre": archivo_subido.get("name"),
        "url": archivo_subido.get("webViewLink")
    }


if __name__ == "__main__":
    print("Módulo Google Drive API v3 cargado correctamente.")
