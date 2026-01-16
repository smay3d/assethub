from __future__ import annotations

import re

from assethub.core.utils.app_log import AppLog


def test_app_log_formats_lines_with_timestamp_and_level() -> None:
    log = AppLog(max_lines=10)
    log.info("hello")
    lines = log.snapshot_lines()
    assert len(lines) == 1
    # Example: "12:34:56 INFO  hello"
    assert re.match(r"^\d{2}:\d{2}:\d{2} INFO\s+hello$", lines[0]) is not None


def test_app_log_caps_memory_to_max_lines() -> None:
    log = AppLog(max_lines=5)
    for i in range(20):
        log.warn(f"m{i}")
    lines = log.snapshot_lines()
    assert len(lines) == 5
    # Should retain the most recent entries.
    assert any("m19" in ln for ln in lines)
    assert all("m0" not in ln for ln in lines)


def test_app_log_sink_is_called_with_formatted_line() -> None:
    got: list[str] = []

    def sink(line: str) -> None:
        got.append(line)

    log = AppLog(max_lines=10)
    log.set_sink(sink)
    log.error("boom")

    assert len(got) == 1
    assert "ERROR" in got[0]
    assert "boom" in got[0]
