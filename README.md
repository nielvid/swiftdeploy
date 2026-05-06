# SwiftDeploy

A declarative deployment tool that generates Nginx and Docker Compose configs from a single `manifest.yaml`, manages the container lifecycle, enforces policy before acting, and audits everything it does.

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
./swiftdeploy deploy    # policy check → bring up stack → wait for health
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

Queries OPA infrastructure policy, then runs `init`, brings up the full stack, and polls `GET /healthz` until healthy or 60s timeout.

The deploy is blocked if disk free < 10GB or CPU load > 2.0.

```bash
./swiftdeploy deploy
```

Expected output:
```
==> Checking infrastructure policy
  disk_free=107GB  cpu_load=0.8
allow=true
  [PASS] Infrastructure policy
==> Initialising
  generated nginx.conf
  generated docker-compose.yml
==> Starting stack
  [+] Running 4/4
==> Waiting for health (timeout 60s)
  [OK] Stack is healthy
```

Blocked output (disk full example):
```
==> Checking infrastructure policy
  disk_free=2GB  cpu_load=0.8
allow=false
  [DENY] Disk free 2GB is below minimum 10GB
  [BLOCKED] Deployment denied by infrastructure policy
```

---

### `./swiftdeploy promote [canary|stable]`

Queries OPA canary safety policy (scrapes `/metrics` to compute error rate and P99 latency), then switches deployment mode with a rolling restart of the app container only.

The promotion is blocked if error rate > 1% or P99 latency > 500ms.

```bash
./swiftdeploy promote canary
./swiftdeploy promote stable
```

Expected output (canary):
```
==> Checking canary safety policy
  error_rate=0.00%  p99=12ms
allow=true
  [PASS] Canary safety policy
==> Promoting to canary
  manifest.yaml updated: mode=canary
  generated nginx.conf
  generated docker-compose.yml
==> Waiting for service to come back
  [OK] Service is healthy
  [OK] X-Mode: canary confirmed
```

Blocked output (unhealthy canary):
```
==> Checking canary safety policy
  error_rate=48.20%  p99=45ms
allow=false
  [DENY] Error rate 48% exceeds maximum 1%
  [BLOCKED] Promotion denied by canary safety policy
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
  [+] Running 4/4
==> Done
```

---

### `./swiftdeploy status`

Live-refreshing terminal dashboard (refreshes every 5s). Scrapes `/metrics`, computes real-time req/s and P99 latency, queries both OPA policies, and appends every scrape to `history.jsonl`.

```bash
./swiftdeploy status
```

Example output:
```
==> SwiftDeploy Status  [2026-05-06T20:10:00Z]  mode=canary

  Throughput : 7.3 req/s
  P99 Latency: 45ms
  Error Rate : 0.00%
  Uptime     : 700s
  Chaos      : none

  Policy Compliance:
    [PASS] infra   — disk=107GB cpu=0.8
    [PASS] canary  — error_rate=0.00% p99=45ms

  (Ctrl+C to exit)
```

---

### `./swiftdeploy audit`

Parses `history.jsonl` and generates `audit_report.md` with four sections: timeline, policy violations, mode changes, and chaos events.

```bash
./swiftdeploy audit
```

Expected output:
```
==> audit_report.md generated
    42 snapshots | 2 violations | 3 mode changes | 1 chaos events
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Welcome message with mode, version, timestamp |
| GET | `/healthz` | Liveness check with process uptime |
| GET | `/metrics` | Prometheus text format metrics |
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

### `GET /metrics`

```bash
curl http://localhost:8080/metrics
```

```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",path="/",status_code="200"} 42
# HELP http_request_duration_seconds Request latency histogram
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{le="0.005"} 40
...
# HELP app_uptime_seconds Seconds since process start
# TYPE app_uptime_seconds gauge
app_uptime_seconds 3600.42
# HELP app_mode Current deployment mode (0=stable 1=canary)
# TYPE app_mode gauge
app_mode 0
# HELP chaos_active Active chaos state (0=none 1=slow 2=error)
# TYPE chaos_active gauge
chaos_active 0
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

## OPA Policies

Policies live in `policies/` and are loaded by the OPA sidecar at startup. Thresholds are in `data.json` files — never hardcoded in Rego.

### Infrastructure Policy (`policies/infra/`)

Evaluated before every `deploy`. Input: host disk and CPU stats.

| File | Purpose |
|------|---------|
| `policy.rego` | Deny if disk free < threshold or CPU load > threshold |
| `data.json` | `{ "min_disk_gb": 10, "max_cpu_load": 2.0 }` |

### Canary Safety Policy (`policies/canary/`)

Evaluated before every `promote`. Input: error rate and P99 latency scraped from `/metrics`.

| File | Purpose |
|------|---------|
| `policy.rego` | Deny if error rate > threshold or P99 > threshold |
| `data.json` | `{ "max_error_rate": 0.01, "max_p99_ms": 500 }` |

To change a threshold, edit the relevant `data.json` and restart OPA:

```bash
docker restart swiftdeploy-opa
```

---

## Project Structure

```
.
├── manifest.yaml                   # Single source of truth
├── swiftdeploy                     # CLI executable
├── Dockerfile                      # App image
├── app/
│   └── main.py                     # Python HTTP service (stdlib only)
├── templates/
│   ├── nginx.conf.j2               # Nginx config template
│   └── docker-compose.yml.j2       # Docker Compose template
├── policies/
│   ├── infra/
│   │   ├── policy.rego             # Infrastructure policy
│   │   └── data.json               # Disk/CPU thresholds
│   └── canary/
│       ├── policy.rego             # Canary safety policy
│       └── data.json               # Error rate/P99 thresholds
├── nginx.conf                      # Generated by init
├── docker-compose.yml              # Generated by init
├── audit_report.md                 # Generated by audit
├── implementation.md               # Stage 4A build plan
├── implementation_b.md             # Stage 4B build plan
├── blog.md                         # Technical blog post
└── README.md
```

---

## Security

- App container runs as non-root user (`uid 1001`)
- All Linux capabilities dropped (`cap_drop: ALL`)
- Service port never exposed directly — all traffic routes through Nginx
- OPA API bound to `127.0.0.1:8181` only — not reachable via the Nginx port
- OPA runs on an isolated `opa-net` network with no connection to the app/nginx network
- Images based on `python:3.12-alpine` (well under 300MB)
