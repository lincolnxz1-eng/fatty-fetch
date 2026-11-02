"""Fatty hosted fetch API: YouTube link -> captions + title + thumbnail (via yt-dlp, subtitles only, no video download)."""
import os, re, glob, html as _html, tempfile, shutil, base64, urllib.request
from fastapi import FastAPI, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import yt_dlp

KEY = os.environ.get("FATTY_FETCH_KEY", "")
CLIENT_CHAINS = [None, ["tv_embedded", "android_vr"], ["android_vr"], ["tv_simply", "web_safari", "mweb"]]

def cookie_file():
    """Netscape cookies.txt from env FATTY_YT_COOKIES (raw text or base64) or path YOUTUBE_COOKIES_FILE."""
    p = os.environ.get("YOUTUBE_COOKIES_FILE")
    if p and os.path.exists(p): return p
    c = os.environ.get("FATTY_YT_COOKIES", "").strip()
    if not c: return None
    if "\t" not in c and "Netscape" not in c:
        try: c = base64.b64decode(c).decode()
        except Exception: pass
    p = os.path.join(tempfile.gettempdir(), "fatty_yt_cookies.txt")
    if not os.path.exists(p):
        with open(p, "w") as f: f.write(c.replace("\\n", "\n") + "\n")
    return p
app = FastAPI(title="Fatty fetch API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"])
ZH = ("yue", "zh-HK", "zh-Hant", "zh-TW", "zh-Hans", "zh-CN", "zh-SG", "zh")

def platform(u):
    h = re.sub(r"^https?://", "", u).split("/")[0].lower()
    return "YouTube" if re.search(r"youtu\.?be", h) else "Instagram" if "instagram" in h else "TikTok" if "tiktok" in h else "other"

def clean_subs(text):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")) or "-->" in line or line.isdigit(): continue
        line = _html.unescape(re.sub(r"<[^>]+>", "", line)).strip()
        line = re.sub(r"\[(music|applause|laughter)\]", "", line, flags=re.I).strip()
        if line and (not out or out[-1] != line): out.append(line)
    return re.sub(r"\s+", " ", " ".join(out)).strip()

def pick_lang(info):
    """Uploaded captions beat auto; Cantonese (yue) > zh-Hant > zh-Hans > en; the video's original-language auto track if no uploads."""
    def rank(l):
        l2 = l.lower()
        for i, z in enumerate(ZH):
            if l2 == z.lower() or l2.startswith(z.lower() + "-"): return i
        return 50 if l2.split("-")[0] == "en" else 99
    for kind, tracks in (("manual", info.get("subtitles") or {}), ("auto", info.get("automatic_captions") or {})):
        langs = [l for l in tracks if l != "live_chat"]
        if kind == "auto":
            o = [l for l in langs if l.endswith("-orig")]
            if o: return o[0].replace("-orig", ""), o[0], kind
            langs = [l for l in langs if l.count("-") <= 1]  # skip auto-translations like zh-Hans-en
        best = sorted([l for l in langs if rank(l) < 99], key=rank)
        if best: return best[0], best[0], kind
        if kind == "manual" and langs: return langs[0], langs[0], kind
    return None, None, None

def thumb_data(u):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=10)
        ct = r.headers.get("Content-Type", "image/jpeg").split(";")[0]; b = r.read()
        if ct.startswith("image") and 1000 < len(b) < 1_500_000: return "data:%s;base64,%s" % (ct, base64.b64encode(b).decode())
    except Exception: pass

def err(msg, code=400, **kw): return JSONResponse({"error": msg, **kw}, status_code=code)

@app.get("/health")
def health(): return {"ok": True, "yt_dlp": yt_dlp.version.__version__, "key_required": bool(KEY), "cookies": bool(cookie_file())}

