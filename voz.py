"""
Voz para el asistente conversacional (texto a voz y voz a texto).

- Texto a voz (salida): pyttsx3, que usa las voces ya instaladas en el
  sistema operativo (SAPI5 en Windows). No requiere internet ni API key.
- Voz a texto (entrada): SpeechRecognition + micrófono, usando el motor
  gratuito de reconocimiento de Google (sin API key, aunque sí necesita
  conexión a internet en el momento de escuchar).

Si alguna librería no está instalada, o no hay micrófono/parlante
disponible en la PC, el sistema NO se cae: el chat sigue funcionando
en modo texto solamente. Por eso todos los imports están protegidos.
"""
import threading
import sys
import re

try:
    import pyttsx3
    _TTS_DISPONIBLE = True
except Exception:
    _TTS_DISPONIBLE = False

try:
    import speech_recognition as sr
    _STT_DISPONIBLE = True
except Exception:
    _STT_DISPONIBLE = False

_EN_WINDOWS = sys.platform == "win32"


_engine_lock = threading.Lock()


def tts_disponible():
    return _TTS_DISPONIBLE


def stt_disponible():
    return _STT_DISPONIBLE


def _limpiar_para_voz(texto):
    """Algunas voces de Windows (SAPI5) leen ciertos símbolos en voz alta
    en vez de pausar naturalmente (ej: '/' como 'barra'). Se limpian acá
    para que la lectura sea más fluida, sin tocar el texto que se
    muestra en pantalla."""
    limpio = texto.replace("/", " o ")
    limpio = limpio.replace("¿", "").replace("¡", "")
    limpio = re.sub(r"\s+", " ", limpio).strip()
    return limpio


def hablar_async(texto):
    """Dice `texto` en voz alta sin bloquear la interfaz gráfica.

    Importante: se crea un motor de pyttsx3 NUEVO en cada llamada (en
    vez de reutilizar uno global). Es un workaround para un bug
    conocido de pyttsx3 en Windows/SAPI5 donde, si se reutiliza la
    misma instancia del motor entre distintos hilos, deja de hablar
    después de la primera vez sin tirar ningún error.
    """
    if not _TTS_DISPONIBLE or not texto:
        return
    texto_hablado = _limpiar_para_voz(texto)

    def _run():
        com_iniciado = False
        try:
            if _EN_WINDOWS:
                # pyttsx3 usa componentes COM (SAPI5) por debajo. Cada hilo
                # que use COM tiene que inicializarlo aparte, si no puede
                # colgarse o cerrar todo el programa sin avisar.
                import pythoncom
                pythoncom.CoInitialize()
                com_iniciado = True

            with _engine_lock:
                engine = pyttsx3.init()
                engine.setProperty("rate", 175)
                engine.say(texto_hablado)
                engine.runAndWait()
                engine.stop()
        except Exception as e:
            print(f"[Voz] No se pudo reproducir audio: {e}")
        finally:
            if com_iniciado:
                import pythoncom
                pythoncom.CoUninitialize()

    threading.Thread(target=_run, daemon=True).start()


def escuchar_async(callback, widget_tk):
    """Escucha el micrófono en un hilo aparte (para no congelar la
    ventana) y devuelve el resultado llamando a:

        callback(texto_reconocido_o_None, motivo_de_error_o_None)

    en el hilo principal de la interfaz (tkinter no es thread-safe,
    por eso se usa widget_tk.after(0, ...) para volver a ese hilo).
    """
    if not _STT_DISPONIBLE:
        widget_tk.after(0, lambda: callback(None, "sin_soporte"))
        return

    def _run():
        com_iniciado = False
        texto, error = None, None
        try:
            if _EN_WINDOWS:
                import pythoncom
                pythoncom.CoInitialize()
                com_iniciado = True

            r = sr.Recognizer()
            with sr.Microphone() as source:
                r.adjust_for_ambient_noise(source, duration=0.4)
                audio = r.listen(source, timeout=6, phrase_time_limit=10)
            texto = r.recognize_google(audio, language="es-AR")
        except sr.WaitTimeoutError:
            error = "timeout"
        except sr.UnknownValueError:
            error = "no_entendido"
        except AttributeError:
            # sr.Microphone() suele fallar así cuando falta PyAudio
            error = "sin_microfono"
        except OSError:
            error = "sin_microfono"
        except Exception as e:
            print(f"[Voz] Error de reconocimiento: {e}")
            error = "error"
        finally:
            if com_iniciado:
                import pythoncom
                pythoncom.CoUninitialize()
        widget_tk.after(0, lambda: callback(texto, error))

    threading.Thread(target=_run, daemon=True).start()
