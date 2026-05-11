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


def extract_emails_from_auth_methods(auth_methods: list) -> list[str]:
    emails = []
    for method in auth_methods or []:
        inst = getattr(method, "actual_instance", None)
        if not inst:
            continue

        method_type = getattr(inst, "type", None)
        if method_type == "email":
            email = getattr(inst, "email", None)
            if email:
                emails.append(email)
            continue

        oauth_email = getattr(inst, "email", None)
        if oauth_email:
            emails.append(oauth_email)

    return sorted(set(emails))


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="List linked emails from CDP end users."
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=50,
        help="Number of end users per request (default: 50)",
    )
    args = parser.parse_args()

    api_key_id = resolve_credential("CDP_API_KEY_ID", "COINBASE_API_KEY_ID")
    api_key_secret = resolve_credential(
        "CDP_API_KEY_SECRET", "COINBASE_API_KEY_SECRET"
    )
    wallet_secret = resolve_credential("CDP_WALLET_SECRET", "COINBASE_WALLET_SECRET")

    result = []
    next_page_token = None

    async with CdpClient(
        api_key_id=api_key_id,
        api_key_secret=api_key_secret,
        wallet_secret=wallet_secret,
    ) as cdp:
        while True:
            page = await cdp.end_user.list_end_users(
                page_size=args.page_size,
                page_token=next_page_token,
            )
            for end_user in page.end_users:
                result.append(
                    {
                        "user_id": end_user.user_id,
                        "linked_emails": extract_emails_from_auth_methods(
                            end_user.authentication_methods
                        ),
                    }
                )

            next_page_token = page.next_page_token
            if not next_page_token:
                break

    print(json.dumps({"end_users": result}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
