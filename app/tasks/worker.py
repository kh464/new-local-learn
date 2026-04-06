from arq.connections import RedisSettings

from app.core.config import Settings
from app.tasks.jobs import run_analysis_job

settings = Settings()


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [run_analysis_job]
