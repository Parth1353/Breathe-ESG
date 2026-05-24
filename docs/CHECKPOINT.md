# CHECKPOINT.md

Complete record of all work done so far on the Breathe ESG Tech Intern Assignment.
Written so any collaborator (or a fresh AI session) has full context to continue without re-researching anything.

---

## Project Overview

**Assignment:** Build a Django REST + React prototype that ingests emissions and activity data from three source types, normalizes it, and surfaces a review dashboard where an analyst can approve rows before they are locked for audit.

**Company:** Breathe ESG

**Three data sources:**
1. SAP — fuel purchase order/procurement line items used for direct combustion (Scope 1)
2. Utility portal — electricity data (Scope 2)
3. Corporate travel platform — flights, hotels, ground transport (Scope 3)

**Deliverables required:**
- Working deployed app (Render / Railway / Fly)
- MODEL.md — data model with multi-tenancy, Scope 1/2/3, audit trail, unit normalization
- DECISIONS.md — every ambiguity resolved with reasoning
- TRADEOFFS.md — 3 things deliberately not built
- SOURCES.md — research for each source

**Grading weights:**
- 35% data model quality
- 25% defense of decisions in post-submission review
- 20% realism of source handling
- 10% analyst UX
- 10% what was deliberately not built

---

## Current Status

### ✅ COMPLETED — Mock Data Phase
All 5 mock source files plus the static emission factor table are finalized, validated, and cross-checked.

### ✅ COMPLETED — DECISIONS.md
Written and aligned with the corrected source assumptions.

### ✅ COMPLETED — SOURCES.md
Written and aligned with the corrected source assumptions.

### ✅ COMPLETED — MODEL.md
Written with multi-tenancy, source-of-truth tracking, unit normalization, audit trail, review status, and locking workflow.

### ✅ COMPLETED — TRADEOFFS.md
Written with three deliberate omissions: live API pulls, miscellaneous travel spend, and market-based Scope 2 accounting.

### ✅ COMPLETED — Django backend
Implemented Django + Django REST Framework backend in `backend/` with models, migrations, ingestion normalizers, REST endpoints, sample data loader, and tests.

### ✅ COMPLETED — React frontend
Implemented Vite + React analyst review dashboard in `frontend/` with batch health, activity filters, suspicious-row focus, raw/detail/audit inspector, edit fields, approve/reject/lock actions, and responsive layout.

Latest UI polish: tightened panel sizing, fixed bottom/footer behavior with an assignment-readiness footer, improved detail-panel scrolling, and verified the flagged-row review path after the change.

### ❌ NOT STARTED — Deployment

### ✅ COMPLETED — Systematic folder structure
Files are now organized into `docs/`, `data/raw/`, `data/reference/`, `backend/`, and reserved `frontend/`.

---

## Mock Data Files — Final Validated State

### 1. `sap_procurement_mock.json`

**Format:** SAP S/4HANA Cloud OData v4 response from CE_PURCHASEORDER_0001 (Purchase Order API)
**Reference:** https://api.sap.com/api/CE_PURCHASEORDER_0001/overview

**Contents:** 3 PurchaseOrderItem records across 2 purchase orders

| PO | Item | Plant | Material | Quantity | Unit | Price | Currency |
|----|------|---------------|----------|----------|------|-------|----------|
| 4500001234 | 00010 | 1010 | 10000145 | 500.00 | L | 0.85 | EUR |
| 4500001234 | 00020 | P104 | 10000203 | 150.50 | GAL | 3.45 | USD |
| 4500001235 | 00010 | 1010 | 10000089 | 1200.00 | M3 | 0.62 | EUR |

**Key design decisions in this file:**
- Material codes are opaque integers (e.g. `10000145`) — realistic SAP format, not English labels
- `Plant` is a 4-character alphanumeric code — maps to facilities via plant lookup
- `CreationDate` is `"YYYYMMDD"` string format — SAP-standard, not ISO 8601
- 3 different units (L, GAL, M3) intentionally to test unit normalization
- 2 different currencies (EUR, USD) intentionally to test multi-currency
- `NetPriceAmount` + `DocumentCurrency` + `NetPriceQuantity` included — API-facing price/currency fields
- `@odata.context` is a full realistic URL, not a placeholder

