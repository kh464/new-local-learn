async def test_analyze_endpoint_returns_urls(api_client, monkeypatch):
    async def fake_enqueue(task_id: str, github_url: str) -> str:
        return task_id

    monkeypatch.setattr("app.api.routes.tasks.enqueue_analysis", fake_enqueue)
    response = await api_client.post(
        "/api/v1/analyze",
        json={"github_url": "https://github.com/octocat/Hello-World"},
    )
    assert response.status_code == 202
    assert response.json()["status_url"].endswith(response.json()["task_id"])
