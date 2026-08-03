"""
Servicio híbrido de Inteligencia Artificial Generativa.

Soporta:
1. Google Gemini API (mediante la librería oficial `google-genai` o `google-generativeai`).
2. Ollama (IA Local gratuita).
3. Fallback automático: Si no hay API key o no hay conexión, retorna None para
   que el sistema use las reglas estáticas sin romper nada.
"""
import os
import settings

def obtener_respuesta_ia(prompt: str, system_instruction: str = "") -> str | None:
    """Genera una respuesta usando el proveedor configurado en settings.
    Retorna la cadena con la respuesta de la IA o None si falla/no está configurada.
    """
    if not settings.get("USAR_IA_GENERATIVA"):
        return None

    provider = settings.get("IA_PROVIDER") or "auto"
    api_key = settings.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")

    # --- Intentar Google Gemini API ---
    if provider in ("gemini", "auto") and api_key:
        resp = _consultar_gemini(prompt, system_instruction, api_key)
        if resp:
            return resp

    # --- Intentar Ollama (Local) ---
    if provider in ("ollama", "auto"):
        model = settings.get("OLLAMA_MODEL") or "llama3"
        host = settings.get("OLLAMA_HOST") or "http://localhost:11434"
        resp = _consultar_ollama(prompt, system_instruction, model, host)
        if resp:
            return resp

    return None


def _consultar_gemini(prompt: str, system_instruction: str, api_key: str) -> str | None:
    try:
        # 1. Intentar el SDK nuevo google-genai
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            full_prompt = f"{system_instruction}\n\nPregunta/Entrada: {prompt}" if system_instruction else prompt
            res = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=full_prompt
            )
            if res and hasattr(res, "text") and res.text:
                return res.text.strip()
        except ImportError:
            pass

        # 2. Fallback al SDK tradicional google-generativeai
        try:
            import google.generativeai as genai_old
            genai_old.configure(api_key=api_key)
            model = genai_old.GenerativeModel("gemini-1.5-flash", system_instruction=system_instruction or None)
            res = model.generate_content(prompt)
            if res and hasattr(res, "text") and res.text:
                return res.text.strip()
        except ImportError:
            pass

    except Exception:
        pass  # Ante cualquier error de red o cuota, se ignora y devuelve None

    return None


def _consultar_ollama(prompt: str, system_instruction: str, model: str, host: str) -> str | None:
    try:
        import ollama
        client = ollama.Client(host=host)
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        res = client.chat(model=model, messages=messages)
        if res and "message" in res and "content" in res["message"]:
            return res["message"]["content"].strip()
    except Exception:
        pass

    return None
