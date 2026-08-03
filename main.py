"""
Sistema Inteligente de Acceso Residencial por Reconocimiento Facial
Implementación funcional basada en el TP1 (Sección 5: Orquestación cíclica
y los diagramas de flujo de la Sección "Diagramas de Flujo").

Ciclo (se repite indefinidamente, como describe el PDF):
  1. Observación      -> detecta presencia frente a la cámara
  2. Análisis          -> prueba de vida (parpadeo) + genera predicción LBPH
  3. Planificación      -> compara contra umbral / lista negra / decide camino
  4. Acción             -> "abre puerta" (simulado) o deniega
  5. Evaluación         -> registra resultado y latencia en la base
  6. Aprendizaje         -> (en este demo: quedará para una futura mejora,
                             ver README) y vuelve al paso 1.

Ejecutar:  python main.py
Requisito previo: haber enrolado al menos una persona con enroll.py
"""
import time
import cv2

import config
import database
import notificaciones
from recognizer import FaceEngine, DetectorDeParpadeo


def abrir_puerta(mensaje):
    # "Acción (Ejecución Física)" del PDF. Acá se simula; en un tótem real
    # esto dispararía el relé del imán electromagnético.
    print(f"\n🔓 PUERTA ABIERTA — {mensaje}\n")


def denegar(mensaje):
    print(f"\n⛔ ACCESO DENEGADO — {mensaje}\n")


def flujo_camino_A(persona, score):
    """Usuario reconocido directamente (Escenario A de Interfaces)."""
    print(f"¡Hola, {persona['nombre']} {persona['apellido']}! Bienvenido/a.")
    abrir_puerta(f"{persona['nombre']} {persona['apellido']} - depto {persona['depto']} (score {score}%)")
    database.log_evento("A", "permitido", persona_id=persona["id"],
                         dni_declarado=persona["dni"], score=score,
                         detalle="Reconocimiento directo")


def flujo_camino_B():
    """No reconocido, declara ser residente -> pide código/PIN (Camino B)."""
    print("No te reconozco. ¿Sos residente del edificio? (s/n): ", end="")
    resp = input().strip().lower()
    if resp != "s":
        return False  # pasa a Camino C

    depto = input("Ingresá tu número de depto: ").strip()
    pin = input("Ingresá tu código/PIN de la app: ").strip()
    persona = database.get_persona_by_pin(depto, pin)

    if persona and not persona["lista_negra"]:
        print("Acceso concedido. Recordá actualizar tu foto en la app.")
        abrir_puerta(f"{persona['nombre']} {persona['apellido']} vía PIN - depto {depto}")
        database.log_evento("B", "permitido", persona_id=persona["id"],
                             depto_destino=depto, detalle="Validado por PIN")
    else:
        denegar("Datos no válidos. Se deriva a guardia/administración.")
        database.log_evento("B", "denegado", depto_destino=depto,
                             detalle="PIN inválido o persona en lista negra")
    return True


def flujo_camino_C():
    """Visita / proveedor: pide depto y simula videollamada al residente."""
    depto = input("Por favor, ingresá el número de depto al que te dirigís (ej: 4B): ").strip()

    rechazos_previos = database.rechazos_recientes_por_depto(depto)
    if rechazos_previos >= config.RECHAZOS_PARA_LISTA_NEGRA:
        denegar("Esta visita fue rechazada varias veces recientemente. Se alerta a guardia.")
        database.log_evento("C", "denegado", depto_destino=depto,
                             detalle="Bloqueo automático por rechazos repetidos")
        return

    emails = database.emails_por_depto(depto)
    notificaciones.enviar_notificacion_visita(
        depto, emails, detalle="Se está intentando comunicar por videollamada al tótem."
    )

    print(f"Llamando al departamento {depto}... (tenés {config.TIMEOUT_LLAMADA_VISITA_SEG}s)")
    print("[Simulación] ¿El residente autoriza el ingreso? (s = sí / n = no / ENTER = no atiende): ", end="")
    resp = input().strip().lower()

    if resp == "s":
        print(f"Acceso autorizado por la unidad {depto}.")
        abrir_puerta(f"Visita autorizada por depto {depto} (foto temporal capturada)")
        database.log_evento("C", "permitido", depto_destino=depto,
                             detalle="Autorizado por videollamada")
    else:
        motivo = "Rechazado por residente" if resp == "n" else "No atendió la llamada"
        denegar(f"El residente no se encuentra disponible o no autorizó el ingreso ({motivo}).")
        database.registrar_rechazo_visita(depto)
        database.log_evento("C", "denegado", depto_destino=depto, detalle=motivo)


