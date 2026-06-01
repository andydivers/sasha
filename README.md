<p align="center">
  <img src="https://img.shields.io/badge/python-3.12-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/telegram-bot-26A5E4" alt="Telegram Bot">
</p>

# Sasha — Voice-First AI Business Assistant for Telegram

Sasha is a voice-first Telegram bot that helps you track expenses, manage tasks, log movements, sync with Google Calendar & Sheets, and get a daily business digest — all by speaking naturally. Built for entrepreneurs who think faster than they type.

## Features

- **🎤 Voice-First** — Speak naturally ("кофе 80 бат", "встреча завтра в 15:00"). No menus, no typing.
- **💰 Expense Tracking** — Just say any number. Saved automatically to Supabase + optional Google Sheets.
- **✅ Task Management** — "добавить задачу купить молоко". Voice commands for todos.
- **📍 Movement Tracking** — "я в кафе на Тверской". Logs where you've been.
- **📅 Calendar Sync** — Create events via voice, synced to Google Calendar.
- **📊 Dashboard** — Web Mini App with expenses, tasks, movements, calendar view.
- **🔁 Recurring Payments** — Monthly subscriptions (rent, SaaS, insurance) auto-tracked.
- **🌐 10 Languages** — English, Русский, Español, Français, 中文, العربية, Português, Deutsch, हिन्दी, 日本語.
- **⚡ Proactive Daily Digest** — Every morning at 8 AM: yesterday's summary, today's schedule.
- **🔔 Re-engagement** — Bot messages you during the day if you've been silent.
- **💳 USDC Wallet + Telegram Stars** — Subscription payments via crypto.
- **📈 Google Sheets Integration** — Optional sync of expenses to your own sheet.

## How It Works

1. Open chat with @HeySasha_bot
2. Press the microphone button in Telegram
3. Speak naturally: "кофе 80 бат" or "встреча в пятницу в 14:00"
4. Sasha saves it, shows confirmation, prompts you to continue

No commands to learn. No menus to navigate. Just talk.

## Quick Start (Self-Host)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/andydivers/sasha)

### Prerequisites
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- [Groq](https://console.groq.com) API key (free tier: 100K tokens/day)
- [Supabase](https://supabase.com) project (free tier)

### 1-Click Deploy
Click the button above, fill in `BOT_TOKEN`, `GROQ_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`.

### Manual Deploy
```bash
git clone https://github.com/andydivers/sasha
cd sasha
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your keys
python main.py
```

### Database Setup
Run the SQL in `supabase_migration.sql` in your Supabase SQL Editor (one time).

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | ✅ | Telegram bot token from @BotFather |
| `GROQ_API_KEY` | ✅ | Groq API key (llama-3.1-8b-instant) |
| `SUPABASE_URL` | ✅ | Supabase project URL |
| `SUPABASE_KEY` | ✅ | Supabase service_role key |
| `APP_URL` | ✅ | Public URL (e.g. https://sasha.onrender.com) |
| `SENTRY_DSN` | ❌ | Sentry error tracking |
| `GOOGLE_SHEETS_CREDENTIALS` | ❌ | Service account JSON for Sheets sync |
| `GEMINI_API_KEY` | ❌ | Gemini API key (legacy, not required) |

## Architecture

```
User Voice ──► Telegram ──► Webhook ──► FastAPI
                                          │
                              ┌───────────┴───────────┐
                              │                       │
                         Groq (STT)              Groq (LLM)
                              │                       │
                              ▼                       ▼
                        Whisper Large           Llama 3.1 8B
                        (transcription)         (intent detection
                                                 + tool calling)
                              │                       │
                              └───────────┬───────────┘
                                          ▼
                                    Tool Handler
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    ▼                     ▼                     ▼
              Supabase DB           Google Sheets       Google Calendar
              (expenses,            (optional sync)     (optional sync)
               tasks, events,
               users, etc.)
                                          │
                                          ▼
                                    Dashboard (HTML)
                                    /api/dashboard
```

## Tech Stack

- **Framework**: FastAPI + aiogram (async Telegram Bot API)
- **STT**: Groq Whisper Large v3 Turbo
- **LLM**: Groq Llama 3.1 8B Instant (tool calling)
- **Database**: Supabase (PostgreSQL)
- **Auth**: Service Role Key (RLS disabled)
- **Integrations**: Google Sheets API, Google Calendar API (service account)
- **Hosting**: Render (free tier, auto-deploy from GitHub)
- **Payments**: USDC (Base network) + Telegram Stars

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome + main menu |
| `/lang` | Change language (10 supported) |
| `/help` | How it works |

Everything else is voice-first — just speak.

## Dashboard

Open `/dashboard` in your browser or tap the 📊 button in the bot menu. Shows expenses, tasks, movements, and calendar events.

## License

MIT

## Contributing

PRs welcome! Check issues for ideas. Main areas: new integrations, UI improvements, language additions.
