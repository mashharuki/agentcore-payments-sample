import logging
import os
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError, LoginRefreshRequired
from dotenv import load_dotenv
from bedrock_agentcore.payments import PaymentManager

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# プロジェクトルートの .env を読み込む
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

# 定数
def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Environment variable '{name}' is required")
    return value


def extract_manager_id(manager_arn: str) -> str:
    return manager_arn.split("/")[-1]


def extract_provider_name(provider_arn: str) -> str:
    return provider_arn.split("/")[-1]


def preflight_check() -> None:
    manager_id = extract_manager_id(PAYMENT_MANAGER_ARN)
    control = boto3.client("bedrock-agentcore-control", region_name=REGION)

    connector = control.get_payment_connector(
        paymentManagerId=manager_id,
        paymentConnectorId=PAYMENT_CONNECTOR_ID,
    )
    status = connector.get("status")
    logger.info("Connector status: %s", status)
    if status != "READY":
        raise RuntimeError(f"Connector status is {status}. Connector must be READY.")

    providers = control.list_payment_credential_providers().get(
        "paymentCredentialProviders", []
    )
    provider_arns = {}
    for p in providers:
        arn = p.get("paymentCredentialProviderArn") or p.get("credentialProviderArn")
        if arn:
            provider_arns[arn] = p.get("status", "UNKNOWN")

    referenced_arns = []
    for cfg in connector.get("credentialProviderConfigurations", []):
        coinbase_arn = cfg.get("coinbaseCDP", {}).get("credentialProviderArn")
        stripe_arn = cfg.get("stripePrivy", {}).get("credentialProviderArn")
        if coinbase_arn:
            referenced_arns.append(coinbase_arn)
        if stripe_arn:
            referenced_arns.append(stripe_arn)

    if not referenced_arns:
        raise RuntimeError(
            "Connector has no credentialProviderConfigurations. "
            "Run src/03_fix_connector.py to attach a credential provider."
        )

    missing = []
    for arn in referenced_arns:
        if arn in provider_arns:
            continue

        provider_name = extract_provider_name(arn)
        try:
            provider = control.get_payment_credential_provider(name=provider_name)
            resolved_arn = provider.get("credentialProviderArn") or provider.get(
                "paymentCredentialProviderArn"
            )
            if resolved_arn:
                provider_arns[resolved_arn] = "UNKNOWN"
            else:
                # 念のため、参照ARN自体を存在扱いとして追加
                provider_arns[arn] = "UNKNOWN"
        except ClientError:
            missing.append(arn)

    if missing:
        raise RuntimeError(
            "Connector references missing credential provider(s): " + ", ".join(missing)
        )

    not_ready = [
        arn for arn in referenced_arns
        if provider_arns.get(arn) not in ("READY", "UNKNOWN")
    ]
    if not_ready:
        details = ", ".join(
            f"{arn} (status={provider_arns.get(arn)})" for arn in not_ready
        )
        raise RuntimeError(
            "Referenced credential provider is not READY: " + details
        )

    # CoinbaseCDP の場合は、参照providerと .env の API key id の一致確認を行う
    expected_api_key_id = os.getenv("COINBASE_API_KEY_ID")
    if expected_api_key_id:
        mismatched = []
        for arn in referenced_arns:
            provider_name = extract_provider_name(arn)
            try:
                provider = control.get_payment_credential_provider(name=provider_name)
            except ClientError:
                continue

            output = provider.get("providerConfigurationOutput", {})
            actual_api_key_id = (
                output.get("coinbaseCdpConfiguration", {}).get("apiKeyId")
            )
            if actual_api_key_id and actual_api_key_id != expected_api_key_id:
                mismatched.append(
                    f"{provider_name}: expected={expected_api_key_id}, actual={actual_api_key_id}"
                )

        if mismatched:
            logger.warning(
                "COINBASE_API_KEY_ID mismatch detected in referenced provider(s): %s",
                "; ".join(mismatched),
            )

    logger.info("Preflight check passed (connector/provider are READY)")


PAYMENT_MANAGER_ARN = get_required_env("PAYMENT_MANAGER_ARN")
PAYMENT_CONNECTOR_ID = get_required_env("PAYMENT_CONNECTOR_ID")
REGION = "us-west-2"
USER_ID = get_required_env("USER_ID")
TARGET_CHAIN = os.getenv("TARGET_CHAIN", "BASE_SEPOLIA")
BALANCE_TOKEN = os.getenv("BALANCE_TOKEN")
LINKED_ACCOUNT_EMAIL = os.getenv("LINKED_ACCOUNT_EMAIL", "test@example.com")

