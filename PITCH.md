# Sasha — AI-ассистент в Telegram

## Питч-презентация для акселераторов / фондов

---

### Проблема

Владельцы малого бизнеса и фрилансеры тонут в операционке:
- Google Sheets для учёта → открыть, найти, отредактировать
- Google Calendar для встреч → создать, поделиться, напомнить
- Отчёты → вручную копировать данные, делать Excel
- Напоминания → держать в голове

На это уходит **3–5 часов в неделю**. Нет единого «мозга», который всё связывает.

### Решение

**Sasha** — Telegram-бот с ИИ. Единый чат для:
- Таблиц (учёт расходов, CRM)
- Календаря (встречи, дедлайны)
- Отчётов (Excel / HTML)
- Анализа скриншотов (через Gemini)
- Голосовых команд (расшифровка через Groq Whisper)
- Списка задач (/todo)
- Напоминаний (/remind)

Вместо 5+ приложений — **один чат**.

### Как работает

1. Пользователь пишет: «добавь кофе $5 в расходы»
2. Groq (LLM) определяет намерение → Google Sheets API
3. Ответ в чат — «кофе записан»
4. Всё. Без приложений, без интерфейсов.

### Технологии

| Компонент | Решение | Стоимость |
|-----------|---------|-----------|
| LLM (определение намерений) | Groq (Mixtral) | $0 |
| Мультимодальность | Gemini 2.0 Flash | $0 |
| База данных | Supabase | $0 |
| Таблицы | Service Account → gspread | $0 |
| Календарь | Service Account → Google Calendar API | $0 |
| Хостинг | Render (Free) | $0 |
| Сбор средств | Telegram Stars | $0 (30% комиссия платформы) |

**Итог: $0/месяц на инфраструктуру** (до 50k пользователей).

### Текущий стек (7 дней разработки)

- ✅ Telegram webhook + FastAPI
- ✅ Groq LLM с Function Calling (интенты: таблицы, календарь, отчёты, фото)
- ✅ Supabase (таблицы, пользователи, чаты, напоминания)
- ✅ Gemini 2.0 Flash (анализ изображений)
- ✅ Google Sheets (чтение/запись/добавление)
- ✅ Google Calendar (создание/список/удаление событий)
- ✅ Отчёты Excel + HTML
- ✅ Напоминания (фоновый чекер каждые 30 сек)
- ✅ Telegram Stars (встроенная монетизация)
- ✅ 10 языков (RU/EN/ES/FR/ZH/AR/PT/DE/HI/JA)
- ✅ I18N on both UI + LLM level

### Рынок

- 950M+ пользователей Telegram
- Массовый рынок для Telegram Stars
- **MVP**: English + Russian (300M+ users)
- **Цель**: 10k MAU в первом квартале
- **Revenue**: Tiered Stars pricing

### Бизнес-модель

| Услуга | Цена |
|--------|------|
| Отчёт Excel | 5 ⭐ |
| Отчёт HTML | 3 ⭐ |
| Генерация текстов | 2 ⭐ |
| *Подписка (30 дней)* | *50 ⭐ (planned)* |

**Current TPS (Transactions Per Star)**: ~100 messages / Stars session (total cost $0 for infra)

### Траектория

| Этап | Что сделано / план |
|------|-------------------|
| День 1–2 | Telegram + LLM + Webhook |
| День 3–4 | База + Мультимодальность |
| День 5 | Google Sheets |
| День 6 | Google Calendar |
| День 7 | Отчёты + Напоминания + Монетизация |
| **День 8 (план)** | Multi-agent system, email monitoring, proactive triggers, Stripe |
| **Q2** | SaaS Dashboard, Enterprise Webhooks, Stripe Subscription |

### Конкуренты

| Feature | Sasha (Telegram) | ChatGPT Telegram bots | Claude / ChatGPT Web | Zapier + Sheets |
|---------|-----------------|---------------------|---------------------|-----------------|
| **What it is** | AI assistant in Telegram — analyzes, stores, schedules, reports | Chatbot clones — text-only or limited function | Web-based chat — no integration with your data | No-code automation — requires setup for every flow |
| **Where it lives** | Inside Telegram — 900M+ users already there | Telegram bot wrappers | Separate browser tab | Separate platforms |
| **Multimodal input** | ✅ Text, photos, voice, screenshots, sheets | ❌ Text only (most) | ✅ Text, images (web only) | ❌ |
| **Google Sheets** | ✅ Read/write — auto-detect URL, 0 config | ❌ | ❌ copy-paste only | ✅ 15-min setup |
| **Google Calendar** | ✅ Create/list/delete events, public link | ❌ | ❌ text only | ✅ complex setup |
| **Reports** | ✅ Excel + HTML, sent as file | ❌ | ❌ text only | ✅ multi-step zap |
| **Voice input** | ✅ Native in Telegram → Groq Whisper | ❌ | ❌ web only | ❌ |
| **Reminders** | ✅ `/remind 30min check email` | ❌ | ❌ | ✅ per-task setup |
| **Persistent memory** | ✅ Lang, timezone, sheet, tasks — all stored | ❌ session only | ✅ per-chat context | ❌ |
| **Monetization** | ✅ Telegram Stars — instant, 0% platform fee | ❌ | $20/mo per user | $20-50/mo |
| **Multi-language** | ✅ 10 languages, instant switch | ❌ usually EN only | ✅ | ❌ |
| **Setup time** | **2 min** — search bot, /start | 5 min | 1 min — no integration | 30-60 min |
| **Cost** | **$0** (free tier Render + free APIs) | Free-$20/mo | $20/mo/user | $20-50/mo + usage |

### Запрос

**$250k — 6 месяцев — 7% equity**

- $60k — Salaries (2 инженера + 1 продакт, 6 месяцев)
- $50k — Инфраструктура (агентные вычисления, GPU, AWS)
- $40k — Разработка SaaS Dashboard и enterprise-функций
- $40k — Юридическое (оформление, патенты, SOC 2)
- $60k — Маркетинг и привлечение пользователей (Telegram Ads, контент)

### Risks & Mitigation

| Risk | Mitigation |
|------|-----------|
| LLM latency | Groq <400ms response time |
| Supabase Free limits | 50k rows = ~50k users |
| Render spin-down | UptimeRobot ping (free) |
| Google API quotas | 60 req/min with exponential backoff |
| iOS App Store rules | Stars only on iOS (per Apple guidelines) |
