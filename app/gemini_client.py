import logging
import time
import json
import base64
import os
import httpx

logger = logging.getLogger(__name__)

_api_key: str = ""
_groq_key: str = ""
_openrouter_key: str = ""


def init_gemini(api_key: str):
    global _api_key, _groq_key, _openrouter_key
    _api_key = api_key
    # Groq API key — already set on Render, supports vision via qwen3.6-27b
    _groq_key = os.getenv("GROQ_API_KEY", "")
    # OpenRouter key — may NOT be set on Render
    _openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    logger.info(
        "Image analysis initialized: Gemini=%s, Groq Vision=%s, OpenRouter=%s",
        "yes" if _api_key else "no",
        "yes" if _groq_key else "no",
        "yes" if _openrouter_key else "no",
    )


# ─── 1. Gemini (Google) ─────────────────────────────────────────────────────

def _call_gemini(model: str, image_bytes: bytes, mime_type: str, prompt: str) -> tuple[str | None, str]:
    base64_img = base64.b64encode(image_bytes).decode()
    body = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": base64_img}}
            ]
        }]
    }
    url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={_api_key}"

    for attempt in range(2):
        resp = httpx.post(url, json=body, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                return "".join(p.get("text", "") for p in parts), None
            return None, "No analysis returned."
        if resp.status_code == 429 and attempt < 1:
            time.sleep(2)
            continue
        return None, f"Gemini {model}: HTTP {resp.status_code} — {resp.text[:200]}"
    return None, "Gemini rate-limited."


# ─── 2. Groq Vision (qwen3.6-27b) ───────────────────────────────────────────

def _call_groq_vision(image_bytes: bytes, mime_type: str, prompt: str) -> tuple[str | None, str]:
    """Use Groq's qwen3.6-27b vision model. GROQ_API_KEY is already on Render."""
    if not _groq_key:
        return None, "No GROQ_API_KEY"

    base64_img = base64.b64encode(image_bytes).decode()
    data_url = f"data:{mime_type};base64,{base64_img}"

    # Groq vision model (llama-4-series decommissioned 2026-07-17)
    models = ["qwen/qwen3.6-27b"]

    for model in models:
        try:
            body = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
                "max_tokens": 1000,
                "temperature": 0.1,
            }
            resp = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {_groq_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if text:
                    return text, None
                return None, f"Groq {model}: empty response"
            else:
                logger.warning("Groq vision %s error: %d %s", model, resp.status_code, resp.text[:200])
        except Exception as e:
            logger.warning("Groq vision %s failed: %s", model, e)
            continue

    return None, "All Groq vision models failed"


# ─── 3. OpenRouter Vision (last resort) ─────────────────────────────────────

def _call_openrouter_vision(image_bytes: bytes, mime_type: str, prompt: str) -> tuple[str | None, str]:
    """Last resort: use OpenRouter vision models (requires OPENROUTER_API_KEY)."""
    if not _openrouter_key:
        return None, "No OPENROUTER_API_KEY"

    base64_img = base64.b64encode(image_bytes).decode()
    data_url = f"data:{mime_type};base64,{base64_img}"

    models = [
        "google/gemma-4-31b-it:free",
        "nvidia/nemotron-nano-12b-2-vl:free",
        "google/gemma-4-26b-a4b-it:free",
    ]

    for model in models:
        try:
            body = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
                "max_tokens": 1000,
                "temperature": 0.1,
            }
            resp = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {_openrouter_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if text:
                    return text, None
            else:
                logger.warning("OpenRouter vision %s error: %d", model, resp.status_code)
        except Exception as e:
            logger.warning("OpenRouter vision %s failed: %s", model, e)
            continue

    return None, "All OpenRouter vision models failed"


# ─── Main entry point ────────────────────────────────────────────────────────

def analyze_image(image_bytes: bytes, mime_type: str, prompt: str = "Describe what you see in this image.") -> str:
    """Analyze an image using a cascade of vision providers.
    
    Priority: Gemini → Groq Vision → OpenRouter Vision
    Groq Vision (qwen3.6-27b) is the most reliable fallback because
    GROQ_API_KEY is already configured on Render.
    """
    
    # 1. Try Gemini first (if key available)
    if _api_key:
        models_to_try = ["gemini-2.0-flash-001", "gemini-2.0-flash", "gemini-2.5-flash"]
        start = time.perf_counter()
        for model in models_to_try:
            result, error = _call_gemini(model, image_bytes, mime_type, prompt)
            if result:
                elapsed = time.perf_counter() - start
                logger.info("Gemini latency: %.2fs (model: %s)", elapsed, model)
                return result
            logger.warning("Gemini %s failed: %s", model, error[:100])

    # 2. Groq Vision — PRIMARY FALLBACK (key already on Render!)
    if _groq_key:
        logger.info("Trying Groq Vision fallback (llama-4-scout)")
        start = time.perf_counter()
        result, error = _call_groq_vision(image_bytes, mime_type, prompt)
        if result:
            elapsed = time.perf_counter() - start
            logger.info("Groq Vision latency: %.2fs", elapsed)
            return result
        logger.warning("Groq Vision failed: %s", error[:100])

    # 3. OpenRouter Vision — last resort
    if _openrouter_key:
        logger.info("Trying OpenRouter vision fallback")
        start = time.perf_counter()
        result, error = _call_openrouter_vision(image_bytes, mime_type, prompt)
        if result:
            elapsed = time.perf_counter() - start
            logger.info("OpenRouter vision latency: %.2fs", elapsed)
            return result
        logger.warning("OpenRouter vision failed: %s", error[:100])

    # All providers failed
    logger.error("All image analysis providers failed. Gemini: exhausted/quota. Groq: %s. OpenRouter: %s",
                 "no key" if not _groq_key else "failed",
                 "no key" if not _openrouter_key else "failed")
    return (
        "Image analysis is not available right now. "
        "Please try again later or describe the expense in text."
    )
