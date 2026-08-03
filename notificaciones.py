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
from email.mime.text import MIMEText
from email.utils import formataddr

import settings


def enviar_notificacion_visita(depto, emails_destino, detalle=""):
    """Notifica a los propietarios/inquilinos de `depto` que hay una
    visita en la puerta. Devuelve True si se pudo enviar, False si no."""
    if not settings.get("NOTIFICAR_VISITAS_POR_EMAIL"):
        return False
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

    try:
        _enviar_smtp(emails_destino, asunto, cuerpo)
        print(f"[Notificaciones] Email enviado a: {', '.join(emails_destino)}")
        return True
    except Exception as e:
        print(f"[Notificaciones] No se pudo enviar el email ({e}). Continúa con la simulación por consola.")
        return False


def enviar_notificacion_ingreso(depto, emails_destino, nombre_persona, metodo, detalle=""):
    """Notifica al/los propietario(s) de `depto` que se concedió un
    ingreso. Se usa tanto para reconocimiento facial (Camino A) como
    para accesos sin registro facial (PIN - Camino B, o visita
    autorizada - Camino C)."""
    if not settings.get("NOTIFICAR_VISITAS_POR_EMAIL"):
        return False
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

    try:
        _enviar_smtp(emails_destino, asunto, cuerpo)
        print(f"[Notificaciones] Email de ingreso enviado a: {', '.join(emails_destino)}")
        return True
    except Exception as e:
        print(f"[Notificaciones] No se pudo enviar el email de ingreso ({e}).")
        return False


def _enviar_smtp(destinatarios, asunto, cuerpo):
    smtp_host = settings.get("SMTP_HOST")
    smtp_port = int(settings.get("SMTP_PORT"))
    smtp_user = settings.get("SMTP_USER")
    smtp_password = settings.get("SMTP_PASSWORD")
    smtp_from_name = settings.get("SMTP_FROM_NAME")

    msg = MIMEText(cuerpo, "plain", "utf-8")
    msg["Subject"] = asunto
    msg["From"] = formataddr((smtp_from_name, smtp_user))
    msg["To"] = ", ".join(destinatarios)

    contexto = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
        server.starttls(context=contexto)
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, destinatarios, msg.as_string())
