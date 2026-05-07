from strands import Agent
from strands_tools import http_request
from bedrock_agentcore.payments.integrations.config import AgentCorePaymentsPluginConfig
from bedrock_agentcore.payments.integrations.strands.plugin import AgentCorePaymentsPlugin

# Configure the payments plugin
config = AgentCorePaymentsPluginConfig(
    payment_manager_arn="arn:aws:bedrock-agentcore:us-west-2:123456789012:payment-manager/pm-abc123",
    user_id="test-user-123",
    payment_instrument_id="payment-instrument-xyz789",
    payment_session_id="payment-session-def456",
    region="ap-northeast-1",
)

# Create agent with automatic payment handling
plugin = AgentCorePaymentsPlugin(config=config)
agent = Agent(
    system_prompt="You are a helpful assistant that can access paid APIs.",
    tools=[http_request],
    plugins=[plugin],
)

# The agent automatically handles 402 responses
agent("Access the premium endpoint at https://example.com/paid-api")