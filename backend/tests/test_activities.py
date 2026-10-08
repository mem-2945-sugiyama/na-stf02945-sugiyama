from fastapi.testclient import TestClient

DAY = "2026-10-07"


def _create(client: TestClient, **overrides) -> dict:
    payload = {"date": DAY, "category": "work", "title": "API 実装"} | overrides
    res = client.post("/api/activities", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def _imported(external_id: str, title: str, **overrides) -> dict:
    return {
        "date": DAY,
        "category": "work",
        "title": title,
        "project": "nippo",
        "started_at": "2026-10-07T10:00:00+09:00",
        "source": "claude",
        "external_id": external_id,
    } | overrides


def test_health(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}


def test_create_and_list(client: TestClient) -> None:
    created = _create(client, project="nippo")
    assert created["source"] == "manual"
    assert created["started_at"]

    listed = client.get("/api/activities", params={"date": DAY}).json()
    assert [a["id"] for a in listed] == [created["id"]]
    assert client.get("/api/activities", params={"date": "2026-10-08"}).json() == []


def test_create_rejects_empty_title_and_unknown_category(client: TestClient) -> None:
    payload = {"date": DAY, "category": "work", "title": ""}
    assert client.post("/api/activities", json=payload).status_code == 422
    payload = {"date": DAY, "category": "unknown", "title": "x"}
    assert client.post("/api/activities", json=payload).status_code == 422


def test_patch_updates_only_sent_fields(client: TestClient) -> None:
    created = _create(client, project="nippo", detail="詳細")
    res = client.patch(f"/api/activities/{created['id']}", json={"category": "tech_learning"})
    assert res.status_code == 200
    body = res.json()
    assert body["category"] == "tech_learning"
    assert body["project"] == "nippo"
    assert body["detail"] == "詳細"


def test_patch_allows_clearing_optional_but_not_required(client: TestClient) -> None:
    created = _create(client, project="nippo")
    res = client.patch(f"/api/activities/{created['id']}", json={"project": None})
    assert res.json()["project"] is None
    res = client.patch(f"/api/activities/{created['id']}", json={"title": None})
    assert res.status_code == 422


def test_patch_and_delete_404(client: TestClient) -> None:
    assert client.patch("/api/activities/999", json={"title": "x"}).status_code == 404
    assert client.delete("/api/activities/999").status_code == 404


def test_delete(client: TestClient) -> None:
    created = _create(client)
    assert client.delete(f"/api/activities/{created['id']}").status_code == 204
    assert client.get("/api/activities", params={"date": DAY}).json() == []


def test_bulk_is_idempotent_and_keeps_user_category(client: TestClient) -> None:
    first = client.post("/api/activities/bulk", json=[_imported("s1", "初回")])
    assert first.json() == {"created": 1, "updated": 0}

    # 取り込み後にユーザーが分類を付け替えた想定
    activity = client.get("/api/activities", params={"date": DAY}).json()[0]
    client.patch(f"/api/activities/{activity['id']}", json={"category": "tech_learning"})

    second = client.post("/api/activities/bulk", json=[_imported("s1", "更新後")])
    assert second.json() == {"created": 0, "updated": 1}

    listed = client.get("/api/activities", params={"date": DAY}).json()
    assert len(listed) == 1
    assert listed[0]["title"] == "更新後"
    assert listed[0]["category"] == "tech_learning"


def test_bulk_handles_duplicate_keys_in_one_request(client: TestClient) -> None:
    res = client.post("/api/activities/bulk", json=[_imported("s1", "a"), _imported("s1", "b")])
    assert res.json() == {"created": 1, "updated": 1}
    assert client.get("/api/activities", params={"date": DAY}).json()[0]["title"] == "b"


def test_bulk_accepts_slack_paste(client: TestClient) -> None:
    item = _imported("paste-1", "Slack の投稿(貼り付け)", source="slack", detail="本文")
    assert client.post("/api/activities/bulk", json=[item]).json() == {"created": 1, "updated": 0}


def test_bulk_rejects_manual_source(client: TestClient) -> None:
    res = client.post("/api/activities/bulk", json=[_imported("s1", "a", source="manual")])
    assert res.status_code == 422


def test_report_draft_save_and_get(client: TestClient) -> None:
    _create(client, title="画面実装", project="nippo")
    _create(client, title="SQLAlchemy 2 の型付きマッピング", category="tech_learning")

    assert client.get(f"/api/reports/{DAY}").status_code == 404

    draft = client.get(f"/api/reports/{DAY}/draft", params={"comment": "順調"}).json()
    assert "- 画面実装" in draft["body"]
    assert "- SQLAlchemy 2 の型付きマッピング" in draft["body"]
    assert draft["body"].rstrip().endswith("今日の一言\n順調")

    saved = client.put(f"/api/reports/{DAY}", json={"body": "編集後", "comment": "順調"})
    assert saved.status_code == 200
    client.put(f"/api/reports/{DAY}", json={"body": "再編集", "comment": "x"})
    got = client.get(f"/api/reports/{DAY}").json()
    assert (got["body"], got["comment"]) == ("再編集", "x")


def test_report_comment_only_keeps_body(client: TestClient) -> None:
    created = client.put(f"/api/reports/{DAY}", json={"comment": "先に一言"}).json()
    assert (created["body"], created["comment"]) == ("", "先に一言")
    client.put(f"/api/reports/{DAY}", json={"body": "AI の本文", "comment": "先に一言"})
    got = client.put(f"/api/reports/{DAY}", json={"comment": "変更"}).json()
    assert (got["body"], got["comment"]) == ("AI の本文", "変更")
