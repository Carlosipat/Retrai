from flask import Flask, request
import requests
import os

# ==========================
# CONFIG
# ==========================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", 8631838501:AAGj-dyi23_Gi_bNh3XawwDVSNeAElXQc2g)
GEMINI_API = os.environ.get("GEMINI_KEY", AIzaSyBlTHfELHg3yhF4hpmOYbLmwX4r98Ziq7Y)
OPENROUTER_API = os.environ.get("OPENROUTER_KEY", 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)
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", https://retrai.onrender.com/webhook)

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
        print(f"[Gemini failed] {e} — trying OpenRouter")
        try:
            reply = ask_openrouter(history, text)
        except Exception as e2:
            print(f"[OpenRouter failed] {e2}")
            return "Sorry, I'm having trouble reaching AI services right now. Please try again."

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

        # Commands
        if text == "/start":
            memory.pop(user_id, None)
            send_message(chat_id, "👋 Hello! I'm your AI assistant powered by Gemini.\n\nSend me any message and I'll help you!\n\nCommands:\n/start - Restart\n/clear - Clear memory\n/help - Show help")
            return "ok"

        if text == "/clear":
            memory.pop(user_id, None)
            send_message(chat_id, "🗑️ Conversation history cleared! Let's start fresh.")
            return "ok"

        if text == "/help":
            send_message(chat_id, "🤖 I'm an AI assistant.\n\nJust type any message and I'll reply!\n\nCommands:\n/start - Restart bot\n/clear - Clear chat memory\n/help - This message")
            return "ok"

        # Show typing indicator
        send_typing(chat_id)

        reply = get_reply(user_id, text)
        send_message(chat_id, reply)

    except Exception as e:
        print(f"[Webhook error] {e}")

    return "ok"


@app.route("/")
def home():
    return "✅ Bot is running!"


# ==========================
# START
# ==========================
if __name__ == "__main__":
    # Register webhook
    resp = requests.get(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook",
        params={"url": f"{WEBHOOK_URL}/webhook"},
    )
    print("Webhook set:", resp.json())
    app.run(host="0.0.0.0", port=5000)
