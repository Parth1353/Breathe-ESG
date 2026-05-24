# DECISIONS.md

Every ambiguity encountered during design, what was chosen, why, and what I would ask the PM.

---

## SAP — Source Format Choice

**Ambiguity:** SAP exposes data in multiple formats — IDoc (flat EDI-style), BAPI (function module calls), flat file exports, and OData services.

**Decision:** OData v4 via the CE_PURCHASEORDER_0001 service (SAP S/4HANA Cloud Public Edition, Purchase Order API).

**Why:**
- OData is the modern SAP S/4HANA standard. IDocs are legacy and mostly used for system-to-system EDI, not ESG data extraction.
- BAPIs require direct RFC connectivity into SAP — not realistic for a third-party ESG tool to request.
- Flat file exports are ad-hoc and have no guaranteed schema — every client exports slightly differently.
- OData has a published, versioned schema on the SAP Business Accelerator Hub (api.sap.com), making it the most defensible choice for a prototype.

**Subset handled:** Only PurchaseOrderItem-level data. Specifically: PurchaseOrder, PurchaseOrderItem, Plant, Material (code), OrderQuantity, PurchaseOrderQuantityUnit, NetPriceAmount, DocumentCurrency, NetPriceQuantity, CreationDate.

**Ignored:** Invoicing plans, subcontracting components, schedule lines, account assignments, partner data, header notes, item delivery addresses. None of these are relevant to emissions calculation.

**What I'd ask the PM:**
- Does the client use SAP S/4HANA Cloud or on-premise? On-premise OData endpoints have different base URLs and authentication.
- Do they already have an API key / OAuth client configured for external access?
- Is material-level data available or do they track fuel at the purchase order header level only?

---

## SAP — Material Code Lookup

**Ambiguity:** SAP material codes (e.g. `10000145`) are opaque integers with no meaning outside SAP's own master data.

**Decision:** Ship a separate `sap_material_lookup.json` that maps material codes to human-readable descriptions, emission category, and emission factor.

**Why:** The ingestion pipeline cannot compute emissions without knowing what the material is. A lookup table is the realistic approach — in production this would be pulled from SAP's Material Master via a separate OData call (MM60 or A_Product service). For this prototype it is a static file the client provides on onboarding.

**What I'd ask the PM:**
- Can the client export their Material Master data, or do we maintain the lookup ourselves?
- Are material codes stable across their SAP landscape or do different plants use different codes for the same material?

---

## SAP — Unit Inconsistency

**Ambiguity:** The PDF calls out inconsistent units. Our mock has litres (L), gallons (GAL), and cubic metres (M3) for the same category of fuel.

**Decision:** Accept all units at ingestion, normalize to a canonical unit (litres for liquid fuels, M3 for gas) during the processing step before emission calculation.

**Why:** Normalizing at ingest time would couple the ingestion layer to business logic. Keeping raw units and normalizing in a separate step means we have an audit trail of exactly what came in from the source.

---

## Travel — Platform Choice

**Ambiguity:** The PDF names Concur and Navan as options.

**Decision:** Navan-style travel export, ingested via JSON file upload (not live API pull).

**Why Navan over Concur:** Navan is a newer platform increasingly common in enterprise clients. Concur has more public documentation, so it is useful as a cross-check for common travel segment categories, but this prototype models a Navan-style export because the assignment explicitly allows Navan or similar platforms.

**Why file upload over API pull:** Navan's API documentation is not publicly accessible. It requires enterprise admin credentials to even read. The JSON payload in this prototype is therefore inferred from realistic travel booking exports and cross-checked against publicly documented Concur segment categories. A realistic deployment would have the client export a trip data dump from Navan's admin portal and upload it. This is also safer — it avoids storing OAuth credentials for a travel platform in our system.

**Subset handled:** FLIGHT, HOTEL, CAR_RENTAL, RAIL segments. For flights, cabin class is captured because DEFRA/DESNZ applies higher factors for premium cabins on long-haul flights.

**Ignored:** Dining, parking, ride-hail (Uber/Lyft). Not ignored because they are unimportant — ride-hail is Scope 3 — but because the data shape varies too much between platforms and the emission impact is comparatively small. Noted as a known gap.

**Distance gap:** Car rental bookings generally do not include actual driven distance at booking time. Emission estimate for car rental falls back to duration × average daily distance assumption (50 km/day). This is flagged as low-confidence in the review dashboard.

**What I'd ask the PM:**
- Does the client use Navan or Concur? If Concur, a Concur-specific export/API parser needs to be added.
- Do they want us to pull via API on a schedule, or will they upload exports manually?
- Should ride-hail (Uber for Business) be in scope?

---

## Utility — Source Format Choice

**Ambiguity:** The PDF lists portal CSV export, PDF bill, or API as options.