**Why these 3 materials:**
- 10000145 = Diesel → Scope 1, liquid fuel, litres
- 10000203 = Unleaded Petrol → Scope 1, liquid fuel, US gallons (tests GAL unit)
- 10000089 = Natural Gas → Scope 1, gas, cubic metres (different emission factor key)

---

### 2. `sap_material_lookup.json`

**Purpose:** Maps opaque SAP material codes to human-readable descriptions and emission factors. Necessary because SAP material codes have no meaning without the Material Master.

**Structure:** Normalized — every material has `emission_factor_value` (float) and `emission_factor_unit` (string) as two separate consistent keys, so ingestion code can access them without branching per material.

```json
{
  "10000145": {
    "description": "Diesel Fuel (Standard Grade)",
    "category": "FUEL",
    "scope": 1,
    "emission_factor_value": 2.51279,
    "emission_factor_unit": "kg_co2e_per_L"
  },
  "10000203": {
    "description": "Unleaded Petrol (Regular)",
    "category": "FUEL",
    "scope": 1,
    "emission_factor_value": 2.0844,
    "emission_factor_unit": "kg_co2e_per_L"
  },
  "10000089": {
    "description": "Natural Gas (Industrial Grade)",
    "category": "FUEL",
    "scope": 1,
    "emission_factor_value": 2.04542,
    "emission_factor_unit": "kg_co2e_per_M3"
  }
}
```

**Cross-check validated:** All 3 material codes (`10000145`, `10000203`, `10000089`) present in both `sap_procurement_mock.json` and this lookup file — no orphaned references.

---

### 3. `sap_plant_lookup.json`

**Purpose:** Maps SAP plant codes (`Plant` in the OData-shaped mock; `WERKS` in many SAP table/flat-file contexts) to physical facility details. In production this comes from SAP table T001W or an equivalent plant/facility lookup. In this prototype it is a static onboarding file.

```json
{
  "1010": {
    "name": "Hamburg Manufacturing Plant",
    "country": "DE",
    "city": "Hamburg",
    "region": "Europe",
    "scope": 1
  },
  "P104": {
    "name": "Chicago Distribution Facility",
    "country": "US",
    "city": "Chicago",
    "region": "North America",
    "scope": 1
  }
}
```

**Cross-check validated:** Both plant codes (`1010`, `P104`) present in both `sap_procurement_mock.json` and this lookup — no orphaned references.

---

### 4. `travel_navan_mock.json`

**Format:** Navan-style trip export JSON
**Research note:** Navan's API has no public documentation — it requires enterprise/admin access. The JSON shape is inferred from realistic travel booking exports and cross-referenced against publicly documented SAP Concur travel/itinerary materials only for common segment categories, not as the payload schema.

**Contents:** 2 trips, 5 segments total

**Trip 1 — NAV-88392 (Q3 Sales Kickoff, London):**
- FLIGHT: BA284, SFO→LHR, Business class (long-haul, high-emission premium cabin factor per DEFRA/DESNZ)
- HOTEL: The Hoxton Holborn, London, 4 nights
- CAR_RENTAL: Hertz, Intermediate, Petrol, LHR pickup/dropoff, `estimatedDistanceKm: null` — intentionally null because car rental bookings are made before the trip; distance is unknown at booking time

**Trip 2 — NAV-99120 (Client Onboarding, NY):**
- FLIGHT: UA14, EWR→BOS, Economy (short domestic)
- RAIL: Amtrak AMT-171, BOS→NYP, `estimatedDistanceKm: 346` — rail routes are fixed so distance is known

**Why this combination:**
- Covers all 3 required transport categories: FLIGHT, HOTEL (ground), CAR_RENTAL (ground), RAIL (ground)
- Tests Business vs Economy cabin class distinction (different emission factors)
- Tests null distance (car rental) vs known distance (rail) — different calculation paths
- Tests long-haul international vs short domestic flight
- `bookingStatus` varies: TICKETED vs CONFIRMED — real platform field

---

### 5. `utility_electricity_mock.csv`

**Format:** Utility portal CSV export — format used by US investor-owned utilities (PG&E, ConEd, ComEd)
**Decision:** CSV over PDF bill (OCR too fragile) and Green Button/ESPI API (inconsistent utility adoption)

**Contents:** 4 rows across 2 accounts/meters

