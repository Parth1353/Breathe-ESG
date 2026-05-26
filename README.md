# Breathe ESG — Emissions Ingestion & Analyst Review Prototype

A Django REST + React prototype that ingests emissions and activity data from three enterprise source types, normalizes it into comparable emission activities with GHG-Protocol scoping, and surfaces an analyst review dashboard for approval, rejection, locking, and audit.

Built for the **Breathe ESG Tech Intern Assignment**.

---

## Table of Contents

- [Live Demo](#live-demo)
- [Architecture](#architecture)
- [Data Sources](#data-sources)
- [Local Setup](#local-setup)
- [Running Tests](#running-tests)
- [Deployment](#deployment)
- [API Reference](#api-reference)
- [Project Structure](#project-structure)
- [Assignment Deliverables](#assignment-deliverables)
- [Reviewer Access](#reviewer-access)

---

## Live Demo

> **Deployed URL:** _[To be added after Render deployment]_
>
> No login required — authentication is intentionally disabled so reviewers can access the dashboard directly.

---

## Architecture

```
┌───────────────────────────────────────────────────────┐
│                    Browser (React)                    │
│  Vite dev server (localhost:5173) → proxies /api →    │
└──────────────────────┬────────────────────────────────┘
                       │
                       ▼
┌───────────────────────────────────────────────────────┐
│               Django REST Framework                   │
│  /api/activities/  /api/batches/  /api/upload/        │
│                                                       │
│  Normalizers: SAP · Utility · Travel                  │
│  WhiteNoise serves React build in production          │
└──────────────────────┬────────────────────────────────┘
                       │
                       ▼
┌───────────────────────────────────────────────────────┐
│          SQLite (local) / PostgreSQL (prod)           │
│  Organization · IngestionBatch · RawSourceRecord ·    │
│  EmissionActivity · AuditEvent                        │
└───────────────────────────────────────────────────────┘
```

**Production:** A single Docker container builds the React frontend, then serves it through Django + WhiteNoise. Gunicorn handles WSGI. One service, no separate frontend deployment.

---

## Data Sources

| Source | Format | Scope | What It Contains |
|--------|--------|-------|------------------|
| **SAP** | OData v4 JSON (`CE_PURCHASEORDER_0001`) | Scope 1 | Fuel procurement line items — diesel, petrol, natural gas |
| **Utility** | Portal CSV export | Scope 2 | Electricity usage with TOU/flat tariffs, peak/off-peak splits, mixed kWh/MWh |
| **Travel** | Navan-style JSON export | Scope 3 (Cat. 6) | Flights, hotels, car rental, rail — with cabin class and distance handling |

Each source has realistic mock data in `data/raw/` and reference lookups in `data/reference/`. The normalizers handle unit conversion, emission factor application, confidence scoring, and flag generation.

**Detailed source research:** [`docs/SOURCES.md`](docs/SOURCES.md)

---

## Local Setup

### Prerequisites

- Python 3.11+ (tested on 3.12)
- Node.js 18+ (tested on 20)

### Backend

```bash
cd backend
python3 -m pip install -r requirements.txt
python3 manage.py migrate
python3 manage.py load_sample_data --reset
python3 manage.py runserver 127.0.0.1:8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** — the Vite dev server proxies `/api` requests to Django on port 8000.

---

## Running Tests

```bash
# Backend unit tests
cd backend
python3 manage.py test

# Frontend build verification
cd frontend
npm run build
```

---

## Deployment

This repository is configured for **one-click Render deployment** using Docker.

### How It Works

The `Dockerfile` performs a multi-stage build:

1. **Stage 1 (Node):** Installs frontend dependencies and runs `npm run build` to produce `frontend/dist/`.
2. **Stage 2 (Python):** Installs Django dependencies, copies the backend, data files, and the built frontend.

At runtime, `bin/start.sh`:
1. Runs Django migrations.
2. Loads sample data if the database is empty.
3. Collects static files via WhiteNoise.
4. Starts Gunicorn on the platform-provided `$PORT`.

### Render Quick Deploy

1. Push this repository to GitHub.
2. In Render, choose **New +** → **Blueprint**.
3. Select this repository — Render reads `render.yaml` automatically.
4. Render creates the web service and a free `breathe-esg-db` PostgreSQL database.
5. Deploy and open the generated live URL.

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | Yes (prod) | Insecure fallback | Cryptographic signing key |
| `DJANGO_DEBUG` | No | `true` | Set to `false` in production |
| `DJANGO_ALLOWED_HOSTS` | No | `localhost,127.0.0.1` | Comma-separated hostnames |
| `DATABASE_URL` | No | SQLite fallback | PostgreSQL connection string |
| `DJANGO_SECURE_SSL_REDIRECT` | No | `true` when DEBUG=false | HTTPS redirect |

See [`.env.example`](.env.example) for a complete template.

---

## API Reference

All endpoints are under `/api/`. No authentication is required for the prototype.

### Activities

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/activities/` | List activities (supports `?source_type=`, `?status=`, `?confidence=`, `?scope=` filters) |
| `GET` | `/api/activities/{id}/` | Activity detail with raw source record and audit events |
| `PATCH` | `/api/activities/{id}/` | Edit normalized values (quantity, unit, CO₂e, confidence) |
| `POST` | `/api/activities/{id}/approve/` | Approve a pending/rejected activity |
| `POST` | `/api/activities/{id}/reject/` | Reject a pending/approved activity |
| `POST` | `/api/activities/{id}/lock/` | Lock an approved activity for audit (irreversible) |

### Batches

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/batches/` | List ingestion batches with record counts |
| `GET` | `/api/batches/{id}/` | Batch detail |

### Upload

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/upload/` | Upload a source file (`source_type` + `file` as multipart form) |

Accepted upload formats:
- **SAP:** JSON shaped like `data/raw/sap/sap_procurement_mock.json`
- **UTILITY:** CSV shaped like `data/raw/utility/utility_electricity_mock.csv`
- **TRAVEL:** JSON shaped like `data/raw/travel/travel_navan_mock.json`

---

## Project Structure

```
.
├── backend/
│   ├── config/              # Django project settings, URLs, WSGI, SPA view
│   ├── emissions/           # Django app: models, views, serializers, normalizers, management commands
│   ├── manage.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Full analyst dashboard (single-page application)
│   │   ├── api.js           # API client
│   │   └── styles.css       # Complete design system
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
├── data/
│   ├── raw/                 # Mock source files (SAP JSON, utility CSV, travel JSON)
│   └── reference/           # Lookup tables (material, plant, emission factors)
├── docs/
│   ├── MODEL.md             # Data model documentation
│   ├── DECISIONS.md         # Ambiguity resolution and design decisions
│   ├── TRADEOFFS.md         # Deliberate omissions
│   ├── SOURCES.md           # Source research and sample data rationale
│   └── CHECKPOINT.md        # Development progress log
├── bin/
│   └── start.sh             # Production entrypoint script
├── Dockerfile               # Multi-stage build (Node + Python)
├── Procfile                 # Heroku/Render process definition
├── render.yaml              # Render Blueprint (web service + PostgreSQL)
├── .env.example             # Environment variable template
└── .gitignore
```

---

## Assignment Deliverables

| Deliverable | Location | Description |
|-------------|----------|-------------|
| **Working deployed app** | [Live URL](#live-demo) | Django serves React SPA via WhiteNoise |
| **MODEL.md** | [`docs/MODEL.md`](docs/MODEL.md) | Data model with multi-tenancy, Scope 1/2/3, source tracking, audit trail, unit normalization |
| **DECISIONS.md** | [`docs/DECISIONS.md`](docs/DECISIONS.md) | Every ambiguity resolved: SAP format choice, utility mode, travel distance handling, unit conversion, date normalization |
| **TRADEOFFS.md** | [`docs/TRADEOFFS.md`](docs/TRADEOFFS.md) | Three deliberate omissions with reasoning |
| **SOURCES.md** | [`docs/SOURCES.md`](docs/SOURCES.md) | Per-source research: real-world formats, what was learned, sample data rationale, production risks |

---

## Dashboard Features

- **Batch health overview** — ingestion status per source file with record counts
- **Activity table** — sortable, filterable rows with source type, scope, emissions, status, confidence
- **Multi-axis filtering** — by source, status, scope, confidence, free-text search, flagged-only toggle
- **Detail inspector** — per-row view with Details / Raw payload / Audit trail tabs
- **Inline editing** — modify normalized quantity, unit, CO₂e, and confidence before approval
- **Review workflow** — Approve → Lock (irreversible) or Reject, with optional review notes
- **CSV export** — download visible rows with all normalized fields
- **Source file upload** — import new SAP JSON, utility CSV, or travel JSON files
- **Dark mode** — toggle with persistent theme preference
- **Responsive layout** — three-panel workspace with side panels and scrollable activity table

---

## Reviewer Access

Repository should be shared with:
- saurav@breatheesg.com
- rahul@breatheesg.com
- shivang@breatheesg.com

Submission email should include:
1. GitHub repository link
2. Deployed app URL
3. Login credentials (none required — open access for demo)
