"""活動の一覧から日報テキストを組み立てる(ルールベース)。

Claude API が使えないため、要約はせずにカテゴリ別の整形だけを行う。
"""

from collections.abc import Sequence
from typing import Protocol

from app.models import Category

EMPTY = "特になし"


class _ActivityLike(Protocol):
    category: str
    project: str | None
    title: str


def build_report(activities: Sequence[_ActivityLike], comment: str) -> str:
    """日報の本文を返す。

    activities は時刻順に並んでいる前提(グループ内の並びにそのまま使う)。
    セクションが空でも見出しは残し「特になし」とする(提出先のフォーマットで見出しを省略しないため)。
    """
    done = _done_lines([a for a in activities if a.category in (Category.WORK, Category.MEETING)])
    tech = [f"- {a.title}" for a in activities if a.category == Category.TECH_LEARNING]
    business = [f"- {a.title}" for a in activities if a.category == Category.BUSINESS_LEARNING]

    sections = [
        ("今日やったこと", done),
        ("技術的に学んだこと", tech),
        ("ビジネス・ヒューマンスキルで学んだこと", business),
        ("今日の一言", [comment.strip()] if comment.strip() else []),
    ]
    return (
        "\n\n".join("\n".join([heading, *(lines or [EMPTY])]) for heading, lines in sections) + "\n"
    )


def _done_lines(activities: Sequence[_ActivityLike]) -> list[str]:
    # 同じプロジェクトの作業を隣接させて読みやすくする(プロジェクト名自体は日報に不要なので出さない)。
    # グループの順は最初に登場した時刻順。会議は【会議】を付けて1か所にまとめる
    groups: dict[str, list[str]] = {}
    for a in activities:
        if a.category == Category.MEETING:
            groups.setdefault("\0meeting", []).append(f"- 【会議】{a.title}")
        else:
            groups.setdefault(a.project or "", []).append(f"- {a.title}")
    return [line for lines in groups.values() for line in lines]
