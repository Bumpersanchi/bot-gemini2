"""Cliente mínimo de la WhatsApp Cloud API de Meta."""

import hashlib
import hmac
import logging
import os

import requests

log = logging.getLogger(__name__)

GRAPH_VERSION = os.getenv("GRAPH_API_VERSION", "v23.0")
MAX_MESSAGE_LENGTH = 4096  # límite de WhatsApp para un mensaje de texto


def verify_signature(raw_body: bytes, signature_header: str | None, app_secret: str) -> bool:
    """Comprueba la cabecera X-Hub-Signature-256 que firma Meta."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))


def extract_text_messages(payload: dict) -> list[dict]:
    """Devuelve [{"id", "from", "text"}] para cada mensaje de texto del webhook."""
    messages = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []):
                if msg.get("type") == "text":
                    messages.append(
                        {"id": msg["id"], "from": msg["from"], "text": msg["text"]["body"]}
                    )
    return messages


def split_message(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Parte un texto largo en trozos que WhatsApp acepte, cortando por saltos de línea si se puede."""
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


def send_text(to: str, body: str) -> None:
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{os.environ['WHATSAPP_PHONE_NUMBER_ID']}/messages"
    headers = {"Authorization": f"Bearer {os.environ['WHATSAPP_TOKEN']}"}
    for chunk in split_message(body):
        resp = requests.post(
            url,
            headers=headers,
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": chunk},
            },
            timeout=30,
        )
        if not resp.ok:
            log.error("Error enviando mensaje a WhatsApp (%s): %s", resp.status_code, resp.text)
            return
