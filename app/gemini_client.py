import logging
import time
import json
import base64
import httpx

logger = logging.getLogger(__name__)

_api_key: str = ""
_gemini_model: str = ""


def init_gemini(api_key: str):
    global _api_key, _gemini_model
    _api_key = api_key
    _gemini_model = "gemini-1.5-flash"
    logger.info("Gemini initialized")


def analyze_image(image_bytes: bytes, mime_type: str, prompt: str = "Describe what you see in this image.") -> str:
    if not _api_key:
        return "Gemini API key is not configured."

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{_gemini_model}:generateContent?key={_api_key}"
    base64_img = base64.b64encode(image_bytes).decode()

    body = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": base64_img}}
            ]
        }]
    }

    start = time.perf_counter()
    resp = httpx.post(url, json=body, timeout=30)
    elapsed = time.perf_counter() - start
    logger.info("Gemini latency: %.2fs (status: %d)", elapsed, resp.status_code)

    if resp.status_code != 200:
        error_detail = resp.text[:300]
        logger.error("Gemini error %d: %s", resp.status_code, error_detail)
        if "not found" in resp.text.lower():
            return "This model is not available. Please enable the Gemini API at https://aistudio.google.com/"
        return f"Image analysis failed. Status: {resp.status_code}"

    data = resp.json()
    candidates = data.get("candidates", [])
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts)
    return "No analysis returned."
