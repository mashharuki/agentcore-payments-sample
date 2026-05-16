import os
import json
import time
from pathlib import Path
import boto3
from botocore.exceptions import ClientError, LoginRefreshRequired
from dotenv import load_dotenv


# プロジェクトルートの .env を読み込む
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")


REGION = os.getenv("REGION", "us-west-2")

def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"missing env var: {name}")
    return value


PROVIDER_NAME = os.getenv("PAYMENT_PROVIDER_NAME", "coinbase-provider-main")


def find_provider_arn_by_name(control, provider_name: str) -> str | None:
    next_token = None
    while True:
        kwargs = {}
        if next_token:
            kwargs["nextToken"] = next_token

        res = control.list_payment_credential_providers(**kwargs)
        providers = res.get("paymentCredentialProviders", [])
        for provider in providers:
            resolved_name = provider.get("name") or provider.get("paymentCredentialProviderName")
            if resolved_name != provider_name:
                continue
            arn = provider.get("paymentCredentialProviderArn") or provider.get(
                "credentialProviderArn"
            )
            if arn:
                return arn

        next_token = res.get("nextToken")
        if not next_token:
            break

    return None


def create_provider(control, provider_name: str, api_key_id: str, api_key_secret: str, wallet_secret: str):
    return control.create_payment_credential_provider(
        name=provider_name,
        credentialProviderVendor="CoinbaseCDP",
        providerConfigurationInput={
            "coinbaseCdpConfiguration": {
                "apiKeyId": api_key_id,
                "apiKeySecret": api_key_secret,
                "walletSecret": wallet_secret,
            }
        },
    )


def main() -> int:
    payment_manager_id = required_env("PAYMENT_MANAGER_ID")
    payment_connector_id = required_env("PAYMENT_CONNECTOR_ID")
    control = boto3.client("bedrock-agentcore-control", region_name=REGION)

    # 1) provider resolve/create (idempotent)
    provider_arn = find_provider_arn_by_name(control, PROVIDER_NAME)
    if provider_arn:
        print(f"provider already exists; reusing: {PROVIDER_NAME}")
    else:
        api_key_id = required_env("COINBASE_API_KEY_ID")
        api_key_secret = required_env("COINBASE_API_KEY_SECRET")
        wallet_secret = required_env("COINBASE_WALLET_SECRET")

        try:
            create_res = create_provider(
                control,
                PROVIDER_NAME,
                api_key_id,
                api_key_secret,
                wallet_secret,
            )
        except ClientError as e:
            if (
                e.response.get("Error", {}).get("Code") == "ValidationException"
                and "already exists" in str(e)
            ):
                provider_arn = find_provider_arn_by_name(control, PROVIDER_NAME)
                if not provider_arn:
                    # 稀に list API から見えない同名 provider が存在するため、別名で再作成して先に進める
                    suffix = str(int(time.time()))[-6:]
                    fallback_name = f"{PROVIDER_NAME}-{suffix}"
                    print(
                        "provider name already exists but cannot be listed; "
                        f"creating with fallback name: {fallback_name}"
                    )
                    create_res = create_provider(
                        control,
                        fallback_name,
                        api_key_id,
                        api_key_secret,
                        wallet_secret,
                    )
            else:
                raise

        if not provider_arn:
            # API model returns `credentialProviderArn` for this operation.
            provider_arn = (
                create_res.get("credentialProviderArn")
                or create_res.get("paymentCredentialProviderArn")
            )

    if not provider_arn:
        raise RuntimeError("Failed to resolve provider ARN")

    # 2) connector update
    update_res = control.update_payment_connector(
        paymentManagerId=payment_manager_id,
        paymentConnectorId=payment_connector_id,
        type="CoinbaseCDP",
        credentialProviderConfigurations=[
            {"coinbaseCDP": {"credentialProviderArn": provider_arn}}
        ],
    )

    print("provider resolved and connector updated")
    print(json.dumps({
        "providerArn": provider_arn,
        "connectorId": update_res.get("paymentConnectorId"),
        "connectorStatus": update_res.get("status"),
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {e}")
        if isinstance(e, ValueError) and "missing env var:" in str(e):
            print("Set required env vars:")
            print("  PAYMENT_MANAGER_ID")
            print("  PAYMENT_CONNECTOR_ID")
            print("  COINBASE_API_KEY_ID")
            print("  COINBASE_API_KEY_SECRET")
            print("  COINBASE_WALLET_SECRET")
        elif isinstance(e, LoginRefreshRequired) or "refresh token has expired" in str(e):
            print("Run `aws login` and retry.")
        raise
