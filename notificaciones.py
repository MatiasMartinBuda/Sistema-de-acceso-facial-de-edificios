"""
Agente de Intercomunicación y Notificaciones (Sección 4 del PDF).

Envía un email al/los propietario(s) de un depto cuando llega una visita
(Camino C), simulando el aviso que en el documento se hace por app/push.

Si el envío falla (sin internet, credenciales mal puestas, etc.) el
sistema NO se cae: se loguea el error y el flujo de acceso sigue andando
con la simulación de la videollamada.
"""
import smtplib
import ssl
import threading
from email.mime.text import MIMEText
from email.utils import formataddr

import settings


def enviar_notificacion_visita(depto, emails_destino, detalle=""):
    """Notifica a los propietarios/inquilinos de `depto` que hay una visita en la puerta."""
    if not emails_destino:
        print(f"[Notificaciones] Depto {depto} no tiene email cargado, no se notifica por correo.")
        return False

    asunto = f"🔔 Visita en la puerta - Depto {depto}"
    cuerpo = (
        f"Hola,\n\n"
        f"Hay una visita en la puerta de acceso solicitando ingreso a tu unidad ({depto}).\n"
        f"{detalle}\n\n"
        f"Este es un mensaje automático del sistema de acceso inteligente del edificio."
    )

    # Disparar en segundo plano para no demorar la respuesta de la web
    threading.Thread(target=_enviar_smtp, args=(emails_destino, asunto, cuerpo), daemon=True).start()
    return True


def enviar_notificacion_ingreso(depto, emails_destino, nombre_persona, metodo, detalle=""):
    """Notifica al/los propietario(s) de `depto` que se concedió un ingreso."""
    if not emails_destino:
        return False

    asunto = f"✅ Acceso concedido - Depto {depto}"
    cuerpo = (
        f"Hola,\n\n"
        f"Se registró un ingreso autorizado a tu unidad ({depto}).\n"
        f"Persona: {nombre_persona}\n"
        f"Método: {metodo}\n"
        f"{detalle}\n\n"
        f"Este es un mensaje automático del sistema de acceso inteligente del edificio."
    )

    threading.Thread(target=_enviar_smtp, args=(emails_destino, asunto, cuerpo), daemon=True).start()
    return True


def probar_envio_email(destinatario):
    """Envía un email de prueba para verificar credenciales SMTP."""
    asunto = "🧪 Prueba de Configuración de Correo - Sistema Acceso Facial"
    cuerpo = (
        "¡Hola!\n\n"
        "Este es un correo de prueba enviado desde tu Sistema Inteligente de Acceso Residencial.\n"
        "Las notificaciones por correo electrónico están funcionando correctamente.\n"
    )
    return _enviar_smtp([destinatario], asunto, cuerpo)


def _enviar_smtp(destinatarios, asunto, cuerpo):
    smtp_host = settings.get("SMTP_HOST") or "smtp.gmail.com"
    smtp_port = int(settings.get("SMTP_PORT") or 587)
    smtp_user = settings.get("SMTP_USER") or ""
    smtp_password = settings.get("SMTP_PASSWORD") or ""
    smtp_from_name = settings.get("SMTP_FROM_NAME") or "Sistema de Acceso - Edificio"

    if not smtp_user or not smtp_password:
        print("[Notificaciones] No se configuró usuario o contraseña SMTP. Omitiendo envío de correo.")
        return False

    try:
        msg = MIMEText(cuerpo, "plain", "utf-8")
        msg["Subject"] = asunto
        msg["From"] = formataddr((smtp_from_name, smtp_user))
        msg["To"] = ", ".join(destinatarios)

        contexto = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls(context=contexto)
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, destinatarios, msg.as_string())
        print(f"[Notificaciones] Email enviado con éxito a: {', '.join(destinatarios)}")
        return True
    except Exception as e:
        print(f"[Notificaciones Error] No se pudo enviar el correo: {e}")
        return False

