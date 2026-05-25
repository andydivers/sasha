import json
import logging
from urllib.request import urlopen
from urllib.error import HTTPError

logger = logging.getLogger(__name__)

API_URL = "https://block.io/api/v2"


def create_address(api_key: str, label: str) -> dict | None:
    try:
        with urlopen(f"{API_URL}/get_new_address/?api_key={api_key}&label={label}", timeout=15) as resp:
            result = json.loads(resp.read())
            if result.get("status") == "success":
                data = result["data"]
                logger.info("Block.io address: %s", data.get("address"))
                return data
            logger.error("Block.io error: %s", result)
            return None
    except HTTPError as e:
        body = e.read().decode()
        logger.error("Block.io HTTP error %s: %s", e.code, body)
        return None
    except Exception as e:
        logger.error("Block.io request failed: %s", e)
        return None


def get_address_balance(api_key: str, address: str) -> float:
    try:
        with urlopen(f"{API_URL}/get_address_balance/?api_key={api_key}&addresses={address}", timeout=15) as resp:
            result = json.loads(resp.read())
            if result.get("status") == "success" and result.get("data"):
                balances = result["data"].get("balances", [])
                if balances:
                    return float(balances[0].get("balance", "0"))
        return 0.0
    except Exception as e:
        logger.error("Block.io balance check failed: %s", e)
        return 0.0
