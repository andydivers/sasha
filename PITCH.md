# Sasha — AI Assistant in Telegram

## Pitch for Accelerators / VCs

---

### Problem

Small business owners and freelancers waste **3–5 hours/week** on operations:
- Tracking expenses across receipts, apps, memory
- Scheduling meetings, setting reminders
- Logging where they were and when
- Managing recurring bills
- Switching between 5+ apps: sheets, calendar, todo, reminders, notes

No single "brain" connects everything in one chat.

### Solution

**Sasha** — Telegram AI bot. **Voice-first.** Just talk to it.

One chat for:
- **Expenses & notes** — say "coffee $5" → saved locally (zero-config)
- **Google Sheets** — optional, connect via link, sync with `/sync`
- **Calendar** — "meeting Friday 10am" → created
- **Location tracking** — "at work" → logged with time + timezone
- **Daily digest** — auto-summary every morning (expenses, movements, todos, anomalies, upcoming bills)
- **Anomaly detection** — spending spikes, large transactions flagged
- **Recurring payments** — "add Netflix $10 monthly" → auto-reminders
- **Reminders** — "remind me in 1 hour"
- **Todo** — "add buy milk to tasks"
- **10 languages** — native EN/RU/ES/FR/ZH/AR/PT/DE/HI/JA
- **Voice input** — Groq Whisper, any language

**Instead of 5+ apps → one Telegram chat. Zero setup.**

### How It Works

1. User sends voice or text: *"add coffee $5, I'm at work, remind me in 1 hour to call John"*
2. Groq `llama-3.3-70b-versatile` detects intent → calls tools in **multi-turn loop** (up to 10 sequential calls)
3. Each tool result feeds back to LLM for next reasoning step
4. Final response — all tasks done in one message

### Key Differentiator

**Zero-config voice-first operation.**
- No Google Sheet needed — expenses save locally in Supabase
- Say "I'm in Bangkok" → auto-sets timezone, shows times as MSK + local
- Say "sync" → pushes all local data to Google Sheet
- `/start` shows inline menu with 4 buttons (how to use, commands, buy, language)
- Help shows only 4 commands — everything else works via chat

### Market

| Country | TG Users | Strategy |
|---------|----------|----------|
| India | 180M | Freemium, local payments |
| Russia | 85M | 🇷🇺 native, USDC |
| Indonesia | 72M | Low-cost subscriptions |
| Brazil | 65M | 🇧🇷 Portuguese |
| USA | 55M | Premium |
| Turkey | 38M | 🇹🇷 Turkish |
| Germany | 32M | Privacy-focused |
| Nigeria | 28M | Crypto-first, USDC |

**1.05B Telegram MAUs globally.** Telegram is becoming a SuperApp — TON, mini-apps, in-app payments, AI bots.

### Current Stack (built in 30 days)

| Component | Solution | Cost |
|-----------|---------|------|
| LLM (intent) | Groq `llama-3.3-70b-versatile` | $0 |
| Multi-turn loop | Sequential tool calls | — |
| Voice transcription | Groq Whisper `large-v3-turbo` | $0 |
| Database | Supabase (500MB, 50k rows) | $0 |
| Google Sheets | Service Account → gspread (optional) | $0 |
| Google Calendar | Service Account → API | $0 |
| Hosting | Render Free (512MB, auto-sleep) | $0 |
| Uptime | UptimeRobot (ping every 5min) | $0 |
| Payments (Stars) | Telegram `sendInvoice` + XTR | ~30% fee |
| Payments (USDC) | Etherscan V2 → 7 EVM chains | $0 |
| Languages | 10 (EN/RU/ES/FR/ZH/AR/PT/DE/HI/JA) | — |
| Reports | Excel (openpyxl) + HTML | — |
| Smart timezone | City→TZ map (120+ cities, 50 countries) | — |
| Daily digest | Background checker per user TZ | — |

**Total infra cost: $0/month** (up to ~50k users).

### Competitive Moat

