from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    langsmith_api_key: str = ""
    langsmith_project: str = "sre-incident-response"
    langchain_tracing_v2: bool = True

    postgres_uri: str = "postgresql://sre:sre_pass@localhost:5433/sre_agent"
    chroma_host: str = "localhost"
    chroma_port: int = 8000

    kubectl_mcp_url: str = "http://localhost:9010/mcp"
    aws_mcp_url: str = "http://localhost:9011/mcp"
    http_check_mcp_url: str = "http://localhost:9012/mcp"

    dangerous_commands: str = "kubectl delete,kubectl drain,aws rds reboot,aws ec2 terminate"
    max_runbook_steps: int = 20
    step_timeout_seconds: int = 30
    api_port: int = 8003


settings = Settings()
