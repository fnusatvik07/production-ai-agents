"""Centralized settings from environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # LangSmith
    langsmith_api_key: str = ""
    langsmith_project: str = "graphrag-research-engine"
    langchain_tracing_v2: bool = True

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "password"

    # Chroma
    chroma_host: str = "localhost"
    chroma_port: int = 8000

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    embedding_cache_ttl_seconds: int = 3600
    semantic_cache_ttl_seconds: int = 86400
    semantic_cache_similarity_threshold: float = 0.92

    # PostgreSQL
    postgres_uri: str = "postgresql://graphrag:graphrag_pass@localhost:5432/graphrag"

    # Retrieval
    hybrid_search_top_k: int = 20
    reranker_top_k: int = 5
    drift_max_hops: int = 3
    drift_community_top_k: int = 3

    # Evaluation
    ci_fail_on_faithfulness_below: float = 0.80
    eval_llm_model: str = "gpt-4o"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8001
    api_workers: int = 2


settings = Settings()