| Feature | Sasha | ChatGPT TG bots | Claude/ChatGPT Web | Zapier |
|---------|-------|-----------------|-------------------|--------|
| Lives inside Telegram | ✅ | ✅ wrapper | ❌ | ❌ |
| Voice-first onboarding | ✅ | ❌ | ❌ web only | ❌ |
| Zero-config (no sheet needed) | ✅ | ❌ | ❌ | ❌ |
| Multi-turn agent loop | ✅ | ❌ single reply | ❌ | ✅ complex |
| Location/time tracking | ✅ | ❌ | ❌ | ❌ |
| Daily digest + anomalies | ✅ | ❌ | ❌ | ❌ |
| Auto-timezone by city | ✅ | ❌ | ❌ | ❌ |
| Google Sheets (optional) | ✅ auto-detect URL | ❌ | ❌ | ✅ 15min setup |
| Google Calendar | ✅ create/list/delete | ❌ | ❌ text only | ✅ complex |
| Voice input | ✅ native → whisper | ❌ | ❌ web only | ❌ |
| Reports (Excel/HTML) | ✅ sent as file | ❌ | ❌ text only | ✅ multi-step |
| Recurring payments | ✅ auto-reminders | ❌ | ❌ | ✅ per-task |
| Re-engagement | ✅ inactive user alerts | ❌ | ❌ | ❌ |
| Persistent memory | ✅ lang/tz/sheet/tasks/digest | ❌ session | ✅ per-chat | ❌ |
| Multi-language | ✅ 10 languages | ❌ usually EN | ✅ limited | ❌ |
| Setup time | **0 minutes** (just talk) | 5min | 1min (no integration) | 30-60min |
| Payments | Stars (instant) + USDC | ❌ | $20/mo | $20-50/mo |
| **Cost to user** | **$4.99 wk / $14.99 mo** | Free-$20/mo | $20/mo | $20-50/mo |

### Monetization

| Tier | Price (Stars) | Price (USDC) | Features |
|------|--------------|-------------|----------|
| Free | $0 | $0 | All basic features (generous free tier) |
| Weekly | 400⭐ | 5 USDC | Priority, unlimited |
| Monthly | 1000⭐ | 15 USDC | All features, priority digest |

- USDC via Etherscan V2 (7 chains: Ethereum, Polygon, Arbitrum, Base, BSC, Optimism, Avalanche)
- Payment matching by unique micro-amount
- 30-min expiry on pending payments
- Telegram Stars auto-renew for monthly subscriptions

### Traction

- Built solo in 30 days — fully functional multi-agent bot
- 10 languages live with native onboarding
- Voice-first: users just talk, bot figures everything out
- Zero-config local storage + optional Google Sheets sync
- Multi-turn tool calling (up to 10 sequential turns)
- USDC payment detection (7 EVM chains, 60s polling)
- Daily digest + anomaly detection + recurring payments
- Automatic re-engagement for inactive users
- Auto-timezone by city name with dual time display

### Roadmap

| Phase | Timeline | Milestone |
|-------|----------|-----------|
| MVP complete | ✅ Now | All core features live |
| Growth | Q3 2026 | Launch in India/Brazil/Indonesia, Telegram Ads |
| TON integration | Q3 2026 | TON Connect wallet, USDT on TON, mini-app |
| SaaS Dashboard | Q4 2026 | Web dashboard, enterprise webhooks |
| Scale | Q1 2027 | 50k MAU, Series A |

### Ask

**$250k — 12 months runway**

| Use | Amount |
|-----|--------|
| Engineering (2 FTE) | $120k |
| Marketing (Telegram Ads + localization) | $60k |
| Infrastructure (GPU, multi-region) | $40k |
| Legal (incorporation, compliance) | $30k |

### Why Now

1. **Telegram at 1.05B MAU** — bigger than ever, still growing
2. **Bot API 9.6** — no-code bots creating awareness for ALL bots
3. **TON + AI wave** — $200M+ in dedicated TG/TON funds actively deploying
4. **No dominant AI assistant in Telegram exists** — first-mover window open
5. **$0 infra cost** — capital-efficient, free tier for 50k users
6. **Voice-first AI assistants becoming mainstream** — perfect timing

### Risks & Mitigation

| Risk | Mitigation |
|------|-----------|
| LLM latency | Groq <400ms; multi-turn capped at 10 turns |
| Free tier limits | Supabase 50k rows → $25/mo upgrade |
| Render spin-down | UptimeRobot ping every 5min |
| Google API quotas | 60 req/min, exponential backoff |
| iOS Stars limitation | USDC on desktop as alternative |

---

**Contact:** andydivers/sasha on GitHub  
**Stack:** Python, Aiogram 3.x, FastAPI, Groq, Supabase, Google APIs  
**Try it:** https://t.me/HeySasha_bot
