# GitHub Tech Doc Generator

Backend-first MVP for generating technical documentation from a GitHub repository.

## Requirements

- Python 3.12+
- Docker Desktop or another Docker runtime

## Install

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Run locally

Start Redis:

```powershell
docker compose up -d redis
```

Start the API:

```powershell
uvicorn app.main:app --reload
```

Start the worker in a second terminal:

```powershell
arq app.tasks.worker.WorkerSettings
```

## Test

```powershell
python -m pytest
```
