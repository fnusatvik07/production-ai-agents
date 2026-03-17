"""
evaluation.py
~~~~~~~~~~~~~
DeepEval CI/CD evaluation for PR review quality.
Measures correctness, hallucination, and ADR citation faithfulness.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def run_pr_review_evaluation(golden_dataset_path: Path, fail_threshold: float = 0.80) -> bool:
    """
    Run DeepEval evaluation on PR review quality.

    Args:
        golden_dataset_path: JSON file with {diff, expected_findings, agent_findings}
        fail_threshold: Minimum average score to pass CI

    Returns:
        True if all metrics pass, False otherwise
    """
    try:
        from deepeval import evaluate as deepeval_evaluate
        from deepeval.metrics import (
            GEval,
            HallucinationMetric,
            FaithfulnessMetric,
        )
        from deepeval.test_case import LLMTestCase

    except ImportError:
        logger.error("deepeval not installed. Run: uv add deepeval")
        return False

    with open(golden_dataset_path) as f:
        dataset = json.load(f)

    # Define metrics
    correctness_metric = GEval(
        name="PR Review Correctness",
        criteria="""The actual output should identify the same critical issues as the expected output.
Minor differences in phrasing are acceptable. Missing critical security or ADR violations is NOT acceptable.""",
        evaluation_params=["actual_output", "expected_output"],
        threshold=fail_threshold,
    )

    hallucination_metric = HallucinationMetric(threshold=0.15)
    faithfulness_metric = FaithfulnessMetric(threshold=fail_threshold)

    test_cases = []
    for sample in dataset:
        test_case = LLMTestCase(
            input=sample["diff"],
            actual_output=json.dumps(sample["agent_findings"], indent=2),
            expected_output=json.dumps(sample["expected_findings"], indent=2),
            context=[sample.get("adr_context", "")],
            retrieval_context=[sample.get("adr_context", "")],
        )
        test_cases.append(test_case)

    results = deepeval_evaluate(
        test_cases=test_cases,
        metrics=[correctness_metric, hallucination_metric, faithfulness_metric],
        run_async=True,
    )

    # Print results
    print("\n── DeepEval PR Review Quality Results ────────────────────")
    all_passed = True
    for test_result in results.test_results:
        for metric_result in test_result.metrics_data:
            status = "✓" if metric_result.success else "✗"
            print(f"  {status} {metric_result.name:<35} {metric_result.score:.3f}")
            if not metric_result.success:
                all_passed = False
    print("─────────────────────────────────────────────────────────")

    return all_passed


def cli_evaluate() -> None:
    import argparse
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument("--golden-dataset", required=True)
    parser.add_argument("--fail-below", type=float, default=0.80)
    args = parser.parse_args()

    passed = run_pr_review_evaluation(Path(args.golden_dataset), args.fail_below)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    cli_evaluate()
