"""Unit tests for ragas_metrics — mock ragas so no AWS/import needed."""
import sys
from unittest.mock import MagicMock, patch


def test_patch_vertexai_stubs_module():
    from evals.metrics.ragas_metrics import _patch_vertexai
    _patch_vertexai()
    import langchain_community.chat_models.vertexai  # noqa: F401  -- must not raise


def test_score_dataset_calls_ragas_evaluate():
    import pandas as pd

    # ragas returns an EvaluationResult (per-row scores), not a dict of means;
    # score_dataset averages it down via .to_pandas().
    mock_result = MagicMock()
    mock_result.to_pandas.return_value = pd.DataFrame(
        {
            "faithfulness": [0.9],
            "answer_relevancy": [0.85],
            "context_precision": [0.88],
            "context_recall": [0.82],
        }
    )
    mock_evaluate = MagicMock(return_value=mock_result)
    mock_ragas = MagicMock()
    mock_ragas.evaluate = mock_evaluate

    mock_dataset_cls = MagicMock()
    mock_dataset_cls.from_dict.return_value = MagicMock()

    with patch.dict(
        sys.modules,
        {
            "ragas": mock_ragas,
            "ragas.metrics": MagicMock(),
            "ragas.run_config": MagicMock(RunConfig=MagicMock()),
            "datasets": MagicMock(Dataset=mock_dataset_cls),
            "langchain_aws": MagicMock(),
        },
    ):
        # Re-import inside context so patched modules are used
        import importlib

        import evals.metrics.ragas_metrics as rm
        importlib.reload(rm)

        with patch.object(rm, "build_ragas_config", return_value=(MagicMock(), MagicMock())):
            with patch("datasets.Dataset", mock_dataset_cls):
                result = rm.score_dataset(
                    questions=["What was revenue?"],
                    answers=["Revenue was $23B"],
                    contexts=[["Revenue was $23B in 10-Q."]],
                    ground_truths=["$23 billion"],
                )

    assert "faithfulness" in result


def test_score_dataset_throttles_ragas_concurrency():
    """ragas defaults to max_workers=16, which blew the 200K TPM budget at
    job 64 of 600 and cascaded into connection errors for the rest of the
    run -- 398 of 600 scoring calls failed. evaluate() must be called with a
    RunConfig that keeps concurrency low and retries patiently on 429s."""
    import pandas as pd

    mock_result = MagicMock()
    mock_result.to_pandas.return_value = pd.DataFrame({"faithfulness": [0.9]})
    mock_evaluate = MagicMock(return_value=mock_result)
    mock_ragas = MagicMock()
    mock_ragas.evaluate = mock_evaluate

    mock_run_config_cls = MagicMock()
    mock_dataset_cls = MagicMock()
    mock_dataset_cls.from_dict.return_value = MagicMock()

    with patch.dict(
        sys.modules,
        {
            "ragas": mock_ragas,
            "ragas.metrics": MagicMock(),
            "ragas.run_config": MagicMock(RunConfig=mock_run_config_cls),
            "datasets": MagicMock(Dataset=mock_dataset_cls),
            "langchain_aws": MagicMock(),
        },
    ):
        import importlib

        import evals.metrics.ragas_metrics as rm
        importlib.reload(rm)

        with patch.object(rm, "build_ragas_config", return_value=(MagicMock(), MagicMock())):
            with patch("datasets.Dataset", mock_dataset_cls):
                rm.score_dataset(
                    questions=["q"], answers=["a"], contexts=[["c"]], ground_truths=["g"]
                )

    assert mock_run_config_cls.called, "RunConfig was never constructed"
    _, kwargs = mock_run_config_cls.call_args
    assert kwargs.get("max_workers", 16) <= 4, (
        f"max_workers={kwargs.get('max_workers')} still exceeds the TPM budget"
    )

    eval_kwargs = mock_evaluate.call_args.kwargs
    assert "run_config" in eval_kwargs, "evaluate() was not given the throttled run_config"