```
Account_Number,Meter_Number,Service_Start_Date,Service_End_Date,Tariff_Schedule,Peak_Usage,OffPeak_Usage,Total_Usage,Usage_Unit,Cost_USD
9876543210,MTR-8819A,2026-01-14,2026-02-12,TOU-8 (Time of Use),8900.30,5600.20,14500.50,kWh,2150.75
9876543210,MTR-8819A,2026-02-12,2026-03-15,TOU-8 (Time of Use),8.10,6.10,14.20,MWh,2100.20
9876543210,MTR-8819A,2026-03-15,2026-04-13,TOU-8 (Time of Use),7950.00,5850.00,13800.00,kWh,2050.00
1122334455,MTR-9920B,2026-02-05,2026-03-04,A-1 (Small General),,,850.00,kWh,120.50
```

**Why this structure:**
- Rows 1–3: TOU-8 tariff — Time-of-Use requires peak/off-peak split columns; a single usage column would be internally inconsistent
- Row 2: MWh usage unit — tests MWh → kWh normalization while preserving raw source units
- Row 4: A-1 flat tariff — `Peak_Usage` and `OffPeak_Usage` intentionally blank (null, not zero); ingestion must handle this
- Billing periods intentionally do NOT start on month boundaries (14th Jan, 12th Feb, 15th Mar) — realistic; tests that data model stores exact start/end dates
- 3 consecutive periods for MTR-8819A — tests period boundary handling and rollup aggregation
- 2 different accounts — tests multi-account/multi-meter handling
- No trailing space before 850.00 on row 4 — validated clean

---

### 6. `emission_factors.json`

**Purpose:** Static prototype factors for sources that do not carry source-specific factors. SAP fuel factors remain in `sap_material_lookup.json` because they are material-code specific.

**Contents:**
- Utility electricity: U.S. eGRID location-based proxy, `0.3497 kg CO2e/kWh`
- Short-haul economy flight: `0.18287 kg CO2e/passenger-km`
- Long-haul economy flight: `0.20011 kg CO2e/passenger-km`
- Long-haul business flight: `0.58028 kg CO2e/passenger-km`
- London hotel: `11.5 kg CO2e/room-night`
- Petrol medium car rental: `0.17726 kg CO2e/km`
- National rail: `0.03546 kg CO2e/passenger-km`

**Why this file exists:** The normalizer needs deterministic factors for utility and travel calculations before a full database-backed `EmissionFactor` model exists.

---

## Key Research Findings

### SAP
- Researched at: api.sap.com (SAP Business Accelerator Hub)
- Service: CE_PURCHASEORDER_0001, OData v4, documented on SAP Business Accelerator Hub
- Chose OData v4 over IDoc (legacy EDI), BAPI (requires RFC), flat file (no guaranteed schema)
- SAP dates are YYYYMMDD strings, not ISO 8601
- SAP unit `GAL` = US gallons by default (ambiguity risk with UK clients)
- Material codes and plant codes are both opaque — both require lookup tables

### Navan (Travel)
- No public API documentation — requires enterprise admin credentials
- Confirmed via search: API details only accessible once during credential creation
- Cross-referenced public SAP Concur travel/itinerary materials for segment type confirmation
- Concur was used to validate common category concepts, not as the Navan JSON schema
- Car class codes: C/E/F/I/L/M/P/S/X (I = Intermediate matches our mock)
- Chose file upload over live API pull because of credential access barrier

### Utility
- Researched Green Button / ESPI — US standard utility API; rejected due to inconsistent utility adoption
- TOU tariffs have peak/off-peak split; flat tariffs do not — single Usage_Amount is inconsistent for TOU
- Billing periods are 28–32 days from meter read date, never aligned to calendar months
- Large meters often report MWh; small meters report kWh — normalization required
- Electricity factor uses a U.S. grid-average EPA/eGRID proxy for the prototype; production needs region/supplier/market-based factors

### Emission Factors
- SAP fuel factors: `sap_material_lookup.json`, sourced from DEFRA/DESNZ 2024
- Utility/travel factors: `emission_factors.json`, sourced from EPA/eGRID proxy and DEFRA/DESNZ 2024
- Production model should load these into an `EmissionFactor` table with geography, effective year, and factor source metadata

---

## Scope Classification (GHG Protocol)

