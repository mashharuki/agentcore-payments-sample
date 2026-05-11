import argparse
import asyncio
import json
import os
import uuid
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


def model_to_dict(model) -> dict:
    result = {}
    for field in ("address", "name", "policies"):
        if hasattr(model, field):
            value = getattr(model, field)
            if value is not None:
                result[field] = value

    if result:
        return result

    if hasattr(model, "model_dump"):
        dumped = model.model_dump()
        if dumped:
            return dumped
    if hasattr(model, "dict"):
        dumped = model.dict()
        if dumped:
            return dumped
    return vars(model)


async def create_single_account(cdp, chain: str, name: str | None, policy: str | None):
    idempotency_key = str(uuid.uuid4())
    if chain == "evm":
        return await cdp.evm.create_account(
            name=name,
            account_policy=policy,
            idempotency_key=idempotency_key,
        )

    return await cdp.solana.create_account(
        name=name,
        account_policy=policy,
        idempotency_key=idempotency_key,
    )


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create Coinbase CDP account (EVM or Solana)."
    )
    parser.add_argument(
        "--chain",
        choices=["evm", "solana"],
        default="evm",
        help="Which account type to create (default: evm)",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Optional account name",
    )
    parser.add_argument(
        "--account-policy",
        default=None,
        help="Optional account policy ID",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of accounts to create (default: 1)",
    )
    args = parser.parse_args()

    if args.count < 1:
        raise ValueError("--count must be >= 1")

    api_key_id = resolve_credential("CDP_API_KEY_ID", "COINBASE_API_KEY_ID")
    api_key_secret = resolve_credential(
        "CDP_API_KEY_SECRET", "COINBASE_API_KEY_SECRET"
    )
    wallet_secret = resolve_credential("CDP_WALLET_SECRET", "COINBASE_WALLET_SECRET")

    created = []
    async with CdpClient(
        api_key_id=api_key_id,
        api_key_secret=api_key_secret,
        wallet_secret=wallet_secret,
    ) as cdp:
        for i in range(args.count):
            name = args.name
            if args.count > 1 and args.name:
                name = f"{args.name}-{i + 1}"
            account = await create_single_account(cdp, args.chain, name, args.account_policy)
            created.append(model_to_dict(account))

    print(
        json.dumps(
            {
                "chain": args.chain,
                "count": len(created),
                "accounts": created,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
