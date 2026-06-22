import logging
import time
import json
import base64
import os
import httpx

logger = logging.getLogger(__name__)

_api_key: str = ""
_openrouter_key: str = ""


def init_gemini(api_key: str):
    global _api_key
    _api_key = api_key
    # Also grab OpenRouter key for fallback
    _openrouter_key = os.getenv("OPENROUTER_API_KEY", "") or os.getenv("GROQ_API_KEY", "")
    logger.info("Gemini initialized (with OpenRouter vision fallback)")


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
        return None, resp.text[:300]
    return None, "Rate-limited."


def _call_openrouter_vision(image_bytes: bytes, mime_type: str, prompt: str) -> tuple[str | None, str]:
    """Fallback: use OpenRouter vision models to analyze images."""
    if not _openrouter_key:
        return None, "No OpenRouter key"

    base64_img = base64.b64encode(image_bytes).decode()
    data_url = f"data:{mime_type};base64,{base64_img}"

    # Try free/cheap vision models on OpenRouter
    models = [
        "google/gemini-2.0-flash-exp:free",
        "meta-llama/llama-4-scout:free",
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
                            {"type": "image_url", "image_url": {"url": data_url}}
                        ]
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

    return None, "All vision models failed"


def analyze_image(image_bytes: bytes, mime_type: str, prompt: str = "Describe what you see in this image.") -> str:
    # Try Gemini first (if key available)
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

    # Fallback: OpenRouter vision models
    logger.info("Falling back to OpenRouter vision")
    start = time.perf_counter()
    result, error = _call_openrouter_vision(image_bytes, mime_type, prompt)
    if result:
        elapsed = time.perf_counter() - start
        logger.info("OpenRouter vision latency: %.2fs", elapsed)
        return result

    logger.error("All image analysis failed. Gemini: exhausted. OpenRouter: %s", error)
    return (
        "Image analysis is not available right now. "
        "Please try again later or describe the expense in text."
    )
