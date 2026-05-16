#!/usr/bin/env python3
"""
Payment Instrument 作成テスト - LinkedAccounts が必須
"""
import logging
import os
from bedrock_agentcore.payments import PaymentManager

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"missing required env var: {name}")
    return value


PAYMENT_MANAGER_ARN = os.getenv("PAYMENT_MANAGER_ARN")
PAYMENT_CONNECTOR_ID = os.getenv("PAYMENT_CONNECTOR_ID")
REGION = os.getenv("AWS_REGION") or os.getenv("REGION", "us-west-2")
USER_ID = os.getenv("AGENTCORE_USER_ID", "test-user-123")

def main() -> int:
    try:
        payment_manager_arn = required_env("PAYMENT_MANAGER_ARN")
        payment_connector_id = required_env("PAYMENT_CONNECTOR_ID")
        manager = PaymentManager(
            payment_manager_arn=payment_manager_arn,
            region_name=REGION
        )

        logger.info("Creating payment instrument with linkedAccounts...")
        instrument = manager.create_payment_instrument(
            user_id=USER_ID,
            payment_connector_id=payment_connector_id,
            payment_instrument_type="EMBEDDED_CRYPTO_WALLET",
            payment_instrument_details={
                "embeddedCryptoWallet": {
                    "network": "ETHEREUM",
                    "linkedAccounts": [{"email": {"emailAddress": "test@example.com"}}]
                }
            }
        )
        logger.info("✅ SUCCESS!")
        logger.info(f"Instrument ID: {instrument.get('paymentInstrumentId')}")
        return 0
    except Exception as e:
        logger.error(f"❌ FAILED: {str(e)[:300]}")
        # エラーの詳細を表示
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
