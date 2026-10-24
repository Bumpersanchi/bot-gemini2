"""Bot de WhatsApp con Claude: servidor del webhook."""

import logging
import os
import threading
from collections import OrderedDict

from dotenv import load_dotenv
from flask import Flask, abort, request

load_dotenv()

import whatsapp  # noqa: E402
from claude_chat import ChatStore  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")

RESET_COMMANDS = {"/reset", "/reiniciar", "/nuevo"}

app = Flask(__name__)
chats = ChatStore()

# Meta puede reenviar el mismo mensaje varias veces; recordamos los últimos IDs.
_seen_ids: OrderedDict[str, None] = OrderedDict()
_seen_lock = threading.Lock()


def _already_seen(message_id: str) -> bool:
    with _seen_lock:
        if message_id in _seen_ids:
            return True
        _seen_ids[message_id] = None
        if len(_seen_ids) > 1000:
            _seen_ids.popitem(last=False)
        return False


def handle_message(sender: str, text: str) -> None:
    try:
        if text.strip().lower() in RESET_COMMANDS:
            chats.reset(sender)
            whatsapp.send_text(sender, "Conversación reiniciada. ¿En qué te ayudo?")
            return
        whatsapp.send_text(sender, chats.reply(sender, text))
    except Exception:
        log.exception("Error procesando el mensaje de %s", sender)


@app.get("/webhook")
def verify_webhook():
    """Verificación inicial que hace Meta al configurar el webhook."""
    if (
        request.args.get("hub.mode") == "subscribe"
        and request.args.get("hub.verify_token") == os.environ["WHATSAPP_VERIFY_TOKEN"]
    ):
        return request.args.get("hub.challenge", ""), 200
    abort(403)


@app.post("/webhook")
def receive_webhook():
    app_secret = os.getenv("WHATSAPP_APP_SECRET")
    if app_secret and not whatsapp.verify_signature(
        request.get_data(), request.headers.get("X-Hub-Signature-256"), app_secret
    ):
        abort(401)

    for msg in whatsapp.extract_text_messages(request.get_json(silent=True) or {}):
        if _already_seen(msg["id"]):
            continue
        # Respondemos a Meta enseguida y llamamos a Claude en segundo plano;
        # si tardamos, Meta reintenta el envío.
        threading.Thread(target=handle_message, args=(msg["from"], msg["text"]), daemon=True).start()
    return "ok", 200


@app.get("/")
def health():
    return "Bot de WhatsApp con Claude funcionando", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
