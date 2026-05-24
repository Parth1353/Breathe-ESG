# SOURCES.md

For each of the three data sources: what real-world format was researched, what was learned, what the mock data looks like and why, and what would break in a real deployment.

---

## Source 1 — SAP (Fuel & Procurement)

### Real-world format researched

SAP S/4HANA Cloud Purchase Order OData v4 service: **CE_PURCHASEORDER_0001**
Documentation: https://api.sap.com/api/CE_PURCHASEORDER_0001/overview

This is a SAP Business Accelerator Hub API for reading purchase orders from SAP S/4HANA Cloud. It is based on OData v4 and returns JSON.

The API exposes the following entity sets relevant to ESG: PurchaseOrder (header), PurchaseOrderItem (line items with material, quantity, unit, plant).

### What was learned

- SAP material codes are opaque integers (e.g. `10000145`). They have no meaning without the Material Master.
- Plant codes are 4-character alphanumeric codes (e.g. `1010`, `P104`). In the OData-shaped mock they appear as `Plant`; in flat SAP/table-style exports they may appear as the internal German field `WERKS`. They map to physical facilities but the mapping lives in a separate SAP table (T001W).
- Quantities use SAP's internal unit codes: `L` (litres), `GAL` (gallons), `M3` (cubic metres), `KG` (kilograms). These are not ISO units — `GAL` is US gallons by default unless the client's SAP is configured for imperial.
- Dates are in `YYYYMMDD` format as a string (e.g. `"20260520"`), not ISO 8601. This is consistent across all SAP OData services.
- A single purchase order can have multiple items (line items) — each item is a separate material/quantity pair.
- Price fields: `NetPriceAmount` is the price per `NetPriceQuantity` unit in `DocumentCurrency`. Currency can vary per line item if the client does multi-currency procurement.

### What the mock data looks like and why

`sap_procurement_mock.json` — 3 line items across 2 purchase orders:
- Item 1: 500L Diesel (material `10000145`) at plant `1010` (Hamburg) — tests liquid fuel in litres
- Item 2: 150.5 GAL Unleaded Petrol (material `10000203`) at plant `P104` (Chicago) — tests US gallon unit and USD currency
- Item 3: 1200 M3 Natural Gas (material `10000089`) at plant `1010` — tests gas in cubic metres

This combination was chosen to exercise three different units, two currencies, and two plants — the specific normalization problems the PDF calls out.

`sap_material_lookup.json` — maps material codes to descriptions and emission factors with normalized structure (`emission_factor_value` + `emission_factor_unit` as separate fields so code can access them with consistent keys regardless of material type).

**Emission factor source:** All SAP fuel emission factors are derived from the UK DEFRA/DESNZ 2024 Government GHG Conversion Factors for Company Reporting, flat-file factor set:
- Diesel: 2.51279 kg CO2e per litre (DEFRA 2024, Fuels → Liquid fuels → Diesel average biofuel blend)
- Petrol: 2.0844 kg CO2e per litre (DEFRA 2024, Fuels → Liquid fuels → Petrol average biofuel blend)
- Natural Gas: 2.04542 kg CO2e per cubic metre (DEFRA 2024, Fuels → Gaseous fuels → Natural gas)

DEFRA was chosen over EPA emission factors because DEFRA provides per-unit factors directly (kg CO2e per litre/m³), while EPA factors require additional heat-content conversions. In production, the emission factor source would be configurable per client based on their reporting jurisdiction.

`sap_plant_lookup.json` — maps plant codes to facility name, country, city, region. In production this is pulled from SAP T001W table via a separate OData call.

`emission_factors.json` — not a source export, but a static prototype factor table. It supplies non-SAP factors for utility electricity and travel because those source files do not carry their own emission factors. Utility electricity uses the US EPA eGRID 2023 U.S. total output CO2e rate: 770.884 lb/MWh, converted to 0.3497 kg CO2e/kWh.

### What would break in a real deployment

