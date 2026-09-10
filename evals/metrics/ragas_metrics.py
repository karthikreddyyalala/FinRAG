"""ragas-based eval metrics. Lazy imports inside functions to avoid
broken langchain_community.chat_models.vertexai import on Python 3.13."""
import sys
import os
from unittest.mock import MagicMock


def _patch_vertexai() -> None:
    """Stub the missing vertexai module before ragas tries to import it."""
    if "langchain_community.chat_models.vertexai" not in sys.modules:
        sys.modules["langchain_community.chat_models.vertexai"] = MagicMock()


def build_ragas_config(bedrock_region: str = "us-east-1"):
    """Return (llm, embeddings) configured for Bedrock via langchain-aws."""
    _patch_vertexai()
    from langchain_aws import ChatBedrockConverse, BedrockEmbeddings

    llm = ChatBedrockConverse(
        model="anthropic.claude-haiku-4-5-20250714-v1:0",
        region_name=bedrock_region,
    )
    embeddings = BedrockEmbeddings(
        model_id="amazon.titan-embed-text-v2:0",
        region_name=bedrock_region,
    )
    return llm, embeddings


def score_dataset(
    questions: list[str],
    answers: list[str],
    contexts: list[list[str]],
    ground_truths: list[str],
    bedrock_region: str = "us-east-1",
) -> dict[str, float]:
    """
    Score a batch of QA pairs with ragas.

    Returns dict with keys: faithfulness, answer_relevancy,
    context_precision, context_recall.
    """
    _patch_vertexai()
    from ragas import evaluate
    from ragas.metrics import (
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
    )
    from datasets import Dataset

    llm, embeddings = build_ragas_config(bedrock_region)

    dataset = Dataset.from_dict(
        {
            "question": questions,
            "answer": answers,
            "contexts": contexts,
            "ground_truth": ground_truths,
        }
    )

    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=llm,
        embeddings=embeddings,
    )
    return {k: float(v) for k, v in result.items()}
