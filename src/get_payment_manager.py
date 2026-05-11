import os
from dotenv import load_dotenv
from bedrock_agentcore.payments.client import PaymentClient

# .env ファイルから環境変数を読み込む
load_dotenv()

# payments インスタンスを生成
payment_client = PaymentClient(region_name="us-west-2");

# 環境変数から payment manager ID を取得
payment_manager_id = os.getenv("PAYMENT_MANAGER_ID")
if not payment_manager_id:
    raise ValueError("PAYMENT_MANAGER_ID environment variable is not set")

# 取得
response = payment_client.get_payment_manager(
    payment_manager_id=payment_manager_id
)

print(f"Status: {response['status']}")