**Decision:** Portal CSV export.

**Why:**
- PDF bill parsing requires OCR — fragile, error-prone, and not worth the complexity for a prototype.
- Utility APIs exist (Green Button, ESPI protocol) but adoption is inconsistent. Most facilities teams export CSVs from their utility portal directly.
- CSV is the most common real-world format facilities teams actually use.

**Subset handled:** Account number, meter number, billing period (start/end date), tariff schedule, peak/off-peak usage split, total usage, usage unit (kWh or MWh), and cost in USD.

**Mixed units:** The CSV includes both kWh and MWh rows to test realistic meter-size differences. Normalization to kWh happens at processing time using `Usage_Unit`.

**TOU tariff handling:** Rows with Time-of-Use tariffs include `Peak_Usage` and `OffPeak_Usage` columns plus `Usage_Unit`. Rows with flat tariffs leave peak/off-peak blank. The ingestion layer treats blank as null, not zero.

**Billing period alignment:** Utility billing periods do not align to calendar months. The data model stores exact start/end dates and does not force month-end bucketing at ingest — that aggregation happens at reporting time.

**What I'd ask the PM:**
- Does the client have multiple utility accounts across facilities? If so, do they track which account maps to which building?
- Are they on a renewable energy tariff? If so, Scope 2 market-based emissions differ from location-based.
- Do they have natural gas utility bills too, or only electricity? Natural gas from utilities is Scope 1.

---

## Scope Classification

**Decision:**
- SAP fuel purchase order line items used for direct combustion → Scope 1
- Utility electricity → Scope 2 (purchased energy)
- Business travel → Scope 3 (Category 6: business travel)

This follows the GHG Protocol Corporate Standard. Generic non-fuel procurement is excluded from this prototype; if handled later, it would usually be Scope 3 purchased goods/services rather than Scope 1. Hotel stays are also Scope 3 Category 6.

---

## Ingestion Mechanism Per Source

**Ambiguity:** The PDF states: "For each source, you decide the ingestion mechanism (file upload, API pull, manual paste, whatever fits the realistic shape). Justify it."

**Decisions:**

| Source | Mechanism | Justification |
|--------|-----------|---------------|
| SAP | JSON file upload | The client's IT team exports OData JSON responses from their SAP S/4HANA system and uploads the file. A live API pull would require OAuth 2.0 credentials stored in our system plus network access to the client's SAP BTP tenant — unrealistic for a prototype and an onboarding friction point for every new client. File upload lets the client control what data leaves their system. |
| Utility | CSV file upload | Facilities teams already export CSVs from utility portals (PG&E, ConEd, ComEd). This is the path of least resistance — no API integration, no credentials, the file format is already what they have. |
| Travel | JSON file upload | Navan's API requires enterprise admin credentials with no publicly accessible documentation. The realistic workflow is: client admin exports trip data from Navan's admin portal, downloads a JSON dump, and uploads it. The prototype JSON shape is inferred rather than claimed as an official Navan schema. This also avoids storing travel platform OAuth credentials in our system. |

**Why file upload for all three:** A unified file upload interface keeps the prototype simple and reflects how most enterprise data onboarding actually works in practice — the first integration with a new client is almost always a file drop, not a live API connection. Live API pull is a Phase 2 enhancement.

**What I'd ask the PM:**
- For which sources, if any, does the client want automated scheduled ingestion (API pull) vs manual upload?
- Is there a volume threshold where file upload becomes impractical (e.g. 100,000+ purchase order items)?

---

## SAP — German Column Headers

**Ambiguity:** The PDF calls out "German column headers in some configurations." SAP was originally built by a German company, and many internal field names are German abbreviations regardless of the client's language settings.

**Decision:** Use English API-facing OData field names in the mock (`Plant`, `OrderQuantity`). If a client supplies a flat SAP export, CDS extract, or table-style file with German/internal names, accept those as aliases and map them to the same internal model fields.

**Alias mapping to support non-OData exports:**
| SAP/Input Field | German Origin | English Meaning | Internal Model Field |
|-----------|--------------|-----------------|---------------------|
| `Plant` / `WERKS` | Werk (factory/plant) | Plant code | `plant_code` |
| `OrderQuantity` / `MENGE` | Menge (quantity) | Order quantity | `quantity` |
| `PurchaseOrderQuantityUnit` | English OData field | Unit of measure | `unit` |

**Why:** The selected OData mock should reflect the API-facing payload, while still acknowledging the PDF's warning that some SAP exports expose German/internal names. The ingestion parser maps accepted aliases to consistent English model fields at the point of ingest. This means downstream code (normalization, emission calculation, dashboard display) never deals with SAP-specific abbreviations.

**What I'd ask the PM:**
- Does the client have any custom Z-fields (client-specific SAP extensions) that we need to map? Custom fields can have arbitrary names.

