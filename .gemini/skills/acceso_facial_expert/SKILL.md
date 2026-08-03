---
name: acceso_facial_expert
description: Guía experta y arquitectura del Sistema Inteligente de Acceso Residencial por Reconocimiento Facial.
---

# Skill: Sistema de Acceso Facial Residencial

## Descripción General
Este proyecto es un sistema de control de acceso residencial basado en visión por computadora (OpenCV, algoritmo LBPH), prueba de vida (liveness detection por parpadeo), base de datos SQLite y asistentes conversacionales para tótems de recepción y administración.

## Arquitectura del Proyecto
- `config.py`: Parámetros de negocio (umbrales de confianza LBPH, timeouts, configuración SMTP e IA).
- `settings.py`: Persistencia editable en caliente (`data/settings.json`) que pisa la configuración por defecto desde la GUI.
- `database.py`: Gestión de la base de datos SQLite (`data/acceso.sqlite3`) para personas, deptos, PINs, tarjetas y logs de acceso.
- `recognizer.py`: Motor de detección de rostros con Haar Cascades y entrenamiento/reconocimiento LBPH (`data/modelo_lbph.yml`).
- `enroll.py`: Captura e inserción de rostros para enrolamiento de residentes (20 fotos por persona).
- `notificaciones.py`: Envio de correos electrónicos vía SMTP (Gmail con contraseña de aplicación).
- `voz.py`: Motor de texto a voz (`pyttsx3`) y reconocimiento de voz (`SpeechRecognition`).
- `ia_service.py`: Servicio híbrido de IA Generativa (Google Gemini API / Ollama / Fallback a reglas).
- `chatbot.py`: Asistente conversacional de recepción (Camino B: PIN residente, Camino C: Visitas).
- `agente_admin.py`: Agente analista de accesos y detector de anomalías para seguridad.
- `gui.py` / `gui1.py`: Interfaz gráfica desarrollada en Tkinter / CustomTkinter.

## Flujos de Acceso (Caminos)
1. **Camino A**: Rostro reconocido con confianza >= `UMBRAL_CONFIANZA_RESIDENTE` y liveness exitoso -> Puerta Abierta.
2. **Camino B**: Residente no reconocido -> Diálogo por el asistente para ingresar Depto y PIN.
3. **Camino C**: Visita -> Diálogo por el asistente para capturar Nombre y Depto de destino, generando videollamada / notificación.
4. **Camino D**: Abandono o timeout -> Retorno al estado de espera sin abrir la puerta.

## Buenas Prácticas de Modificación
- Mantener la tolerancia a fallos: Si la cámara, micrófono o internet (IA Generativa / SMTP) fallan, el sistema DEBE seguir funcionando con los fallbacks locales.
- No alterar las firmas de funciones de `database.py` ni la estructura del esquema SQLite existente.
