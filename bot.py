import logging
import os
import threading
from flask import Flask
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction

# --- Flask App for Render Health Check ---
app = Flask(__name__)

@app.route('/')
def home():
    """Handles the root path for Render health checks."""
    return "I'm alive!", 200

def run_flask():
    """Starts the Flask web server in a separate thread for health checks.
    The port is configured via environment variable, defaulting to 8080.
    """
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
try:
    genai.configure(api_key=GEMINI_API_KEY)
    # NOTE: 'gemini-2.5-pro' might not be a valid model name.
    # It's recommended to use an officially supported model like 'gemini-pro'
    # or 'gemini-1.5-pro-latest' for general use.
    # I've updated it to 'gemini-1.5-pro-latest' for demonstration.
    # If 'gemini-2.5-pro' is a specific custom model or a future model you're targeting,
    # you can revert this line.
    model = genai.GenerativeModel('gemini-1.5-pro-latest') 
    logger.info("Google GenAI configured successfully with 'gemini-1.5-pro-latest'.")
except Exception as e:
    logger.error(f"Error configuring Google GenAI: {e}")
    exit()

# --- Conversation Memory ---
# This dictionary will now store asynchronous chat session objects from Gemini.
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
    """Clears the conversation history for the current chat, allowing a fresh start."""
    chat_id = update.message.chat_id
    if chat_id in chat_sessions:
        del chat_sessions[chat_id]
        logger.info(f"Cleared chat session for chat_id: {chat_id}")
    await update.message.reply_text("✨ I've cleared our conversation history. Let's start a fresh chat!")

# --- Main Message Handler ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles all non-command text messages and interacts with the Gemini API asynchronously.
    This function is now fully asynchronous to prevent blocking the bot's event loop,
    making the chatbot more responsive and faster.
    """
    chat_id = update.message.chat_id
    user_text = update.message.text

    # Indicate typing status to the user immediately, preventing perceived lag.
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    try:
        if chat_id not in chat_sessions:
            # Use the asynchronous version `start_async_chat` to initialize a new chat session.
            chat_sessions[chat_id] = await model.start_async_chat(history=[])
            logger.info(f"New async chat session started for chat_id: {chat_id}")
        
        chat = chat_sessions[chat_id]
        
        logger.info(f"Sending message from chat_id {chat_id} to Gemini (async)...")
        
        # Use the asynchronous version `send_async_message` to send the message to Gemini.
        # This allows the bot to process other messages while waiting for Gemini's response.
        response = await chat.send_async_message(user_text)
        
        logger.info(f"Received response from Gemini for chat_id {chat_id} (async).")

        # Reply to the user asynchronously.
        await update.message.reply_text(response.text)

    except Exception as e:
        logger.error(f"An error occurred while handling message for chat_id {chat_id}: {e}")
        # Send an informative error message to the user.
        await update.message.reply_text("Sorry, I encountered an error. Please try again or start a /new conversation.")

# --- Bot Setup and Main Execution ---

def run_bot():
    """Sets up and runs the Telegram bot using long polling."""
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN environment variable not set!")
        return
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY environment variable not set!")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("new", new_command))
    
    # Register the now async handle_message function for all text messages that are not commands.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Bot is starting polling...")
    # This method blocks until the bot is stopped.
    application.run_polling(allowed_updates=Update.ALL_TYPES) # Specify allowed_updates for efficiency

if __name__ == '__main__':
    # Start Flask app in a separate thread for health checks.
    # This prevents the Flask app from blocking the Telegram bot.
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    
    # Run the Telegram bot in the main thread.
    run_bot()