1. **Material Master gap:** Our lookup only covers 3 materials. A real client may have hundreds of material codes, many of which are not fuels (office supplies, spare parts). The ingestion pipeline must handle unmapped materials gracefully — flag them for analyst review rather than failing.
2. **GAL ambiguity:** SAP's `GAL` unit is US gallons by default, but clients with UK operations may have configured it as imperial gallons (4.546L vs 3.785L). Without confirming the SAP system's unit configuration, unit conversion will silently produce wrong numbers.
3. **Authentication:** The CE_PURCHASEORDER_0001 service requires OAuth 2.0 client credentials. Each client needs to provision an API key in their SAP BTP account. This is an onboarding friction point.
4. **On-premise SAP:** Clients on SAP ECC (on-premise, older) do not have this OData service. They would need IDoc extracts or BAPI calls, which require a completely different ingestion path.
5. **Date parsing:** `"20260520"` must be parsed as `datetime.strptime(date_str, "%Y%m%d")`. Any deviation (e.g. a client with a differently configured date format output) will silently produce wrong dates or crash.

---

## Source 2 — Utility (Electricity)

### Real-world format researched

Utility portal CSV exports — specifically the format used by US investor-owned utilities (PG&E, ConEd, ComEd) when facilities teams export usage data from their online portals.

Also reviewed: Green Button / ESPI (Energy Service Provider Interface) — the US standard for utility data APIs. Decided against it (see DECISIONS.md).

### What was learned

- Billing periods do not align to calendar months. A billing cycle is typically 28–32 days starting from the meter read date, not the 1st of the month.
- The same meter can report in kWh or MWh depending on meter size — large industrial meters often report in MWh. Both appear in the same export.
- Time-of-Use (TOU) tariffs split consumption into peak and off-peak bands. A single `Usage_Amount` column is internally inconsistent for a TOU tariff — you need at minimum two columns.
- Tariff schedule names are utility-specific strings (e.g. `TOU-8`, `A-1`) with no universal standard.
- Large accounts often have multiple meters under one account number — a campus may have 10+ meters, each with its own billing period.
- Cost does not directly map to emissions. A renewable energy tariff (e.g. 100% wind) still has a location-based Scope 2 emission — the market-based emission is zero, but both need to be tracked per GHG Protocol Scope 2 guidance.

### What the mock data looks like and why

`utility_electricity_mock.csv` — 4 rows across 2 accounts:
- Rows 1–3: MTR-8819A (large meter, TOU-8 tariff) with peak/off-peak split, billing periods of ~29 days each, and mixed units (`kWh` plus one `MWh` row)
- Row 4: MTR-9920B (small meter, flat A-1 tariff) with blank peak/off-peak columns

Rows 1–3 intentionally cover 3 consecutive billing periods to test period boundary handling and kWh/MWh normalization. Row 4 uses a different account and a flat tariff to test that the ingestion layer handles null peak/off-peak gracefully.

The billing periods were chosen to not start on month boundaries (14th Jan, 12th Feb, etc.) — this is realistic and tests that the data model stores exact dates rather than forcing calendar-month alignment.

### What would break in a real deployment

1. **MWh vs kWh mixed in the same export:** Row 2 uses MWh while the other rows use kWh. The parser must detect `Usage_Unit`, convert MWh to kWh during normalization, and preserve the raw unit for audit.
2. **Tariff string parsing:** `TOU-8 (Time of Use)` contains the tariff type in the string. This is fragile — a different utility may write `Time-of-Use Rate Schedule 8` or just `TOU8`. The ingestion layer needs a configurable tariff-type classifier, not a string match.
3. **Multiple meters per account:** Our mock has 2 accounts. A real enterprise client may have 50+ meters. Aggregation logic must handle this without double-counting.
4. **Renewable tariff tracking:** Our mock does not include a renewable flag. In production, if the client has a Power Purchase Agreement (PPA) or renewable energy certificates (RECs), Scope 2 market-based emissions differ from location-based. This is a gap.
5. **PDF bills:** Many smaller facilities teams receive PDF bills, not CSV exports. PDF parsing is not handled in this prototype.
6. **Electricity factor geography:** The prototype uses a U.S. grid-average location-based proxy from EPA/eGRID. A real deployment needs eGRID subregion, supplier-specific, and market-based factors.

