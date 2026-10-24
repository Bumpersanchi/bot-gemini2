"""Conversaciones con Claude, una por cada número de WhatsApp."""

import logging
import os
import threading

import anthropic

log = logging.getLogger(__name__)

MODEL = os.getenv("BOT_MODEL", "claude-opus-5-5")
EFFORT = os.getenv("BOT_EFFORT", "low")  # low | medium | high | xhigh | max
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "Eres un asistente amable que responde por WhatsApp. "
    "Responde en el idioma del usuario, de forma breve y clara. "
    "No uses tablas ni encabezados Markdown: WhatsApp solo admite "
    "*negrita*, _cursiva_ y listas sencillas.",
)

# Compaction resume la conversación en el servidor cuando crece mucho, así que
# nunca recortamos el historial a mano (editarlo invalidaría el razonamiento
# guardado). "default" reintenta en otro modelo si Claude rechaza la petición.
BETAS = ["compact-2026-01-12", "server-side-fallback-2026-07-01"]

ERROR_REPLY = "Lo siento, ahora mismo no puedo responder. Inténtalo de nuevo en un momento."
REFUSAL_REPLY = "Lo siento, no puedo ayudarte con eso."


class ChatStore:
    """Guarda en memoria el historial de cada usuario."""

    def __init__(self, client: anthropic.Anthropic | None = None):
        self.client = client or anthropic.Anthropic()
        self._histories: dict[str, list] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock_for(self, user_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(user_id, threading.Lock())

    def reset(self, user_id: str) -> None:
        with self._lock_for(user_id):
            self._histories.pop(user_id, None)

    def reply(self, user_id: str, text: str) -> str:
        # Un mensaje a la vez por usuario, para que el historial no se mezcle.
        with self._lock_for(user_id):
            history = self._histories.setdefault(user_id, [])
            request = history + [{"role": "user", "content": text}]
            try:
                response = self.client.beta.messages.create(
                    model=MODEL,
                    max_tokens=16000,
                    system=SYSTEM_PROMPT,
                    messages=request,
                    output_config={"effort": EFFORT},
                    betas=BETAS,
                    fallbacks="default",
                    context_management={"edits": [{"type": "compact_20260112"}]},
                )
            except anthropic.RateLimitError:
                log.warning("Límite de peticiones de Anthropic alcanzado")
                return ERROR_REPLY
            except anthropic.APIStatusError as e:
                log.error("Error de la API de Anthropic (%s): %s", e.status_code, e.message)
                return ERROR_REPLY
            except anthropic.APIConnectionError:
                log.error("No se pudo conectar con la API de Anthropic")
                return ERROR_REPLY

            if response.stop_reason == "refusal":
                # No guardamos el turno rechazado: el usuario puede seguir hablando.
                return REFUSAL_REPLY

            # Guardamos el contenido completo (no solo el texto) para conservar
            # los bloques de compaction y de razonamiento.
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": response.content})

            answer = "".join(b.text for b in response.content if b.type == "text").strip()
            return answer or ERROR_REPLY
