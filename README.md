# Breathe ESG Prototype

Django REST + React prototype for the Breathe ESG technical intern assignment.

The app ingests realistic SAP procurement/fuel, utility electricity, and corporate travel exports; normalizes the rows into comparable emission activities; and gives analysts a review dashboard for flags, edits, approvals, rejections, audit locking, raw payload inspection, and CSV export.

## Assignment Deliverables

- Working app: Django backend plus React frontend. Local dev uses Vite; production serves the built React app from Django.
- Data model: [`docs/MODEL.md`](docs/MODEL.md)
- Decisions and ambiguities: [`docs/DECISIONS.md`](docs/DECISIONS.md)
- Tradeoffs: [`docs/TRADEOFFS.md`](docs/TRADEOFFS.md)
- Source research: [`docs/SOURCES.md`](docs/SOURCES.md)

## Implemented Scope

- SAP OData-shaped purchase order item JSON for direct-combustion fuel procurement.
- Utility portal CSV for electricity usage, TOU tariffs, billing periods, and mixed kWh/MWh units.
- Navan-style JSON travel export covering flights, hotels, car rental, and rail.
- Source-of-truth tracking through ingestion batches and immutable raw source records.
- Unit normalization with raw quantity/unit retained for audit.
- Scope 1/2/3 classification and Scope 3 Category 6 for business travel.
- Audit events for created, edited, approved, rejected, and locked rows.
- Analyst dashboard with filters, dark mode, flag visibility, raw/audit tabs, CSV export, and source file upload.

## Local Setup

Backend:

```bash
cd backend
python3 -m pip install -r requirements.txt
python3 manage.py migrate
python3 manage.py load_sample_data --reset
python3 manage.py runserver 127.0.0.1:8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open [`http://127.0.0.1:5173`](http://127.0.0.1:5173).

The Vite dev server proxies `/api` to Django on port `8000`.

## Source Uploads

The Imports panel accepts:

- `SAP`: JSON shaped like `data/raw/sap/sap_procurement_mock.json`
- `UTILITY`: CSV shaped like `data/raw/utility/utility_electricity_mock.csv`
- `TRAVEL`: JSON shaped like `data/raw/travel/travel_navan_mock.json`

Upload parsing uses the same normalizers as the sample loader and creates a new ingestion batch.

## Tests

```bash
cd backend
python3 manage.py test

cd ../frontend
npm run build
```

## Deployment

This repo includes a `Dockerfile`, `render.yaml`, and `Procfile` for one-service deployment.

The container build:

1. Builds the React frontend with Node.
2. Installs Django requirements with Python.
3. Copies the built frontend into the Django-serving layout.

The runtime start script:

1. Runs migrations.
2. Loads demo sample data only if it is not already present.
3. Collects static files.
4. Starts Gunicorn on the platform-provided `PORT`.

Required environment variables:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=false`
- `DJANGO_ALLOWED_HOSTS=<your-render-hostname>`
- `DATABASE_URL=<postgres-url>` for persistent production storage

Without `DATABASE_URL`, Django falls back to SQLite, which is fine locally but not durable on most hosted platforms.

### Render Quick Deploy

1. Push this repository to GitHub.
2. In Render, choose **New +** → **Blueprint**.
3. Select this repository. Render will read `render.yaml`.
4. Render will create the web service and `breathe-esg-db` Postgres database.
5. Deploy and open the generated live URL.

## Reviewer Notes

Authentication is intentionally not enforced in the demo dashboard so reviewers can open the deployed URL directly. The data model still includes `Organization`, `UserProfile`, role fields, and actor fields so tenant scoping and authenticated analyst actions can be enabled without changing the core schema.
