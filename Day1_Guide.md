# Day 1. Base: Aiogram + FastAPI + Render + Sentry

## What we're doing
Launch a Telegram bot with Aiogram 3.x, a FastAPI server with webhook, connect Sentry for error monitoring, and deploy to Render.

---

## 1. Registrations (do now, takes 10 min)

### 1.1 Telegram Bot Token — @BotFather
1. Open Telegram → find `@BotFather`
2. Send `/newbot`
3. Name: `Viktor` (or anything)
4. Username: `viktoryourname_bot` (must end with `bot`)
5. You'll get a **token**. Copy it to `.env`:
   ```
   BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
   ```
6. Set up commands: `/setcommands` → select your bot → send:
   ```
   start — Start
   help — Help
   ping — Ping
   webhook — Webhook status
   ```

### 1.2 Sentry — error tracking (free)
1. Go to https://sentry.io/signup/
2. Sign up (GitHub account — fastest)
3. Create project → choose **FastAPI** (or Python)
4. You'll get a **DSN** like:
   ```
   https://abc123@o123456.ingest.sentry.io/1234567
   ```
5. Copy to `.env`:
   ```
   SENTRY_DSN=https://abc123@o123456.ingest.sentry.io/1234567
   ```

### 1.3 GitHub — repository
1. Go to https://github.com
2. Sign in or sign up
3. Click green **New** button
   - Name: `viktor-bot`
   - Public (free)
   - Don't check anything, just Create
4. Copy the repo URL:
   ```
   https://github.com/yourname/viktor-bot.git
   ```

### 1.4 Render — hosting (free)
1. Go to https://dashboard.render.com
2. Sign up via GitHub (one click)
3. Grant access to repo `viktor-bot`
4. Done, don't create anything yet

---

## 2. Run code locally

### 2.1 Project structure
Copy files from `viktor-bot/` folder:

```
viktor-bot/
├── main.py            # Entry point
├── Procfile           # Render start command
├── runtime.txt        # Python version
├── requirements.txt   # Dependencies
├── .env               # Tokens (DO NOT git!)
├── .env.example       # Template for others
└── app/
    ├── __init__.py
    ├── config.py      # Config
    ├── bot.py         # Bot creation + Sentry
    └── handlers.py    # Bot commands
```

### 2.2 Install Python (if not installed)
- Download: https://www.python.org/downloads/
- Check **Add Python to PATH** during install
- Verify:
```bash
python --version
```

### 2.3 Create virtual environment
```bash
# Inside viktor-bot folder
python -m venv venv

# Activate:
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate
```

### 2.4 Install dependencies
```bash
pip install -r requirements.txt
```

### 2.5 Fill .env
Open `.env` and paste your tokens:
```
BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
SENTRY_DSN=https://abc123@o123456.ingest.sentry.io/1234567
APP_URL=http://localhost:8000        # For now local
PORT=8000
```

### 2.6 Run locally
```bash
python main.py
```
Open browser: http://localhost:8000 — you'll see `{"status":"ok","bot":"Viktor"}`

Terminal should show:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Webhook set to http://localhost:8000/webhook
INFO:     Application startup complete.
```

### 2.7 Test the bot
Message your bot in Telegram:
- `/start` — welcome message
- `/ping` — `Pong!`
- `/webhook` — shows webhook URL

---

## 3. Deploy to Render

### 3.1 Push code to GitHub
```bash
# Inside viktor-bot folder
git init
git add .
git commit -m "Day 1: base bot with FastAPI webhook"
git remote add origin https://github.com/yourname/viktor-bot.git
git branch -M main
git push -u origin main
```

### 3.2 Create Web Service on Render
1. Go to https://dashboard.render.com
2. Click **New +** → **Web Service**
3. Select your repo `viktor-bot`
4. Fill in:
   - **Name**: `viktor-bot`
   - **Region**: `Frankfurt` (EU)
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
   - **Plan**: **Free**
5. Click **Advanced** → **Add Environment Variable**:
   - `BOT_TOKEN` = your token
   - `SENTRY_DSN` = your DSN
   - `APP_URL` = leave empty (Render will set it)
   - `PORT` = `10000`
6. **Health Check Path**: `/health`

### 3.3 Wait for deploy
- Build takes 2-3 minutes
- Watch **Logs** tab
- When you see `Application startup complete.` — it's live
- URL will be: `https://viktor-bot.onrender.com`

### 3.4 Update APP_URL
In **Dashboard** → **Environment** add:
```
APP_URL = https://viktor-bot.onrender.com
```
Click **Manual Deploy** → **Deploy latest commit**

### 3.5 Final test
Send `/webhook` to your bot — should show:
```
Webhook:
URL: https://viktor-bot.onrender.com/webhook
Errors: None
```

---

## 4. Verification checklist

| Check | Expected |
|-------|----------|
| `/start` | Welcome from Viktor |
| `/ping` | Pong! |
| `/webhook` | URL set, no errors |
| `https://viktor-bot.onrender.com/health` | `{"status":"healthy"}` |
| Sentry Dashboard | 0 errors (for now) |

---

## 5. Troubleshooting

**Bot doesn't reply** → check Render logs (Logs tab)

**Webhook not set** → check APP_URL in environment variables

**Error `BOT_TOKEN not set`** → you forgot to add env var in Render

**Sentry shows nothing** → check DSN in `.env` or Render

---

**Done!** You now have a live Telegram bot with webhook that won't crash. Tomorrow — Day 2: add Groq + Function Calling.
