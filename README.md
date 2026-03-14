# AI-generated-imagesNvideos MVP (PR#1)

Project skeleton for an internal AI image/video mid-platform MVP using FastAPI + Celery + Redis + SQLite + Nginx (Basic Auth) + local disk storage.

## Project structure

- `backend/` - FastAPI app (`/health`, `/api/tasks`, download endpoints)
- `worker/` - Celery worker code for mock generation pipeline
- `nginx/` - reverse proxy + basic auth config
- `data/` - persistent local storage (`uploads/`, `outputs/`, `zips/`, `logs/`, `db/`)
- `docker-compose.yml`
- `.env.example`

## Prerequisites

- Docker Desktop (Windows local dev) or Docker Engine (Ubuntu 22.04)
- Docker Compose v2

## Run

1. Copy env file:

```bash
cp .env.example .env
```

2. Start services:

```bash
docker compose up --build
```

3. Verify health (Basic Auth required):

```bash
curl -u admin:admin123 http://localhost:8080/health
```

Expected:

```json
{"status":"ok"}
```

## API examples

### Mock image task

### Create task (google image)

```bash
curl -u admin:admin123 -X POST http://localhost:8080/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "type": "image",
    "provider": "google_image",
    "request_text": "a cute cat",
    "n_outputs": 1,
    "params": {
      "size": "1024x1024",
      "style": "poster",
      "seed": 12345
    }
  }'
```

### Prompt optimizer task

```bash
curl -u admin:admin123 -X POST http://localhost:8080/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "type": "prompt",
    "provider": "prompt_optimizer",
    "request_text": "a cinematic sunset city skyline",
    "params": {
      "style": "cinematic"
    }
  }'
```

### List tasks (latest first)

```bash
curl -u admin:admin123 http://localhost:8080/api/tasks
```

### Get task detail (with outputs)

```bash
curl -u admin:admin123 http://localhost:8080/api/tasks/<task_id>
```

### Download one output

```bash
curl -u admin:admin123 -L \
  http://localhost:8080/api/tasks/<task_id>/outputs/<output_id> \
  --output output.png
```

### Download zip

```bash
curl -u admin:admin123 -L \
  http://localhost:8080/api/tasks/<task_id>/download.zip \
  --output task_outputs.zip
```

## Verification flow

1. Create a task (`status=queued`).
2. Wait ~3-5 seconds.
3. Query task detail and confirm status becomes `done`.
4. Confirm output files are present under `data/outputs/<task_id>/`.
5. Confirm zip exists under `data/zips/<task_id>.zip` after first zip download.

## Troubleshooting

- **Port 8080 already in use**: change nginx mapping in `docker-compose.yml` (e.g. `8081:8080`).
- **Windows file permission/path issues**: ensure repo is under a Docker Desktop shared drive and restart Docker Desktop.
- **Worker not processing tasks**: check `docker compose logs worker` and `docker compose logs redis`.
- **SQLite locked errors**: avoid heavy concurrent writes in MVP; restart stack if needed.
- **401 Unauthorized**: include `-u admin:admin123` in curl commands.

## Non-goals in PR#1

- No Gemini/Veo integration yet.
- No frontend UI.
- No user/account system.
