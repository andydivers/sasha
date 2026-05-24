import logging
import time
import google.generativeai as genai

logger = logging.getLogger(__name__)


def init_gemini(api_key: str):
    genai.configure(api_key=api_key)
    logger.info("Gemini initialized")


def analyze_image(image_bytes: bytes, mime_type: str, prompt: str = "Describe what you see in this image in detail.") -> str:
    start = time.perf_counter()
    model = genai.GenerativeModel("models/gemini-1.5-flash")
    response = model.generate_content([prompt, {"mime_type": mime_type, "data": image_bytes}])
    elapsed = time.perf_counter() - start
    logger.info("Gemini latency: %.2fs", elapsed)
    return response.text