---

## Source 3 — Corporate Travel (Navan)

### Real-world format researched

Navan (formerly TripActions) travel booking data. Navan's public API documentation is not accessible without enterprise/admin access, so the JSON shape in this prototype is inferred rather than claimed as an official Navan schema.

Cross-referenced with publicly documented SAP Concur travel/itinerary materials only to validate common segment categories across corporate travel platforms: air, car, hotel, rail, ride, parking, and dining. The Concur reference is not used as the payload schema for `travel_navan_mock.json`.

### What was learned

- Flight segments always have origin/destination airport codes (IATA), airline code, flight number, and cabin class. Distance is not provided — it must be derived from airport coordinates if needed for emission calculation. Most emission calculators use great-circle distance from IATA codes.
- Cabin class matters significantly for emissions: DEFRA/DESNZ publishes separate economy, premium economy, business, and first-class factors for long-haul flights.
- Car rental segments do not include distance — the booking is made before the trip. Emission estimates require a proxy (duration × assumed daily km).
- Hotel emissions are Scope 3 Category 6. Emission factor per room-night varies by country and hotel type. Without a specific hotel's energy data, a regional average is used.
- Navan's API is not publicly accessible — it requires enterprise admin credentials. This makes live API pull impractical for a prototype. File upload of an inferred, client-provided JSON export is the realistic ingestion path.
- Rail segments (Amtrak, Eurostar) do provide distance in some platforms because the route is fixed, unlike car rental.

### What the mock data looks like and why

`travel_navan_mock.json` — 2 trips:

**Trip NAV-88392 (London):** 3 segments — FLIGHT (SFO→LHR, Business class, long-haul, high emission), HOTEL (4 nights London), CAR_RENTAL (Hertz, 4 days, `estimatedDistanceKm: null` because distance is unknown at booking). This trip tests the distance-null gap and the business class multiplier.

**Trip NAV-99120 (New York):** 2 segments — FLIGHT (EWR→BOS, Economy, short domestic), RAIL (BOS→NYP Amtrak with known distance 346km). This trip tests short-haul economy flight and rail with known distance — different emission factor from flight.

All 3 ground transport types are represented: CAR_RENTAL, RAIL, and the FLIGHT segments serve as the air category. Ride-hail is acknowledged as a gap in DECISIONS.md.

`emission_factors.json` provides the static prototype factors used to normalize these segments:
- Short-haul economy flight: 0.18287 kg CO2e/passenger-km.
- Long-haul business flight: 0.58028 kg CO2e/passenger-km.
- London hotel stay: 11.5 kg CO2e/room-night.
- Medium petrol rental car: 0.17726 kg CO2e/km.
- National rail: 0.03546 kg CO2e/passenger-km.

These travel factors come from the UK DEFRA/DESNZ 2024 Government GHG Conversion Factors. They are defensible for a prototype, but production should swap them for jurisdiction/client-preferred factors.

### What would break in a real deployment

1. **Distance calculation for flights:** Airport code pairs must be resolved to great-circle distances. This requires an airport coordinates lookup table (or an external API). Without it, flight emissions cannot be calculated.
2. **Car rental distance gap:** `estimatedDistanceKm: null` means emission calculation must fall back to a duration-based proxy. This proxy assumption (50 km/day) is hardcoded and may be wrong for clients whose employees drive significantly more or less.
3. **Navan API access:** Live API pull requires enterprise credentials and OAuth 2.0 setup per client. The prototype uses file upload as a proxy, but a production deployment needs proper OAuth client management.
4. **Hotel emission factors:** Room-night emission factors are regional averages. A client staying at a certified green hotel would have lower actual emissions, but we have no way to capture that without the hotel's own disclosure.
5. **Multi-passenger bookings:** Our mock assumes one employee per booking. Group bookings (one booking ID, multiple travellers) would inflate emissions if counted per booking rather than per passenger.
