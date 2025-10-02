import os
import logging
import google.generativeai as genai
from telegram import Update, constants
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configure the Gemini API
genai.configure(api_key=GEMINI_API_KEY)
# Use the stable gemini-1.0-pro model
model = genai.GenerativeModel('gemini-1.0-pro')

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- Bot Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_name = update.effective_user.first_name
    await update.message.reply_text(f"👋 Hello, {user_name}! I'm a bot powered by Gemini. Ask me anything!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html("Simply send me a message, and I will generate a response. Use /start to begin.")

# --- Main Message Handler (IMPROVED) ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message_text = update.message.text
    # Show "typing..." action to the user
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)
    
    try:
        # Send the prompt to Gemini
        response = model.generate_content(message_text)
        
        # --- NEW: Check for safety blocks or empty response ---
        if not response.parts:
            # This handles cases where the response was blocked for safety
            await update.message.reply_text("I'm sorry, my safety filters prevented me from responding to that. Please try a different topic.")
            logger.warning(f"Gemini response for '{message_text}' was blocked or empty.")
            return

        # Send the response back to the user
        await update.message.reply_text(response.text)

    except Exception as e:
        logger.error(f"An error occurred while handling message: {e}")
        await update.message.reply_text("An error occurred while processing your request. Please try again later.")

# --- Main Bot Execution ---
def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables!")
        return
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not found in environment variables!")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Bot is starting polling...")
    application.run_polling()

if __name__ == "__main__":
    main()
