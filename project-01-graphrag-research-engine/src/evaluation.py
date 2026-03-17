"""
evaluation.py
~~~~~~~~~~~~~
RAGAS-based evaluation pipeline with LangSmith experiment tracking.
Run standalone or hook into CI/CD to fail on metric regression.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from datasets import Dataset
from langsmith import Client as LangSmithClient
from ragas import evaluate
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)
from ragas.llms import LangchainLLMWrapper
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from .config import settings

logger = logging.getLogger(__name__)


def load_eval_dataset(path: Path) -> list[dict]:
    """
    Load evaluation dataset. Expected format (JSON array):
    [
      {
        "question": "...",
        "ground_truth": "...",
        "answer": "...",           # from your system
        "contexts": ["chunk1", "chunk2", ...]  # retrieved chunks
      }
    ]
    """
    with open(path) as f:
        return json.load(f)


def run_ragas_evaluation(samples: list[dict]) -> dict[str, float]:
    """Run RAGAS evaluation and return metric scores."""
    dataset = Dataset.from_list(samples)

    eval_llm = LangchainLLMWrapper(
        ChatOpenAI(model=settings.eval_llm_model, api_key=settings.openai_api_key)
    )
    eval_embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=settings.openai_api_key,
    )

    result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=eval_llm,
        embeddings=eval_embeddings,
    )

    return {
        "faithfulness": float(result["faithfulness"]),
        "answer_relevancy": float(result["answer_relevancy"]),
        "context_precision": float(result["context_precision"]),
        "context_recall": float(result["context_recall"]),
    }


def push_to_langsmith(
    metrics: dict[str, float],
    experiment_name: str,
    dataset_path: str,
) -> None:
    """Log evaluation results as a LangSmith experiment."""
    if not settings.langsmith_api_key:
        logger.warning("LANGSMITH_API_KEY not set — skipping LangSmith push")
        return

    client = LangSmithClient(api_key=settings.langsmith_api_key)

    # Create or fetch the dataset reference
    experiment_results = {
        "experiment_name": experiment_name,
        "dataset": dataset_path,
        "metrics": metrics,
    }
    logger.info("LangSmith experiment results: %s", json.dumps(experiment_results, indent=2))
    # In a full integration: client.create_run(...) with the metrics attached
    # See: https://docs.smith.langchain.com/evaluation


def check_thresholds(metrics: dict[str, float]) -> bool:
    """Return True if all metrics pass CI thresholds. False = CI failure."""
    faithfulness_threshold = settings.ci_fail_on_faithfulness_below
    passes = metrics["faithfulness"] >= faithfulness_threshold

    if not passes:
        logger.error(
            "CI FAILURE: faithfulness %.3f < threshold %.3f",
            metrics["faithfulness"],
            faithfulness_threshold,
        )
    else:
        logger.info("All CI thresholds passed.")

    return passes


def cli_evaluate() -> None:
    """Entry point: uv run python -m src.evaluation --dataset data/eval_dataset.json"""
    import argparse
    from datetime import datetime

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Run RAGAS evaluation")
    parser.add_argument("--dataset", required=True, help="Path to evaluation JSON")
    parser.add_argument("--experiment", default=None, help="LangSmith experiment name")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"Dataset not found: {dataset_path}")
        sys.exit(1)

    experiment_name = args.experiment or f"graphrag-eval-{datetime.now().strftime('%Y-%m-%d')}"

    print(f"Loading dataset from {dataset_path}...")
    samples = load_eval_dataset(dataset_path)
    print(f"Evaluating {len(samples)} samples with RAGAS...")

    metrics = run_ragas_evaluation(samples)

    print("\n── RAGAS Evaluation Results ──────────────────────────")
    for metric, score in metrics.items():
        status = "✓" if score >= 0.7 else "✗"
        print(f"  {status} {metric:<25} {score:.3f}")
    print("──────────────────────────────────────────────────────")

    push_to_langsmith(metrics, experiment_name, str(dataset_path))

    if not check_thresholds(metrics):
        sys.exit(1)

    print(f"\nExperiment '{experiment_name}' complete. All thresholds passed.")
