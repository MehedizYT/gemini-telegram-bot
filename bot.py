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
try:
    genai.configure(api_key=GEMINI_API_KEY)
    # Note: 'gemini-2.5-pro' is not a standard public model name.
    # Common options are 'gemini-pro', 'gemini-1.5-pro'.
    # I'll keep 'gemini-2.5-pro' assuming you have access, but verify if it causes issues.
    model = genai.GenerativeModel('gemini-2.5-pro') 
    logger.info("Google GenAI configured successfully.")
except Exception as e:
    logger.error(f"Error configuring Google GenAI: {e}")
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
        logger.info(f"Chat session cleared for chat_id: {chat_id}")
    await update.message.reply_text("✨ I've cleared our conversation history. Let's start a fresh chat!")

# --- Main Message Handler ---

# REVERTED CHANGE 1: Made the function async again
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all non-command text messages and interacts with the Gemini API."""
    chat_id = update.message.chat_id
    user_text = update.message.text

    if not user_text: # Handle cases where text might be empty for some reason
        logger.warning(f"Received empty message from chat_id {chat_id}. Ignoring.")
        return

    # Await the chat action so it's sent promptly and non-blocking
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    logger.info(f"User {update.effective_user.id} in chat {chat_id} sent: '{user_text}'")

    try:
        if chat_id not in chat_sessions:
            # start_chat can be synchronous or asynchronous depending on the specific model/library version.
            # If it's truly async, you'd await it. For now, assuming it's okay without await or has a sync fallback.
            # However, typically you'd start the chat once, and then 'send_message' is the async part.
            chat_sessions[chat_id] = model.start_chat(history=[])
            logger.info(f"New chat session started for chat_id: {chat_id}")
        
        chat = chat_sessions[chat_id]
        
        logger.info(f"Sending message from chat_id {chat_id} to Gemini...")
        
        # REVERTED CHANGE 2: Switched back to the asynchronous version of the call with 'await'
        response = await chat.send_message(user_text)
        
        logger.info(f"Received response from Gemini for chat_id {chat_id}.")

        # Await the reply so it happens non-blocking
        await update.message.reply_text(response.text)

    except Exception as e:
        logger.error(f"An error occurred while handling message for chat_id {chat_id}: {e}", exc_info=True)
        # Await the error message reply
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
    # Message handlers should point to async functions
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Bot is starting polling...")
    application.run_polling()

if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    
    run_bot()
