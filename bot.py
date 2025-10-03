import logging
import os
import threading
from flask import Flask
import google.generativeai as genai # Correct import for GenerativeModel
import google.generativeai.types as genai_types # For AsyncGenerativeModel types
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction
import asyncio # Needed for running async operations

# --- Flask App for Render Health Check ---
app = Flask(__name__)

@app.route('/')
def home():
    return "I'm alive!", 200

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    # Use 0.0.0.0 for Render deployment
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
# Use AsyncGenerativeModel for non-blocking asynchronous calls
# This is crucial for integrating well with telegram.ext's async handlers
try:
    genai.configure(api_key=GEMINI_API_KEY)
    # Use AsyncGenerativeModel for asynchronous operations
    gemini_model = genai.GenerativeModel('gemini-2.5-pro')
    logger.info("Google GenAI configured successfully.")
except Exception as e:
    logger.error(f"Error configuring Google GenAI: {e}")
    # It's better to raise the error or exit if the core functionality can't be set up
    exit(1) # Exit with an error code

# --- Conversation Memory ---
# Store chat sessions, which include history
# Key: chat_id, Value: genai.ChatSession object
chat_sessions: dict[int, genai_types.ChatSession] = {}

# --- Telegram Bot Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message and explains basic usage."""
    welcome_message = (
        "👋 Hello! I'm a Gemini-powered AI bot.\n\n"
        "I can remember our conversation. To start over, just send the /new command.\n\n"
        "How can I help you today?"
    )
    await update.message.reply_text(welcome_message)
    logger.info(f"User {update.effective_user.id} started a new chat.")

async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clears the conversation history for the current chat."""
    chat_id = update.message.chat_id
    if chat_id in chat_sessions:
        del chat_sessions[chat_id]
        logger.info(f"Chat session cleared for chat_id: {chat_id}")
    await update.message.reply_text("✨ I've cleared our conversation history. Let's start a fresh chat!")

# --- Main Message Handler ---

# This function MUST be async to correctly await Telegram and Gemini operations
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles all non-command text messages and interacts with the Gemini API."""
    chat_id = update.message.chat_id
    user_text = update.message.text

    if not user_text:
        logger.warning(f"Received empty message from chat_id {chat_id}.")
        return

    logger.info(f"Received message from chat_id {chat_id}: '{user_text[:50]}...'") # Log first 50 chars

    # Send typing action immediately, no need for create_task if handler is async
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    try:
        if chat_id not in chat_sessions:
            # Start a new chat session for this user
            # chat_sessions[chat_id] = gemini_model.start_chat(history=[]) # This is synchronous
            # To make it truly async, we would use AsyncGenerativeModel and await start_chat
            # However, `google-generativeai` GenerativeModel.start_chat is sync.
            # We'll stick to the existing GenerativeModel, but need to run its sync call in a thread pool
            # to prevent blocking the event loop.
            chat_sessions[chat_id] = await asyncio.to_thread(gemini_model.start_chat, history=[])
            logger.info(f"New chat session started for chat_id: {chat_id}")
        
        chat = chat_sessions[chat_id]
        
        logger.info(f"Sending message from chat_id {chat_id} to Gemini...")
        
        # Use asyncio.to_thread to run the synchronous `send_message` call
        # in a separate thread, preventing it from blocking the main event loop.
        # If you were using `genai.AsyncGenerativeModel`, you would just `await chat.send_message(user_text)`
        response = await asyncio.to_thread(chat.send_message, user_text)
        
        logger.info(f"Received response from Gemini for chat_id {chat_id}.")

        # Reply to the user, no need for create_task if handler is async
        await update.message.reply_text(response.text)

    except Exception as e:
        logger.error(f"An error occurred while handling message for chat_id {chat_id}: {e}", exc_info=True)
        await update.message.reply_text("Sorry, I encountered an error while processing your request. Please try again or start a /new conversation.")

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
    
    # Register handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("new", new_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)) # handle_message is now async
    
    logger.info("Bot is starting polling...")
    application.run_polling(poll_interval=1.0) # Add poll_interval for better control

if __name__ == '__main__':
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True) # daemon=True ensures thread exits with main program
    flask_thread.start()
    
    # Run the bot in the main thread
    run_bot()
