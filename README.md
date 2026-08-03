# Sistema Inteligente de Acceso Residencial por Reconocimiento Facial

Implementación funcional del TP1 (UTN FRBA — IA Aplicada a Organizaciones,
Budassi / Paredes / Quiñones). Usa tu webcam para reproducir el ciclo
completo descripto en el documento: **Observación → Análisis → Planificación
→ Acción → Evaluación**, con los 3 caminos de decisión (A: reconocido,
B: residente con PIN, C: visita con "llamada" simulada), memoria
persistente en SQLite, y ahora una **interfaz gráfica de escritorio**.

## 0. Interfaz gráfica (recomendado)

```bash
pip install -r requirements.txt
python gui.py
```

Se abre una ventana con 7 botones:

1. **Registrar nueva persona** — carga sus datos y abre la cámara para
   capturarle las fotos automáticamente.
2. **Iniciar reconocimiento en vivo** — abre la cámara y corre el ciclo
   completo (Observación → Análisis → Planificación → Acción →
   Evaluación) con ventanas de diálogo en vez de la consola.
3. **Agregar fotos a usuario existente** — sumale más fotos a alguien ya
   registrado (mejora la precisión).
4. **Borrar usuario** — elimina a una persona (datos + fotos) y
   reentrena el modelo automáticamente.
5. **Usuarios enrolados** — tabla con todos los registrados; doble clic
   (o "Editar seleccionado") para modificarle depto, email, PIN,
   categoría, tipo de acceso o marcarlo en lista negra.
6. **Generar reporte (.xlsx)** — exporta un Excel a la carpeta
   `reportes/` con el resumen semanal, el listado de personas y el
   historial de accesos.
7. **Configuración** — cámara, umbral de confianza, prueba de vida,
   cantidad de fotos por enrolamiento y credenciales SMTP para las
   notificaciones por email. Se guarda en `data/settings.json`.

El resto de este README describe también la versión por consola
(`enroll.py` / `main.py` / `reporte.py`), que sigue funcionando igual
si preferís no usar la interfaz gráfica.

## 0.1. Asistente conversacional (Camino B y C)

Cuando el sistema no reconoce un rostro, en vez de mostrar formularios
o cuadros de sí/no, se abre una ventana de chat con un asistente
virtual que charla en lenguaje natural para completar el ingreso:

- Le pregunta si sos residente o venís de visita.
- Si sos residente: te pide el depto y el PIN, y valida contra la base.
- Si sos visita: te pide tu nombre y a qué depto vas, notifica por
  email al depto (si tiene email cargado) y simula la videollamada con
  3 botones (autorizar / no autorizar / no atiende).

Podés escribirle por teclado, o (si tenés micrófono y las librerías de
voz instaladas) apretar el botón 🎤 para hablarle. Si tenés parlantes,
el asistente también te va a **responder por voz**, no solo por texto.

**Importante — esto es un chatbot de reglas, no un modelo de lenguaje
externo**: no usa ninguna API de OpenAI/Anthropic/etc. ni tiene costo.
Entiende frases simples (extrae el número de depto y el PIN de lo que
escribís/decís), pero no es una IA conversacional de propósito general.

**Sobre la voz — instalación:**

```bash
pip install pyttsx3 SpeechRecognition PyAudio
```

- `pyttsx3` (texto a voz) funciona directo en Windows.
- `PyAudio` (necesario para el micrófono) a veces falla al instalar
  con `pip` en Windows. Si te tira error, probá:
  ```bash
  pip install pipwin
  pipwin install pyaudio
  ```
- Si ninguna de las dos librerías está instalada, **no pasa nada**: el
  chat sigue funcionando por teclado nomás, sin errores. Podés
  desactivar la voz manualmente desde **7. Configuración** → "Habilitar
  voz" si preferís que no intente hablar.

## 0.2. Imagen de bienvenida

