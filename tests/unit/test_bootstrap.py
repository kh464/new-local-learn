from app.core.config import Settings
from app.core.models import TaskStage, TaskState, TaskStatus
from app.storage.artifacts import ArtifactPaths


def test_settings_and_models_bootstrap(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "workspace"))

    settings = Settings()
    status = TaskStatus(task_id="task-1", state=TaskState.RUNNING, stage=TaskStage.FETCH_REPO, progress=10)
    paths = ArtifactPaths(base_dir=settings.artifacts_dir, task_id="task-1")

    assert settings.redis_url == "redis://localhost:6379/0"
    assert status.stage is TaskStage.FETCH_REPO
    assert paths.markdown_path.name == "result.md"
