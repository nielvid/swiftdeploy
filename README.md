# SwiftDeploy

A declarative deployment tool that generates Nginx and Docker Compose configs from a single `manifest.yaml`, manages the container lifecycle, and keeps your stack running.

---

## Prerequisites

- Docker + Docker Compose v2
- Python 3.10+ with `pyyaml`:
  ```bash
  pip install pyyaml
  ```
- `curl`, `lsof`

---

## Setup

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd stage4
```

### 2. Make the CLI executable

```bash
chmod +x swiftdeploy
```

### 3. Build the app image

The image must be built before running any subcommand. The tag must match `services.image` in `manifest.yaml`.

```bash
docker build -t swift-deploy-1-node:latest .
```

### 4. Install Python dependency

```bash
pip install pyyaml
```

---

## Quick Start

```bash
./swiftdeploy init      # generate nginx.conf + docker-compose.yml
./swiftdeploy validate  # run 5 pre-flight checks
./swiftdeploy deploy    # bring up the stack and wait for health
```

---

## manifest.yaml

The only file you edit. All generated configs are derived from it.

```yaml
services:
  image: swift-deploy-1-node:latest
  port: 3000
  mode: stable        # stable | canary
  version: "1.0.0"

nginx:
  image: nginx:latest
  port: 8080
  proxy_timeout: 30

network:
  name: swiftdeploy-net
  driver_type: bridge
```

---

## Subcommands

### `./swiftdeploy init`

Parses `manifest.yaml` and renders:
- `nginx.conf` from `templates/nginx.conf.j2`
- `docker-compose.yml` from `templates/docker-compose.yml.j2`

```bash
./swiftdeploy init
```

Expected output:
```
==> Rendering templates from manifest.yaml
  generated nginx.conf
  generated docker-compose.yml
==> Done
```

---

### `./swiftdeploy validate`

Runs 5 pre-flight checks and prints PASS/FAIL for each. Exits non-zero if any check fails.

1. `manifest.yaml` exists and is valid YAML
2. All required fields are present and non-empty
3. Docker image referenced in manifest exists locally
4. Nginx port is not already bound on the host
5. Generated `nginx.conf` is syntactically valid

```bash
./swiftdeploy validate
```

Expected output:
```
==> Running pre-flight checks
  [PASS] manifest.yaml exists and is valid YAML
  [PASS] All required fields present and non-empty
  [PASS] Docker image 'swift-deploy-1-node:latest' exists locally
  [PASS] Nginx port 8080 is not already bound
  [PASS] nginx.conf is syntactically valid

  Results: 5 passed, 0 failed
```

---

### `./swiftdeploy deploy`

Runs `init`, brings up the full stack, then polls `GET /healthz` every 2 seconds until it responds or 60 seconds elapse.

```bash
./swiftdeploy deploy
```

Expected output:
```
==> Initialising
  generated nginx.conf
  generated docker-compose.yml
==> Starting stack
  [+] Running 3/3
==> Waiting for health (timeout 60s)
  [OK] Stack is healthy
```

---

### `./swiftdeploy promote [canary|stable]`

Switches deployment mode with a rolling restart of the app container only:

1. Updates `mode` in `manifest.yaml` in-place
2. Regenerates `docker-compose.yml` with the new `MODE` env var
3. Restarts only the app container (`--force-recreate --no-deps`)
4. Confirms the new mode via `/healthz` and `X-Mode` header

```bash
./swiftdeploy promote canary
./swiftdeploy promote stable
```

Expected output (canary):
```
==> Promoting to canary
  manifest.yaml updated: mode=canary
  generated nginx.conf
  generated docker-compose.yml
==> Waiting for service to come back
  [OK] X-Mode: canary confirmed
```

Expected output (stable):
```
==> Promoting to stable
  manifest.yaml updated: mode=stable
  generated nginx.conf
  generated docker-compose.yml
==> Waiting for service to come back
  [OK] Promoted to stable
```

---

### `./swiftdeploy teardown [--clean]`

Removes all containers, networks, and volumes.  
`--clean` also deletes the generated `nginx.conf` and `docker-compose.yml`.

```bash
./swiftdeploy teardown
./swiftdeploy teardown --clean
```

Expected output:
```
==> Tearing down stack
  [+] Running 3/3
==> Done
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Welcome message with mode, version, timestamp |
| GET | `/healthz` | Liveness check with process uptime |
| POST | `/chaos` | Simulate degraded behaviour (canary mode only) |

### `GET /`

```bash
curl http://localhost:8080/
```

```json
{
  "message": "Welcome to SwiftDeploy [stable]",
  "mode": "stable",
  "version": "1.0.0",
  "timestamp": "2025-01-01T00:00:00Z"
}
```

### `GET /healthz`

```bash
curl http://localhost:8080/healthz
```

```json
{
  "status": "ok",
  "uptime": 42.3
}
```

### `POST /chaos` (canary mode only)

```bash
# Slow responses — sleep N seconds
curl -X POST http://localhost:8080/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode":"slow","duration":3}'

# Error injection — 500 on ~50% of requests
curl -X POST http://localhost:8080/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode":"error","rate":0.5}'

# Recover — cancel active chaos
curl -X POST http://localhost:8080/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode":"recover"}'
```

Response:
```json
{ "chaos": "slow", "active": true }
```

---

## Project Structure

```
.
├── manifest.yaml              # Single source of truth
├── swiftdeploy                # CLI executable
├── Dockerfile                 # App image
├── app/
│   └── main.py                # Python HTTP service (stdlib only)
├── templates/
│   ├── nginx.conf.j2          # Nginx config template
│   └── docker-compose.yml.j2  # Docker Compose template
├── nginx.conf                 # Generated by init
├── docker-compose.yml         # Generated by init
└── README.md
```

---

## Security

- App container runs as non-root user (`uid 1001`)
- All Linux capabilities dropped (`cap_drop: ALL`)
- Service port never exposed directly — all traffic routes through Nginx
- Images based on `python:3.12-alpine` (well under 300MB)
