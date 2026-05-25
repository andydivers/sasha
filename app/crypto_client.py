import json
import logging
from urllib.request import Request, urlopen
from urllib.error import HTTPError

logger = logging.getLogger(__name__)

API_URL = "https://api.coingate.com/v2"


def create_invoice(api_key: str, price_amount: float, order_id: str, description: str, callback_url: str) -> dict | None:
    data = json.dumps({
        "price_amount": price_amount,
        "price_currency": "USD",
        "receive_currency": "DO_NOT_CONVERT",
        "order_id": order_id,
        "title": description,
        "description": description,
        "callback_url": callback_url,
        "success_url": callback_url,
        "cancel_url": callback_url,
    }).encode()

    req = Request(
        f"{API_URL}/orders",
        data=data,
        headers={
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            logger.info("CoinGate order: %s", result.get("id"))
            return result
    except HTTPError as e:
        body = e.read().decode()
        logger.error("CoinGate error %s: %s", e.code, body)
        return None
    except Exception as e:
        logger.error("CoinGate request failed: %s", e)
        return None


def verify_webhook(body: bytes) -> dict | None:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None

    if data.get("status") != "paid":
        return None

    return data
