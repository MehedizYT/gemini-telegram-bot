import logging
import os
import threading
import asyncio
from flask import Flask
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction

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

# --- Gemini AI Configuration ---
# ADDED A CHECK HERE: If the key is missing, we log it clearly and stop.
if not GEMINI_API_KEY:
    logger.critical("FATAL ERROR: GEMINI_API_KEY environment variable not found!")
    exit()

try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-pro')
    logger.info("Google GenAI configured successfully.")
except Exception as e:
    # ADDED DETAILED LOGGING HERE
    logger.critical(f"FATAL ERROR: Could not configure Google GenAI. Check your API key. Details: {e}", exc_info=True)
    exit()

# --- Conversation Memory ---
chat_sessions = {}

# --- Telegram Bot Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "👋 Hello! I'm a Gemini-powered AI bot.\n\n"
        "I can remember our conversation. To start over, just send the /new command.\n\n"
        "How can I help you today?"
    )
    await update.message.reply_text(welcome_message)

async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if chat_id in chat_sessions:
        del chat_sessions[chat_id]
    await update.message.reply_text("✨ I've cleared our conversation history. Let's start a fresh chat!")

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
        
        logger.info(f"Attempting to send message to Gemini for chat_id {chat_id}...")
        
        response = await asyncio.to_thread(chat.send_message, user_text)
        
        # ADDED SUCCESS LOG
        logger.info(f"Successfully received response from Gemini for chat_id {chat_id}.")
        
        await update.message.reply_text(response.text)

    except Exception as e:
        # THIS IS THE MOST IMPORTANT CHANGE: Log the full error traceback
        logger.error(f"An error occurred in handle_message for chat_id {chat_id}. Error details: {e}", exc_info=True)
        await update.message.reply_text("Sorry, I encountered a critical error with the AI service. The administrator has been notified.")

# --- Bot Setup and Main Execution ---
def run_bot():
    if not TELEGRAM_TOKEN:
        logger.critical("FATAL ERROR: TELEGRAM_TOKEN environment variable not set!")
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
