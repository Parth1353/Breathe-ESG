# TRADEOFFS.md

Three things deliberately not built in this prototype, and why.

---

## 1. Live API Pulls

**Not built:** Direct scheduled API integrations with SAP, Navan/Concur, or utility providers.

**Why:** Live integrations require client-specific credentials, OAuth setup, network access, security review, and vendor-specific configuration. For a 4-day prototype, file upload is the realistic first onboarding path and keeps the focus on source shape, normalization, review, and auditability.

**Impact:** The prototype cannot automatically refresh data. A client admin or analyst must upload exports manually.

**Future version:** Add scheduled import jobs per source after onboarding, with encrypted credential storage, retry handling, import logs, and per-client connector configuration.

---

## 2. Ride-Hail, Dining, Parking, and Miscellaneous Travel Spend

**Not built:** Uber/Lyft, taxis, meals, parking, and other incidental travel expenses.

**Why:** The assignment asks for flights, hotels, and ground transport. The prototype covers flight, hotel, car rental, and rail. Ride-hail and incidental categories vary heavily by platform and receipt data quality, and they add parser complexity without improving the core data-model demonstration.

**Impact:** Some Scope 3 Category 6 emissions are omitted. This is acceptable for the prototype only because the omission is explicit and the higher-impact travel categories are represented.

**Future version:** Add expense-line ingestion from Concur/Navan/expense CSV exports with merchant/category mapping and separate confidence levels for receipt-derived estimates.

---

## 3. Market-Based Scope 2 Accounting

**Not built:** Renewable energy tariffs, RECs, PPAs, supplier-specific emission factors, and dual location-based/market-based Scope 2 reporting.

**Why:** The utility mock focuses on realistic CSV shape, billing periods, meter units, and TOU usage. Market-based Scope 2 requires contract data that is usually separate from utility usage exports and needs careful audit handling.

**Impact:** Electricity emissions use a default location-based grid factor in `emission_factors.json`. This is enough to show normalization and review workflow, but it is not sufficient for production-grade Scope 2 reporting.

**Future version:** Add energy contract records, REC/PPA certificate tracking, supplier factors, effective dates, and side-by-side location-based vs market-based Scope 2 calculations.
