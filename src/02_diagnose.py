import boto3
import logging
import os
from botocore.exceptions import BotoCoreError, ClientError, LoginRefreshRequired


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


REGION = os.getenv("AWS_REGION") or os.getenv("REGION", "us-west-2")
PAYMENT_MANAGER_ID = os.getenv("PAYMENT_MANAGER_ID")


def extract_provider_name(provider_arn: str) -> str:
    return provider_arn.split("/")[-1]


def main() -> int:
    if not PAYMENT_MANAGER_ID:
        logger.error("PAYMENT_MANAGER_ID environment variable is required.")
        return 2

    control = boto3.client("bedrock-agentcore-control", region_name=REGION)

    try:
        managers = control.list_payment_managers().get("paymentManagers", [])
        logger.info("payment managers: %d", len(managers))

        connectors = control.list_payment_connectors(
            paymentManagerId=PAYMENT_MANAGER_ID
        ).get("paymentConnectors", [])
        logger.info("payment connectors: %d", len(connectors))
        referenced_provider_arns = set()
        for c in connectors:
            logger.info(
                "connector id=%s status=%s type=%s",
                c.get("paymentConnectorId"),
                c.get("status"),
                c.get("type"),
            )
            connector_id = c.get("paymentConnectorId")
            if not connector_id:
                continue
            try:
                detail = control.get_payment_connector(
                    paymentManagerId=PAYMENT_MANAGER_ID,
                    paymentConnectorId=connector_id,
                )
            except ClientError as ge:
                logger.warning(
                    "skip connector detail fetch: id=%s error=%s",
                    connector_id,
                    ge,
                )
                continue
            for cfg in detail.get("credentialProviderConfigurations", []):
                coinbase_arn = cfg.get("coinbaseCDP", {}).get("credentialProviderArn")
                stripe_arn = cfg.get("stripePrivy", {}).get("credentialProviderArn")
                if coinbase_arn:
                    referenced_provider_arns.add(coinbase_arn)
                if stripe_arn:
                    referenced_provider_arns.add(stripe_arn)

        providers = control.list_payment_credential_providers().get(
            "paymentCredentialProviders", []
        )
        logger.info("payment credential providers: %d", len(providers))
        for p in providers:
            logger.info(
                "provider id=%s status=%s type=%s",
                p.get("paymentCredentialProviderId"),
                p.get("status"),
                p.get("type"),
            )

        if referenced_provider_arns:
            logger.info(
                "connector referenced provider arns: %d", len(referenced_provider_arns)
            )
            for arn in sorted(referenced_provider_arns):
                name = extract_provider_name(arn)
                try:
                    provider = control.get_payment_credential_provider(name=name)
                    logger.info(
                        "provider reachable by get: name=%s arn=%s vendor=%s",
                        provider.get("name"),
                        provider.get("credentialProviderArn")
                        or provider.get("paymentCredentialProviderArn"),
                        provider.get("credentialProviderVendor")
                        or provider.get("type"),
                    )
                except ClientError as ge:
                    logger.warning(
                        "provider not reachable by get: name=%s arn=%s error=%s",
                        name,
                        arn,
                        ge,
                    )

    except Exception as e:  # show friendly remediation for auth expiry
        msg = str(e)
        if isinstance(e, LoginRefreshRequired) or "refresh token has expired" in msg:
            logger.error("AWS 認証セッションの期限が切れています。`aws login` を実行してください。")
            return 2
        if isinstance(e, (ClientError, BotoCoreError)):
            logger.error("AWS API エラー: %s", msg)
            return 1
        logger.exception("Unexpected error")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