Cada vez que se concede un acceso (Camino A, B o C), aparece un cartel
con la ilustración del edificio y el texto "¡BIENVENIDO, [NOMBRE]!"
compuesto en el momento sobre la imagen. Queda visible 6 segundos por
defecto (configurable desde **7. Configuración** → "Duración del
cartel de bienvenida"), o se puede cerrar antes con el botón "Cerrar".

## 0.3. Asistente administrativo (segunda IA)

Además del asistente que atiende a las visitas, hay un **segundo
asistente** pensado para quien administra el edificio: responde
preguntas en lenguaje natural sobre los registros de acceso, y puede
escanear los logs buscando patrones sospechosos.

Se accede desde dos lugares:
- **8. 🛡️ Asistente administrativo (IA)** en el menú principal.
- El botón **"🛡️ Preguntarle a la IA"** dentro de "Usuarios enrolados".

También corre automáticamente cada vez que generás un reporte
(**6. Generar reporte**): si detecta algo raro en las últimas 24hs, te
lo muestra antes de abrir la carpeta.

Ejemplos de preguntas que entiende:
- "¿Cuántos accesos hubo hoy?" / "...esta semana?"
- "¿Quién entró último?"
- "Accesos del depto 4B"
- "¿Hay alguien en lista negra?"
- "Dame un resumen"

Y detecta automáticamente:
- Deptos con 3 o más accesos denegados en 24hs (posible visita insistente).
- Intentos de acceso de personas en lista negra.
- Fallos repetidos de prueba de vida (posibles intentos con foto/pantalla).

Igual que el asistente de recepción, **es un motor de reglas sobre la
base de datos, no un modelo de lenguaje externo** — funciona sin
conexión y sin costo.

## 1. Instalación

Necesitás Python 3.9+ y una webcam. Corré esto en tu PC (no en este sandbox,
que no tiene cámara):

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Enrolar personas

Antes de usar el sistema tenés que registrar al menos una persona (rostro):

```bash
python enroll.py
```

Te va a pedir DNI, nombre, categoría (administrador / propietario / inquilino
/ visita frecuente), depto, tipo de acceso y un PIN opcional (para el Camino
B). Después abre la cámara y capturar 20 fotos de tu rostro automáticamente
— movete un poco la cara para variar el ángulo.

Repetí esto por cada persona que quieras dar de alta.

## 3. Correr el sistema

```bash
python main.py
```

- Si tu rostro está enrolado y coincide (score ≥ umbral en `config.py`),
  el sistema saluda y "abre la puerta" — **Camino A**.
- Antes de reconocer, el sistema pide un **parpadeo** (prueba de vida) para
  evitar que se engañe con una foto en pantalla.
- Si no te reconoce, te pregunta por consola si sos residente:
  - **Sí → Camino B**: pide depto + PIN (el que definiste al enrolar).
  - **No → Camino C**: pide a qué depto vas y simula una "videollamada"
    (en la consola vos mismo respondés s/n como si fueras el residente).
- Todo evento (permitido/denegado, camino, score, timestamp) queda
  guardado en `data/acceso.sqlite3`.
- Si una visita es rechazada varias veces hacia distintos deptos en
  24hs, el sistema la bloquea automáticamente sin volver a preguntar
  (regla de "memoria persistente" de la Sección 6 del TP).

Salir con la tecla **q** sobre la ventana de video.

## 3.1. Notificaciones por email

El sistema le manda un email al propietario/inquilino del depto en estas
situaciones:

- **Reconocimiento facial exitoso (Camino A)**: se notifica apenas se
  concede el acceso por rostro.
- **Ingreso sin registro facial (Camino B con PIN, o Camino C - visita
  autorizada)**: también se notifica al propietario del depto correspondiente.
- **Visita en la puerta (Camino C)**: además, apenas alguien indica a
  qué depto se dirige (antes de la autorización), se manda un aviso de
  "hay una visita en la puerta".

Para activarlo desde la interfaz gráfica: abrí **7. Configuración** en
`gui.py`, completá los campos de SMTP y guardá — no hace falta editar
código. También podés seguir editando `config.py` a mano si preferís
usar la versión por consola.

Con Gmail **no funciona tu contraseña normal**: tenés que generar una
"Contraseña de aplicación" en https://myaccount.google.com/apppasswords
(requiere tener la verificación en 2 pasos activada) y pegar esa
contraseña de 16 caracteres ahí.

Si no configurás nada o falla el envío (sin internet, credenciales mal
puestas), el sistema **no se rompe**: solo te avisa por consola que no
pudo mandar el mail y sigue con la simulación de la videollamada como
antes.

## 4. Ver reportes

```bash
python reporte.py
```

Muestra un mini-dashboard: totales de la semana, accesos por camino, y
el listado de personas registradas (incluye quiénes están en lista negra).

## 6. Estructura del proyecto

```
sistema_acceso_facial/
├── gui.py            # interfaz gráfica (los 7 botones)
├── chatbot.py          # lógica del asistente conversacional (reglas, sin IA externa)
├── voz.py               # texto a voz / voz a texto (opcional, se degrada solo)
├── config.py         # valores por defecto (umbrales, timeouts, SMTP)
├── settings.py        # overrides guardados desde la pantalla Configuración
├── database.py        # memoria persistente (SQLite): alta, edición, borrado
├── recognizer.py       # detección de rostro, parpadeo (liveness) y LBPH
├── notificaciones.py    # envío de emails (Camino B/C)
├── reportes_excel.py     # genera el .xlsx en reportes/
├── enroll.py           # alta por consola (alternativa a la GUI)
├── main.py             # loop principal por consola (alternativa a la GUI)
├── reporte.py           # dashboard en consola (alternativa a la GUI)
├── reportes/             # se crea sola: ahí caen los .xlsx generados
└── data/                 # se crea sola: rostros, modelo, DB, settings.json
```

## 6. Decisiones técnicas y simplificaciones (para tu defensa del TP)

- **Reconocimiento facial**: se usa **LBPH** (`cv2.face.LBPHFaceRecognizer`)
  en vez de un embedding profundo (FaceNet/ArcFace/InsightFace, que
  menciona el PDF como acelerador ideal). LBPH corre 100% local sin
  dependencias pesadas (no requiere `dlib`), es liviano y suficiente
  para una demo con pocas personas. Para producción real, migrar a
  `insightface` u otro modelo preentrenado sería el paso natural — el
  documento ya lo señala en la Sección 8.
- **Prueba de vida**: se implementó con detección de parpadeo (aparición/
  desaparición de los ojos vía Haar Cascade) en vez de cámaras de
  profundidad IR, que requieren hardware específico no disponible en una
  webcam estándar.
- **Videollamada al depto (Camino C)**: está *simulada* por consola (vos
  mismo respondés como si fueras el residente). Conectarla a una app real
  requeriría un backend de notificaciones push + servidor SIP, como
  describe el diagrama de arquitectura del PDF.
- **Lista negra automática**: se aproxima contando rechazos hacia
  distintos deptos en una ventana de 24hs, en vez de "reconocer" al
  visitante rechazado por su rostro (para eso haría falta guardar y
  comparar embeddings incluso de gente no enrolada, fuera del alcance de
  esta demo).

## 7. Próximos pasos posibles

- Agregar un panel web (Flask/FastAPI) que reemplace la consola para el
  Camino B/C, más cercano al mockup de "Notificación Push" del PDF.
- Migrar de LBPH a un modelo de embeddings preentrenado si se necesita
  mayor precisión con muchos usuarios.
- Guardar la foto temporal real del frame en el Camino C (hoy solo se
  registra el evento; el archivo de imagen no se persiste todavía).
