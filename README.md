# Fatty fetch API (hosted, Render free tier)

Lets the phone (Chrome PWA or Fatty.apk) turn a **YouTube** link into captions without the computer bridge.

## API
- `GET /health` → `{"ok":true,"yt_dlp":"<ver>","key_required":false}`
- `POST /fetch` body `{"url":"https://www.youtube.com/watch?v=..."}` (or `GET /fetch?url=...`)
  - Header `X-Fatty-Key: <key>` required only if env `FATTY_FETCH_KEY` is set.
  - 200 → `{transcript, captions, title, description, thumbnail, thumbnail_data, url, source_url, platform, language, caption_kind, source, caption_error}`
    (`source` = `captions` or `description` when captions couldn't be read)
  - Errors → `{"error": "..."}` with 400 bad url, 401 bad key, 422 Instagram/TikTok (`needs_login:true`, not supported yet), 503 YouTube bot-block, 502/404 no captions.
- Caption track order: uploaded before auto; yue (Cantonese) → zh-HK/zh-Hant/zh-TW → zh-Hans/zh-CN → en. Subtitles only — no video/audio download, no ffmpeg.
- CORS `*`.

## Deploy on Render (free)
1. Put this repo (the `fattys-recipe-maker` folder, with `render.yaml` at its root) on GitHub.
2. Render dashboard → **New → Blueprint** → pick the repo (uses `render.yaml`: Docker, plan free, rootDir `fetch-api`).
   Or **New → Web Service** → repo → Language **Docker**, Root Directory `fetch-api`, Instance type **Free**, Health check `/health`.
3. Optional but recommended: Environment → add `FATTY_FETCH_KEY` = some long random string.
4. After deploy you get `https://<name>.onrender.com`. Check `https://<name>.onrender.com/health`.

## Point Fatty at it
- In the app: **☁️ Hosted fetch** (under the mode note) → paste the URL (+ key) → **Save & test**.
- Or bake it in: `FATTY_FETCH_API=https://<name>.onrender.com python3 build_dist.py` then rebuild the APK (`cd android-apk && npm run apk`).

## Limits
- Free tier sleeps after ~15 min idle; first request takes ~30–60 s (the app shows "waking up").
- YouTube sometimes rate-limits (429) or bot-blocks datacenter IPs; then you get the description only or an error → paste captions or use the Computer bridge.
- Instagram/TikTok: not supported (need login cookies).
- Local test: `pip install -r requirements.txt && uvicorn app:app --port 10000`

## YouTube "sign in to confirm you're not a bot"
The server tries several yt-dlp player clients (default, tv_embedded+android_vr, android_vr, tv_simply/web_safari/mweb).
If Render's IP is still blocked, give it YouTube cookies once:
1. In desktop Chrome, install the "Get cookies.txt LOCALLY" extension, open youtube.com while signed in (ideally a throwaway Google account), click the extension, Export (Netscape format).
2. Render dashboard -> fatty-fetch -> Environment -> add `FATTY_YT_COOKIES` = the whole file contents (or base64 of it). Save; it redeploys.
3. `/health` shows `"cookies": true`. Re-export if YouTube starts blocking again (cookies expire / get rotated).
