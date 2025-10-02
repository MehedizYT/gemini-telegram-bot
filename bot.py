import logging
import os
import threading
from flask import Flask
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction

# --- Flask App for Render Health Check ---
# This part is the "trick" to keep the free Render web service alive.
app = Flask(__name__)

@app.route('/')
def home():
    # Render sends a request to this endpoint to check if the service is alive.
    return "I'm alive!", 200

def run_flask():
    # Get the port from the environment variable Render sets. Default to 8080 for local testing.
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# --- Bot Configuration ---
# Get API keys from environment variables for security
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Set up logging to see errors
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Gemini AI Configuration ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    logger.info("Google GenAI configured successfully.")
except Exception as e:
    logger.error(f"Error configuring Google GenAI: {e}")
    exit()

# --- Conversation Memory ---
chat_sessions = {}

# --- Telegram Bot Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message when the /start command is issued."""
    welcome_message = (
        "👋 Hello! I'm a Gemini-powered AI bot.\n\n"
        "I can remember our conversation. To start over, just send the /new command.\n\n"
        "How can I help you today?"
    )
    await update.message.reply_text(welcome_message)

async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts a new conversation, clearing the history."""
    chat_id = update.message.chat_id
    if chat_id in chat_sessions:
        del chat_sessions[chat_id]
    await update.message.reply_text("✨ I've cleared our conversation history. Let's start a fresh chat!")

# --- Main Message Handler ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all non-command text messages and interacts with the Gemini API."""
    chat_id = update.message.chat_id
    user_text = update.message.text

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    try:
        if chat_id not in chat_sessions:
            chat_sessions[chat_id] = model.start_chat(history=[])
            logger.info(f"New chat session started for chat_id: {chat_id}")
        
        chat = chat_sessions[chat_id]
        response = await chat.send_message_async(user_text)
        await update.message.reply_text(response.text)

    except Exception as e:
        logger.error(f"An error occurred while handling message for chat_id {chat_id}: {e}")
        await update.message.reply_text("Sorry, I encountered an error. Please try again or start a /new conversation.")

# --- Bot Setup and Main Execution ---

def run_bot():
    """Sets up and runs the Telegram bot."""
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN environment variable not set!")
        return
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY environment variable not set!")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("new", new_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Bot is starting polling...")
    application.run_polling()

if __name__ == '__main__':
    # Run Flask app in a separate thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    
    # Run the bot in the main thread
    run_bot()
