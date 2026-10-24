# bot-gemini2 — Bot de WhatsApp con Claude

Bot que responde mensajes de WhatsApp usando **Claude** (Anthropic) a través de la
**WhatsApp Cloud API oficial de Meta**. Recuerda la conversación de cada persona.

## Cómo funciona

```
WhatsApp ──► Meta ──(webhook)──► app.py ──► Claude
                                   │
WhatsApp ◄── Meta ◄──(Graph API)───┘
```

- `app.py` — servidor Flask que recibe los mensajes en `/webhook`.
- `claude_chat.py` — guarda el historial de cada usuario y pide la respuesta a Claude.
- `whatsapp.py` — verifica la firma de Meta y envía las respuestas.

Comandos dentro del chat: `/reset`, `/reiniciar` o `/nuevo` borran la conversación.

## 1. Requisitos

- Python 3.10 o superior.
- Una clave de API de Anthropic: <https://console.anthropic.com/settings/keys>
- Una app en Meta for Developers con el producto **WhatsApp**: <https://developers.facebook.com/apps>
  (Meta te da un número de prueba gratis).

## 2. Instalación

```bash
python -m venv .venv
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # y rellena los valores
```

En `.env` necesitas:

| Variable | Dónde se consigue |
|---|---|
| `ANTHROPIC_API_KEY` | Consola de Anthropic → API Keys |
| `WHATSAPP_TOKEN` | Meta → tu app → WhatsApp → Configuración de la API (token temporal, o uno permanente de un usuario del sistema) |
| `WHATSAPP_PHONE_NUMBER_ID` | La misma página: "Identificador del número de teléfono" |
| `WHATSAPP_VERIFY_TOKEN` | Una palabra secreta que **tú inventas** |
| `WHATSAPP_APP_SECRET` | Meta → tu app → Configuración → Básica → Clave secreta de la app |

Opcionales: `BOT_MODEL` (por defecto `claude-opus-5-5`), `BOT_EFFORT` (`low` por defecto;
súbelo a `medium` o `high` si quieres respuestas más elaboradas) y `SYSTEM_PROMPT` para darle
otra personalidad al bot (por ejemplo, "Eres el asistente de mi tienda de zapatillas…").

## 3. Arrancar el bot

```bash
python app.py                                  # desarrollo
gunicorn -w 1 --threads 8 -b 0.0.0.0:8000 app:app   # producción
```

> Usa un solo proceso (`-w 1`): el historial de conversaciones vive en memoria.

Meta necesita una URL pública con HTTPS. Para probar en tu ordenador puedes usar
[ngrok](https://ngrok.com/): `ngrok http 8000`. Para tenerlo siempre encendido, despliégalo
en Render (siguiente sección), Railway, Fly.io o un VPS.

### Desplegar en Render

El repositorio incluye `render.yaml`, así que Render lo configura casi todo solo.

1. Entra en <https://dashboard.render.com> (puedes registrarte con tu cuenta de GitHub).
2. **New** → **Blueprint** → conecta GitHub y elige el repositorio `bot-gemini2`.
3. Render te pedirá los valores secretos. Pega los de la tabla de arriba:
   `ANTHROPIC_API_KEY`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` y `WHATSAPP_APP_SECRET`.
   `WHATSAPP_VERIFY_TOKEN` se genera solo.
4. Pulsa **Apply**. Cuando termine, tendrás una URL como
   `https://whatsapp-claude-bot.onrender.com`. Si la abres debe decir
   "Bot de WhatsApp con Claude funcionando".
5. En Render → tu servicio → **Environment**, copia el valor de `WHATSAPP_VERIFY_TOKEN`:
   lo necesitas en el paso 4 de abajo, con la URL `https://whatsapp-claude-bot.onrender.com/webhook`.

Notas:

- El blueprint usa el plan **Starter** (unos 7 $/mes). El plan **Free** también funciona
  (cambia `plan: starter` por `plan: free`), pero el servidor se duerme tras 15 minutos sin
  mensajes: el primer mensaje tarda casi un minuto en contestarse y se pierde el historial.
- El token temporal de Meta caduca a las 24 horas. Para producción crea un token permanente:
  Meta Business Suite → Configuración del negocio → **Usuarios del sistema** → genera un token
  con los permisos `whatsapp_business_messaging` y `whatsapp_business_management`, y
  cámbialo en Render → **Environment**.
- Cada vez que fusiones cambios en `main`, Render vuelve a desplegar el bot automáticamente.

## 4. Conectar el webhook en Meta

1. Meta → tu app → WhatsApp → **Configuración** → Webhook → *Editar*.
2. URL de devolución de llamada: `https://TU-DOMINIO/webhook`
3. Token de verificación: el mismo valor que pusiste en `WHATSAPP_VERIFY_TOKEN`.
4. Pulsa *Verificar y guardar* y suscríbete al campo **messages**.
5. En *Configuración de la API*, añade tu número personal como destinatario de prueba y
   escribe al número de prueba. ¡El bot debería contestarte!

## Pruebas

```bash
pip install -r requirements-dev.txt
pytest
```

## Limitaciones

- El historial se guarda en memoria: se pierde al reiniciar el servidor.
- Solo responde a mensajes de texto (ignora fotos, audios, etc.).
- Con el número de prueba de Meta solo puedes escribir a números que hayas añadido como destinatarios.