---

## Date Format Normalization

**Ambiguity:** The three data sources use three different date formats:
- SAP: `"20260520"` — YYYYMMDD string, no separators (SAP standard)
- Utility CSV: `"2026-01-14"` — YYYY-MM-DD (ISO 8601 date)
- Travel (Navan): `"2026-08-15T19:30:00Z"` — ISO 8601 datetime with timezone

**Decision:** Normalize all dates to ISO 8601 (`YYYY-MM-DD`) at ingestion time. Store as a proper `DateField` in Django. Timestamps (travel departure/arrival) are stored as `DateTimeField` with timezone awareness.

**Why:**
- SAP's YYYYMMDD format is a legacy string format that is error-prone if parsed incorrectly (e.g. `"20260520"` could be misread if a client's SAP outputs `"05/20/2026"` instead).
- Storing all dates in a consistent format ensures that period-based queries (e.g. "show all utility records for Q1 2026") work correctly across all sources.
- Keeping timezone info on travel timestamps matters because a flight departing SFO at 19:30 UTC is a different local time than LHR arrival — relevant for reporting by region.

**Parsing rules:**
| Source | Input Format | Parse Method | Storage |
|--------|-------------|--------------|---------|
| SAP | `YYYYMMDD` | `datetime.strptime(val, "%Y%m%d").date()` | `DateField` |
| Utility | `YYYY-MM-DD` | `datetime.strptime(val, "%Y-%m-%d").date()` | `DateField` |
| Travel dates | `YYYY-MM-DD` | `datetime.strptime(val, "%Y-%m-%d").date()` | `DateField` |
| Travel timestamps | ISO 8601 | `datetime.fromisoformat(val)` | `DateTimeField(tz)` |

---

## Unit Conversion — GAL to Litres

**Ambiguity:** The SAP mock includes material 10000203 (Unleaded Petrol) procured in US gallons (`GAL`), but the emission factor for petrol is defined per litre (`kg_co2e_per_L`). The emission factor cannot be applied without converting the quantity first.

**Decision:** Convert GAL → litres at the normalization step (after ingestion, before emission calculation). Conversion factor: **1 US GAL = 3.78541 litres**.

**Why:** The raw ingested row retains the original unit (`GAL`) and original quantity (`150.50`) for audit trail purposes. The normalized quantity (`569.90 L`) and the conversion factor used are stored as separate fields so an auditor can verify the math. This two-step approach (raw → normalized) is the standard pattern in carbon accounting tools.

**Risk:** SAP's `GAL` unit is US gallons by default, but a client with UK operations may have configured imperial gallons (`1 imperial GAL = 4.54609 L`). The difference is ~20%, which is material for emissions reporting. The conversion factor should be configurable per client in production.

**Supported conversions for this prototype:**
| From | To | Factor |
|------|----|--------|
| GAL (US) | L | × 3.78541 |
| M3 | M3 | × 1.0 (no conversion needed) |
| L | L | × 1.0 (no conversion needed) |
| MWh | kWh | × 1000.0 |

---

## Emission Factors — Static Prototype Table

**Ambiguity:** SAP fuel rows have material-code-specific factors in `sap_material_lookup.json`, but utility electricity and travel segments need their own factors.

**Decision:** Add `emission_factors.json` as a static prototype factor table for utility electricity and business travel. SAP fuel factors remain in `sap_material_lookup.json` because they are tied to material master codes.

**Why:** The normalizer needs a deterministic factor reference before calculating `co2e_kg`. A static JSON file is enough for the prototype and avoids building a full factor-management UI before the core ingestion/review flow exists.

**Factors included:**
- Utility electricity: U.S. grid-average location-based proxy from EPA/eGRID.
- Flights: DEFRA/DESNZ 2024 passenger-km factors with radiative forcing for short-haul economy, long-haul economy, and long-haul business.
- Hotels: DEFRA/DESNZ 2024 London room-night factor.
- Car rental: DEFRA/DESNZ 2024 medium petrol car per-km factor, used with the 50 km/day proxy when distance is missing.
- Rail: DEFRA/DESNZ 2024 national rail passenger-km factor.

**Known limitation:** The electricity factor is a U.S. CO2 proxy rather than a full client-specific Scope 2 CO2e factor. Production must support eGRID subregion, supplier-specific factors, RECs, PPAs, effective dates, and market-based reporting.

---

## What I Would Ask the PM (General)

1. Is this a single-tenant prototype or does it need to support multiple client companies from day one?
2. What is the target audit standard — GHG Protocol, ISO 14064, or a specific regulatory framework?
3. Do analysts need to edit individual rows, or only approve/reject at the row level?
4. Is there a materiality threshold — rows below a certain emission quantity that can be auto-approved?
