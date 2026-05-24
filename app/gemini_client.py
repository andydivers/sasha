import logging
import time
import json
import base64
import httpx

logger = logging.getLogger(__name__)

_api_key: str = ""


def init_gemini(api_key: str):
    global _api_key
    _api_key = api_key
    logger.info("Gemini initialized")


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
    resp = httpx.post(url, json=body, timeout=30)
    if resp.status_code == 200:
        data = resp.json()
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts), None
        return None, "No analysis returned."
    return None, resp.text[:300]


def analyze_image(image_bytes: bytes, mime_type: str, prompt: str = "Describe what you see in this image.") -> str:
    if not _api_key:
        return "Gemini API key is not configured."

    models_to_try = ["gemini-2.0-flash-001", "gemini-2.0-flash", "gemini-2.5-flash"]
    errors = []

    start = time.perf_counter()
    for model in models_to_try:
        result, error = _call_gemini(model, image_bytes, mime_type, prompt)
        if result:
            elapsed = time.perf_counter() - start
            logger.info("Gemini latency: %.2fs (model: %s)", elapsed, model)
            return result
        errors.append(f"{model}: {error[:100]}")

    elapsed = time.perf_counter() - start
    logger.error("All Gemini models failed: %s", errors)
    return (
        "Image analysis is not available right now. "
        "Make sure the Gemini API is enabled at https://aistudio.google.com/ "
        "and you have an active API key."
    )
