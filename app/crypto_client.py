import json
import logging
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

ETHERSCAN_V2 = "https://api.etherscan.io/v2/api"

NETWORKS = {
    "ethereum": {"chainid": "1", "usdc": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "decimals": 6},
    "polygon": {"chainid": "137", "usdc": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359", "decimals": 6},
    "arbitrum": {"chainid": "42161", "usdc": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", "decimals": 6},
    "base": {"chainid": "8453", "usdc": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "decimals": 6},
    "bsc": {"chainid": "56", "usdc": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d", "decimals": 18},
    "optimism": {"chainid": "10", "usdc": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85", "decimals": 6},
    "avalanche": {"chainid": "43114", "usdc": "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E", "decimals": 6},
}

SOLSCAN_TX_URL = "https://api.solscan.io/v2/transaction/detail?tx={txid}"
SOLANA_USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def _fetch_json(url: str) -> dict | None:
    try:
        req = Request(url, headers={"User-Agent": "SashaBot/1.0"})
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        logger.warning("Fetch failed for %s: %s", url[:60], e)
        return None


def fetch_incoming_usdc_transfers(address: str, api_key: str) -> list[dict]:
    transfers = []
    for name, net in NETWORKS.items():
        if not api_key:
            continue
        url = (
            f"{ETHERSCAN_V2}?chainid={net['chainid']}&module=account&action=tokentx"
            f"&contractaddress={net['usdc']}&address={address}"
            f"&startblock=0&endblock=99999999&sort=desc&offset=25&apikey={api_key}"
        )
        data = _fetch_json(url)
        if not data or data.get("status") != "1" or "result" not in data:
            continue
        for tx in data["result"]:
            to_addr = tx.get("to", "").lower()
            if to_addr != address.lower():
                continue
            value = int(tx.get("value", "0")) / (10 ** net["decimals"])
            transfers.append({
                "txid": tx.get("hash", ""),
                "value": value,
                "from": tx.get("from", ""),
                "network": name,
                "confirmations": int(tx.get("confirmations", "0")),
                "timestamp": tx.get("timeStamp", "0"),
            })
    return transfers


def check_usdc_evm(txid: str, address: str, network: str, api_key: str) -> dict | None:
    net = NETWORKS.get(network)
    if not net or not api_key:
        return None

    url = (
        f"{ETHERSCAN_V2}?chainid={net['chainid']}&module=account&action=tokentx"
        f"&contractaddress={net['usdc']}&address={address}"
        f"&startblock=0&endblock=99999999&sort=desc&apikey={api_key}"
    )
    data = _fetch_json(url)
    if not data or data.get("status") != "1" or "result" not in data:
        return None

    for tx in data["result"]:
        if tx.get("hash", "").lower() == txid.lower():
            value = int(tx.get("value", "0")) / (10 ** net["decimals"])
            return {
                "value": value,
                "from": tx.get("from", ""),
                "to": tx.get("to", ""),
                "confirmations": int(tx.get("confirmations", "0")),
                "network": network,
            }
    return None


def check_usdc_solana(txid: str, address: str, api_key: str) -> dict | None:
    if not api_key:
        return None
    data = _fetch_json(SOLSCAN_TX_URL.format(txid=txid))
    if not data or "data" not in data:
        return None

    tx_data = data["data"]
    for change in tx_data.get("tokenTransfers", []):
        if change.get("mint") != SOLANA_USDC_MINT:
            continue
        dest = change.get("destinationOwner", "")
        source = change.get("sourceOwner", "")
        if dest.lower() == address.lower() or source.lower() == address.lower():
            value = float(change.get("rawTokenAmount", {}).get("tokenAmount", 0)) / 1_000_000
            return {
                "value": value,
                "from": source,
                "to": dest,
                "confirmations": min(tx_data.get("blockHeight", 0), 1),
                "network": "solana",
            }
    return None
