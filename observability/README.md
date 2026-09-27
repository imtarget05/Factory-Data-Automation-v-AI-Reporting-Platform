# Observability - Factory Data Automation

Self-contained Prometheus + Grafana + Alertmanager stack for this repo. It lives
here rather than in a shared folder, so cloning **this** repository is enough to
see the whole runtime picture - which is what a reviewer, a demo or a debugging
session actually needs.

## Quickstart

```bash
cd Factory-Data-Automation-v-AI-Reporting-Platform/observability
docker compose up -d
docker compose config                     # validate without starting
```

| Service | Port | URL |
|---|---|---|
| Prometheus | 9104 | http://localhost:9104 (`Status -> Targets`) |
| Grafana | 3204 | http://localhost:3204 (admin / `$GF_SECURITY_ADMIN_PASSWORD`, default `admin`) |
| Alertmanager | 9304 | http://localhost:9304 |

Reload a config change without a restart:

```bash
curl -XPOST http://localhost:9104/-/reload
```

## Scrape targets

| Job | Metrics path | Port | Service |
|---|---|---|---|
| `llm-gateway` | `/metrics` | 8787 | vendored `llm-gateway/` |
| `factory` | `/metrics` | 8002 | Factory Data Automation |

## Dashboards

- `project-factory.json` - Factory Data - data-loaded flag, active alerts, per-KPI values
- `golden-signals.json` - Golden signals - QPS / error rate / P95 / saturation per scrape job
- `llm-platform.json` - LLM platform - traffic, latency, token usage, cost governance

## Metrics this repo exposes

| Endpoint | Service | Series |
|---|---|---|
| `GET /metrics` | FastAPI (`app/api/main.py`) | `factory_data_up`, `factory_alerts_active`, `factory_kpi_value{kpi}` |
| `GET /metrics` | llm-gateway (vendored) | `llm_requests_total`, `llm_latency_seconds` |

`factory_kpi_value` carries one series per KPI label so a dashboard shows KPI drift over
time rather than a single reading. Raw dataset rows are never exported.

## Alerts

`prometheus/alerts.yml` has two groups. `gateway`: upstream down, scrape down, 5xx ratio > 5%, P95 > 2s, circuit breaker open. `services`: any scrape target down for 2m.

## SLOs

`slo.yaml` holds the machine-readable SLI / target / window / error-budget table.

## Operational notes

- Grafana `admin` + a default password is fine for a local demo. For anything
  shared, set `GF_SECURITY_ADMIN_PASSWORD` and keep anonymous access off.
- Every `/metrics` endpoint is aggregate-only and unauthenticated, because a
  Prometheus scraper carries no session cookie. Business detail stays behind the
  existing auth-protected endpoints.
- A target that is not running shows `DOWN`; it never blocks the other jobs.
- Ports are offset per project (Prometheus 9104) so several portfolios can run
  at the same time. Override with `PROMETHEUS_PORT` / `GRAFANA_PORT` /
  `ALERTMANAGER_PORT`.
- Docker is required. CI asserts these configs parse; it does not start the stack.