def procesar_rostro_no_reconocido():
    if not flujo_camino_B():
        flujo_camino_C()


def main():
    database.init_db()
    engine = FaceEngine()

    if not engine.modelo_disponible():
        print("⚠️  No hay ningún rostro enrolado todavía.")
        print("   Corré primero:  python enroll.py")
        print("   El sistema puede seguir igual: cualquier rostro caerá en el Camino B/C.\n")

    cap = cv2.VideoCapture(config.CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)

    if not cap.isOpened():
        print("No se pudo abrir la cámara.")
        return

    print("Sistema en ESTADO DE ESPERA. Presioná 'q' en la ventana de video para salir.\n")

    liveness = DetectorDeParpadeo()
    frames_rostro_estable = 0
    estado = "ESPERA"

    while True:
        ok, frame = cap.read()
        if not ok:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        rostros = engine.detectar_rostros(gray)

        if len(rostros) == 0:
            frames_rostro_estable = 0
            liveness.reset()
            estado = "ESPERA"
            cv2.putText(frame, "Estado: ESPERA - acerquese a la camara", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
        else:
            (x, y, w, h) = max(rostros, key=lambda r: r[2] * r[3])  # rostro más grande
            frames_rostro_estable += 1
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 255), 2)

            roi_gray = gray[y:y + h, x:x + w]
            eyes = engine.detectar_ojos(roi_gray)
            liveness.actualizar(hay_ojos=len(eyes) > 0)

            cv2.putText(frame, "Estado: ANALIZANDO (prueba de vida)...", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            listo_para_evaluar = (
                frames_rostro_estable >= config.FRAMES_MINIMOS_ROSTRO_ESTABLE
                and (liveness.confirmado() or not config.LIVENESS_REQUIERE_PARPADEO or liveness.expirado())
            )

            if listo_para_evaluar:
                t0 = time.time()
                label, score = engine.predecir(roi_gray)
                latencia = round(time.time() - t0, 3)

                cv2.imshow("Sistema de Acceso Facial", frame)
                cv2.waitKey(1)

                if not liveness.confirmado() and config.LIVENESS_REQUIERE_PARPADEO:
                    denegar("No se pudo confirmar prueba de vida (posible foto/pantalla).")
                    database.log_evento("A", "denegado", score=score,
                                         detalle=f"Liveness no confirmado, latencia={latencia}s")
                elif label is not None and score >= config.UMBRAL_CONFIANZA_RESIDENTE:
                    persona = database.get_persona_by_label(label)
                    if persona is None:
                        procesar_rostro_no_reconocido()
                    elif persona["lista_negra"]:
                        denegar("Persona en lista negra. Se alerta a la guardia automáticamente.")
                        database.log_evento("A", "denegado", persona_id=persona["id"],
                                             score=score, detalle="Lista negra")
                    else:
                        flujo_camino_A(persona, score)
                else:
                    procesar_rostro_no_reconocido()

                print(f"(latencia de reconocimiento: {latencia}s)\n")
                print("Sistema en ESTADO DE ESPERA. Presioná 'q' para salir.\n")
                frames_rostro_estable = 0
                liveness.reset()
                estado = "ESPERA"

        cv2.imshow("Sistema de Acceso Facial", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
