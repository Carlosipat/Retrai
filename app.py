from flask import Flask, request
import requests
import os

# ==========================
# CONFIG
# ==========================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API", "YOUR_GEMINI_API_KEY")
OPENROUTER_KEY = os.environ.get("OPENROUTER_API", "YOUR_OPENROUTER_API_KEY")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "YOUR_RENDER_URL")

SYSTEM_PROMPT = """
You are a smart, friendly AI assistant.
Be helpful, concise, and natural in your replies.
Remember the conversation context.
"""

MAX_HISTORY = 6

# ==========================
app = Flask(__name__)
memory: dict = {}


# ==========================
# TELEGRAM
# ==========================
def send_message(chat_id: int, text: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)


def send_typing(chat_id: int) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction"
    requests.post(url, json={"chat_id": chat_id, "action": "typing"}, timeout=5)


# ==========================
# GEMINI
# ==========================
def ask_gemini(history: list, user_text: str) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-1.5-flash:generateContent?key={GEMINI_API}"
    )

    contents = []
    for item in history[-(MAX_HISTORY * 2):]:
        role = "model" if item["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": item["content"]}]})

    contents.append({"role": "user", "parts": [{"text": user_text}]})

    data = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
    }

    r = requests.post(url, json=data, timeout=30)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


# ==========================
# OPENROUTER (FALLBACK)
# ==========================
def ask_openrouter(history: list, user_text: str) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += history[-(MAX_HISTORY * 2):]
    messages.append({"role": "user", "content": user_text})

    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API}",
            "Content-Type": "application/json",
        },
        json={"model": "openai/gpt-4o-mini", "messages": messages},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


# ==========================
# REPLY LOGIC
# ==========================
def get_reply(user_id: int, text: str) -> str:
    history = memory.setdefault(user_id, [])

    try:
        reply = ask_gemini(history, text)
    except Exception as e:
        print(f"[Gemini failed] {type(e).__name__}: {e}")
        try:
            reply = ask_openrouter(history, text)
        except Exception as e2:
            print(f"[OpenRouter failed] {type(e2).__name__}: {e2}")
            # Shows actual error in Telegram for debugging
            return f"⚠️ Debug Info:\n\nGemini error:\n{e}\n\nOpenRouter error:\n{e2}"

    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": reply})

    return reply


# ==========================
# ROUTES
# ==========================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True)
    if not data:
        return "ok"

    try:
        msg = data.get("message", {})
        chat_id = msg["chat"]["id"]
        user_id = msg["from"]["id"]
        text = msg.get("text", "").strip()

        if not text:
            return "ok"

        if text == "/start":
            memory.pop(user_id, None)
            send_message(chat_id, "👋 Hello! I'm your AI assistant powered by Gemini.\n\nSend me any message!\n\nCommands:\n/start - Restart\n/clear - Clear memory\n/help - Help")
            return "ok"

        if text == "/clear":
            memory.pop(user_id, None)
            send_message(chat_id, "🗑️ Conversation history cleared!")
            return "ok"

        if text == "/help":
            send_message(chat_id, "🤖 AI Assistant\n\nJust type any message!\n\nCommands:\n/start - Restart\n/clear - Clear memory\n/help - This message")
            return "ok"

        send_typing(chat_id)
        reply = get_reply(user_id, text)
        send_message(chat_id, reply)

    except Exception as e:
        print(f"[Webhook error] {e}")

    return "ok"


# ==========================
# DEBUG ROUTE
# ==========================
@app.route("/")
def home():
    return (
        f"✅ Bot is running!<br><br>"
        f"Telegram token ends: ...{TELEGRAM_TOKEN[-6:]}<br>"
        f"Gemini key ends: ...{GEMINI_API[-6:]}<br>"
        f"OpenRouter key ends: ...{OPENROUTER_API[-6:]}<br>"
        f"Webhook URL: {WEBHOOK_URL}"
    )


# ==========================
# START
# ==========================
if __name__ == "__main__":
    resp = requests.get(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook",
        params={"url": f"{WEBHOOK_URL}/webhook"},
    )
    print("Webhook set:", resp.json())
    app.run(host="0.0.0.0", port=5000)
