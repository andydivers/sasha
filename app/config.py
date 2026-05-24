import os
from dataclasses import dataclass, field


@dataclass
class Config:
    bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    sentry_dsn: str = field(default_factory=lambda: os.getenv("SENTRY_DSN", ""))
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    supabase_url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    supabase_key: str = field(default_factory=lambda: os.getenv("SUPABASE_KEY", ""))
    app_url: str = field(default_factory=lambda: os.getenv("RENDER_EXTERNAL_URL", "") or os.getenv("APP_URL", ""))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))

    @property
    def webhook_url(self) -> str:
        return f"{self.app_url}/webhook" if self.app_url else ""

    def validate(self):
        errors = []
        if not self.bot_token:
            errors.append("BOT_TOKEN is not set. Get it from @BotFather")
        if not self.groq_api_key:
            errors.append("GROQ_API_KEY is not set. Get it from console.groq.com")
        if not self.app_url:
            errors.append("APP_URL / RENDER_EXTERNAL_URL is not set. It should be your server URL on Render")
        if errors:
            raise ValueError("\n".join(errors))
