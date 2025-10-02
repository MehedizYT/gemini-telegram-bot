import logging
import os
import threading
import asyncio
from flask import Flask
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest

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
    
    system_instruction = (
        "You are a helpful and friendly AI assistant. Your name is GeminiBot. "
        "Provide clear, concise, and informative answers. "
        "Use Telegram's Markdown formatting (like *bold* for emphasis and _italics_ for nuances) to improve readability. "
        "You can use emojis where appropriate to make the conversation more engaging."
    )

    model = genai.GenerativeModel(
        model_name='gemini-2.5-pro',
        system_instruction=system_instruction
    )
    logger.info("Google GenAI configured successfully with 'gemini-pro' model.")
except Exception as e:
    logger.error(f"Error configuring Google GenAI: {e}")
    exit()

# --- Conversation Memory ---
chat_sessions = {}

# --- Telegram Bot Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "👋 Hello! I'm GeminiBot, your AI assistant.\n\n"
        "I can remember our conversation. To start over, send /new.\n\n"
        "How can I assist you today?"
    )
    await update.message.reply_text(welcome_message)

async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if chat_id in chat_sessions:
        del chat_sessions[chat_id]
    await update.message.reply_text("✨ Fresh start! Our previous conversation has been cleared.")

# --- Main Message Handler (MODIFIED with Robust Streaming) ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_text = update.message.text
    
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    try:
        if chat_id not in chat_sessions:
            chat_sessions[chat_id] = model.start_chat(history=[])
            logger.info(f"New chat session started for chat_id: {chat_id}")
        
        chat = chat_sessions[chat_id]
        
        logger.info(f"Sending message from chat_id {chat_id} to Gemini (streaming)...")
        
        response_stream = await asyncio.to_thread(chat.send_message, user_text, stream=True)
        
        sent_message = await update.message.reply_text("🤔")
        
        full_response_text = ""
        buffer = ""
        last_edit_time = 0
        
        for chunk in response_stream:
            buffer += chunk.text
            current_time = asyncio.get_event_loop().time()
            
            # Update message every 1.5 seconds or when a significant amount of text is buffered
            if current_time - last_edit_time > 1.5 or len(buffer) > 100:
                new_text = full_response_text + buffer
                # Avoid editing if text hasn't changed
                if new_text != sent_message.text:
                    try:
                        await context.bot.edit_message_text(
                            text=new_text + " ▌",
                            chat_id=sent_message.chat_id,
                            message_id=sent_message.message_id,
                            parse_mode=ParseMode.MARKDOWN
                        )
                        full_response_text = new_text
                        buffer = "" # Clear buffer after successful edit
                        sent_message.text = new_text # Update local copy
                    except BadRequest as e:
                        # This is the key fix: Ignore "Message is not modified" and Markdown parse errors
                        if "Message is not modified" not in str(e) and "Can't parse entities" not in str(e):
                            logger.warning(f"Error editing message, will retry: {e}")
                last_edit_time = current_time

        # Final update with the complete text, removing the cursor
        final_text = full_response_text + buffer
        try:
            await context.bot.edit_message_text(
                text=final_text,
                chat_id=sent_message.chat_id,
                message_id=sent_message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                 # If the final Markdown is still broken, send as plain text
                logger.error(f"Final Markdown failed: {e}. Sending as plain text.")
                await context.bot.edit_message_text(
                    text=final_text,
                    chat_id=sent_message.chat_id,
                    message_id=sent_message.message_id
                )

    except Exception as e:
        logger.error(f"An error occurred while handling message for chat_id {chat_id}: {e}", exc_info=True)
        await update.message.reply_text("Sorry, a critical error occurred. Please start a /new conversation.")

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
