"""The app behind a Lambda Function URL: public, lazy, and health-checked.

Probing through Mangum with real Function URL events found two crashes
before the first deploy (421 Invalid Host; LifespanFailure on the second
warm request). Those regressions stay covered here.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

HOST = "abc123.lambda-url.us-east-1.on.aws"
INITIALIZE = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
               "clientInfo": {"name": "test", "version": "0"}},
}
TOOLS_LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
TOOL_NAMES = {"search_sec_filings", "get_company_financials", "compare_companies",
              "get_latest_filing", "list_covered_companies", "verify_figures"}


@pytest.fixture(autouse=True)
def _aws_region():
    with patch.dict("os.environ", {"AWS_DEFAULT_REGION": "us-east-1"}):
        yield


def _event(body, path="/mcp"):
    return {
        "version": "2.0", "rawPath": path, "rawQueryString": "",
        "headers": {"host": HOST, "content-type": "application/json",
                    "accept": "application/json, text/event-stream"},
        "requestContext": {
            "http": {"method": "POST", "path": path, "sourceIp": "1.2.3.4",
                     "protocol": "HTTP/1.1", "userAgent": "test"},
            "domainName": HOST, "stage": "$default",
        },
        "body": json.dumps(body), "isBase64Encoded": False,
    }


@pytest.fixture
def handler():
    """The real handler; dependency loading must not happen for list calls."""
    import server.main as main

    main.get_dependencies.cache_clear()
    with (
        patch.object(main, "load_secrets_from_ssm"),
        patch.object(main, "_build_production_dependencies",
                     side_effect=AssertionError("deps loaded for a list call")),
    ):
        yield main.handler
    main.get_dependencies.cache_clear()


def test_anyone_can_list_the_six_read_only_tools_without_a_token(handler):
    resp = handler(_event(TOOLS_LIST), MagicMock())
    assert resp["statusCode"] == 200, resp["body"][:300]
    tools = json.loads(resp["body"])["result"]["tools"]
    assert {t["name"] for t in tools} == TOOL_NAMES
    assert all(t["annotations"]["readOnlyHint"] for t in tools)


def test_initialize_sends_instructions_that_require_verifying_figures(handler):
    resp = handler(_event(INITIALIZE), MagicMock())
    instructions = json.loads(resp["body"])["result"]["instructions"]
    assert "verify_figures" in instructions and "list_covered_companies" in instructions


def test_warm_lambda_serves_repeated_invocations(handler):
    """The second request to a warm instance used to crash the lifespan."""
    for i in range(3):
        resp = handler(_event(INITIALIZE), MagicMock())
        assert resp["statusCode"] == 200, f"invocation {i + 1}: {resp['body'][:200]}"


def test_no_oauth_discovery_endpoint_so_clients_connect_without_sign_in(handler):
    resp = handler(_event({}, path="/.well-known/oauth-protected-resource"), MagicMock())
    assert resp["statusCode"] == 404


def test_health_check_runs_one_real_retrieval():
    import server.main as main

    with patch.object(main, "load_secrets_from_ssm"), \
         patch.object(main, "get_dependencies", return_value=MagicMock()), \
         patch.object(main, "find_passages", return_value=([{"chunk_id": "a1"}], None)) as fp:
        assert main.handler({"finrag_health_check": True}, MagicMock()) == {
            "ok": True, "passages": 1}
    assert fp.call_args.kwargs["ticker"] == "MMM"


@pytest.mark.parametrize("found", [([], None), ([{"chunk_id": "a1"}], "Keyword search only")])
def test_health_check_fails_loudly_on_no_passages_or_keyword_fallback(found):
    import server.main as main

    with patch.object(main, "load_secrets_from_ssm"), \
         patch.object(main, "get_dependencies", return_value=MagicMock()), \
         patch.object(main, "find_passages", return_value=found), \
         pytest.raises(RuntimeError, match="health check failed"):
        main.handler({"finrag_health_check": True}, MagicMock())


# What clients are told must match what the server does.

def _tool_descriptions(handler):
    resp = handler(_event(TOOLS_LIST), MagicMock())
    return {t["name"]: t["description"] for t in json.loads(resp["body"])["result"]["tools"]}


def test_instructions_state_the_real_company_count_and_citation_format():
    from pathlib import Path

    from server.main import INSTRUCTIONS
    from server.retrieval.evidence import format_citation

    corpus = json.loads((Path(__file__).parents[2] / "dashboard/data/corpus.json").read_text())
    assert f"filings of {corpus['companies']} large companies" in " ".join(INSTRUCTIONS.split())
    # EDGAR filings are HTML, so no chunk has a page number and no citation shows one.
    example = format_citation({"ticker": "MMM", "filing_type": "10-K",
                               "period": "2019-02-07", "page_number": None})
    assert f"e.g. {example}." in INSTRUCTIONS
    assert " p." not in INSTRUCTIONS


def test_verify_figures_description_matches_what_it_checks(handler):
    from server.retrieval.numerical_verifier import check_figures

    description = _tool_descriptions(handler)["verify_figures"]
    # Plain digits are not checked at all; units are not converted.
    assert check_figures("1577", ["(1,577)"]) == ([], [])
    assert '"1577"' in description
    assert check_figures("$1.58 billion", ["(1,577)"]) == ([], ["$1.58 billion"])
    assert '"$1.58 billion"' in description
    assert "unknown_ids" in description


def test_search_fiscal_year_doc_states_its_range_and_window(handler):
    from server.retrieval.query_filters import period_window

    description = _tool_descriptions(handler)["search_sec_filings"]
    assert "1993 to 2100" in description
    assert period_window((2018, 2018)) == ("2018-01-01", "2019-12-31")
    assert "filed in that year or the next" in description
