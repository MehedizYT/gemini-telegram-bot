import logging
import os
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction

# --- Configuration ---
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
# Configure the generative AI client
try:
    genai.configure(api_key=GEMINI_API_KEY)
    # Using gemini-1.5-flash for speed and cost-effectiveness
    model = genai.GenerativeModel('gemini-1.5-flash')
    logger.info("Google GenAI configured successfully.")
except Exception as e:
    logger.error(f"Error configuring Google GenAI: {e}")
    # If the API key is invalid, the bot can't start.
    # We exit here because the bot is non-functional without the model.
    exit()

# --- Conversation Memory ---
# A dictionary to store conversation history for each chat
# Key: chat_id, Value: Gemini chat session object
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
        del chat_sessions[chat_id]  # Delete the old session
    await update.message.reply_text("✨ I've cleared our conversation history. Let's start a fresh chat!")

# --- Main Message Handler ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all non-command text messages and interacts with the Gemini API."""
    chat_id = update.message.chat_id
    user_text = update.message.text

    # Show a "typing..." action to the user for better UX
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    try:
        # Check if a chat session already exists for this user
        if chat_id not in chat_sessions:
            # If not, create a new one
            chat_sessions[chat_id] = model.start_chat(history=[])
            logger.info(f"New chat session started for chat_id: {chat_id}")
        
        # Get the existing chat session
        chat = chat_sessions[chat_id]
        
        # Send the user's message to Gemini and get the response
        response = await chat.send_message_async(user_text)

        # Send Gemini's response back to the user
        await update.message.reply_text(response.text)

    except Exception as e:
        logger.error(f"An error occurred while handling message for chat_id {chat_id}: {e}")
        # Inform the user that something went wrong
        await update.message.reply_text("Sorry, I encountered an error while processing your request. Please try again or start a /new conversation.")

# --- Bot Setup and Main Execution ---

def main():
    """Starts the bot."""
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN environment variable not set!")
        return
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY environment variable not set!")
        return

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add handlers for commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("new", new_command))

    # Add a handler for all text messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the Bot
    logger.info("Bot is starting...")
    application.run_polling()

if __name__ == '__main__':
    main()
