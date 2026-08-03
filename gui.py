"""
Interfaz gráfica del Sistema Inteligente de Acceso Residencial.

Menú principal con 7 opciones:
  1. Registrar nueva persona
  2. Iniciar reconocimiento en vivo
  3. Agregar fotos a usuario existente
  4. Borrar usuario
  5. Usuarios enrolados (ver / editar)
  6. Reporte (.xlsx en la carpeta reportes/)
  7. Configuración

Ejecutar: python gui.py
"""
import os
import time
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import cv2
from PIL import Image, ImageTk, ImageDraw, ImageFont

import config
import settings
import database
import notificaciones
import chatbot
import voz
import agente_admin
from recognizer import FaceEngine, DetectorDeParpadeo
import reportes_excel


CATEGORIAS = ["administrador", "propietario", "inquilino", "visita_frecuente"]
TIPOS_ACCESO = ["permanente", "temporal", "residente"]

# --- Tema de colores (punto 4: fondo verde claro, botones verde oscuro) ---
COLOR_FONDO = "#E8F5E9"
COLOR_BOTON = "#1B5E20"
COLOR_BOTON_TEXTO = "#FFFFFF"
COLOR_BOTON_HOVER = "#2E7D32"
COLOR_TITULO = "#1B5E20"


def boton_estilizado(parent, texto, comando, **kwargs):
    opciones = dict(bg=COLOR_BOTON, fg=COLOR_BOTON_TEXTO,
                     activebackground=COLOR_BOTON_HOVER, activeforeground=COLOR_BOTON_TEXTO,
                     relief="flat", cursor="hand2", font=("Segoe UI", 10, "bold"))
    opciones.update(kwargs)
    return tk.Button(parent, text=texto, command=comando, **opciones)


def _validar_solo_numeros(texto_propuesto):
    return texto_propuesto == "" or texto_propuesto.isdigit()


def entry_dni(parent, textvariable, **kwargs):
    """Entry restringido a solo dígitos (punto: el DNI debe ser numérico)."""
    vcmd = (parent.register(_validar_solo_numeros), "%P")
    return tk.Entry(parent, textvariable=textvariable, validate="key", validatecommand=vcmd, **kwargs)


_imagen_puerta_cache = None


def _cargar_fuente(tamano, negrita=True):
    """Intenta usar una tipografía prolija de Windows; si no está
    disponible (ej. corriendo en otro sistema), usa la fuente por
    defecto de Pillow en el mismo tamaño para no romper nada."""
    candidatos = (
        ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"] if negrita
        else ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"]
    )
    for ruta in candidatos:
        try:
            return ImageFont.truetype(ruta, tamano)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=tamano)
    except Exception:
        return ImageFont.load_default()


def _generar_imagen_bienvenida(nombre_persona, subtitulo):
    """Compone, en el momento, el texto de bienvenida sobre la
    ilustración de la puerta (así puede incluir el nombre de cada
    persona en particular)."""
    base = Image.open(config.IMAGEN_PUERTA_ABIERTA).convert("RGBA")
    W, H = base.size
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # cartel semitransparente abajo, para que el texto se lea bien
    alto_cartel = 120
    draw.rectangle([0, H - alto_cartel, W, H], fill=(27, 94, 32, 215))

    titulo = f"¡BIENVENIDO, {nombre_persona.upper()}!" if nombre_persona else "¡BIENVENIDO!"
    fuente_titulo = _cargar_fuente(30, negrita=True)
    fuente_sub = _cargar_fuente(16, negrita=False)

    bbox = draw.textbbox((0, 0), titulo, font=fuente_titulo)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) / 2, H - alto_cartel + 18), titulo, font=fuente_titulo, fill="white")

    if subtitulo:
        bbox2 = draw.textbbox((0, 0), subtitulo, font=fuente_sub)
        tw2 = bbox2[2] - bbox2[0]
        draw.text(((W - tw2) / 2, H - alto_cartel + 62), subtitulo, font=fuente_sub, fill="#C8E6C9")

    # insignia de check verde arriba a la izquierda
    cx, cy, r = 45, 45, 28
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(76, 175, 80, 255))
    draw.line([(cx - 12, cy), (cx - 3, cy + 12), (cx + 15, cy - 12)], fill="white", width=5, joint="curve")

    compuesta = Image.alpha_composite(base, overlay).convert("RGB")
    return compuesta


def _reproducir_chime_destrabe():
    """Reproduce una secuencia de bips/chime estilo destrabe electrónico en Windows."""
    try:
        import winsound
        import threading

        def _sound():
            try:
                winsound.Beep(1200, 150)
                winsound.Beep(1800, 250)
            except Exception:
                pass

        threading.Thread(target=_sound, daemon=True).start()
    except Exception:
        pass


