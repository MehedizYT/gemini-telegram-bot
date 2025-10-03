import logging
import os
import threading
import asyncio
from flask import Flask
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction, ParseMode
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# --- Flask App for Render Health Check ---
app = Flask(__name__)

@app.route('/')
def home():
    return "I'm alive!", 200

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# --- Bot Configuration ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- NEW: ADVANCED GEMINI CONFIGURATION ---
try:
    genai.configure(api_key=GEMINI_API_KEY)

    # --- UPGRADE 1: System Instructions for Improved Writing ---
    # Give the bot a personality and instructions for better, formatted responses.
    SYSTEM_INSTRUCTION = (
        "You are a helpful and intelligent AI assistant named GeminiBot. "
        "Your goal is to provide accurate and concise information. "
        "Format your answers using Telegram's MarkdownV2 syntax for clarity. "
        "Use *bold* for emphasis, `code` for snippets, and lists for steps. "
        "Do not use markdown headers (#)." # Telegram doesn't support headers well.
    )

    # --- UPGRADE 2: Advanced Generation and Safety Settings ---
    generation_config = {
        "temperature": 0.7,
        "top_p": 1,
        "top_k": 1,
        "max_output_tokens": 2048,
    }

    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    }

    # --- UPGRADE 3: Use the Latest, Most Powerful Model ---
    model = genai.GenerativeModel(
        model_name="gemini-2.5-pro",
        generation_config=generation_config,
        system_instruction=SYSTEM_INSTRUCTION,
        safety_settings=safety_settings
    )
    logger.info("Google GenAI configured successfully with gemini-1.5-pro-latest.")

except Exception as e:
    logger.error(f"Error configuring Google GenAI: {e}")
    exit()

# --- Conversation Memory ---
chat_sessions = {}

# --- Telegram Bot Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "👋 *Hello\\!* I'm an advanced AI assistant powered by `Gemini 1\\.5 Pro`\\.\n\n"
        "I can remember our conversation and stream responses in real\\-time\\. "
        "To start a new chat, just send the /new command\\.\n\n"
        "How can I help you today?"
    )
    await update.message.reply_text(welcome_message, parse_mode=ParseMode.MARKDOWN_V2)

async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if chat_id in chat_sessions:
        del chat_sessions[chat_id]
    await update.message.reply_text("✨ I've cleared our conversation history. Let's start fresh!")

# --- Main Message Handler ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_text = update.message.text

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    try:
        if chat_id not in chat_sessions:
            chat_sessions[chat_id] = model.start_chat(history=[])
            logger.info(f"New chat session started for chat_id: {chat_id}")
        
        chat = chat_sessions[chat_id]
        
        logger.info(f"Sending message from chat_id {chat_id} to Gemini...")

        # --- UPGRADE 4: STREAMING FOR FAST RESPONSE ---
        # Send an initial placeholder message
        placeholder_message = await update.message.reply_text("🤔")

        # Use asyncio.to_thread to run the blocking API call in a separate thread
        response_iterator = await asyncio.to_thread(
            chat.send_message,
            user_text,
            stream=True
        )

        full_response_text = ""
        last_sent_text = ""
        # The buffer size controls how often we update the message.
        # A smaller buffer feels more "real-time" but risks hitting Telegram's rate limits.
        buffer_size = 75 

        for chunk in response_iterator:
            # Escape special markdown characters for safe rendering
            escaped_chunk = chunk.text.replace(
                "_", "\\_"
            ).replace(
                "*", "\\*"
            ).replace(
                "[", "\\["
            ).replace(
                "]", "\\]"
            ).replace(
                "(", "\\("
            ).replace(
                ")", "\\)"
            ).replace(
                "~", "\\~"
            ).replace(
                "`", "\\`"
            ).replace(
                ">", "\\>"
            ).replace(
                "#", "\\#"
            ).replace(
                "+", "\\+"
            ).replace(
                "-", "\\-"
            ).replace(
                "=", "\\="
            ).replace(
                "|", "\\|"
            ).replace(
                "{", "\\{"
            ).replace(
                "}", "\\}"
            ).replace(
                ".", "\\."
            ).replace(
                "!", "\\!"
            )
            full_response_text += escaped_chunk
            
            # Update the message in chunks to avoid hitting rate limits
            if len(full_response_text) - len(last_sent_text) > buffer_size:
                try:
                    await context.bot.edit_message_text(
                        text=full_response_text + " ▌", # Add a typing cursor for effect
                        chat_id=chat_id,
                        message_id=placeholder_message.message_id,
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
                    last_sent_text = full_response_text
                    await asyncio.sleep(0.1) # Small delay to prevent spamming edits
                except Exception as e:
                    # Ignore "Message is not modified" error which is common
                    if "Message is not modified" not in str(e):
                        logger.warning(f"Error editing message: {e}")

        # Final update to send the complete message without the cursor
        if full_response_text != last_sent_text:
            await context.bot.edit_message_text(
                text=full_response_text,
                chat_id=chat_id,
                message_id=placeholder_message.message_id,
                parse_mode=ParseMode.MARKDOWN_V2
            )

    except Exception as e:
        logger.error(f"An error occurred while handling message: {e}", exc_info=True)
        await update.message.reply_text("Sorry, I encountered an error. Please try again or start a /new conversation.")

# --- Bot Setup and Main Execution ---
def run_bot():
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
        logger.error("TELEGRAM_TOKEN or GEMINI_API_KEY environment variables not set!")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("new", new_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Bot is starting polling...")
    application.run_polling()

if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    run_bot()
