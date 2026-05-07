from bedrock_agentcore.payments import PaymentManager

# Create PaymentManager インスタンス
manager = PaymentManager(
    payment_manager_arn=mgr["paymentManagerArn"],
    region_name="us-weat-2"
)

# Create payment instrument (Ethereum Type)
instrument = manager.create_payment_instrument(
    user_id="test-haruki-123",
    payment_connector_id=PAYMENT_CONNECTOR_ID,
    payment_instrument_type="EMBEDDED_CRYPTO_WALLET",
    payment_instrument_details={
        "embeddedCryptoWallet": {
            "network": "ETHEREUM",
            "linkedAccounts": [{
                "email": {
                    "emailAddress": "myemail@example.com"
                }
            }]
        }
    },
)