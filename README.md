# agentcore-payment-sample

Amazon Bedrock Payments Sample Code

## 必要な前提条件

このサンプルを実行するには、以下の設定が必要です：

### 1. Payment Manager の作成
```bash
aws bedrock-agentcore-control create-payment-manager \
  --region us-west-2
```

### 2. Payment Connector の設定
CoinbaseCDP コネクタを使用するには、以下が必要です：

#### 2.1 Payment Credential Provider の作成・設定（boto3 推奨）
```bash
export COINBASE_API_KEY_ID="..."
export COINBASE_API_KEY_SECRET="..."
export COINBASE_WALLET_SECRET="..."

.venv/bin/python - << 'PY'
import os, boto3, json
c = boto3.client('bedrock-agentcore-control', region_name='us-west-2')
res = c.create_payment_credential_provider(
    name='coinbase-provider-main',
    credentialProviderVendor='CoinbaseCDP',
    providerConfigurationInput={
        'coinbaseCdpConfiguration': {
            'apiKeyId': os.environ['COINBASE_API_KEY_ID'],
            'apiKeySecret': os.environ['COINBASE_API_KEY_SECRET'],
            'walletSecret': os.environ['COINBASE_WALLET_SECRET'],
        }
    },
)
print(json.dumps(res, indent=2, default=str))
PY
```

#### 2.2 Payment Connector の作成
```bash
.venv/bin/python - << 'PY'
import boto3, json
c = boto3.client('bedrock-agentcore-control', region_name='us-west-2')
res = c.create_payment_connector(
    paymentManagerId='paymentmanager-xxxx',
    name='coinbase-connector-main',
    description='Coinbase connector',
    type='CoinbaseCDP',
    credentialProviderConfigurations=[
        {
            'coinbaseCDP': {
                'credentialProviderArn': 'arn:aws:bedrock-agentcore:us-west-2:<account>:token-vault/default/paymentcredentialprovider/<provider-id>'
            }
        }
    ],
)
print(json.dumps(res, indent=2, default=str))
PY
```

### 3. サンプル実行

```bash
# 依存関係をインストール
uv sync

# セットアップスクリプトで、現在の Payment Manager と Connector を確認
.venv/bin/python src/01_create.py

# 環境変数として設定
export PAYMENT_MANAGER_ARN="arn:aws:bedrock-agentcore:us-west-2:..."
export PAYMENT_CONNECTOR_ID="test1234-..."

# メインスクリプト実行
.venv/bin/python src/strands_sample.py
```

## トラブルシューティング

### `aws ... list-payment-credential-providers` が invalid choice になる
原因：AWS CLI 側が AgentCore Payments の最新 operation をまだサポートしていない

解決策：boto3 経由で確認する
```bash
.venv/bin/python - << 'PY'
import boto3
c = boto3.client('bedrock-agentcore-control', region_name='us-west-2')
print(c.list_payment_credential_providers())
PY
```

### `LoginRefreshRequired` / `refresh token has expired`
原因：AWS Builder ID / IAM Identity Center のログインセッション期限切れ

解決策：再ログインしてから再実行
```bash
aws login
# その後
.venv/bin/python src/01_create.py
.venv/bin/python src/strands_sample.py
```

### `InternalServerException` が発生する場合
原因：Connector が未登録/無効な Credential Provider ARN を参照している

解決策：
1. `.venv/bin/python src/02_diagnose.py` で provider 件数を確認
2. provider が 0 件なら、上記 2.1 で provider を作成
3. connector の `credentialProviderArn` を新しい provider ARN に更新

復旧を自動化する場合：
```bash
export COINBASE_API_KEY_ID="..."
export COINBASE_API_KEY_SECRET="..."
export COINBASE_WALLET_SECRET="..."
.venv/bin/python src/03_fix_connector.py
```

### LinkedAccounts パラメータ エラー
原因：`embeddedCryptoWallet` の `linkedAccounts` が必須

解決策：以下の形式で指定
```python
"linkedAccounts": [
  {
    "email": {
      "emailAddress": "user@example.com"
    }
  }
]
```

### Coinbase CDP の登録済みアカウント一覧を確認したい
`cdp-sdk` を使って EVM/Solana のアカウント一覧を取得できます。

```bash
# .env の COINBASE_* か CDP_* を利用
uv run src/list_cdp_accounts.py

# EVM のみ
uv run src/list_cdp_accounts.py --chain evm

# Solana のみ
uv run src/list_cdp_accounts.py --chain solana
```

### Coinbase CDP のアカウントを作成したい
`cdp-sdk` を使って EVM/Solana アカウントを作成できます。

```bash
# EVM アカウントを1つ作成
uv run src/create_cdp_account.py --chain evm

# Solana アカウントを1つ作成（名前指定）
uv run src/create_cdp_account.py --chain solana --name my-solana-account

# EVM アカウントを3つ作成（name-1, name-2, name-3）
uv run src/create_cdp_account.py --chain evm --name my-evm-account --count 3
```

## 参考資料

- [AWS Bedrock AgentCore Payments API Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/payments.html)
- [Coinbase CDP API](https://cdp.coinbase.com/docs/v1/api)
- [Introducing Amazon Bedrock AgentCore Payments, Powered by x402 and Coinbase](https://www.coinbase.com/blog/introducing-amazon-bedrock-agentcore-payments-powered-by-x402-and-coinbase)