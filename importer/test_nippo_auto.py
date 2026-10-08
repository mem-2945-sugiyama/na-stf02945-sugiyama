"""nippo_auto のテスト。実行: uv run --with pytest --with truststore pytest importer"""

import datetime as dt
import os
import stat
from pathlib import Path

import pytest

import nippo_auto

DAY = dt.date(2026, 10, 7)


def _activity(source: str, title: str, **extra) -> dict:
    return {"source": source, "title": title, "category": "work", "project": None} | extra


def test_format_materials_groups_by_source_and_marks_manual_category() -> None:
    text = nippo_auto.format_materials(
        [
            _activity("claude", "API 実装", project="nippo", detail="依頼:\n- 作って"),
            _activity("manual", "報告は結論から", category="business_learning"),
            _activity("calendar", "朝会", category="meeting"),
        ]
    )
    assert "## Claude Code での作業\n- API 実装\n  プロジェクト: nippo\n  依頼:\n  - 作って" in text
    assert "## 手入力メモ\n- 報告は結論から(分類: ビジネスの学び)" in text
    assert "## カレンダーの予定\n- 朝会" in text


def test_build_prompt_includes_comment_or_placeholder() -> None:
    assert "(なし)" in nippo_auto.build_prompt(DAY, [], "  ")
    prompt = nippo_auto.build_prompt(DAY, [], "楽しかった")
    assert "# 今日の一言(本人の入力)\n楽しかった" in prompt
    assert "(記録なし)" in prompt


def test_extension_version_sorts_numerically() -> None:
    paths = [
        "/x/anthropic.claude-code-2.1.99-darwin-x64/resources/native-binary/claude",
        "/x/anthropic.claude-code-2.1.281-darwin-x64/resources/native-binary/claude",
    ]
    assert max(paths, key=nippo_auto._extension_version) == paths[1]


def _fake_claude(tmp_path: Path, output: str, code: int = 0) -> str:
    script = tmp_path / "claude"
    script.write_text(f"#!/bin/sh\ncat > /dev/null\nprintf '%s' '{output}'\nexit {code}\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def test_run_claude_accepts_report_format(tmp_path: Path) -> None:
    body = "\n\n".join(f"{h}\n- x" for h in nippo_auto.HEADINGS)
    assert nippo_auto.run_claude(_fake_claude(tmp_path, body), "p", "sonnet") == body + "\n"


def test_run_claude_rejects_unexpected_output(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="日報の形式"):
        nippo_auto.run_claude(_fake_claude(tmp_path, "はい、承知しました"), "p", "sonnet")


def test_run_claude_reports_failure(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="実行に失敗"):
        nippo_auto.run_claude(_fake_claude(tmp_path, "", code=1), "p", "sonnet")


def test_find_calendar_export_picks_latest_of_the_day(tmp_path: Path) -> None:
    def touch(name: str, when: dt.datetime) -> Path:
        path = tmp_path / name
        path.write_bytes(b"x")
        os.utime(path, (when.timestamp(), when.timestamp()))
        return path

    jst = nippo_auto.JST
    touch("old.ical.zip", dt.datetime(2026, 10, 6, 18, tzinfo=jst))
    touch("morning.ical.zip", dt.datetime(2026, 10, 7, 9, tzinfo=jst))
    latest = touch("evening.ical.zip", dt.datetime(2026, 10, 7, 17, tzinfo=jst))
    touch("unrelated.zip", dt.datetime(2026, 10, 7, 18, tzinfo=jst))

    patterns = list(nippo_auto.DEFAULT_EXPORT_PATTERNS)
    assert nippo_auto.find_calendar_export(tmp_path, DAY, patterns) == latest
    # 過去日を指定して後日実行しても、その日以降のエクスポートを使う
    assert nippo_auto.find_calendar_export(tmp_path, dt.date(2026, 10, 1), patterns) == latest
    assert nippo_auto.find_calendar_export(tmp_path, dt.date(2026, 10, 8), patterns) is None

    # 後から保存された招待状(単体の .ics)より、エクスポートの zip を優先する
    touch("invite.ics", dt.datetime(2026, 10, 7, 19, tzinfo=jst))
    assert nippo_auto.find_calendar_export(tmp_path, DAY, patterns) == latest
