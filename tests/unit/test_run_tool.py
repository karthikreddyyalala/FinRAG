from unittest.mock import MagicMock, patch

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from server.mcp_tools.common import Deps, run_tool
from server.rate_limit import RateLimited


def _deps(dynamodb):
    return Deps(MagicMock(), MagicMock(), MagicMock(), dynamodb)


def test_rate_limited_call_becomes_a_tool_error_with_retry_time():
    with patch("server.mcp_tools.common.check_rate_limit", side_effect=RateLimited(42)):
        with pytest.raises(ToolError, match="Try again in 42 seconds"):
            run_tool(lambda: _deps(MagicMock()), "search_sec_filings", {}, lambda d: {})


def test_cache_hit_skips_the_work():
    work = MagicMock()
    with (
        patch("server.mcp_tools.common.check_rate_limit"),
        patch("server.mcp_tools.common.get_cached", return_value={"passages": []}),
    ):
        result = run_tool(lambda: _deps(MagicMock()), "t", {}, work, cache=True)
    assert result == {"passages": []}
    work.assert_not_called()


def test_cache_miss_runs_the_work_and_stores_it():
    with (
        patch("server.mcp_tools.common.check_rate_limit"),
        patch("server.mcp_tools.common.get_cached", return_value=None),
        patch("server.mcp_tools.common.put_cached") as put,
    ):
        result = run_tool(lambda: _deps(MagicMock()), "t", {"q": 1}, lambda d: {"x": 1},
                          cache=True)
    assert result == {"x": 1}
    assert put.call_args.args[-1] == {"x": 1}


def test_every_call_is_logged_even_when_the_work_fails():
    with (
        patch("server.mcp_tools.common.log_call") as log,
        pytest.raises(ToolError),
    ):
        run_tool(lambda: _deps(None), "t", {}, MagicMock(side_effect=ToolError("bad input")))
    assert log.call_args.kwargs["error"] == "ToolError: bad input"
