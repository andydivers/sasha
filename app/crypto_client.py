import hashlib
import hmac
import json
import logging
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError

logger = logging.getLogger(__name__)

API_URL = "https://api.nowpayments.io/v1"


def create_invoice(api_key: str, price_amount: float, order_id: str, description: str, ipn_callback_url: str) -> dict | None:
    data = json.dumps({
        "price_amount": price_amount,
        "price_currency": "usd",
        "order_id": order_id,
        "order_description": description,
        "ipn_callback_url": ipn_callback_url,
    }).encode()

    req = Request(
        f"{API_URL}/invoice",
        data=data,
        headers={
            "x-api-key": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            logger.info("NowPayments invoice created: %s", result.get("id"))
            return result
    except HTTPError as e:
        body = e.read().decode()
        logger.error("NowPayments invoice error %s: %s", e.code, body)
        return None
    except Exception as e:
        logger.error("NowPayments request failed: %s", e)
        return None


def verify_webhook(ipn_secret: str, body: bytes, signature_header: str) -> dict | None:
    expected_sig = hmac.new(ipn_secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, signature_header):
        logger.warning("NowPayments webhook: invalid signature")
        return None

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        logger.warning("NowPayments webhook: invalid JSON")
        return None

    payment_status = data.get("payment_status")
    if payment_status != "finished":
        logger.info("NowPayments webhook: status=%s, not finished yet", payment_status)
        return None

    order_id = data.get("order_id", "")
    pay_amount = data.get("pay_amount", 0)
    logger.info("NowPayments payment confirmed: order=%s amount=%s", order_id, pay_amount)
    return data
