"""Envío SMTP con TLS; las credenciales se configuran en variables de entorno."""
import json
import hashlib
from urllib.request import Request, urlopen
import smtplib
import ssl
from email.message import EmailMessage
from app.core.config import settings

def mail_is_configured():
    return bool((settings.STORIES_MAIL_FROM or settings.SMTP_FROM) and (settings.RESEND_API_KEY or settings.SMTP_HOST))

def send_password_reset(email: str, link: str):
    message = EmailMessage()
    message["Subject"] = "Recuperá tu acceso a System Lab Stories"
    message["From"] = settings.STORIES_MAIL_FROM or settings.SMTP_FROM
    message["To"] = email
    message.set_content(
        "Recibimos una solicitud para restablecer tu contraseña de System Lab Stories.\n\n"
        "Abrí este enlace (vence en 30 minutos y solo se puede usar una vez):\n" + link +
        "\n\nSi no lo solicitaste, podés ignorar este correo. Tu contraseña no cambiará."
    )
    if settings.RESEND_API_KEY:
        payload = {"from": message["From"], "to": [email], "subject": message["Subject"], "text": message.get_content()}
        request = Request("https://api.resend.com/emails", data=json.dumps(payload).encode(), method="POST", headers={
            "Authorization": "Bearer " + settings.RESEND_API_KEY,
            "Content-Type": "application/json", "User-Agent": "SystemLab-Stories/1.0",
            "Idempotency-Key": hashlib.sha256(link.encode()).hexdigest(),
        })
        with urlopen(request, timeout=20) as response:
            if not json.loads(response.read()).get("id"):
                raise RuntimeError("El proveedor no confirmó el envío.")
        return
    context = ssl.create_default_context()
    factory = smtplib.SMTP_SSL if settings.SMTP_USE_SSL else smtplib.SMTP
    options = {"context": context} if settings.SMTP_USE_SSL else {}
    with factory(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20, **options) as client:
        if not settings.SMTP_USE_SSL:
            client.starttls(context=context)
        if settings.SMTP_USERNAME:
            client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        client.send_message(message)
