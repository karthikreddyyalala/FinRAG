"""verify_figures: which figures in a draft answer the cited passages actually contain."""
from __future__ import annotations

from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from server.mcp_tools.common import READ_ONLY, GetDeps, check_length, run_tool
from server.retrieval.numerical_verifier import check_figures

MAX_PASSAGE_IDS = 20
MAX_ANSWER_CHARS = 20_000


def register_verify_figures_tool(mcp: MCPServer, get_deps: GetDeps) -> None:
    """Register verify_figures on an MCPServer."""

    @mcp.tool(title="Verify figures", annotations=READ_ONLY)
    def verify_figures(answer: str, passage_ids: list[str]) -> dict[str, Any]:
        """Check that every figure in a draft answer appears in the passages it cites.

        Call this before giving a final answer that contains numbers. Fix or flag
        anything in not_found. Matching is by value: "(1,577)" in a cash flow
        table grounds "$1,577 million", but "$1,234.56" does not ground "$1,234".

        Args:
            answer: The draft answer text.
            passage_ids: The id of each passage the answer relied on (1 to 20).
        """
        check_length("answer", answer, MAX_ANSWER_CHARS)
        ids = list(dict.fromkeys(passage_ids))
        if not 1 <= len(ids) <= MAX_PASSAGE_IDS:
            raise ToolError(f"Pass 1 to {MAX_PASSAGE_IDS} passage ids.")

        def work(deps):
            found = deps.keyword_index.get_by_ids(ids)
            grounded, not_found = check_figures(answer, [c["text"] for c in found.values()])
            return {"grounded": grounded, "not_found": not_found,
                    "unknown_ids": [i for i in ids if i not in found],
                    "checked_against": len(found)}

        return run_tool(get_deps, "verify_figures", {"answer": answer, "passage_ids": ids}, work)
