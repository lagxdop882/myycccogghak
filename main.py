import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters
)
from duckduckgo_search import DDGS

# Hardcoded Telegram Bot Token
TELEGRAM_BOT_TOKEN = "8031306974:AAFUlWwpvWDSeFDM3pjvDDv0_vo2l95wk5U"

# ---------------------------------------------------------
# 1. SILENT BACKGROUND START COMMAND
# ---------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Background mein silently run hoga, chat mein kuch nahi dikhega
    pass

# ---------------------------------------------------------
# 2. API-FREE SEARCH HANDLER (DuckDuckGo Text Backend)
# ---------------------------------------------------------
async def handle_developer_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    
    try:
        results_text = ""
        # Using DuckDuckGo text search to fetch information without any API key
        with DDGS() as ddgs:
            results = list(ddgs.text(user_message, max_results=3))
            if results:
                for r in results:
                    title = r.get('title', '')
                    body = r.get('body', '')
                    results_text += f"**{title}**\n{body}\n\n"
            else:
                results_text = "No direct search results found."

        reply_text = f"{results_text}\nMade by yuangeluyou.com :)"
        
        # Telegram 4000 character limit handling
        if len(reply_text) > 4000:
            for i in range(0, len(reply_text), 4000):
                await update.message.reply_text(reply_text[i:i+4000])
        else:
            await update.message.reply_text(reply_text)
            
    except Exception as e:
        await update.message.reply_text(f"⚠️ Execution Error: {str(e)}\nMade by yuangeluyou.com :)")

# ---------------------------------------------------------
# 3. CORE BOT INITIALIZATION
# ---------------------------------------------------------
def main():
    if not TELEGRAM_BOT_TOKEN:
        print("Critical Error: Missing Telegram Token.")
        return

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Registering Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_developer_ai))

    print("⚡ Bot is fully online with DuckDuckGo Search Backend...")
    app.run_polling()

if __name__ == "__main__":
    main()
