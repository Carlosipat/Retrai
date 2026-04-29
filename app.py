from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from google import genai
from google.genai import types
from openai import OpenAI
import os
import asyncio

# ----------------------------
# ENV VARIABLES
# ----------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
GEMINI_KEY = os.getenv("GEMINI_KEY")

# ----------------------------
# GEMINI SETUP
# ----------------------------
client_gemini = genai.Client(api_key=GEMINI_KEY)

GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

# ----------------------------
# FLASK + TELEGRAM SETUP
# ----------------------------
app = Flask(__name__)
bot = Bot(token=TELEGRAM_TOKEN)
ptb_app = Application.builder().token(TELEGRAM_TOKEN).build()

# ----------------------------
# MEMORY
# ----------------------------
memory = {}

# ----------------------------
# AI FUNCTION
# ----------------------------
def ask_ai(uid, text):
    history = memory.setdefault(uid, [])
    history.append({"role": "user", "parts": [text]})

    for model_name in GEMINI_MODELS:
        try:
            response = client_gemini.models.generate_content(
                model=model_name,
                contents=history,
                config=types.GenerateContentConfig(
                    system_instruction="You are a helpful AI assistant.",
                    max_output_tokens=600
                )
            )
            reply = response.text
            history.append({"role": "model", "parts": [reply]})
            memory[uid] = history[-10:]
            return reply
        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower() or "rate" in err.lower():
                continue
            else:
                return f"⚠️ Error: {err}"

    # Final fallback: OpenRouter DeepSeek
    try:
        client = OpenAI(
            api_key=OPENROUTER_KEY,
            base_url="https://openrouter.ai/api/v1"
        )
        res = client.chat.completions.create(
            model="deepseek/deepseek-r1:free",
            messages=[{"role": "user", "content": text}],
            max_tokens=600
        )
        return res.choices[0].message.content
    except Exception as e:
        return f"⚠️ OpenRouter Error: {str(e)}"

# ----------------------------
# TELEGRAM HANDLER
# ----------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text
    reply = ask_ai(uid, text)
    await update.message.reply_text(reply)

ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

# ----------------------------
# EVENT LOOP
# ----------------------------
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.run_until_complete(ptb_app.initialize())

# ----------------------------
# ROUTES
# ----------------------------
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, bot)
    loop.run_until_complete(ptb_app.process_update(update))
    return "ok"

@app.route("/setwebhook")
def set_webhook():
    loop.run_until_complete(bot.set_webhook(WEBHOOK_URL))
    return "Webhook set!"

@app.route("/")
def home():
    return "Bot is alive"

# ----------------------------
# RUN
# ----------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
