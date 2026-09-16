"""ragas-based eval metrics. Lazy imports inside functions to avoid
broken langchain_community.chat_models.vertexai import on Python 3.13."""
import sys
from unittest.mock import MagicMock


def _patch_vertexai() -> None:
    """Stub the missing vertexai module before ragas tries to import it."""
    if "langchain_community.chat_models.vertexai" not in sys.modules:
        sys.modules["langchain_community.chat_models.vertexai"] = MagicMock()


def build_ragas_config(bedrock_region: str = "us-east-1"):
    """Return (llm, embeddings) configured for OpenAI — fast, no throttling."""
    _patch_vertexai()
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
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
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

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
        raise_exceptions=False,
    )
    df = result.to_pandas()
    metric_cols = [c for c in df.columns if df[c].dtype != object]

    # raise_exceptions=False turns a failed evaluation into NaN, and
    # Series.mean() skips NaN -- so 28 failures out of 30 would report the
    # mean of the 2 survivors and sail through the CI threshold. Count the
    # NaNs and surface them so a degraded run is visibly degraded.
    scores: dict[str, float] = {}
    for col in metric_cols:
        scored = int(df[col].notna().sum())
        scores[col] = float(df[col].mean()) if scored else 0.0
        scores[f"{col}_scored_n"] = scored

    total = len(df)
    failed = sum(total - int(scores[f"{c}_scored_n"]) for c in metric_cols)
    if failed:
        print(f"WARNING: {failed} metric evaluations failed across {total} rows (scored as NaN)")
    return scores
