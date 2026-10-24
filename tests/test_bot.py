import hashlib
import hmac
import json
import os
import sys
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ["WHATSAPP_VERIFY_TOKEN"] = "secreto"
os.environ["WHATSAPP_APP_SECRET"] = "app-secret"

import app as bot  # noqa: E402
import whatsapp  # noqa: E402
from claude_chat import REFUSAL_REPLY, ChatStore  # noqa: E402


def _payload(msg_id="wamid.1", sender="34600000000", text="Hola"):
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"messages": [
            {"id": msg_id, "from": sender, "type": "text", "text": {"body": text}}
        ]}}]}],
    }


def _signed_post(client, payload):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
    return client.post(
        "/webhook", data=body, content_type="application/json",
        headers={"X-Hub-Signature-256": sig},
    )


def test_verify_webhook():
    client = bot.app.test_client()
    ok = client.get("/webhook?hub.mode=subscribe&hub.verify_token=secreto&hub.challenge=123")
    assert ok.status_code == 200 and ok.data == b"123"
    bad = client.get("/webhook?hub.mode=subscribe&hub.verify_token=otro&hub.challenge=123")
    assert bad.status_code == 403


def test_rejects_bad_signature():
    client = bot.app.test_client()
    resp = client.post("/webhook", json=_payload(), headers={"X-Hub-Signature-256": "sha256=mal"})
    assert resp.status_code == 401


def test_message_is_answered_once():
    client = bot.app.test_client()
    with mock.patch.object(bot.threading, "Thread") as thread:
        _signed_post(client, _payload(msg_id="wamid.dup"))
        _signed_post(client, _payload(msg_id="wamid.dup"))
    assert thread.call_count == 1
    assert thread.call_args.kwargs["args"] == ("34600000000", "Hola")


def test_handle_message_sends_claude_reply():
    with mock.patch.object(bot.chats, "reply", return_value="¡Hola!"), \
         mock.patch.object(bot.whatsapp, "send_text") as send:
        bot.handle_message("346", "Hola")
    send.assert_called_once_with("346", "¡Hola!")


def test_reset_command():
    with mock.patch.object(bot.chats, "reset") as reset, \
         mock.patch.object(bot.whatsapp, "send_text"):
        bot.handle_message("346", "/reset")
    reset.assert_called_once_with("346")


def test_extract_ignores_non_text():
    payload = _payload()
    payload["entry"][0]["changes"][0]["value"]["messages"].append({"id": "x", "from": "1", "type": "image"})
    assert whatsapp.extract_text_messages(payload) == [{"id": "wamid.1", "from": "34600000000", "text": "Hola"}]
    assert whatsapp.extract_text_messages({"entry": [{"changes": [{"value": {"statuses": []}}]}]}) == []


def test_split_message():
    text = "a" * 3000 + "\n" + "b" * 3000
    chunks = whatsapp.split_message(text)
    assert chunks == ["a" * 3000, "b" * 3000]
    assert all(len(c) <= 4096 for c in whatsapp.split_message("x" * 10000))


def _response(text, stop_reason="end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=text)],
    )


def test_chat_store_keeps_history_per_user():
    client = mock.Mock()
    client.beta.messages.create.side_effect = [_response("Hola Ana"), _response("Te llamas Ana")]
    store = ChatStore(client=client)

    assert store.reply("1", "Me llamo Ana") == "Hola Ana"
    assert store.reply("1", "¿Cómo me llamo?") == "Te llamas Ana"

    sent = client.beta.messages.create.call_args.kwargs["messages"]
    assert [m["role"] for m in sent] == ["user", "assistant", "user"]
    assert sent[-1]["content"] == "¿Cómo me llamo?"


def test_chat_store_refusal_not_saved():
    client = mock.Mock()
    client.beta.messages.create.return_value = _response("", stop_reason="refusal")
    store = ChatStore(client=client)
    assert store.reply("1", "algo") == REFUSAL_REPLY
    assert store._histories["1"] == []
