"""Test that generate_answer works via OpenAI when Bedrock is unavailable."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_generate_answer_returns_nonempty_string():
    """generate_answer must return a non-empty string using OpenAI fallback."""
    from server.generation.answer_generator import generate_answer

    # Fake bedrock client that always raises ThrottlingException
    class FakeBedrock:
        def converse(self, **kwargs):
            raise Exception("ThrottlingException")

    chunks = [
        {
            "text": "Apple total revenue in FY2022 was $394.3 billion.",
            "ticker": "AAPL",
            "filing_type": "10-K",
            "period": "FY2022",
            "page_number": 1,
        }
    ]

    result = generate_answer(FakeBedrock(), "What was Apple revenue in FY2022?", chunks)
    assert isinstance(result, str), "result must be a string"
    assert len(result) > 20, f"result too short: {result!r}"
    print(f"PASS — answer length {len(result)} chars")
    print(f"Answer preview: {result[:200]}")


if __name__ == "__main__":
    test_generate_answer_returns_nonempty_string()