| Source | Scope | Category |
|--------|-------|----------|
| SAP fuel PO line items (diesel, petrol, natural gas) | Scope 1 | Direct combustion |
| Utility electricity | Scope 2 | Purchased energy |
| Flights | Scope 3 | Category 6: Business travel |
| Hotels | Scope 3 | Category 6: Business travel |
| Car rental | Scope 3 | Category 6: Business travel |
| Rail | Scope 3 | Category 6: Business travel |

---

## Known Gaps (Acknowledged in DECISIONS.md and SOURCES.md)

1. Ride-hail (Uber/Lyft) not in travel mock — acknowledged gap, low relative emission impact
2. Car rental distance is null — falls back to 50 km/day proxy, flagged as low-confidence
3. Flight distance not in source data — must be derived from IATA airport code pairs via great-circle calculation
4. Hotel emission factors are regional averages — no per-property data
5. Renewable energy tariff / PPA tracking not in utility mock — market-based vs location-based Scope 2 gap
6. SAP material lookup only covers 3 materials — unmapped codes must be flagged for analyst review, not silently ignored
7. SAP GAL unit ambiguity — US vs imperial gallons unresolvable without client SAP configuration confirmation
8. On-premise SAP (ECC) not supported — prototype is S/4HANA Cloud only

---

## Files Produced So Far

| File | Status |
|------|--------|
| `data/raw/sap/sap_procurement_mock.json` | ✅ Final |
| `data/reference/sap/sap_material_lookup.json` | ✅ Final |
| `data/reference/sap/sap_plant_lookup.json` | ✅ Final |
| `data/raw/travel/travel_navan_mock.json` | ✅ Final |
| `data/raw/utility/utility_electricity_mock.csv` | ✅ Final |
| `data/reference/emissions/emission_factors.json` | ✅ Final |
| `docs/DECISIONS.md` | ✅ Final (updated: OData field names, ingestion mechanisms, German alias handling, date normalization, GAL conversion) |
| `docs/SOURCES.md` | ✅ Final (updated: corrected DEFRA 2024 factors and softened inferred Navan payload wording) |
| `docs/MODEL.md` | ✅ Final |
| `docs/TRADEOFFS.md` | ✅ Final |
| `backend/` Django backend | ✅ Implemented and tested |
| `frontend/` React dashboard | ✅ Implemented and browser-tested |
| Deployment | ❌ Not started |

---

## Next Steps (In Order)

1. **Deployment** — mandatory, local-only submissions not reviewed

---

## Tech Stack Decision

**Backend:** Django + Django REST Framework — implemented in `backend/`
**Frontend:** React + Vite — implemented in `frontend/`
**Database:** SQLite for local development, with `DATABASE_URL` support for PostgreSQL on deployment
**Deployment target:** Render or Railway (simplest free-tier options)
**Python version:** 3.12.2 locally; 3.11+ acceptable for deployment

---

## Backend Implementation Notes

- Run local backend setup from `backend/`.
- Apply migrations with `python3 manage.py migrate`.
- Load demo data with `python3 manage.py load_sample_data --reset`.
- Run tests with `python3 manage.py test`.
- Public API routes implemented:
  - `GET /api/activities/`
  - `GET /api/activities/{id}/`
  - `PATCH /api/activities/{id}/`
  - `POST /api/activities/{id}/approve/`
  - `POST /api/activities/{id}/reject/`
  - `POST /api/activities/{id}/lock/`
  - `GET /api/batches/`
  - `GET /api/batches/{id}/`

---

## Frontend Implementation Notes

- Run local frontend setup from `frontend/`.
- Install dependencies with `npm install`.
- Start the dashboard with `npm run dev -- --port 5173`.
- The Vite dev server proxies `/api` to `http://127.0.0.1:8000`.
- Production build verified with `npm run build`.
- Browser-tested flows:
  - Dashboard renders all 12 normalized activity rows.
  - Flagged filter narrows to the car-rental proxy row and syncs the detail panel.
  - Raw/detail/audit tabs render source payload and review metadata.
  - Approve enables lock; locking disables approve/reject/edit controls.

---

## Grader Access Required (From Assignment PDF)

Repository must be shared with:
- saurav@breatheesg.com
- rahul@breatheesg.com
- shivang@breatheesg.com

Submission email must include: GitHub repo link, deployed app URL, login credentials.
