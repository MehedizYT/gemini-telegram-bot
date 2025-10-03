import logging
import os
import threading
import asyncio
from flask import Flask
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
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

# --- Gemini AI Advanced Configuration ---

# IMPROVEMENT 1: System Instruction for better logic and personality
SYSTEM_INSTRUCTION = (
    "You are a helpful and friendly AI assistant. "
    "Your goal is to provide concise, accurate, and logical answers. "
    "When asked for opinions, be balanced. When asked for facts, be precise. "
    "Format your responses for clarity on a mobile screen using markdown where appropriate."
)

# IMPROVEMENT 2: Fine-tuning generation for better quality responses
GENERATION_CONFIG = {
    "temperature": 0.8,
    "top_p": 0.95,
    "top_k": 40,
}

# IMPROVEMENT 3: Setting safety thresholds to be less restrictive
# This can prevent the bot from refusing to answer harmless questions.
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
}

try:
    genai.configure(api_key=GEMINI_API_KEY)
    
    # IMPROVEMENT 4: Using the latest, most powerful model
    model = genai.GenerativeModel(
        model_name='gemini-1.5-pro-latest',
        generation_config=GENERATION_CONFIG,
        system_instruction=SYSTEM_INSTRUCTION,
        safety_settings=SAFETY_SETTINGS
    )
    logger.info("Google GenAI configured successfully with gemini-1.5-pro-latest.")

except Exception as e:
    logger.error(f"Error configuring Google GenAI: {e}", exc_info=True)
    # The bot cannot run without a configured model.
    exit()

# --- Conversation Memory ---
chat_sessions = {}

# --- Telegram Bot Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "👋 Hello! I'm your upgraded Gemini 1.5 Pro assistant.\n\n"
        "I have persistent memory in our chat. To start a fresh conversation, send /new.\n\n"
        "How can I help you today?"
    )
    await update.message.reply_text(welcome_message)

async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if chat_id in chat_sessions:
        del chat_sessions[chat_id]
    await update.message.reply_text("✨ Fresh start! Our previous conversation has been cleared.")

# --- Main Message Handler ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_text = update.message.text

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    try:
        # Get or create a chat session for the user
        if chat_id not in chat_sessions:
            # The model now contains the system instructions, so we start a clean chat
            chat_sessions[chat_id] = model.start_chat(history=[])
            logger.info(f"New chat session started for chat_id: {chat_id}")
        
        chat = chat_sessions[chat_id]
        
        logger.info(f"Sending message from chat_id {chat_id} to Gemini...")
        
        # IMPROVEMENT 5: Using the native async method for better performance
        response = await chat.send_message_async(user_text)
        
        logger.info(f"Received response from Gemini for chat_id {chat_id}.")
        
        await update.message.reply_text(response.text)

    except Exception as e:
        logger.error(f"An error occurred while handling message for chat_id {chat_id}: {e}", exc_info=True)
        await update.message.reply_text("I'm sorry, I encountered an issue while processing your request. Please try again or start a /new conversation.")

# --- Bot Setup and Main Execution ---
def run_bot():
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
        logger.error("FATAL: TELEGRAM_TOKEN or GEMINI_API_KEY environment variables not set!")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("new", new_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Bot is starting polling...")
    application.run_polling()

if __name__ == '__main__':
    # Run the Flask app in a separate thread to keep Render's web service alive
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    
    # Run the bot in the main thread
    run_bot()