@app.api_route("/fetch", methods=["GET", "POST"])
async def fetch(request: Request, x_fatty_key: str = Header(default="")):
    if KEY and x_fatty_key != KEY: return err("Wrong or missing X-Fatty-Key.", 401)
    url = request.query_params.get("url")
    if request.method == "POST":
        try: url = (await request.json()).get("url") or url
        except Exception: pass
    url = (url or "").strip()
    if not re.match(r"^https?://", url): return err("Send {\"url\": \"https://...\"}.")
    plat = platform(url)
    if plat in ("Instagram", "TikTok"):
        return err(f"{plat} isn't supported by the hosted fetch yet (it needs your login cookies). Paste the caption into box 2, or use the Computer bridge.", 422, needs_login=True, site=plat)
    if plat != "YouTube": return err("The hosted fetch only does YouTube links for now.", 422)
    tmp = tempfile.mkdtemp(prefix="fatty_")
    try:
        common = {"quiet": True, "no_warnings": True, "noprogress": True, "noplaylist": True, "skip_download": True, "socket_timeout": 25,
                  "outtmpl": os.path.join(tmp, "v.%(ext)s")}
        ck = cookie_file()
        if ck: common["cookiefile"] = ck
        info = None; last = ""
        for chain in CLIENT_CHAINS:
            opts = {**common, "ignore_no_formats_error": True}
            if chain: opts["extractor_args"] = {"youtube": {"player_client": chain}}
            try:
                with yt_dlp.YoutubeDL(opts) as y: info = y.extract_info(url, download=False)
                if info: common = opts; break
            except Exception as e:
                last = str(e)
        if not info:
            if re.search(r"not a bot|sign in|cookies", last, re.I):
                return err("YouTube blocked the server (\"sign in to confirm you're not a bot\")" + ("" if ck else "; set FATTY_YT_COOKIES on the server") + ". Paste the captions or use the Computer bridge.", 503, blocked=True, cookies=bool(ck))
            return err("Couldn't fetch from YouTube: " + last.split(":", 1)[-1].strip()[:200], 502)
        lang, track, kind = pick_lang(info); text = ""; cap_err = None
        if track:
            try:
                with yt_dlp.YoutubeDL({**common, "writesubtitles": kind == "manual", "writeautomaticsub": kind == "auto",
                                       "subtitleslangs": [track], "subtitlesformat": "vtt/srt/best"}) as y:
                    y.process_ie_result(info, download=True)
                subs = glob.glob(os.path.join(tmp, "*.vtt")) + glob.glob(os.path.join(tmp, "*.srt"))
                if subs: text = clean_subs(open(subs[0], encoding="utf-8", errors="ignore").read())
            except Exception as e:
                cap_err = str(e).split(":", 1)[-1].strip()[:200]
            for attempt in range(2 if not text else 0):  # fallback: read the track URL directly (retry once after a 429)
                if text: break
                if attempt: __import__("time").sleep(2)
                tr = ((info.get("subtitles") if kind == "manual" else info.get("automatic_captions")) or {}).get(track) or []
                for f in sorted(tr, key=lambda f: f.get("ext") != "vtt"):
                    try:
                        raw = urllib.request.urlopen(urllib.request.Request(f["url"], headers={"User-Agent": "Mozilla/5.0"}), timeout=15).read().decode("utf-8", "ignore")
                        if f.get("ext") == "vtt": text = clean_subs(raw); break
                    except Exception as e: cap_err = cap_err or str(e)[:200]
        desc = (info.get("description") or "")[:4000]
        if len(text) <= 40 and len(desc) <= 40:
            return err("Couldn't read this video's captions" + (f" ({cap_err})" if cap_err else " (none found)") + ". Paste the transcript into box 2.", 502 if cap_err else 404)
        th = info.get("thumbnail")
        return {"transcript": text if len(text) > 40 else "", "captions": text, "title": info.get("title"), "description": desc,
                "thumbnail": th, "thumbnail_data": thumb_data(th) if th else None, "url": url, "source_url": info.get("webpage_url") or url,
                "platform": plat, "language": lang if text else (info.get("language") or None), "caption_kind": kind if text else None,
                "source": "captions" if len(text) > 40 else "description", "caption_error": None if text else cap_err}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
