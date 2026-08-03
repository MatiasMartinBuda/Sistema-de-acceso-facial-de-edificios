"""
Agente Intercomunicador conversacional (Sección 4 del PDF).

Chatbot basado en reglas -no en un modelo de lenguaje externo, así no
depende de ninguna API paga- que conversa en lenguaje natural con la
persona frente al tótem para completar el Camino B (residente sin
reconocimiento facial) o el Camino C (visita), en vez de mostrarle
formularios/popups.

Uso típico:

    asistente = AsistenteConversacional()
    mensaje = asistente.iniciar()               # primer saludo
    ...
    mensaje, evento = asistente.responder(texto_del_usuario)
    # `evento` es None mientras la charla sigue, o un dict con lo que
    # hay que hacer (validar PIN, avisar a un depto, etc.) cuando
    # el asistente ya juntó todos los datos que necesitaba.
"""
import re
try:
    import ia_service
except ImportError:
    ia_service = None

AFIRMATIVO = {"si", "sí", "s", "yes", "obvio", "correcto", "dale", "sip", "claro"}

NEGATIVO = {"no", "nop", "para nada", "negativo", "nel"}

_NUMEROS_EN_PALABRAS = {
    "primero": "1", "primer": "1", "uno": "1",
    "segundo": "2", "dos": "2",
    "tercero": "3", "tercer": "3", "tres": "3",
    "cuarto": "4", "cuatro": "4",
    "quinto": "5", "cinco": "5",
    "sexto": "6", "seis": "6",
    "septimo": "7", "séptimo": "7", "siete": "7",
    "octavo": "8", "ocho": "8",
    "noveno": "9", "nueve": "9",
    "decimo": "10", "décimo": "10", "diez": "10",
}

_RELLENO_DEPTO = ["voy al", "voy a la", "voy a", "vengo al", "departamento", "depto",
                   "número", "numero", "piso", "el ", "la "]

_PREFIJOS_NOMBRE = ["me llamo ", "mi nombre es ", "soy la ", "soy el ", "soy "]


def _contiene_alguna(texto, palabras):
    t = texto.lower()
    return any(p in t for p in palabras)


def _extraer_depto(texto):
    t = f" {texto.lower().strip()} "
    for palabra in _RELLENO_DEPTO:
        t = t.replace(f" {palabra}", " ")
    t = t.strip()

    # caso "4b", "12 c"
    m = re.search(r"\b(\d{1,3}\s?[a-zA-Z])\b", t)
    if m:
        return m.group(1).replace(" ", "").upper()

    # caso solo número: "4", "12"
    m = re.search(r"\b(\d{1,3})\b", t)
    if m:
        return m.group(1)

    # caso número escrito en palabras: "primero", "cuarto b", etc.
    for palabra, numero in _NUMEROS_EN_PALABRAS.items():
        if palabra in t:
            m2 = re.search(r"\b([a-dA-D])\b", t.replace(palabra, ""))
            letra = m2.group(1).upper() if m2 else ""
            return numero + letra

    return t.strip().upper() if t.strip() else texto.strip().upper()


def _extraer_pin(texto):
    digitos = re.findall(r"\d", texto)
    return "".join(digitos) if digitos else texto.strip()


def _extraer_nombre(texto):
    t = texto.strip()
    tl = t.lower()
    for prefijo in _PREFIJOS_NOMBRE:
        if tl.startswith(prefijo):
            t = t[len(prefijo):]
            break
    return t.strip().title() if t.strip() else "Visitante"


class AsistenteConversacional:
    def __init__(self):
        self.estado = "inicio"
        self.datos = {}

    def iniciar(self):
        self.estado = "inicio"
        self.datos = {}
        return ("¡Hola! Bienvenido, soy el asistente virtual del edificio. "
                "¿Sos residente o venís de visita?")

    def responder(self, texto):
        texto = (texto or "").strip()
        if not texto:
            return "No te escuché bien, ¿podés repetirlo?", None
        metodo = getattr(self, f"_estado_{self.estado}", None)
        if metodo is None:
            return self.iniciar(), None
        return metodo(texto)

    # ---------------- Estado inicial ----------------

    def _estado_inicio(self, texto):
        t = texto.lower()
        # ojo: hay que chequear negaciones ("no resido", "no vivo acá")
        # ANTES que las palabras positivas, porque "no resido" contiene
        # la palabra "resid" y si no, se interpretaría al revés.
        if re.search(r"\bno\s+(resid|vivo|soy)", t):
            self.estado = "c_nombre"
            return "Dale, decime tu nombre por favor.", None
        if _contiene_alguna(t, ["resid", "vivo", "propietario", "inquilino"]) or t in AFIRMATIVO:
            self.estado = "b_depto"
            return "Perfecto. Decime tu número de departamento (por ejemplo 4B).", None
        if _contiene_alguna(t, ["visit", "no soy"]) or t in NEGATIVO:
            self.estado = "c_nombre"
            return "Dale, decime tu nombre por favor.", None
        if ia_service:
            prompt_ia = f"El usuario en la puerta dijo: '{texto}'. Respondé amablemente preguntándole si es residente del edificio o si viene de visita."
            resp = ia_service.obtener_respuesta_ia(prompt_ia, "Sos un recepcionista virtual conciso y amable.")
            if resp:
                return resp, None

        return ("No te entendí bien. ¿Sos residente del edificio o venís de "
                "visita? Podés responder 'residente' o 'visita'."), None


    # ---------------- Camino B: residente con PIN ----------------

    def _estado_b_depto(self, texto):
        self.datos["depto"] = _extraer_depto(texto)
        self.estado = "b_depto_confirmar"
        return f"Entendí depto {self.datos['depto']}. ¿Es correcto? (sí/no)", None

    def _estado_b_depto_confirmar(self, texto):
        t = texto.lower()
        if t in AFIRMATIVO or _contiene_alguna(t, ["si", "correcto", "exacto"]):
            self.estado = "b_pin"
            return "Buenísimo. Ahora decime tu código PIN.", None
        self.estado = "b_depto"
        return "Perdón, decime de nuevo el número de depto.", None

    def _estado_b_pin(self, texto):
        self.datos["pin"] = _extraer_pin(texto)
        self.estado = "fin"
        return "Gracias, dejame verificarlo...", {
            "camino": "B",
            "depto": self.datos["depto"],
            "pin": self.datos["pin"],
        }

    # ---------------- Camino C: visita ----------------

    def _estado_c_nombre(self, texto):
        self.datos["nombre"] = _extraer_nombre(texto)
        self.estado = "c_depto"
        return f"Un gusto, {self.datos['nombre']}. ¿A qué departamento venís? Por ejemplo 4B.", None

    def _estado_c_depto(self, texto):
        self.datos["depto"] = _extraer_depto(texto)
        self.estado = "c_depto_confirmar"
        return f"Entendí depto {self.datos['depto']}. ¿Es correcto? (sí/no)", None

    def _estado_c_depto_confirmar(self, texto):
        t = texto.lower()
        if t in AFIRMATIVO or _contiene_alguna(t, ["si", "correcto", "exacto"]):
            self.estado = "fin"
            return (f"Dale, voy a avisarle al depto {self.datos['depto']} que estás "
                    f"en la puerta. Un momento."), {
                "camino": "C",
                "depto": self.datos["depto"],
                "nombre": self.datos["nombre"],
            }
        self.estado = "c_depto"
        return "Perdón, decime de nuevo a qué depto vas.", None

    def _estado_fin(self, texto):
        return "Ya te avisé el resultado más arriba. Que tengas buen día.", None
