# MODEL.md

Data model for the Breathe ESG prototype. The goal is to preserve messy source data, normalize it into comparable emission activity rows, and support analyst review before records are locked for audit.

---

## Design Goals

1. **Multi-tenancy:** every client company has isolated data.
2. **Source-of-truth tracking:** every normalized row points back to the uploaded file, source row, and raw payload that produced it.
3. **Unit normalization:** raw values are preserved, normalized values are calculated separately.
4. **Audit trail:** analyst edits and approvals are append-only events.
5. **Review workflow:** analysts can approve, reject, flag, and lock rows before audit export.

---

## Core Entities

### Organization

Represents one client company.

| Field | Type | Why |
|---|---|---|
| `id` | UUID | Stable tenant key |
| `name` | string | Display name |
| `created_at` | datetime | Tenant creation audit |

All client-owned tables include `organization_id`.

### UserProfile

Extends Django's built-in `User`.

| Field | Type | Why |
|---|---|---|
| `user_id` | FK to Django User | Authentication |
| `organization_id` | FK to Organization | Tenant scoping |
| `role` | enum: `admin`, `analyst`, `viewer` | Permissions |

### IngestionBatch

One uploaded file or source import run.

| Field | Type | Why |
|---|---|---|
| `id` | UUID | Batch identifier |
| `organization_id` | FK | Tenant isolation |
| `source_type` | enum: `SAP`, `UTILITY`, `TRAVEL` | Source tracking |
| `original_filename` | string | Human traceability |
| `file_hash` | string | Duplicate detection |
| `uploaded_by` | FK to User | Accountability |
| `ingested_at` | datetime | Source-of-truth timestamp |
| `status` | enum: `processing`, `completed`, `failed` | Batch health |
| `error_summary` | text nullable | Import failure detail |

### RawSourceRecord

Stores the untouched source row/object.

| Field | Type | Why |
|---|---|---|
| `id` | UUID | Raw record identifier |
| `organization_id` | FK | Tenant isolation |
| `batch_id` | FK to IngestionBatch | Source file/run |
| `source_row_number` | integer nullable | CSV row or JSON array position |
| `source_record_key` | string | PO item, meter-period, booking-segment key |
| `raw_payload` | JSONB | Exact source data for audit/debug |
| `parse_status` | enum: `parsed`, `warning`, `failed` | Import status |
| `parse_errors` | JSONB | Field-level parse errors |
| `created_at` | datetime | Raw capture timestamp |

Raw records are never edited. If a parser or analyst changes interpretation, a new normalized activity or audit event records that change.

### EmissionFactor

Reference table loaded from `sap_material_lookup.json` and `emission_factors.json`.

| Field | Type | Why |
|---|---|---|
| `id` | UUID | Factor identifier |
| `factor_key` | string unique | Example: `flight_long_haul_business_with_rf` |
| `activity_type` | enum | Fuel, electricity, flight, hotel, car rental, rail |
| `scope` | integer | GHG Scope 1/2/3 |
| `scope3_category` | integer nullable | Category 6 for business travel |
| `factor_value` | decimal | Numeric multiplier |
| `factor_unit` | string | Example: `kg_co2e_per_passenger_km` |
| `geography` | string nullable | Region/grid/country |
| `source_name` | string | DEFRA, EPA/eGRID, client-specific |
| `effective_year` | integer | Versioning |
| `is_default` | boolean | Prototype fallback |

Production should allow client-specific and year-specific factors. For the prototype, static JSON factors are enough.

### EmissionActivity

Canonical normalized row shown in the analyst dashboard.

| Field | Type | Why |
|---|---|---|
| `id` | UUID | Activity identifier |
| `organization_id` | FK | Tenant isolation |
| `batch_id` | FK | Source batch |
| `raw_record_id` | FK | Raw source-of-truth pointer |
| `source_type` | enum: `SAP`, `UTILITY`, `TRAVEL` | Source tracking |
| `activity_type` | enum: `FUEL`, `ELECTRICITY`, `FLIGHT`, `HOTEL`, `CAR_RENTAL`, `RAIL` | Calculation path |
| `scope` | integer | Scope 1/2/3 |
| `scope3_category` | integer nullable | Category 6 for travel |
| `activity_start_date` | date nullable | Period/trip start |
| `activity_end_date` | date nullable | Period/trip end |
| `raw_quantity` | decimal nullable | Source value |
| `raw_unit` | string nullable | Source unit |
| `normalized_quantity` | decimal nullable | Converted activity value |
| `normalized_unit` | string nullable | Canonical unit |
| `conversion_factor_used` | decimal nullable | Unit conversion factor |
| `emission_factor_id` | FK nullable | Calculation factor |
| `emission_factor_value` | decimal nullable | Snapshot at calculation time |
| `emission_factor_unit` | string nullable | Snapshot at calculation time |
| `co2e_kg` | decimal nullable | Calculated emissions |
| `confidence` | enum: `high`, `medium`, `low` | Review priority |
| `flags` | JSONB | Suspicious conditions |
| `status` | enum | Review workflow |
| `approved_by` | FK nullable | Analyst approval |
| `approved_at` | datetime nullable | Approval timestamp |
| `rejected_by` | FK nullable | Rejection audit |
| `rejected_at` | datetime nullable | Rejection timestamp |
| `locked_at` | datetime nullable | Audit lock |
| `edited_by` | FK nullable | Last analyst edit |
| `edited_at` | datetime nullable | Last edit timestamp |
| `created_at` | datetime | Row creation |
| `updated_at` | datetime | Row update |

