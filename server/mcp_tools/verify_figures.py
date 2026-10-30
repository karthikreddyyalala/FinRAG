"""verify_figures: which figures in a draft answer the cited passages and facts contain."""
from __future__ import annotations

from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from server.mcp_tools.common import READ_ONLY, GetDeps, check_length, run_tool
from server.retrieval.numerical_verifier import (
    check_figures,
    check_figures_against_values,
    extract_numbers,
)
from server.retrieval.xbrl_facts import value_for_id

MAX_PASSAGE_IDS = 20
MAX_ANSWER_CHARS = 20_000


def register_verify_figures_tool(mcp: MCPServer, get_deps: GetDeps) -> None:
    """Register verify_figures on an MCPServer."""

    @mcp.tool(title="Verify figures", annotations=READ_ONLY)
    def verify_figures(answer: str, passage_ids: list[str]) -> dict[str, Any]:
        """Check the figures in a draft answer against the passages and figures it cites.

        Call this before giving a final answer that contains numbers. Fix or flag
        anything in not_found. It checks dollar amounts ("$1,577 million"),
        percentages ("12.5%") and comma-grouped numbers ("1,577"); other numbers,
        such as "1577" or a year, are not checked.

        Against a passage, matching is by value as written, with no unit conversion:
        "(1,577)" grounds "$1,577 million" but not "$1.58 billion". Against a figure
        id from get_company_financials ("xbrl:..."), units convert and rounding to
        the precision written is accepted: 33,723,297,000 grounds "$33.7 billion".
        A computed ratio or percentage is never grounded; show its inputs instead.
        unknown_ids lists ids that matched nothing.

        Args:
            answer: The draft answer text.
            passage_ids: Ids of the passages and figures the answer relied on (1 to 20).
        """
        check_length("answer", answer, MAX_ANSWER_CHARS)
        if len(passage_ids) > MAX_PASSAGE_IDS:
            raise ToolError(f"Pass 1 to {MAX_PASSAGE_IDS} passage ids.")
        if any(len(i) > 100 for i in passage_ids):
            raise ToolError("passage id is too long.")
        ids = list(dict.fromkeys(passage_ids))
        if not ids:
            raise ToolError(f"Pass 1 to {MAX_PASSAGE_IDS} passage ids.")

        def work(deps):
            fact_ids = [i for i in ids if i.startswith("xbrl:")]
            found = deps.keyword_index.get_by_ids([i for i in ids if i not in fact_ids])
            facts = {i: v for i in fact_ids if (v := value_for_id(i))}
            ok = set(check_figures(answer, [c["text"] for c in found.values()])[0])
            if facts:
                ok |= set(check_figures_against_values(answer, [v for v, _ in facts.values()])[0])
            figures = extract_numbers(answer)
            return {"grounded": [f for f in figures if f in ok],
                    "not_found": [f for f in figures if f not in ok],
                    "unknown_ids": [i for i in ids if i not in found and i not in facts],
                    "checked_against": len(found) + len(facts)}

        return run_tool(
            get_deps, "verify_figures",
            {"answer_chars": len(answer), "passage_ids": ids}, work,
        )