def mostrar_puerta_abierta(parent, nombre_persona="", subtitulo="", duracion_ms=None):
    """Punto 3 mejorado: ventana emergente interactiva de acceso concedido con:
    1. Animación gráfica de puertas deslizantes en tiempo real (Tkinter Canvas).
    2. Sonido de destrabe electrónico (Chime / Relé).
    3. Saludo por voz en segundo plano con voz.hablar_async().
    4. Reloj digital y cuenta regresiva de cierre automático.
    5. Disparo de evento de relé de hardware (simulado en log).
    """
    ms_totales = duracion_ms if duracion_ms is not None else int(settings.get("DURACION_PUERTA_MS"))
    segundos_totales = max(1, ms_totales // 1000)

    # 1. Reproducir sonido de destrabe y saludo por voz sintética
    _reproducir_chime_destrabe()

    texto_saludo = f"¡Bienvenido {nombre_persona}!" if nombre_persona else "¡Acceso concedido!"
    if subtitulo:
        texto_saludo += f" {subtitulo}"
    voz.hablar_async(texto_saludo)

    print(f"[RELÉ HARDWARE] Signal HIGH -> Destrabe de relé enviado a puerta (Tiempo activo: {segundos_totales}s)")

    top = tk.Toplevel(parent)
    top.title("🚪 ACCESO CONCEDIDO")
    top.configure(bg="#1E272C")
    top.resizable(False, False)
    top.attributes("-topmost", True)

    W, H = 520, 420
    top.geometry(f"{W}x{H}")

    # Header de estado verde deslumbrante
    frame_header = tk.Frame(top, bg="#2E7D32", height=45)
    frame_header.pack(fill="x")

    lbl_status_header = tk.Label(
        frame_header,
        text="🔓 CERRADURA DESTRABADA - RELÉ ACTIVO",
        font=("Segoe UI", 12, "bold"),
        fg="#FFFFFF",
        bg="#2E7D32"
    )
    lbl_status_header.pack(pady=10)

    # Canvas para la animación de las puertas de vidrio deslizantes
    canvas = tk.Canvas(top, width=W, height=220, bg="#111827", highlightthickness=0)
    canvas.pack(pady=10)

    # Marco exterior de la puerta
    canvas.create_rectangle(40, 20, W - 40, 200, outline="#4B5563", width=4)

    # Coordenadas iniciales de las dos hojas deslizantes
    hoja_izq = canvas.create_rectangle(45, 25, 255, 195, fill="#1E3A8A", outline="#60A5FA", width=2)
    hoja_der = canvas.create_rectangle(265, 25, 475, 195, fill="#1E3A8A", outline="#60A5FA", width=2)

    # Manijas / bordes metálicos
    manija_izq = canvas.create_rectangle(245, 80, 250, 140, fill="#9CA3AF", outline="")
    manija_der = canvas.create_rectangle(270, 80, 275, 140, fill="#9CA3AF", outline="")

    # Texto interior visible al abrirse las puertas
    canvas.create_text(W // 2, 85, text="✨ ACCESO PERMITIDO ✨", font=("Segoe UI", 13, "bold"), fill="#10B981")
    if nombre_persona:
        canvas.create_text(W // 2, 120, text=nombre_persona.upper(), font=("Segoe UI", 16, "bold"), fill="#FFFFFF")
    if subtitulo:
        canvas.create_text(W // 2, 150, text=subtitulo, font=("Segoe UI", 11), fill="#A7F3D0")

    # Animación de apertura suave
    frames_animacion = 25
    step_actual = 0
    desplazamiento_max = 160

    def _animar_apertura():
        nonlocal step_actual
        if step_actual < frames_animacion:
            step_actual += 1
            dx = desplazamiento_max / frames_animacion
            canvas.move(hoja_izq, -dx, 0)
            canvas.move(manija_izq, -dx, 0)
            canvas.move(hoja_der, dx, 0)
            canvas.move(manija_der, dx, 0)
            top.after(20, _animar_apertura)

    top.after(80, _animar_apertura)

    # Footer con cuenta regresiva dinámica
    frame_footer = tk.Frame(top, bg="#1E272C")
    frame_footer.pack(fill="x", pady=5)

    lbl_cuenta = tk.Label(
        frame_footer,
        text=f"⏱️ Cierre automático en: {segundos_totales}s",
        font=("Segoe UI", 11, "bold"),
        fg="#FBBF24",
        bg="#1E272C"
    )
    lbl_cuenta.pack()

    # Reloj y fecha actual
    ahora_str = time.strftime("%H:%M:%S — %d/%m/%Y")
    lbl_reloj = tk.Label(
        frame_footer,
        text=f"📅 {ahora_str}",
        font=("Segoe UI", 9),
        fg="#9CA3AF",
        bg="#1E272C"
    )
    lbl_reloj.pack(pady=(2, 6))

    tiempo_restante = segundos_totales

    def _actualizar_cuenta():
        nonlocal tiempo_restante
        if top.winfo_exists():
            tiempo_restante -= 1
            if tiempo_restante > 0:
                lbl_cuenta.config(text=f"⏱️ Cierre automático en: {tiempo_restante}s")
                top.after(1000, _actualizar_cuenta)
            else:
                lbl_status_header.config(text="🔒 CERRADURA BLOQUEADA", bg="#D32F2F")
                print("[RELÉ HARDWARE] Signal LOW -> Relé desactivado (Puerta Bloqueada)")

    top.after(1000, _actualizar_cuenta)

    # Centrar la ventana en pantalla
    top.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (W // 2)
    y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (H // 2)
    top.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    top.after(ms_totales, lambda: top.destroy() if top.winfo_exists() else None)



# ==========================================================================
# Ventana principal
# ==========================================================================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sistema de Acceso Facial - Edificio")
        self.geometry("480x640")
        self.resizable(False, False)
        self.configure(bg=COLOR_FONDO)

        database.init_db()
        os.makedirs(config.ROSTROS_DIR, exist_ok=True)
        os.makedirs(config.REPORTES_DIR, exist_ok=True)

        self.engine = FaceEngine()

        tk.Label(self, text="Sistema Inteligente de Acceso",
                 font=("Segoe UI", 16, "bold"), bg=COLOR_FONDO, fg=COLOR_TITULO).pack(pady=(20, 0))
        tk.Label(self, text="Reconocimiento facial - Edificio",
                 font=("Segoe UI", 10), bg=COLOR_FONDO, fg="#33691E").pack(pady=(0, 20))

        botones = [
            ("1. Registrar nueva persona", self.abrir_registro),
            ("2. Iniciar reconocimiento en vivo", self.abrir_reconocimiento),
            ("3. Agregar fotos a usuario existente", self.abrir_agregar_fotos),
            ("4. Borrar usuario", self.abrir_borrar_usuario),
            ("5. Usuarios enrolados", self.abrir_usuarios),
            ("6. Generar reporte (.xlsx)", self.generar_reporte),
            ("7. Configuración", self.abrir_configuracion),
            ("8. 🛡️ Asistente administrativo (IA)", self.abrir_admin_ia),
        ]
        for texto, comando in botones:
            boton_estilizado(self, texto, comando, width=34, height=2).pack(pady=6)

        self.status = tk.Label(self, text=self._resumen_estado(), fg="#33691E", bg=COLOR_FONDO,
                                font=("Segoe UI", 9))
        self.status.pack(side="bottom", pady=10)

    def _resumen_estado(self):
        n = len(database.listar_personas())
        modelo = "modelo entrenado" if self.engine.modelo_disponible() else "sin modelo entrenado todavía"
        return f"{n} persona(s) registrada(s) — {modelo}"

    def refrescar_status(self):
        self.status.config(text=self._resumen_estado())

    # ---- Handlers de los 7 botones ----

    def abrir_registro(self):
        RegistroDialog(self, self.engine, on_close=self.refrescar_status)

    def abrir_reconocimiento(self):
        if not self.engine.modelo_disponible():
            if not messagebox.askyesno(
                "Sin personas enroladas",
                "Todavía no enrolaste a nadie, así que cualquier rostro va a "
                "caer en el Camino B/C. ¿Querés continuar igual?"
            ):
                return
        ReconocimientoWindow(self, self.engine)

    def abrir_agregar_fotos(self):
        personas = database.listar_personas()
        if not personas:
            messagebox.showinfo("Sin usuarios", "Todavía no hay personas registradas.")
            return
        SeleccionarUsuarioDialog(
            self, personas, titulo="Agregar fotos a usuario existente",
            on_seleccionar=lambda p: self._agregar_fotos_a(p)
        )

    def _agregar_fotos_a(self, persona):
        CapturaFotosWindow(
            self, self.engine, persona["label_lbph"],
            f"{persona['nombre']} {persona['apellido']}",
            on_finish=self.refrescar_status
        )

    def abrir_borrar_usuario(self):
        personas = database.listar_personas()
        if not personas:
            messagebox.showinfo("Sin usuarios", "Todavía no hay personas registradas.")
            return
        SeleccionarUsuarioDialog(
            self, personas, titulo="Borrar usuario",
            on_seleccionar=self._confirmar_borrado
        )

    def _confirmar_borrado(self, persona):
        nombre = f"{persona['nombre']} {persona['apellido']}"
        if not messagebox.askyesno(
            "Confirmar borrado",
            f"¿Seguro que querés borrar a {nombre} (depto {persona['depto']})?\n"
            f"Se eliminan sus datos y sus fotos. Esta acción no se puede deshacer."
        ):
            return

        label = persona["label_lbph"]
        database.eliminar_persona(label)

        carpeta = os.path.join(config.ROSTROS_DIR, str(label))
        if os.path.isdir(carpeta):
            import shutil
            shutil.rmtree(carpeta, ignore_errors=True)

        if not self.engine.entrenar_desde_disco():
            # no quedan fotos de nadie -> borrar el modelo viejo
            if os.path.exists(config.MODELO_PATH):
                os.remove(config.MODELO_PATH)
            self.engine._model_cargado = False

        messagebox.showinfo("Listo", f"{nombre} fue eliminado del sistema.")
        self.refrescar_status()

    def abrir_usuarios(self):
        UsuariosWindow(self, self.engine, on_change=self.refrescar_status)

    def generar_reporte(self):
        try:
            ruta = reportes_excel.generar_reporte_xlsx()
        except Exception as e:
            messagebox.showerror("Error al generar reporte", str(e))
            return

        alertas = agente_admin.detectar_anomalias(horas=24)
        alertas_reales = [a for a in alertas if not a.startswith("✅")]
        mensaje = f"Se guardó en:\n{ruta}\n\n"
        if alertas_reales:
            mensaje += "🛡️ La IA administrativa detectó:\n" + "\n".join(f"• {a}" for a in alertas_reales)
            mensaje += "\n\n¿Abrir la carpeta del reporte?"
        else:
            mensaje += "🛡️ La IA administrativa no detectó anomalías en las últimas 24hs.\n\n¿Abrir la carpeta?"

        if messagebox.askyesno("Reporte generado", mensaje):
            self._abrir_carpeta(config.REPORTES_DIR)

    @staticmethod
    def _abrir_carpeta(ruta):
        try:
            if os.name == "nt":
                os.startfile(ruta)  # Windows
            elif os.uname().sysname == "Darwin":
                os.system(f'open "{ruta}"')
            else:
                os.system(f'xdg-open "{ruta}"')
        except Exception:
            pass

    def abrir_configuracion(self):
        ConfiguracionDialog(self)

    def abrir_admin_ia(self):
        AdminChatWindow(self)


# ==========================================================================
# Registrar nueva persona
# ==========================================================================

class RegistroDialog(tk.Toplevel):
    def __init__(self, master, engine, on_close=None):
        super().__init__(master)
        self.engine = engine
        self.on_close = on_close
        self.title("Registrar nueva persona")
        self.geometry("380x480")
        self.resizable(False, False)
        self.configure(bg=COLOR_FONDO)
        self.grab_set()

        campos = [
            ("DNI (solo números)", "dni"), ("Nombre", "nombre"), ("Apellido", "apellido"),
            ("Departamento (ej: 4B)", "depto"), ("PIN alternativo (opcional)", "pin"),
            ("Email (opcional)", "email"),
        ]
        self.vars = {}
        for etiqueta, clave in campos:
            tk.Label(self, text=etiqueta, anchor="w", bg=COLOR_FONDO).pack(fill="x", padx=20, pady=(10, 0))
            var = tk.StringVar()
            if clave == "dni":
                entry_dni(self, var).pack(fill="x", padx=20)
            else:
                tk.Entry(self, textvariable=var).pack(fill="x", padx=20)
            self.vars[clave] = var

        tk.Label(self, text="Categoría", anchor="w", bg=COLOR_FONDO).pack(fill="x", padx=20, pady=(10, 0))
        self.categoria = ttk.Combobox(self, values=CATEGORIAS, state="readonly")
        self.categoria.current(2)
        self.categoria.pack(fill="x", padx=20)

        tk.Label(self, text="Tipo de acceso", anchor="w", bg=COLOR_FONDO).pack(fill="x", padx=20, pady=(10, 0))
        self.tipo_acceso = ttk.Combobox(self, values=TIPOS_ACCESO, state="readonly")
        self.tipo_acceso.current(0)
        self.tipo_acceso.pack(fill="x", padx=20)

        tk.Button(self, text="Guardar y capturar fotos", bg=COLOR_BOTON, fg=COLOR_BOTON_TEXTO,
                  font=("Segoe UI", 10, "bold"), command=self.guardar).pack(pady=20, fill="x", padx=20)

    def guardar(self):
        dni = self.vars["dni"].get().strip()
        nombre = self.vars["nombre"].get().strip()
        apellido = self.vars["apellido"].get().strip()
        if not (dni and nombre and apellido):
            messagebox.showwarning("Faltan datos", "DNI, nombre y apellido son obligatorios.")
            return
        if not dni.isdigit():
            messagebox.showwarning("DNI inválido", "El DNI debe contener solo números, sin puntos ni letras.")
            return

        try:
            label = database.alta_persona(
                dni=dni, nombre=nombre, apellido=apellido,
                categoria=self.categoria.get(), depto=self.vars["depto"].get().strip(),
                tipo_acceso=self.tipo_acceso.get(),
                pin=self.vars["pin"].get().strip() or None,
                email=self.vars["email"].get().strip() or None,
            )
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo registrar: {e}")
            return

        nombre_completo = f"{nombre} {apellido}"
        self.destroy()
        CapturaFotosWindow(self.master, self.engine, label, nombre_completo, on_finish=self.on_close)


# ==========================================================================
# Selección genérica de usuario (usada por Borrar / Agregar fotos)
# ==========================================================================

class SeleccionarUsuarioDialog(tk.Toplevel):
    def __init__(self, master, personas, titulo, on_seleccionar):
        super().__init__(master)
        self.title(titulo)
        self.geometry("420x360")
        self.configure(bg=COLOR_FONDO)
        self.grab_set()
        self.on_seleccionar = on_seleccionar
        self.personas = personas

        tk.Label(self, text=titulo, font=("Segoe UI", 12, "bold"), bg=COLOR_FONDO, fg=COLOR_TITULO).pack(pady=10)

        cont = tk.Frame(self, bg=COLOR_FONDO)
        cont.pack(fill="both", expand=True, padx=10)
        self.listbox = tk.Listbox(cont, font=("Consolas", 10))
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll = tk.Scrollbar(cont, command=self.listbox.yview)
        scroll.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=scroll.set)

        for p in personas:
            self.listbox.insert(
                "end",
                f"#{p['label_lbph']:>3}  {p['apellido']}, {p['nombre']}  -  depto {p['depto']}"
            )

        tk.Button(self, text="Seleccionar", bg=COLOR_BOTON, fg=COLOR_BOTON_TEXTO,
                  command=self._confirmar).pack(pady=10, fill="x", padx=10)

    def _confirmar(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showwarning("Nada seleccionado", "Elegí una persona de la lista.")
            return
        persona = self.personas[sel[0]]
        self.destroy()
        self.on_seleccionar(persona)


# ==========================================================================
# Captura de fotos por webcam (usada en alta y en "agregar fotos")
# ==========================================================================

class CapturaFotosWindow(tk.Toplevel):
    def __init__(self, master, engine, label, nombre_completo, on_finish=None):
        super().__init__(master)
        self.engine = engine
        self.label_persona = label
        self.on_finish = on_finish
        self.title(f"Capturando fotos - {nombre_completo}")
        self.geometry("680x560")
        self.configure(bg=COLOR_FONDO)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.cerrar)

        self.total_fotos = int(settings.get("FOTOS_POR_ENROLAMIENTO"))
        self.capturas = 0
        self.carpeta = os.path.join(config.ROSTROS_DIR, str(label))
        os.makedirs(self.carpeta, exist_ok=True)
        # continuar la numeración si ya había fotos (caso "agregar fotos")
        existentes = [f for f in os.listdir(self.carpeta) if f.lower().endswith(".jpg")]
        self.offset = len(existentes)

        tk.Label(self, text=f"Mirá a la cámara, {nombre_completo}",
                 font=("Segoe UI", 12, "bold"), bg=COLOR_FONDO, fg=COLOR_TITULO).pack(pady=8)
        self.video_label = tk.Label(self, bg=COLOR_FONDO)
        self.video_label.pack()
        self.progreso = ttk.Progressbar(self, maximum=self.total_fotos, length=500)
        self.progreso.pack(pady=10)
        self.estado_label = tk.Label(self, text=f"Capturas: 0/{self.total_fotos}", bg=COLOR_FONDO)
        self.estado_label.pack()
        boton_estilizado(self, "Cancelar", self.cerrar).pack(pady=8)

        self.cap = cv2.VideoCapture(int(settings.get("CAMERA_INDEX")))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
        self.activo = True
        self._ultimo_guardado = 0

        if not self.cap.isOpened():
            messagebox.showerror("Cámara", "No se pudo abrir la cámara.")
            self.cerrar()
            return

        self._loop()

    def _loop(self):
        if not self.activo:
            return
        ok, frame = self.cap.read()
        if ok:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            rostros = self.engine.detectar_rostros(gray)
            for (x, y, w, h) in rostros:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                ahora = time.time()
                if self.capturas < self.total_fotos and (ahora - self._ultimo_guardado) > 0.25:
                    recorte = cv2.resize(gray[y:y + h, x:x + w], (200, 200))
                    idx = self.offset + self.capturas
                    cv2.imwrite(os.path.join(self.carpeta, f"{idx:03d}.jpg"), recorte)
                    self.capturas += 1
                    self._ultimo_guardado = ahora
                break

            self._mostrar_frame(frame)
            self.progreso["value"] = self.capturas
            self.estado_label.config(text=f"Capturas: {self.capturas}/{self.total_fotos}")

        if self.capturas >= self.total_fotos:
            self._finalizar()
            return

        self.after(30, self._loop)

    def _mostrar_frame(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        imgtk = ImageTk.PhotoImage(image=img)
        self.video_label.imgtk = imgtk
        self.video_label.config(image=imgtk)

    def _finalizar(self):
        self.activo = False
        if self.cap.isOpened():
            self.cap.release()
        self.estado_label.config(text="Reentrenando modelo...")
        self.update()
        self.engine.entrenar_desde_disco()
        messagebox.showinfo("Listo", f"Se capturaron {self.capturas} fotos y se actualizó el modelo.")
        if self.on_finish:
            self.on_finish()
        self.destroy()

    def cerrar(self):
        self.activo = False
        if self.cap.isOpened():
            self.cap.release()
        # aunque se cancele la captura de fotos, la persona ya quedó
        # guardada en la base al completar el formulario -> hay que
        # refrescar igual el contador de la ventana principal.
        if self.on_finish:
            self.on_finish()
        self.destroy()


# ==========================================================================
# Usuarios enrolados (ver / editar)
# ==========================================================================

class UsuariosWindow(tk.Toplevel):
    def __init__(self, master, engine, on_change=None):
        super().__init__(master)
        self.engine = engine
        self.on_change = on_change
        self.title("Usuarios enrolados")
        self.geometry("860x460")
        self.configure(bg=COLOR_FONDO)
        self.grab_set()

        tk.Label(self, text="Usuarios enrolados", font=("Segoe UI", 13, "bold"),
                 bg=COLOR_FONDO, fg=COLOR_TITULO).pack(pady=(12, 0))
        tk.Label(self, text="Doble clic sobre un usuario (o el botón de abajo) para editar y guardar cambios",
                 font=("Segoe UI", 9), bg=COLOR_FONDO, fg="#33691E").pack(pady=(0, 8))

        columnas = ("id", "nombre", "dni", "categoria", "depto", "email", "lista_negra")
        self.tree = ttk.Treeview(self, columns=columnas, show="headings", height=15)
        titulos = {"id": "#", "nombre": "Nombre", "dni": "DNI", "categoria": "Categoría",
                   "depto": "Depto", "email": "Email", "lista_negra": "Lista negra"}
        anchos = {"id": 40, "nombre": 160, "dni": 90, "categoria": 110,
                  "depto": 70, "email": 190, "lista_negra": 90}
        for c in columnas:
            self.tree.heading(c, text=titulos[c])
            self.tree.column(c, width=anchos[c], anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.tree.bind("<Double-1>", lambda e: self.editar_seleccionado())

        botonera = tk.Frame(self, bg=COLOR_FONDO)
        botonera.pack(pady=(0, 12))
        boton_estilizado(botonera, "✏️  Editar y guardar cambios", self.editar_seleccionado,
                          width=24).pack(side="left", padx=5)
        boton_estilizado(botonera, "🛡️ Preguntarle a la IA", lambda: AdminChatWindow(self),
                          width=18).pack(side="left", padx=5)
        boton_estilizado(botonera, "Cerrar", self.destroy, bg="#555", width=12).pack(side="left", padx=5)

        self._cargar()

    def _cargar(self):
        self.tree.delete(*self.tree.get_children())
        for p in database.listar_personas():
            self.tree.insert("", "end", iid=p["label_lbph"], values=(
                p["label_lbph"], f"{p['nombre']} {p['apellido']}", p["dni"],
                p["categoria"], p["depto"], p["email"] or "-",
                "Sí" if p["lista_negra"] else "No",
            ))

    def editar_seleccionado(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Nada seleccionado", "Elegí un usuario de la tabla.")
            return
        label = int(sel[0])
        persona = database.get_persona_by_label(label)
        EditarUsuarioDialog(self, persona, on_guardado=self._on_guardado)

    def _on_guardado(self):
        self._cargar()
        if self.on_change:
            self.on_change()


class EditarUsuarioDialog(tk.Toplevel):
    """Permite agregarle/editar información a un propietario ya registrado
    (depto, email, PIN, categoría, tipo de acceso, lista negra)."""

    def __init__(self, master, persona, on_guardado=None):
        super().__init__(master)
        self.persona = persona
        self.on_guardado = on_guardado
        self.title(f"Editar - {persona['nombre']} {persona['apellido']}")
        self.geometry("360x480")
        self.configure(bg=COLOR_FONDO)
        self.grab_set()

        campos = [
            ("DNI (solo números)", "dni", persona["dni"]),
            ("Nombre", "nombre", persona["nombre"]),
            ("Apellido", "apellido", persona["apellido"]),
            ("Departamento", "depto", persona["depto"]),
            ("PIN alternativo", "pin", persona["pin"] or ""),
            ("Email", "email", persona["email"] or ""),
        ]
        self.vars = {}
        for etiqueta, clave, valor in campos:
            tk.Label(self, text=etiqueta, anchor="w", bg=COLOR_FONDO).pack(fill="x", padx=20, pady=(8, 0))
            var = tk.StringVar(value=valor)
            if clave == "dni":
                entry_dni(self, var).pack(fill="x", padx=20)
            else:
                tk.Entry(self, textvariable=var).pack(fill="x", padx=20)
            self.vars[clave] = var

        tk.Label(self, text="Categoría", anchor="w", bg=COLOR_FONDO).pack(fill="x", padx=20, pady=(8, 0))
        self.categoria = ttk.Combobox(self, values=CATEGORIAS, state="readonly")
        self.categoria.set(persona["categoria"])
        self.categoria.pack(fill="x", padx=20)

        tk.Label(self, text="Tipo de acceso", anchor="w", bg=COLOR_FONDO).pack(fill="x", padx=20, pady=(8, 0))
        self.tipo_acceso = ttk.Combobox(self, values=TIPOS_ACCESO, state="readonly")
        self.tipo_acceso.set(persona["tipo_acceso"])
        self.tipo_acceso.pack(fill="x", padx=20)

        self.lista_negra_var = tk.BooleanVar(value=bool(persona["lista_negra"]))
        tk.Checkbutton(self, text="Marcar en lista negra (acceso prohibido)",
                        variable=self.lista_negra_var, bg=COLOR_FONDO).pack(pady=10, anchor="w", padx=20)

        boton_estilizado(self, "💾  Guardar cambios", self.guardar).pack(pady=15, fill="x", padx=20)

    def guardar(self):
        dni = self.vars["dni"].get().strip()
        if not dni.isdigit():
            messagebox.showwarning("DNI inválido", "El DNI debe contener solo números, sin puntos ni letras.")
            return

        database.actualizar_persona(
            self.persona["label_lbph"],
            dni=dni,
            nombre=self.vars["nombre"].get().strip(),
            apellido=self.vars["apellido"].get().strip(),
            depto=self.vars["depto"].get().strip(),
            pin=self.vars["pin"].get().strip() or None,
            email=self.vars["email"].get().strip() or None,
            categoria=self.categoria.get(),
            tipo_acceso=self.tipo_acceso.get(),
        )
        with database.get_conn() as conn:
            conn.execute("UPDATE personas SET lista_negra = ? WHERE label_lbph = ?",
                         (1 if self.lista_negra_var.get() else 0, self.persona["label_lbph"]))

        messagebox.showinfo("Listo", "Los datos se actualizaron correctamente.")
        self.destroy()
        if self.on_guardado:
            self.on_guardado()


# ==========================================================================
# Reconocimiento en vivo
# ==========================================================================

class ReconocimientoWindow(tk.Toplevel):
    def __init__(self, master, engine):
        super().__init__(master)
        self.engine = engine
        self.title("Reconocimiento en vivo")
        self.geometry("760x660")
        self.configure(bg=COLOR_FONDO)
        self.protocol("WM_DELETE_WINDOW", self.cerrar)

        self.video_label = tk.Label(self, bg=COLOR_FONDO)
        self.video_label.pack(pady=8)
        self.estado_label = tk.Label(self, text="Estado: ESPERA", font=("Segoe UI", 12, "bold"),
                                      bg=COLOR_FONDO, fg=COLOR_TITULO)
        self.estado_label.pack()

        tk.Label(self, text="Registro de eventos:", anchor="w", bg=COLOR_FONDO).pack(
            fill="x", padx=10, pady=(10, 0))
        self.log = tk.Text(self, height=8, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        boton_estilizado(self, "Detener", self.cerrar, bg="#555").pack(pady=(0, 10))

        self.cap = cv2.VideoCapture(int(settings.get("CAMERA_INDEX")))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
        if not self.cap.isOpened():
            messagebox.showerror("Cámara", "No se pudo abrir la cámara.")
            self.destroy()
            return

        self.liveness = DetectorDeParpadeo()
        self.frames_estable = 0
        self.activo = True
        self.evaluando = False
        self._loop()

    def _log(self, texto):
        self.log.config(state="normal")
        self.log.insert("end", f"{time.strftime('%H:%M:%S')}  {texto}\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _loop(self):
        if not self.activo:
            return
        ok, frame = self.cap.read()
        if not ok:
            self.after(30, self._loop)
            return

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        rostros = self.engine.detectar_rostros(gray)

        if len(rostros) == 0 or self.evaluando:
            self.frames_estable = 0
            self.liveness.reset()
            self.estado_label.config(text="Estado: ESPERA")
        else:
            (x, y, w, h) = max(rostros, key=lambda r: r[2] * r[3])
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 255), 2)
            self.frames_estable += 1

            roi_gray = gray[y:y + h, x:x + w]
            ojos = self.engine.detectar_ojos(roi_gray)
            self.liveness.actualizar(hay_ojos=len(ojos) > 0)
            self.estado_label.config(text="Estado: ANALIZANDO (prueba de vida)...")

            listo = (
                self.frames_estable >= config.FRAMES_MINIMOS_ROSTRO_ESTABLE
                and (self.liveness.confirmado()
                     or not settings.get("LIVENESS_REQUIERE_PARPADEO")
                     or self.liveness.expirado())
            )
            if listo:
                self.evaluando = True
                self._mostrar_frame(frame)
                self.after(10, lambda: self._evaluar(roi_gray))
                return

        self._mostrar_frame(frame)
        self.after(30, self._loop)

    def _mostrar_frame(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        imgtk = ImageTk.PhotoImage(image=img)
        self.video_label.imgtk = imgtk
        self.video_label.config(image=imgtk)

    def _evaluar(self, roi_gray):
        t0 = time.time()
        label, score = self.engine.predecir(roi_gray)
        latencia = round(time.time() - t0, 3)
        umbral = float(settings.get("UMBRAL_CONFIANZA_RESIDENTE"))

        if not self.liveness.confirmado() and settings.get("LIVENESS_REQUIERE_PARPADEO"):
            self._log("⛔ Denegado: no se pudo confirmar prueba de vida (posible foto/pantalla).")
            database.log_evento("A", "denegado", score=score, detalle="Liveness no confirmado")
        elif label is not None and score >= umbral:
            persona = database.get_persona_by_label(label)
            if persona is None:
                self._log(f"(latencia de reconocimiento: {latencia}s)")
                self._abrir_chat_ia()
                return  # el loop se reanuda cuando se cierra el chat
            elif persona["lista_negra"]:
                self._log("⛔ Persona en lista negra detectada. Acceso denegado automáticamente.")
                database.log_evento("A", "denegado", persona_id=persona["id"], score=score, detalle="Lista negra")
            else:
                self._log(f"✅ Acceso permitido: {persona['nombre']} {persona['apellido']} "
                          f"(score {score}%, depto {persona['depto']})")
                database.log_evento("A", "permitido", persona_id=persona["id"], score=score,
                                     detalle="Reconocimiento directo")
                self._acceso_concedido(
                    depto=persona["depto"],
                    nombre_persona=f"{persona['nombre']} {persona['apellido']}",
                    metodo="Reconocimiento facial",
                    mensaje=f"{persona['nombre']} {persona['apellido']} - depto {persona['depto']}",
                )
        else:
            self._log(f"(latencia de reconocimiento: {latencia}s)")
            self._abrir_chat_ia()
            return  # el loop se reanuda cuando se cierra el chat

        self._log(f"(latencia de reconocimiento: {latencia}s)")
        self._reanudar_loop()

    def _acceso_concedido(self, depto, nombre_persona, metodo, mensaje=""):
        """Centraliza lo que pasa cada vez que se abre la puerta (puntos 1, 2 y 3):
        muestra la imagen de la puerta y notifica por email al propietario del depto."""
        subtitulo = f"Depto {depto} · {metodo}" if depto else metodo
        mostrar_puerta_abierta(self, nombre_persona=nombre_persona, subtitulo=subtitulo)
        emails = database.emails_por_depto(depto) if depto else []
        if emails:
            if notificaciones.enviar_notificacion_ingreso(depto, emails, nombre_persona, metodo):
                self._log(f"📧 Se notificó por email al propietario del depto {depto}.")
        elif depto:
            self._log(f"(Depto {depto} no tiene email cargado, no se notificó por correo)")

    def _reanudar_loop(self):
        self.evaluando = False
        self.frames_estable = 0
        self.liveness.reset()
        if self.activo:
            self.after(30, self._loop)

    def _abrir_chat_ia(self):
        """No reconocido: en vez del popup de antes, se abre el asistente
        conversacional (texto + voz) que completa el Camino B o C charlando."""
        self._log("🤖 Rostro no reconocido. Se abre el asistente conversacional...")
        ChatWindow(self, on_finalizar=self._chat_finalizado, on_cerrar=self._reanudar_loop)

    def _chat_finalizado(self, evento):
        """Se llama cuando el chat concede el acceso (Camino B o C)."""
        self._log(f"✅ {evento.get('detalle', 'Acceso concedido')} - depto {evento.get('depto')}")
        self._acceso_concedido(
            depto=evento["depto"],
            nombre_persona=evento.get("nombre_persona", "Persona"),
            metodo=evento.get("metodo", "Asistente virtual"),
            mensaje=f"{evento.get('nombre_persona', '')} - depto {evento['depto']}",
        )

    def cerrar(self):
        self.activo = False
        if self.cap.isOpened():
            self.cap.release()
        self.destroy()


# ==========================================================================
# Chat con el asistente conversacional (Caminos B y C)
# ==========================================================================

class ChatWindow(tk.Toplevel):
    """Reemplaza los formularios/popups del Camino B/C por una charla en
    lenguaje natural (texto y, si está disponible, voz) con un asistente
    basado en reglas (chatbot.AsistenteConversacional) — sin usar
    ninguna IA generativa externa ni API paga."""

    def __init__(self, master, on_finalizar=None, on_cerrar=None):
        super().__init__(master)
        self.on_finalizar = on_finalizar
        self.on_cerrar = on_cerrar
        self.title("Asistente virtual - Recepción")
        self.geometry("480x580")
        self.configure(bg=COLOR_FONDO)
        self.protocol("WM_DELETE_WINDOW", self._cerrar)

        self.asistente = chatbot.AsistenteConversacional()
        self.voz_habilitada = bool(settings.get("IA_VOZ_HABILITADA")) and voz.tts_disponible()
        self._resuelto = False

        tk.Label(self, text="🤖 Asistente del edificio", font=("Segoe UI", 13, "bold"),
                 bg=COLOR_FONDO, fg=COLOR_TITULO).pack(pady=(10, 0))
        if not voz.stt_disponible() or not voz.tts_disponible():
            tk.Label(self, text="(voz no disponible en esta PC — usá el teclado)",
                     font=("Segoe UI", 8), bg=COLOR_FONDO, fg="#888").pack()

        self.chat_text = tk.Text(self, state="disabled", wrap="word", font=("Segoe UI", 10), height=17)
        self.chat_text.pack(fill="both", expand=True, padx=10, pady=10)
        self.chat_text.tag_config("ia", foreground=COLOR_BOTON, font=("Segoe UI", 10, "bold"))
        self.chat_text.tag_config("usuario", foreground="#222")
        self.chat_text.tag_config("sistema", foreground="#888", font=("Segoe UI", 9, "italic"))

        self.contenedor_botones = tk.Frame(self, bg=COLOR_FONDO)
        self.contenedor_botones.pack(fill="x", padx=10)

        entrada_frame = tk.Frame(self, bg=COLOR_FONDO)
        entrada_frame.pack(fill="x", padx=10, pady=10)
        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(entrada_frame, textvariable=self.entry_var, font=("Segoe UI", 10))
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry.bind("<Return>", lambda e: self._enviar())
        self.entry.focus_set()

        boton_estilizado(entrada_frame, "Enviar", self._enviar, width=8).pack(side="left", padx=(6, 0))

        if voz.stt_disponible():
            self.boton_mic = boton_estilizado(entrada_frame, "🎤", self._escuchar, width=3, bg="#33691E")
            self.boton_mic.pack(side="left", padx=(6, 0))
        else:
            self.boton_mic = None

        self._decir_ia(self.asistente.iniciar())

    # ---- helpers de UI ----

    def _agregar(self, quien, texto, tag):
        self.chat_text.config(state="normal")
        self.chat_text.insert("end", f"{quien}: {texto}\n\n", tag)
        self.chat_text.see("end")
        self.chat_text.config(state="disabled")

    def _decir_ia(self, texto):
        self._agregar("🤖 Asistente", texto, "ia")
        if self.voz_habilitada:
            voz.hablar_async(texto)

    def _enviar(self):
        texto = self.entry_var.get().strip()
        if not texto:
            return
        self.entry_var.set("")
        self._agregar("Vos", texto, "usuario")
        self._procesar(texto)

    def _escuchar(self):
        self.boton_mic.config(state="disabled", text="🎙️...")
        self._agregar("Sistema", "Escuchando... (hablá ahora)", "sistema")
        voz.escuchar_async(self._al_escuchar, self)

    def _al_escuchar(self, texto, error):
        if self.boton_mic:
            self.boton_mic.config(state="normal", text="🎤")
        if texto:
            self.entry_var.set(texto)
            self._enviar()
        else:
            motivos = {
                "timeout": "No escuché nada. ¿Podés intentar de nuevo o escribir?",
                "no_entendido": "No te entendí bien. ¿Podés repetir o escribir?",
                "sin_soporte": "El reconocimiento de voz no está disponible en esta PC, escribime nomás.",
                "sin_microfono": "No encontré un micrófono conectado. Escribime nomás.",
                "error": "Hubo un problema con el micrófono. Escribime nomás.",
            }
            self._agregar("Sistema", motivos.get(error, "Hubo un problema con el micrófono."), "sistema")

    # ---- lógica de la conversación ----

    def _procesar(self, texto):
        mensaje_ia, evento = self.asistente.responder(texto)
        self._decir_ia(mensaje_ia)
        if evento:
            self._resolver_evento(evento)

    def _resolver_evento(self, evento):
        if evento["camino"] == "B":
            self._resolver_camino_b(evento)
        elif evento["camino"] == "C":
            self._resolver_camino_c(evento)

    def _resolver_camino_b(self, evento):
        depto, pin = evento["depto"], evento["pin"]
        persona = database.get_persona_by_pin(depto, pin)
        if persona and not persona["lista_negra"]:
            self._decir_ia(f"¡Listo, {persona['nombre']}! Acceso concedido, bienvenido.")
            self._finalizar({
                "camino": "B", "resultado": "permitido", "depto": depto,
                "persona_id": persona["id"], "detalle": "Validado por PIN (asistente conversacional)",
                "nombre_persona": f"{persona['nombre']} {persona['apellido']}",
                "metodo": "PIN vía asistente virtual",
            })
        else:
            self._decir_ia("Mmm, ese código no es válido. Voy a derivar tu caso a la administración.")
            self._finalizar({
                "camino": "B", "resultado": "denegado", "depto": depto,
                "detalle": "PIN inválido (asistente conversacional)",
            })

    def _resolver_camino_c(self, evento):
        depto, nombre = evento["depto"], evento["nombre"]

        if database.rechazos_recientes_por_depto(depto) >= config.RECHAZOS_PARA_LISTA_NEGRA:
            self._decir_ia("Este depto rechazó varias visitas hace poco, así que no puedo dejarte "
                            "pasar. Ya avisé a seguridad.")
            self._finalizar({"camino": "C", "resultado": "denegado", "depto": depto,
                              "detalle": "Bloqueo por rechazos repetidos"})
            return

        emails = database.emails_por_depto(depto)
        if notificaciones.enviar_notificacion_visita(depto, emails, detalle=f"{nombre} está en la puerta."):
            self._agregar("Sistema", f"📧 Se notificó por email al depto {depto}.", "sistema")

        self._agregar("Sistema", f"📞 Comunicando con el depto {depto}...", "sistema")
        self._mostrar_botones_autorizacion(depto, nombre)

    def _mostrar_botones_autorizacion(self, depto, nombre):
        for w in self.contenedor_botones.winfo_children():
            w.destroy()
        tk.Label(self.contenedor_botones, text=f"Simulación: respuesta del residente del depto {depto}",
                 bg=COLOR_FONDO, font=("Segoe UI", 9)).pack(anchor="w")
        fila = tk.Frame(self.contenedor_botones, bg=COLOR_FONDO)
        fila.pack(fill="x", pady=4)
        tk.Button(fila, text="Sí, autorizo", bg="#4CAF50", fg="white",
                  command=lambda: self._responder_autorizacion(depto, nombre, "s")).pack(side="left", padx=3)
        tk.Button(fila, text="No autorizo", bg="#f44336", fg="white",
                  command=lambda: self._responder_autorizacion(depto, nombre, "n")).pack(side="left", padx=3)
        tk.Button(fila, text="No atiende",
                  command=lambda: self._responder_autorizacion(depto, nombre, None)).pack(side="left", padx=3)

    def _responder_autorizacion(self, depto, nombre, resultado):
        for w in self.contenedor_botones.winfo_children():
            w.destroy()
        if resultado == "s":
            self._decir_ia(f"¡Listo, {nombre}! Te autorizaron el ingreso. Bienvenido.")
            self._finalizar({
                "camino": "C", "resultado": "permitido", "depto": depto,
                "detalle": "Autorizado por videollamada (asistente conversacional)",
                "nombre_persona": f"{nombre} (visita)", "metodo": "Visita autorizada - asistente virtual",
            })
        else:
            motivo = "Rechazado por residente" if resultado == "n" else "No atendió la llamada"
            self._decir_ia(f"Lo siento {nombre}, no pude confirmar tu ingreso ({motivo.lower()}).")
            database.registrar_rechazo_visita(depto)
            self._finalizar({"camino": "C", "resultado": "denegado", "depto": depto, "detalle": motivo})

    def _finalizar(self, evento):
        self._resuelto = True
        database.log_evento(
            evento["camino"], evento["resultado"],
            persona_id=evento.get("persona_id"), depto_destino=evento.get("depto"),
            detalle=evento.get("detalle", "")
        )
        if evento["resultado"] == "permitido" and self.on_finalizar:
            self.on_finalizar(evento)
        # se cierra sola a los pocos segundos para dar tiempo a leer el último mensaje
        self.after(3500, self._cerrar)

    def _cerrar(self):
        if not self._resuelto:
            database.log_evento("B/C", "abandono", detalle="El visitante cerró el chat sin terminar")
        if self.on_cerrar:
            self.on_cerrar()
        if self.winfo_exists():
            self.destroy()


# ==========================================================================
# Configuración
# ==========================================================================

# ==========================================================================
# Asistente administrativo (consulta y anomalías sobre los registros)
# ==========================================================================

class AdminChatWindow(tk.Toplevel):
    """Segunda IA del sistema: en vez de atender visitantes, responde
    preguntas sobre los registros de acceso y puede escanear los logs
    en busca de patrones sospechosos (agente_admin.py)."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Asistente administrativo")
        self.geometry("520x560")
        self.configure(bg=COLOR_FONDO)

        tk.Label(self, text="🛡️ IA de administración de accesos", font=("Segoe UI", 13, "bold"),
                 bg=COLOR_FONDO, fg=COLOR_TITULO).pack(pady=(12, 0))
        tk.Label(self, text="Preguntale por los registros, o pedile que busque anomalías.",
                 font=("Segoe UI", 9), bg=COLOR_FONDO, fg="#33691E").pack(pady=(0, 8))

        self.chat_text = tk.Text(self, state="disabled", wrap="word", font=("Segoe UI", 10), height=18)
        self.chat_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.chat_text.tag_config("ia", foreground=COLOR_BOTON, font=("Segoe UI", 10, "bold"))
        self.chat_text.tag_config("usuario", foreground="#222")
        self.chat_text.tag_config("alerta", foreground="#B71C1C")

        botonera = tk.Frame(self, bg=COLOR_FONDO)
        botonera.pack(fill="x", padx=10, pady=(0, 6))
        boton_estilizado(botonera, "🔍 Detectar anomalías (24hs)", self._detectar_anomalias).pack(side="left")

        entrada_frame = tk.Frame(self, bg=COLOR_FONDO)
        entrada_frame.pack(fill="x", padx=10, pady=(0, 10))
        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(entrada_frame, textvariable=self.entry_var, font=("Segoe UI", 10))
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry.bind("<Return>", lambda e: self._enviar())
        self.entry.focus_set()
        boton_estilizado(entrada_frame, "Enviar", self._enviar, width=8).pack(side="left", padx=(6, 0))

        self._agregar("🛡️ IA Admin", "Hola, puedo contarte sobre los accesos registrados. Por ejemplo: "
                       "'¿cuántos accesos hubo hoy?', '¿quién entró último?', 'accesos del depto 4B' "
                       "o '¿hay alguien en lista negra?'.", "ia")

    def _agregar(self, quien, texto, tag):
        self.chat_text.config(state="normal")
        self.chat_text.insert("end", f"{quien}: {texto}\n\n", tag)
        self.chat_text.see("end")
        self.chat_text.config(state="disabled")

    def _enviar(self):
        texto = self.entry_var.get().strip()
        if not texto:
            return
        self.entry_var.set("")
        self._agregar("Vos", texto, "usuario")
        respuesta = agente_admin.responder_pregunta(texto)
        self._agregar("🛡️ IA Admin", respuesta, "ia")

    def _detectar_anomalias(self):
        self._agregar("Vos", "Detectar anomalías en las últimas 24 horas", "usuario")
        alertas = agente_admin.detectar_anomalias(horas=24)
        for alerta in alertas:
            tag = "alerta" if alerta.startswith(("⚠️", "🚫", "👁️")) else "ia"
            self._agregar("🛡️ IA Admin", alerta, tag)


class ConfiguracionDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Configuración")
        self.geometry("380x740")
        self.configure(bg=COLOR_FONDO)
        self.grab_set()

        actuales = settings.get_all()
        self.vars = {}

        tk.Label(self, text="Cámara y reconocimiento", font=("Segoe UI", 11, "bold"),
                 bg=COLOR_FONDO, fg=COLOR_TITULO).pack(pady=(15, 5), anchor="w", padx=20)

        self._campo_texto("Índice de cámara (0, 1, 2...)", "CAMERA_INDEX", actuales)
        self._campo_texto("Umbral de confianza (%) para acceso directo", "UMBRAL_CONFIANZA_RESIDENTE", actuales)
        self._campo_texto("Fotos a capturar por enrolamiento", "FOTOS_POR_ENROLAMIENTO", actuales)
        self._campo_texto("Duración del cartel de bienvenida (milisegundos)", "DURACION_PUERTA_MS", actuales)

        self.liveness_var = tk.BooleanVar(value=actuales["LIVENESS_REQUIERE_PARPADEO"])
        tk.Checkbutton(self, text="Exigir prueba de vida (parpadeo)",
                        variable=self.liveness_var, bg=COLOR_FONDO).pack(anchor="w", padx=20, pady=5)

        tk.Label(self, text="Asistente conversacional", font=("Segoe UI", 11, "bold"),
                 bg=COLOR_FONDO, fg=COLOR_TITULO).pack(pady=(15, 5), anchor="w", padx=20)

        voz_texto = "Habilitar voz (el asistente habla, y escucha si hay micrófono)"
        if not voz.tts_disponible() and not voz.stt_disponible():
            voz_texto += "\n(no se detectaron pyttsx3/SpeechRecognition instalados)"
        self.voz_var = tk.BooleanVar(value=actuales["IA_VOZ_HABILITADA"])
        tk.Checkbutton(self, text=voz_texto, variable=self.voz_var, bg=COLOR_FONDO,
                        justify="left", wraplength=330).pack(anchor="w", padx=20, pady=5)

        tk.Label(self, text="Notificaciones por email", font=("Segoe UI", 11, "bold"),
                 bg=COLOR_FONDO, fg=COLOR_TITULO).pack(pady=(15, 5), anchor="w", padx=20)

        self.notificar_var = tk.BooleanVar(value=actuales["NOTIFICAR_VISITAS_POR_EMAIL"])
        tk.Checkbutton(self, text="Notificar accesos e ingresos por email",
                        variable=self.notificar_var, bg=COLOR_FONDO).pack(anchor="w", padx=20, pady=5)

        self._campo_texto("Servidor SMTP", "SMTP_HOST", actuales)
        self._campo_texto("Puerto SMTP", "SMTP_PORT", actuales)
        self._campo_texto("Usuario / email remitente", "SMTP_USER", actuales)
        self._campo_texto("Contraseña de aplicación", "SMTP_PASSWORD", actuales, oculto=True)
        self._campo_texto("Nombre del remitente", "SMTP_FROM_NAME", actuales)

        boton_estilizado(self, "Guardar configuración", self.guardar).pack(pady=20, fill="x", padx=20)

    def _campo_texto(self, etiqueta, clave, actuales, oculto=False):
        tk.Label(self, text=etiqueta, anchor="w", bg=COLOR_FONDO).pack(fill="x", padx=20, pady=(6, 0))
        var = tk.StringVar(value=str(actuales.get(clave, "")))
        tk.Entry(self, textvariable=var, show="*" if oculto else "").pack(fill="x", padx=20)
        self.vars[clave] = var

    def guardar(self):
        try:
            nuevos = {
                "CAMERA_INDEX": int(self.vars["CAMERA_INDEX"].get()),
                "UMBRAL_CONFIANZA_RESIDENTE": float(self.vars["UMBRAL_CONFIANZA_RESIDENTE"].get()),
                "FOTOS_POR_ENROLAMIENTO": int(self.vars["FOTOS_POR_ENROLAMIENTO"].get()),
                "DURACION_PUERTA_MS": int(self.vars["DURACION_PUERTA_MS"].get()),
                "SMTP_PORT": int(self.vars["SMTP_PORT"].get()),
            }
        except ValueError:
            messagebox.showerror("Error", "Índice de cámara, umbral, fotos, duración y puerto deben ser números.")
            return

        nuevos["LIVENESS_REQUIERE_PARPADEO"] = self.liveness_var.get()
        nuevos["IA_VOZ_HABILITADA"] = self.voz_var.get()
        nuevos["NOTIFICAR_VISITAS_POR_EMAIL"] = self.notificar_var.get()
        for clave in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM_NAME"):
            nuevos[clave] = self.vars[clave].get()

        settings.guardar(nuevos)
        messagebox.showinfo("Listo", "Configuración guardada.")
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