`status` choices:
- `pending_review`
- `needs_info`
- `approved`
- `rejected`
- `locked`

Locked rows cannot be edited. If a correction is needed after lock, create a reversal/correction row instead of mutating the locked record.

### ActivityDetail

Source-specific fields live in typed nullable columns or a JSONB detail object. For the prototype, use `details` JSONB on `EmissionActivity` to avoid over-normalizing early.

Examples:
- SAP: `purchase_order`, `purchase_order_item`, `plant_code`, `material_code`, `material_description`
- Utility: `account_number`, `meter_number`, `tariff_schedule`, `peak_usage`, `offpeak_usage`
- Travel: `booking_id`, `employee_id`, `segment_type`, `origin`, `destination`, `cabin_class`, `hotel_city`, `room_count`

Frequently filtered fields can later be promoted into typed columns.

### AuditEvent

Append-only log of all review and edit actions.

| Field | Type | Why |
|---|---|---|
| `id` | UUID | Event identifier |
| `organization_id` | FK | Tenant isolation |
| `activity_id` | FK to EmissionActivity | Row being changed |
| `actor_id` | FK to User | Who changed it |
| `action` | enum: `created`, `edited`, `flagged`, `approved`, `rejected`, `locked`, `unlocked_by_admin` | Audit semantics |
| `before` | JSONB nullable | Previous values |
| `after` | JSONB nullable | New values |
| `reason` | text nullable | Analyst/admin note |
| `created_at` | datetime | Event timestamp |

The dashboard writes an `AuditEvent` for every analyst edit, approval, rejection, and lock.

---

## Normalization Rules

### SAP Fuel

Input: `sap_procurement_mock.json` + `sap_material_lookup.json` + `sap_plant_lookup.json`

Rules:
- `Plant` maps to facility details.
- `Material` maps to fuel description and factor.
- `L` stays `L`.
- `GAL` converts to `L` using `3.78541`.
- `M3` stays `M3`.
- Fuel purchase order line items are Scope 1 only when the material is a direct-combustion fuel.

Suspicious flags:
- Missing material lookup.
- Missing plant lookup.
- Unsupported unit.
- Non-fuel material.

### Utility Electricity

Input: `utility_electricity_mock.csv` + `emission_factors.json`

Rules:
- `kWh` stays `kWh`.
- `MWh` converts to `kWh` using `1000`.
- TOU rows must satisfy `Peak_Usage + OffPeak_Usage = Total_Usage`.
- Flat-tariff rows may leave peak/off-peak blank.
- Default factor is `us_grid_average_location_based` until a region or supplier-specific factor is configured.

Suspicious flags:
- Billing period overlap for the same meter.
- Unknown `Usage_Unit`.
- TOU row missing peak/off-peak values.
- Renewable/PPA data missing for market-based Scope 2.

### Travel

Input: `travel_navan_mock.json` + `emission_factors.json`

Rules:
- Flights use airport-code pair distance from an airport lookup or distance service. If distance cannot be derived, flag `missing_distance`.
- Cabin class selects the flight factor key where available.
- Hotel emissions use `room_count * room_nights * hotel_country_or_city_factor`.
- Car rental distance falls back to `rental_days * 50 km/day` when actual distance is null.
- Rail uses provided `estimatedDistanceKm`.

Suspicious flags:
- Missing flight distance.
- Car rental estimated distance is null and proxy was used.
- Hotel country/city factor missing.
- Multi-passenger booking without passenger count.

---

## Analyst Review Workflow

1. Upload creates an `IngestionBatch`.
2. Parser stores each original row/object as `RawSourceRecord`.
3. Normalizer creates `EmissionActivity` rows with `pending_review` status.
4. Dashboard shows raw values, normalized values, factors, emissions, confidence, and flags.
5. Analyst can edit normalized fields, add notes, approve, or reject rows.
6. Approval sets `status = approved`, `approved_by`, and `approved_at`.
7. Locking sets `status = locked` and `locked_at`; locked rows are immutable.
8. Every action writes an `AuditEvent`.

Batch actions are allowed for low-risk rows, but flagged rows should require individual review.

---

## Dashboard Queries Needed

- Show all `pending_review` rows for an organization.
- Filter by `source_type`, `scope`, `activity_type`, `confidence`, and `flags`.
- Show raw payload and normalized calculation side-by-side.
- Batch approve rows with no flags.
- Reject rows with required reason.
- Lock approved rows for audit export.
- Export locked rows with source batch, raw record key, factor source, and audit history.

---

## Why This Model Fits the Assignment

- **Multi-tenancy:** `organization_id` exists on every client-owned record.
- **Scope 1/2/3:** `scope` and `scope3_category` are stored on each activity row.
- **Source-of-truth:** `EmissionActivity` links to `RawSourceRecord` and `IngestionBatch`.
- **Unit normalization:** raw and normalized quantities are separate fields.
- **Audit trail:** edits and approvals are append-only `AuditEvent` records.
- **Analyst UX:** review status, confidence, flags, and lock fields directly support the required dashboard.
