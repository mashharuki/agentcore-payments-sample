# Strands Agentを使った統合パターン
import logging
import os
import boto3
from strands import Agent
from strands_tools import http_request
from bedrock_agentcore.payments import PaymentManager
from bedrock_agentcore.payments.integrations.config import AgentCorePaymentsPluginConfig
from bedrock_agentcore.payments.integrations.strands.plugin import AgentCorePaymentsPlugin

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ここは作成された値を入力する
def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"missing required env var: {name}")
    return value


PAYMENT_MANAGER_ARN = os.getenv("PAYMENT_MANAGER_ARN")
PAYMENT_CONNECTOR_ID = os.getenv("PAYMENT_CONNECTOR_ID")
REGION = os.getenv("AWS_REGION") or os.getenv("REGION", "us-west-2")
USER_ID = os.getenv("AGENTCORE_USER_ID", "test-user-123")


def extract_manager_id(manager_arn: str) -> str:
    return manager_arn.split("/")[-1]


def preflight_check() -> None:
    manager_id = extract_manager_id(PAYMENT_MANAGER_ARN)
    control = boto3.client("bedrock-agentcore-control", region_name=REGION)

    connector = control.get_payment_connector(
        paymentManagerId=manager_id,
        paymentConnectorId=PAYMENT_CONNECTOR_ID,
    )
    status = connector.get("status")
    if status != "READY":
        raise RuntimeError(
            f"Connector status is {status}. Connector must be READY."
        )

    provider_arns = set()
    for item in control.list_payment_credential_providers().get(
        "paymentCredentialProviders", []
    ):
        arn = item.get("paymentCredentialProviderArn")
        if arn:
            provider_arns.add(arn)

    referenced_arns = []
    for cfg in connector.get("credentialProviderConfigurations", []):
        if cfg.get("coinbaseCDP", {}).get("credentialProviderArn"):
            referenced_arns.append(cfg["coinbaseCDP"]["credentialProviderArn"])
        if cfg.get("stripePrivy", {}).get("credentialProviderArn"):
            referenced_arns.append(cfg["stripePrivy"]["credentialProviderArn"])

    missing = [arn for arn in referenced_arns if arn not in provider_arns]
    if missing:
        raise RuntimeError(
            "Connector references missing credential provider(s): "
            + ", ".join(missing)
        )

def main() -> int:
    global PAYMENT_MANAGER_ARN, PAYMENT_CONNECTOR_ID

    try:
        PAYMENT_MANAGER_ARN = required_env("PAYMENT_MANAGER_ARN")
        PAYMENT_CONNECTOR_ID = required_env("PAYMENT_CONNECTOR_ID")
        logger.info(f"PaymentManager初期化開始: {PAYMENT_MANAGER_ARN}")
        manager = PaymentManager(
            payment_manager_arn=PAYMENT_MANAGER_ARN,
            region_name=REGION
        )
        logger.info("PaymentManager初期化成功")
    except Exception as e:
        logger.error(f"PaymentManager初期化失敗: {e}", exc_info=True)
        return 1

    # 事前検証: 既存の Payment Instruments を確認
    try:
        logger.info("Connector/Provider preflight check 中...")
        preflight_check()
        logger.info("Connector/Provider preflight check 成功")

        logger.info("既存のPayment Instrumentsをリスト化中...")
        existing_instruments = manager.list_payment_instruments(user_id=USER_ID)
        logger.info(f"既存Instruments: {existing_instruments}")
    except Exception as e:
        logger.error(f"事前検証に失敗: {e}")
        logger.error("Credential Provider を作成/再作成し、Connector の参照先を更新してください。")
        return 1

    # Create payment instrument (Ethereum)
    try:
        logger.info(f"Payment Instrument作成開始: connector_id={PAYMENT_CONNECTOR_ID}")
        logger.info("⚠️  InternalServerException が発生する場合:")
        logger.info("   1. Payment Credential Provider が正しく設定されているか確認")
        logger.info("   2. Coinbase CDP API キーが有効か確認")
        logger.info("   3. README.md のトラブルシューティングを参照")

        instrument = manager.create_payment_instrument(
            user_id=USER_ID,
            payment_connector_id=PAYMENT_CONNECTOR_ID,
            payment_instrument_type="EMBEDDED_CRYPTO_WALLET",
            payment_instrument_details={
                "embeddedCryptoWallet": {
                    "network": "ETHEREUM",
                    "linkedAccounts": [
                        {"email": {"emailAddress": "myemail@example.com"}}
                    ],
                }
            },
        )
        logger.info(f"Payment Instrument作成成功: {instrument}")
    except Exception as e:
        logger.error(f"Payment Instrument作成失敗: {e}", exc_info=True)
        return 1

    # 支払いセッション(100ドル分は承認無しに自動支払いを可能とする)
    try:
        logger.info("Payment Session作成開始")
        session = manager.create_payment_session(
            user_id=USER_ID,
            limits={"maxSpendAmount": {"value": "100.00", "currency": "USD"}},
            expiry_time_in_minutes=60
        )
        logger.info(f"Payment Session作成成功: {session}")
    except Exception as e:
        logger.error(f"Payment Session作成失敗: {e}", exc_info=True)
        return 1

    # Configure the plugin
    try:
        logger.info("Plugin設定開始")
        config = AgentCorePaymentsPluginConfig(
            payment_manager_arn=PAYMENT_MANAGER_ARN,
            user_id=USER_ID,
            payment_instrument_id=instrument["paymentInstrumentId"],
            payment_session_id=session["paymentSessionId"],
            region=REGION,
        )
        logger.info("Plugin設定成功")
    except Exception as e:
        logger.error(f"Plugin設定失敗: {e}", exc_info=True)
        return 1

    # Create the plugin
    try:
        logger.info("AgentCorePaymentsPlugin初期化中")
        plugin = AgentCorePaymentsPlugin(config=config)
        logger.info("AgentCorePaymentsPlugin初期化成功")
    except Exception as e:
        logger.error(f"AgentCorePaymentsPlugin初期化失敗: {e}", exc_info=True)
        return 1

    # Create agent with the plugin
    agent = Agent(
        system_prompt="You are a helpful assistant that can access paid APIs.",
        tools=[http_request],
        plugins=[plugin],
    )

    # The agent automatically handles 402 responses
    logger.info("Agentを実行中...")
    agent("Access the premium endpoint at https://api.run402.com/tiers/v1/prototype")
    logger.info("✅ 処理完了")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
