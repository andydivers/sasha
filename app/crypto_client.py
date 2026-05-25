import hashlib
import json
import logging
import base64
from urllib.request import Request, urlopen
from urllib.error import HTTPError

logger = logging.getLogger(__name__)

API_URL = "https://api.cryptomus.com/v1"


def _sign(payload: str, api_key: str) -> str:
    return hashlib.md5((payload + api_key).encode()).hexdigest()


def create_invoice(merchant_id: str, api_key: str, price_amount: float, order_id: str, description: str, callback_url: str) -> dict | None:
    body = {
        "amount": str(price_amount),
        "currency": "USD",
        "order_id": order_id,
        "url_callback": callback_url,
        "is_payment_multiple": True,
        "lifetime": 3600,
    }
    payload = json.dumps(body, separators=(",", ":"))
    b64_payload = base64.b64encode(payload.encode()).decode()
    sign = _sign(b64_payload, api_key)

    req = Request(
        f"{API_URL}/payment",
        data=payload.encode(),
        headers={
            "merchant": merchant_id,
            "sign": sign,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            if result.get("state") == 0 and result.get("result"):
                logger.info("Cryptomus invoice created: %s", result["result"].get("uuid"))
                return result["result"]
            logger.error("Cryptomus error: %s", result)
            return None
    except HTTPError as e:
        body = e.read().decode()
        logger.error("Cryptomus HTTP error %s: %s", e.code, body)
        return None
    except Exception as e:
        logger.error("Cryptomus request failed: %s", e)
        return None


def verify_webhook(api_key: str, body: bytes, merchant_header: str, sign_header: str) -> dict | None:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        logger.warning("Cryptomus webhook: invalid JSON")
        return None

    expected_sign = hashlib.md5(body + api_key.encode()).hexdigest()
    if expected_sign != sign_header:
        logger.warning("Cryptomus webhook: invalid signature")
        return None

    status = data.get("status")
    if status != "paid":
        logger.info("Cryptomus webhook: status=%s, not paid yet", status)
        return None

    order_id = data.get("order_id", "")
    logger.info("Cryptomus payment confirmed: order=%s", order_id)
    return data
