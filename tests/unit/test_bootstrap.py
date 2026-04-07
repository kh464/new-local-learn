from pathlib import Path

from app.core.config import Settings
from app.core.models import TaskStage, TaskState, TaskStatus
from app.storage.artifacts import ArtifactPaths


def test_settings_and_models_bootstrap(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("ALLOWED_GITHUB_HOSTS", "github.com,github.internal")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.example.com,https://admin.example.com")
    monkeypatch.setenv("API_KEYS", "alpha,beta")
    monkeypatch.setenv("API_KEY_RECORDS", "ci:ci-secret:analyze:create|tasks:read;ops:ops-secret:metrics:read|artifacts:read")
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://issuer.example.com/realms/local")
    monkeypatch.setenv("OIDC_AUDIENCE", "local-learn-api")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://issuer.example.com/realms/local/protocol/openid-connect/certs")
    monkeypatch.setenv("OIDC_SCOPE_CLAIM", "scope")
    monkeypatch.setenv("OIDC_SUBJECT_CLAIM", "preferred_username")

    settings = Settings()
    status = TaskStatus(task_id="task-1", state=TaskState.RUNNING, stage=TaskStage.FETCH_REPO, progress=10)
    paths = ArtifactPaths(base_dir=settings.artifacts_dir, task_id="task-1")

    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.clone_timeout_seconds == 60
    assert settings.stream_poll_interval_seconds == 0.1
    assert settings.worker_job_timeout_seconds == 300
    assert settings.worker_max_jobs == 10
    assert settings.max_total_bytes == 2_000_000
    assert settings.rate_limit_window_seconds == 60
    assert settings.rate_limit_max_requests == 10
    assert settings.task_ttl_seconds == 86400
    assert settings.artifact_ttl_seconds == 86400
    assert settings.llm_enabled is True
    assert settings.llm_config_path == Path("config/llm.yaml")
    assert settings.llm_profile is None
    assert settings.api_keys == ("alpha", "beta")
    assert settings.api_key_records == (
        "ci:ci-secret:analyze:create|tasks:read",
        "ops:ops-secret:metrics:read|artifacts:read",
    )
    assert settings.oidc_issuer_url == "https://issuer.example.com/realms/local"
    assert settings.oidc_audience == "local-learn-api"
    assert settings.oidc_jwks_url == "https://issuer.example.com/realms/local/protocol/openid-connect/certs"
    assert settings.oidc_scope_claim == "scope"
    assert settings.oidc_subject_claim == "preferred_username"
    assert settings.allowed_github_hosts == ("github.com", "github.internal")
    assert settings.cors_allowed_origins == ("https://app.example.com", "https://admin.example.com")
    assert status.stage is TaskStage.FETCH_REPO
    assert paths.markdown_path.name == "result.md"
