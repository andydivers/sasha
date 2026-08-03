import os
from dataclasses import dataclass, field


def _env(*names: str) -> str:
    for n in names:
        v = os.getenv(n, "").strip()
        if v:
            return v
    return ""


@dataclass
class Config:
    bot_token: str = field(default_factory=lambda: _env("BOT_TOKEN"))
    groq_api_key: str = field(default_factory=lambda: _env("GROQ_API_KEY"))
    openrouter_api_key: str = field(default_factory=lambda: _env("OPENROUTER_API_KEY", "OPENROUTER_API_KEY2"))
    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY"))
    google_sheets_creds: str = field(default_factory=lambda: os.getenv("GOOGLE_SHEETS_CREDENTIALS", ""))
    supabase_url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    supabase_key: str = field(default_factory=lambda: os.getenv("SUPABASE_KEY", ""))
    usdc_address: str = field(default_factory=lambda: os.getenv("USDC_ADDRESS", ""))
    etherscan_api_key: str = field(default_factory=lambda: os.getenv("ETHERSCAN_API_KEY", ""))
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
