from dataclasses import dataclass

from app.services.report_builder import build_report


@dataclass
class A:
    category: str
    title: str
    project: str | None = None


def test_full_report_format() -> None:
    body = build_report(
        [
            A("work", "API 実装", "nippo"),
            A("meeting", "朝会"),
            A("work", "資料作成"),
            A("work", "画面実装", "nippo"),
            A("tech_learning", "FastAPI の依存性注入"),
            A("business_learning", "報告は結論から"),
        ],
        "楽しかった",
    )
    assert body == (
        "今日やったこと\n"
        "- API 実装\n"
        "- 画面実装\n"
        "- 【会議】朝会\n"
        "- 資料作成\n"
        "\n"
        "技術的に学んだこと\n"
        "- FastAPI の依存性注入\n"
        "\n"
        "ビジネス・ヒューマンスキルで学んだこと\n"
        "- 報告は結論から\n"
        "\n"
        "今日の一言\n"
        "楽しかった\n"
    )


def test_empty_sections_are_marked() -> None:
    body = build_report([], "  ")
    assert body.count("特になし") == 4


def test_project_named_like_meeting_is_not_merged_into_meetings() -> None:
    body = build_report([A("meeting", "定例"), A("work", "作業", "会議")], "")
    assert "- 【会議】定例\n- 作業" in body
