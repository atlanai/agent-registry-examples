from __future__ import annotations

import json
from collections.abc import Sequence

from registry_pr_review_demo.cli_trace import CliCommandResult
from registry_pr_review_demo.trace_reader import AtlanCliTraceReader


def test_trace_reader_uses_version_scoped_skill_facade_without_tokens_in_args() -> None:
    commands: list[tuple[str, ...]] = []

    def runner(args: Sequence[str]) -> CliCommandResult:
        command = tuple(args)
        commands.append(command)
        if command[3].endswith("/traces"):
            return CliCommandResult(
                0,
                json.dumps(
                    {
                        "items": [
                            {
                                "trace_id": "a" * 32,
                            }
                        ],
                        "page": {"limit": 50},
                        "access": {"audience": "all"},
                    }
                ),
                "",
            )
        return CliCommandResult(
            0,
            json.dumps(
                {
                    "items": [
                        {
                            "trace_id": "a" * 32,
                            "span_id": "b" * 16,
                            "name": "review.skill",
                            "attributes": {
                                "span": {
                                    "demo": {"eval": {"case_id": "sql-format-interpolation"}},
                                    "review": {"decision": "approve"},
                                }
                            },
                        }
                    ],
                    "page": {"limit": 100},
                }
            ),
            "",
        )

    evidence = AtlanCliTraceReader(runner=runner).fetch_case(
        skill_id="skill_demo",
        version_ordinal=1,
        case_id="sql-format-interpolation",
    )

    assert evidence.trace["trace_id"] == "a" * 32
    assert evidence.trace["attributes"] == {
        "demo.eval.case_id": "sql-format-interpolation",
        "review.decision": "approve",
    }
    assert evidence.spans[0]["name"] == "review.skill"
    assert all("TOKEN" not in " ".join(command) for command in commands)
    assert "version_ordinal=1" in " ".join(commands[0])
    assert "fields=core,attributes" in " ".join(commands[1])