if LINKED_ACCOUNT_EMAIL == "test@example.com":
    raise ValueError(
        "LINKED_ACCOUNT_EMAIL is not set. Set your Coinbase linked account email in .env "
        "(default test@example.com is not valid for production API calls)."
    )

# PaymentManager の初期化
try:
    logger.info(f"Initializing PaymentManager: {PAYMENT_MANAGER_ARN}")
    manager = PaymentManager(
        payment_manager_arn=PAYMENT_MANAGER_ARN,
        region_name=REGION
    )
    logger.info("✓ PaymentManager initialized")
except Exception as e:
    logger.error(f"✗ PaymentManager initialization failed: {e}")
    raise

try:
    logger.info("Running preflight checks...")
    preflight_check()
except Exception as e:
    msg = str(e)
    if isinstance(e, LoginRefreshRequired) or "refresh token has expired" in msg:
        logger.error("AWS 認証が期限切れです。`aws login` 後に再実行してください。")
    elif isinstance(e, (ClientError, BotoCoreError)):
        logger.error("AWS API エラー: %s", msg)
    else:
        logger.error("Preflight failed: %s", msg)
    raise

# Base Sepolia を使う場合でも instrument network は ETHEREUM を指定する
patterns = [
    {
        "name": "Pattern 1: ETHEREUM + linkedAccounts (recommended)",
        "instrument_type": "EMBEDDED_CRYPTO_WALLET",
        "details": {
            "embeddedCryptoWallet": {
                "network": "ETHEREUM",
                "linkedAccounts": [{"email": {"emailAddress": LINKED_ACCOUNT_EMAIL}}],
            }
        }
    },
]

# 各パターンで試す
success = False
for i, pattern in enumerate(patterns, 1):
    logger.info(f"\n=== Attempting {pattern['name']} ===")
    try:
        logger.info(f"Parameters:")
        logger.info(f"  - connector_id: {PAYMENT_CONNECTOR_ID}")
        logger.info(f"  - instrument_type: {pattern['instrument_type']}")
        logger.info(f"  - details: {pattern['details']}")
        
        instrument = manager.create_payment_instrument(
            user_id=USER_ID,
            payment_connector_id=PAYMENT_CONNECTOR_ID,
            payment_instrument_type=pattern['instrument_type'],
            payment_instrument_details=pattern['details']
        )
        
        logger.info(f"✓✓✓ SUCCESS! ✓✓✓")
        logger.info(f"Created instrument: {instrument}")
        logger.info(
            "For Base Sepolia, keep embeddedCryptoWallet.network=ETHEREUM and use chain=%s in chain-aware APIs.",
            TARGET_CHAIN,
        )

        if BALANCE_TOKEN:
            try:
                balance = manager.get_payment_instrument_balance(
                    user_id=USER_ID,
                    payment_connector_id=PAYMENT_CONNECTOR_ID,
                    payment_instrument_id=instrument["paymentInstrumentId"],
                    chain=TARGET_CHAIN,
                    token=BALANCE_TOKEN,
                )
                logger.info("Balance on %s (%s): %s", TARGET_CHAIN, BALANCE_TOKEN, balance)
            except Exception as balance_err:
                logger.warning("Balance check on %s failed: %s", TARGET_CHAIN, balance_err)

        print(f"\n✅ Pattern {i} succeeded:\n{pattern['name']}")
        success = True
        break
        
    except Exception as e:
        error_str = str(e)
        logger.warning(f"✗ Failed: {error_str[:200]}")
        cause = getattr(e, "__cause__", None)
        request_id = None
        if isinstance(cause, ClientError):
            request_id = cause.response.get("ResponseMetadata", {}).get("RequestId")
        if request_id:
            logger.warning("  → AWS RequestId: %s", request_id)
        if "network" in error_str.lower():
            logger.warning("  → Issue with network parameter")
        elif "linkedAccounts" in error_str:
            logger.warning("  → Issue with linkedAccounts parameter")
        elif "not found" in error_str.lower():
            logger.warning("  → Connector or resource not found")
        elif "InternalServerException" in error_str:
            logger.warning(
                "  → Backend-side error. Verify LINKED_ACCOUNT_EMAIL and Coinbase API credentials, "
                "then check src/02_diagnose.py and src/03_fix_connector.py"
            )
        else:
            logger.warning(f"  → Other error (see details above)")

logger.info("\n=== Test Complete ===")
if not success:
    raise SystemExit("No pattern succeeded. Run src/02_diagnose.py and src/03_fix_connector.py.")
