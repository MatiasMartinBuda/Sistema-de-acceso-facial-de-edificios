"""
Agente de Registros / Enrolador (Sección 4 del PDF).

Registra una persona nueva:
1. Pide sus datos (DNI, nombre, apellido, categoría, depto, PIN opcional).
2. Captura varias fotos del rostro por webcam (mejora detección, Sección 8).
3. Da de alta en la base de datos (memoria persistente).
4. Reentrena el modelo LBPH con el nuevo rostro incluido.

Uso: python enroll.py
"""
import os
import cv2

import config
import database
from recognizer import FaceEngine


def pedir_datos():
    print("=== Enrolamiento de nueva persona ===")
    dni = input("DNI: ").strip()
    nombre = input("Nombre: ").strip()
    apellido = input("Apellido: ").strip()
    print("Categoría: [1] Administrador  [2] Propietario  [3] Inquilino  [4] Visita frecuente")
    cat_map = {"1": "administrador", "2": "propietario", "3": "inquilino", "4": "visita_frecuente"}
    categoria = cat_map.get(input("Opción: ").strip(), "inquilino")
    depto = input("Departamento (ej: 4B): ").strip()
    print("Tipo de acceso: [1] Permanente  [2] Temporal  [3] Residente")
    tipo_map = {"1": "permanente", "2": "temporal", "3": "residente"}
    tipo_acceso = tipo_map.get(input("Opción: ").strip(), "permanente")
    pin = input("PIN alternativo (Camino B, opcional, ENTER para omitir): ").strip() or None
    email = input("Email (para notificarte cuando llegue una visita, opcional): ").strip() or None
    return dni, nombre, apellido, categoria, depto, tipo_acceso, pin, email


def capturar_rostros(label, engine: FaceEngine):
    carpeta = os.path.join(config.ROSTROS_DIR, str(label))
    os.makedirs(carpeta, exist_ok=True)

    cap = cv2.VideoCapture(config.CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)

    if not cap.isOpened():
        print("No se pudo abrir la cámara. Revisá conexión/permisos.")
        return 0

    print(f"Mirá a la cámara. Se van a capturar {config.FOTOS_POR_ENROLAMIENTO} fotos.")
    print("Presioná 'q' para cancelar en cualquier momento.")

    capturas = 0
    while capturas < config.FOTOS_POR_ENROLAMIENTO:
        ok, frame = cap.read()
        if not ok:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        rostros = engine.detectar_rostros(gray)

        for (x, y, w, h) in rostros:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            recorte = gray[y:y + h, x:x + w]
            recorte = cv2.resize(recorte, (200, 200))
            path = os.path.join(carpeta, f"{capturas:03d}.jpg")
            cv2.imwrite(path, recorte)
            capturas += 1
            break  # una cara por frame

        cv2.putText(frame, f"Capturas: {capturas}/{config.FOTOS_POR_ENROLAMIENTO}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imshow("Enrolamiento - presione q para cancelar", frame)

        if cv2.waitKey(150) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    return capturas


def main():
    os.makedirs(config.DATA_DIR, exist_ok=True)
    database.init_db()
    engine = FaceEngine()

    dni, nombre, apellido, categoria, depto, tipo_acceso, pin, email = pedir_datos()
    label = database.alta_persona(dni, nombre, apellido, categoria, depto, tipo_acceso, pin, email)

    capturas = capturar_rostros(label, engine)
    if capturas == 0:
        print("No se capturaron fotos. El enrolamiento quedó incompleto (sin biometría).")
        return

    print("Reentrenando modelo con el nuevo rostro...")
    engine.entrenar_desde_disco()
    print(f"Listo. {nombre} {apellido} ({categoria}, depto {depto}) fue registrado con {capturas} fotos.")


if __name__ == "__main__":
    main()
