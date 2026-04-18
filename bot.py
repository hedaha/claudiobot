#!/usr/bin/env python3
"""
MrPink Bot — Telegram ↔ Claude bridge
Hernan habla con Claude directamente desde Telegram.
"""

import os
import logging
from dotenv import load_dotenv
from anthropic import Anthropic
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ── Config ──────────────────────────────────────────────────────────────────
load_dotenv()

TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY")
ALLOWED_USER_IDS = set(os.getenv("ALLOWED_USER_ID", "").split(",")) - {""}  # IDs separados por coma

MODEL     = "claude-sonnet-4-6"
MAX_TOKENS = 4096
SYSTEM_PROMPT = """Sos Claude, el asistente de IA de Anthropic.
Estás hablando con Hernan a través de Telegram.
Respondé de forma natural, directa y en el idioma que use Hernan.
Podés usar markdown básico (negrita, cursiva, código) ya que Telegram lo soporta."""

# ── Setup ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

client = Anthropic(api_key=ANTHROPIC_KEY)

# Historial de conversación por chat (en memoria)
conversation_history: dict[int, list] = {}


# ── Helpers ──────────────────────────────────────────────────────────────────
def is_allowed(update: Update) -> bool:
    """Si ALLOWED_USER_IDS está definido, solo esos usuarios pueden usar el bot."""
    if not ALLOWED_USER_IDS:
        return True
    return str(update.effective_user.id) in ALLOWED_USER_IDS


async def send_typing(update: Update):
    await update.effective_chat.send_action("typing")


# ── Handlers ─────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id
    conversation_history[chat_id] = []
    await update.message.reply_text(
        "👋 ¡Hola Hernan! Soy Claude. ¿En qué te puedo ayudar?"
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id
    conversation_history[chat_id] = []
    await update.message.reply_text("🔄 Conversación reiniciada.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text("⛔ No tenés acceso a este bot.")
        return

    chat_id   = update.effective_chat.id
    user_text = update.message.text

    # Inicializar historial si es la primera vez
    if chat_id not in conversation_history:
        conversation_history[chat_id] = []

    # Agregar mensaje del usuario
    conversation_history[chat_id].append({
        "role": "user",
        "content": user_text,
    })

    await send_typing(update)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=conversation_history[chat_id],
        )
        assistant_text = response.content[0].text

        # Guardar respuesta en historial
        conversation_history[chat_id].append({
            "role": "assistant",
            "content": assistant_text,
        })

        # Telegram tiene límite de 4096 chars por mensaje
        if len(assistant_text) <= 4096:
            await update.message.reply_text(assistant_text, parse_mode="Markdown")
        else:
            # Partir en chunks si la respuesta es muy larga
            for i in range(0, len(assistant_text), 4096):
                await update.message.reply_text(
                    assistant_text[i:i+4096], parse_mode="Markdown"
                )

    except Exception as e:
        logger.error(f"Error llamando a Claude: {e}")
        await update.message.reply_text(
            "⚠️ Hubo un error al contactar a Claude. Intentá de nuevo."
        )


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    if not TELEGRAM_TOKEN or not ANTHROPIC_KEY:
        raise ValueError(
            "Faltan variables de entorno. "
            "Asegurate de completar el archivo .env con TELEGRAM_TOKEN y ANTHROPIC_API_KEY."
        )

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🤖 Bot corriendo... Mandá un mensaje en Telegram!")
    app.run_polling()


if __name__ == "__main__":
    main()
