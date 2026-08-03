"""
Agente de Visión (Edge) + Agente de Procesamiento y Análisis (Sección 4 del PDF).

- Detección de rostro (Haar Cascade, corre local / "Edge")
- Prueba de vida simplificada por detección de parpadeo (Anti-Spoofing)
- Reconocimiento facial con LBPH (Local Binary Patterns Histograms)

Nota honesta: LBPH no es un embedding tipo FaceNet/ArcFace como menciona
el PDF (Sección 8, aceleradores), pero corre 100% local, sin dependencias
pesadas (dlib/face_recognition) y es suficiente para una demo funcional
con webcam. El diseño (umbral, reintentos, liveness) es fiel al documento.
"""
import os
import time
import cv2
import numpy as np

import config
import settings
import database



class FaceEngine:
    def __init__(self):
        # Usamos los archivos de cascada incluidos en el proyecto
        # (data/cascades/) en vez de cv2.data.haarcascades: en algunas
        # instalaciones de Windows/Python nuevas ese paquete no trae
        # los .xml y cv2 tira "Can't open file ... in read mode".
        cascades_locales = os.path.join(config.DATA_DIR, "cascades")
        ruta_rostro_local = os.path.join(cascades_locales, "haarcascade_frontalface_default.xml")
        ruta_ojos_local = os.path.join(cascades_locales, "haarcascade_eye.xml")

        if os.path.exists(ruta_rostro_local) and os.path.exists(ruta_ojos_local):
            ruta_rostro, ruta_ojos = ruta_rostro_local, ruta_ojos_local
        else:
            cascades_cv2 = cv2.data.haarcascades
            ruta_rostro = cascades_cv2 + "haarcascade_frontalface_default.xml"
            ruta_ojos = cascades_cv2 + "haarcascade_eye.xml"

        self.face_cascade = cv2.CascadeClassifier(ruta_rostro)
        self.eye_cascade = cv2.CascadeClassifier(ruta_ojos)

        if self.face_cascade.empty() or self.eye_cascade.empty():
            raise RuntimeError(
                "No se pudieron cargar los clasificadores de rostro/ojos.\n"
                f"Rutas probadas:\n  {ruta_rostro}\n  {ruta_ojos}\n"
                "Verificá que existan esos archivos, o reinstalá con:\n"
                "  pip uninstall opencv-python opencv-python-headless opencv-contrib-python\n"
                "  pip install opencv-contrib-python"
            )

        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        self._model_cargado = False
        self._cargar_modelo_si_existe()

    # ---------- Detección ----------

    def detectar_rostros(self, frame_gray):
        return self.face_cascade.detectMultiScale(
            frame_gray, scaleFactor=1.2, minNeighbors=5, minSize=(90, 90)
        )

    def detectar_ojos(self, roi_gray):
        return self.eye_cascade.detectMultiScale(roi_gray, scaleFactor=1.1, minNeighbors=8)

    # ---------- Entrenamiento / reconocimiento (LBPH) ----------

    def _cargar_modelo_si_existe(self):
        if os.path.exists(config.MODELO_PATH):
            self.recognizer.read(config.MODELO_PATH)
            self._model_cargado = True

    def modelo_disponible(self):
        return self._model_cargado

    def entrenar_desde_disco(self):
        """Lee data/rostros/<label>/*.jpg y (re)entrena el modelo LBPH.
        Se llama automáticamente después de cada enrolamiento (Aprendizaje continuo)."""
        rostros, labels = [], []
        if not os.path.isdir(config.ROSTROS_DIR):
            return False

        for carpeta in os.listdir(config.ROSTROS_DIR):
            carpeta_path = os.path.join(config.ROSTROS_DIR, carpeta)
            if not os.path.isdir(carpeta_path):
                continue
            try:
                label = int(carpeta)
            except ValueError:
                continue
            for archivo in os.listdir(carpeta_path):
                if not archivo.lower().endswith((".jpg", ".png")):
                    continue
                img = cv2.imread(os.path.join(carpeta_path, archivo), cv2.IMREAD_GRAYSCALE)
                if img is None or img.size == 0:
                    continue
                img_resized = cv2.resize(img, (200, 200))
                rostros.append(img_resized)
                labels.append(label)

        if not rostros or len(labels) == 0:
            return False

        try:
            self.recognizer.train(rostros, np.array(labels, dtype=np.int32))
            os.makedirs(config.DATA_DIR, exist_ok=True)
            self.recognizer.save(config.MODELO_PATH)
            self._model_cargado = True
            return True
        except Exception as err:
            print(f"[LBPH Train Error] {err}")
            return False


    def predecir(self, rostro_gray_recortado):
        """Devuelve (label, score_0_100). Score alto = mejor coincidencia."""
        if not self._model_cargado:
            return None, 0.0
        rostro = cv2.resize(rostro_gray_recortado, (200, 200))
        label, confidence = self.recognizer.predict(rostro)
        # LBPH: confidence es una distancia (menor = mejor). La invertimos a score 0-100.
        score = max(0.0, (1 - min(confidence, config.LBPH_CONFIDENCE_MAX) / config.LBPH_CONFIDENCE_MAX) * 100)
        return label, round(score, 1)

    def entrenar_modelo(self):
        """Alias para entrenar_desde_disco."""
        return self.entrenar_desde_disco()

    def evaluar_fotograma(self, frame):
        """Evalúa un fotograma recibido (por webcam local o web) para detectar rostro, liveness y reconocimiento LBPH."""
        if frame is None:
            return {"estado": "buscando", "mensaje": "Sin frame"}

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        rostros = self.detectar_rostros(gray)

        if len(rostros) == 0:
            return {"estado": "buscando", "mensaje": "No se detectó ningún rostro."}

        (x, y, w, h) = rostros[0]
        rostro_crop = gray[y:y+h, x:x+w]

        ojos = self.detectar_ojos(rostro_crop)
        parpadeo_ok = len(ojos) > 0

        label, score = self.predecir(rostro_crop)
        umbral = float(settings.get("UMBRAL_CONFIANZA_RESIDENTE") or 60.0)

        if label is not None and score >= umbral:
            persona = database.get_persona_by_label(label)
            if persona:
                if persona["lista_negra"]:
                    return {
                        "estado": "denegado",
                        "es_residente": False,
                        "nombre": f"{persona['nombre']} {persona['apellido']}",
                        "depto": persona["depto"],
                        "score": score,
                        "parpadeo_ok": parpadeo_ok,
                        "camino": "A",
                        "persona_id": persona["id"],
                        "mensaje": "Persona en lista negra"
                    }
                return {
                    "estado": "permitido",
                    "es_residente": True,
                    "nombre": f"{persona['nombre']} {persona['apellido']}",
                    "depto": persona["depto"],
                    "score": score,
                    "parpadeo_ok": parpadeo_ok,
                    "camino": "A",
                    "persona_id": persona["id"],
                    "mensaje": "Acceso concedido"
                }

        return {
            "estado": "buscando",
            "es_residente": False,
            "nombre": "",
            "depto": "",
            "score": score,
            "parpadeo_ok": parpadeo_ok,
            "camino": "B",
            "mensaje": "Rostro no reconocido o confianza insuficiente"
        }



class DetectorDeParpadeo:
    """Prueba de vida (liveness) simplificada: exige que en la ventana de
    tiempo configurada se detecten ojos y luego, momentáneamente, dejen de
    detectarse (parpadeo) antes de volver a detectarse. Evita fotos estáticas."""

    def __init__(self, timeout_seg=None):
        self.timeout_seg = timeout_seg or config.LIVENESS_TIMEOUT_SEG
        self.reset()

    def reset(self):
        self._t_inicio = time.time()
        self._vio_ojos = False
        self._vio_ausencia = False
        self._confirmado = False

    def expirado(self):
        return (time.time() - self._t_inicio) > self.timeout_seg

    def actualizar(self, hay_ojos):
        if self._confirmado:
            return True
        if hay_ojos:
            if self._vio_ausencia and self._vio_ojos:
                self._confirmado = True
            self._vio_ojos = True
        else:
            if self._vio_ojos:
                self._vio_ausencia = True
        return self._confirmado

    def confirmado(self):
        return self._confirmado
