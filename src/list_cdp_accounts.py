import argparse
import asyncio
import json
import os
from pathlib import Path

from cdp import CdpClient
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def resolve_credential(env_primary: str, env_fallback: str) -> str:
    value = os.getenv(env_primary) or os.getenv(env_fallback)
    if not value:
        raise ValueError(
            f"Missing credential: set {env_primary} or {env_fallback} in .env"
        )
    return value


async def fetch_all_accounts(list_func, page_size: int) -> list:
    accounts = []
    next_page_token = None

    while True:
        response = await list_func(page_size=page_size, page_token=next_page_token)
        accounts.extend(response.accounts or [])
        next_page_token = response.next_page_token
        if not next_page_token:
            break

    return accounts


def model_to_dict(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    return vars(model)


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="List registered Coinbase CDP accounts (EVM/Solana)."
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=50,
        help="Number of accounts per request (default: 50)",
    )
    parser.add_argument(
        "--chain",
        choices=["all", "evm", "solana"],
        default="all",
        help="Which account set to fetch",
    )
    args = parser.parse_args()

    api_key_id = resolve_credential("CDP_API_KEY_ID", "COINBASE_API_KEY_ID")
    api_key_secret = resolve_credential(
        "CDP_API_KEY_SECRET", "COINBASE_API_KEY_SECRET"
    )
    wallet_secret = resolve_credential("CDP_WALLET_SECRET", "COINBASE_WALLET_SECRET")

    async with CdpClient(
        api_key_id=api_key_id,
        api_key_secret=api_key_secret,
        wallet_secret=wallet_secret,
    ) as cdp:
        result = {}

        if args.chain in ("all", "evm"):
            evm_accounts = await fetch_all_accounts(cdp.evm.list_accounts, args.page_size)
            result["evm"] = [model_to_dict(a) for a in evm_accounts]

        if args.chain in ("all", "solana"):
            solana_accounts = await fetch_all_accounts(
                cdp.solana.list_accounts, args.page_size
            )
            result["solana"] = [model_to_dict(a) for a in solana_accounts]

        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
