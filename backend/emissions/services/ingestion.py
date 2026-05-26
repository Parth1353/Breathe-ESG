import csv
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from django.db import transaction

from emissions.models import (
    AuditEvent,
    EmissionActivity,
    EmissionFactor,
    IngestionBatch,
    Organization,
    RawSourceRecord,
)


DECIMAL_4 = Decimal("0.0001")
DECIMAL_8 = Decimal("0.00000001")
US_GALLON_TO_LITRES = Decimal("3.78541")
MWH_TO_KWH = Decimal("1000")

AIRPORT_COORDS = {
    "SFO": (Decimal("37.6213"), Decimal("-122.3790")),
    "LHR": (Decimal("51.4700"), Decimal("-0.4543")),
    "EWR": (Decimal("40.6895"), Decimal("-74.1745")),
    "BOS": (Decimal("42.3656"), Decimal("-71.0096")),
}


@dataclass
class IngestionCounts:
    raw_records: int = 0
    activities: int = 0
    warnings: int = 0
    failed: int = 0


def decimal_from(value):
    if value is None or value == "":
        return None
    return Decimal(str(value))


def quantize(value, places=DECIMAL_4):
    if value is None:
        return None
    return Decimal(value).quantize(places)


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_sap_date(value):
    return datetime.strptime(value, "%Y%m%d").date()


def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_datetime_date(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def great_circle_km(origin, destination):
    start = AIRPORT_COORDS.get(origin)
    end = AIRPORT_COORDS.get(destination)
    if not start or not end:
        return None

    lat1, lon1 = [math.radians(float(part)) for part in start]
    lat2, lon2 = [math.radians(float(part)) for part in end]
    d_lat = lat2 - lat1
    d_lon = lon2 - lon1
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return Decimal(str(6371.0088 * c))


def create_batch(organization, source_type, path, uploaded_by=None, original_filename=None):
    return IngestionBatch.objects.create(
        organization=organization,
        source_type=source_type,
        original_filename=original_filename or Path(path).name,
        file_hash=file_hash(path),
        uploaded_by=uploaded_by,
        status=IngestionBatch.Status.PROCESSING,
    )


def create_raw_record(organization, batch, row_number, record_key, payload, flags=None, errors=None):
    errors = errors or []
    flags = flags or {}
    if errors:
        parse_status = RawSourceRecord.ParseStatus.FAILED
    elif flags:
        parse_status = RawSourceRecord.ParseStatus.WARNING
    else:
        parse_status = RawSourceRecord.ParseStatus.PARSED

    return RawSourceRecord.objects.create(
        organization=organization,
        batch=batch,
        source_row_number=row_number,
        source_record_key=record_key,
        raw_payload=payload,
        parse_status=parse_status,
        parse_errors=errors,
    )


def create_activity(**kwargs):
    activity = EmissionActivity.objects.create(**kwargs)
    AuditEvent.objects.create(
        organization=activity.organization,
        activity=activity,
        action=AuditEvent.Action.CREATED,
        after={
            "status": activity.status,
            "co2e_kg": str(activity.co2e_kg) if activity.co2e_kg is not None else None,
            "confidence": activity.confidence,
            "flags": activity.flags,
        },
    )
    return activity


def load_emission_factors(data_root):
    data_root = Path(data_root)
    sap_materials = json.loads((data_root / "reference/sap/sap_material_lookup.json").read_text())
    for material_code, material in sap_materials.items():
        EmissionFactor.objects.update_or_create(
            factor_key=f"sap_material_{material_code}",
            defaults={
                "activity_type": EmissionFactor.ActivityType.FUEL,
                "scope": material["scope"],
                "scope3_category": None,
                "factor_value": quantize(decimal_from(material["emission_factor_value"]), DECIMAL_8),
                "factor_unit": material["emission_factor_unit"],
                "geography": "",
                "source_name": "UK DEFRA/DESNZ 2024 Government GHG Conversion Factors",
                "effective_year": 2024,
                "is_default": False,
            },
        )

    factor_table = json.loads((data_root / "reference/emissions/emission_factors.json").read_text())
    for section in ["utility_electricity", "business_travel"]:
        for factor_key, factor in factor_table[section].items():
            EmissionFactor.objects.update_or_create(
                factor_key=factor_key,
                defaults={
                    "activity_type": factor["activity_type"],
                    "scope": factor["scope"],
                    "scope3_category": factor.get("scope3_category"),
                    "factor_value": quantize(decimal_from(factor["factor_value"]), DECIMAL_8),
                    "factor_unit": factor["factor_unit"],
                    "geography": factor.get("geography", ""),
                    "source_name": factor["source"],
                    "effective_year": 2024,
                    "is_default": True,
                },
            )


def factor_by_key(key):
    return EmissionFactor.objects.get(factor_key=key)


def co2e(normalized_quantity, factor):
    if normalized_quantity is None or factor is None:
        return None
    return quantize(normalized_quantity * factor.factor_value)


def complete_batch(batch, counts):
    if counts.failed:
        batch.status = IngestionBatch.Status.FAILED
        batch.error_summary = f"{counts.failed} records failed to parse."
    else:
        batch.status = IngestionBatch.Status.COMPLETED
        batch.error_summary = ""
    batch.save(update_fields=["status", "error_summary"])


@transaction.atomic
def ingest_sap(organization: Organization, data_root, uploaded_by=None, source_path=None, original_filename=None):
    data_root = Path(data_root)
    source_path = Path(source_path) if source_path else data_root / "raw/sap/sap_procurement_mock.json"
    material_lookup = json.loads((data_root / "reference/sap/sap_material_lookup.json").read_text())
    plant_lookup = json.loads((data_root / "reference/sap/sap_plant_lookup.json").read_text())
    payload = json.loads(source_path.read_text())
    batch = create_batch(organization, IngestionBatch.SourceType.SAP, source_path, uploaded_by, original_filename)
    counts = IngestionCounts()

    for index, item in enumerate(payload.get("value", []), start=1):
        flags = {}
        material_code = item.get("Material")
        plant_code = item.get("Plant")
        material = material_lookup.get(material_code)
        plant = plant_lookup.get(plant_code)
        if not material:
            flags["missing_material_lookup"] = material_code
        if not plant:
            flags["missing_plant_lookup"] = plant_code

        quantity = decimal_from(item.get("OrderQuantity"))
        raw_unit = item.get("PurchaseOrderQuantityUnit", "")
        factor = factor_by_key(f"sap_material_{material_code}") if material else None
        normalized_quantity = None
        normalized_unit = ""
        conversion = None

        if material:
            factor_unit = material["emission_factor_unit"]
            if factor_unit.endswith("_per_L"):
                normalized_unit = "L"
                if raw_unit == "L":
                    conversion = Decimal("1")
                elif raw_unit == "GAL":
                    conversion = US_GALLON_TO_LITRES
                else:
                    flags["unsupported_unit"] = raw_unit
            elif factor_unit.endswith("_per_M3"):
                normalized_unit = "M3"
                if raw_unit == "M3":
                    conversion = Decimal("1")
                else:
                    flags["unsupported_unit"] = raw_unit
            if conversion is not None and quantity is not None:
                normalized_quantity = quantize(quantity * conversion)

        if material and material.get("category") != "FUEL":
            flags["non_fuel_material"] = material_code

        record_key = f"{item.get('PurchaseOrder')}:{item.get('PurchaseOrderItem')}"
        raw_record = create_raw_record(organization, batch, index, record_key, item, flags)
        confidence = EmissionActivity.Confidence.MEDIUM if flags else EmissionActivity.Confidence.HIGH
        activity = create_activity(
            organization=organization,
            batch=batch,
            raw_record=raw_record,
            source_type=EmissionActivity.SourceType.SAP,
            activity_type=EmissionActivity.ActivityType.FUEL,
            scope=1,
            scope3_category=None,
            activity_start_date=parse_sap_date(item["CreationDate"]),
            activity_end_date=parse_sap_date(item["CreationDate"]),
            raw_quantity=quantize(quantity),
            raw_unit=raw_unit,
            normalized_quantity=normalized_quantity,
            normalized_unit=normalized_unit,
            conversion_factor_used=quantize(conversion, DECIMAL_8),
            emission_factor=factor,
            emission_factor_value=factor.factor_value if factor else None,
            emission_factor_unit=factor.factor_unit if factor else "",
            co2e_kg=co2e(normalized_quantity, factor),
            confidence=confidence,
            flags=flags,
            details={
                "purchase_order": item.get("PurchaseOrder"),
                "purchase_order_item": item.get("PurchaseOrderItem"),
                "plant_code": plant_code,
                "plant": plant,
                "material_code": material_code,
                "material_description": material.get("description") if material else None,
                "net_price_amount": item.get("NetPriceAmount"),
                "document_currency": item.get("DocumentCurrency"),
                "net_price_quantity": item.get("NetPriceQuantity"),
            },
        )
        counts.raw_records += 1
        counts.activities += 1 if activity else 0
        counts.warnings += 1 if flags else 0

    complete_batch(batch, counts)
    return counts


@transaction.atomic
def ingest_utility(organization: Organization, data_root, uploaded_by=None, source_path=None, original_filename=None):
    data_root = Path(data_root)
    source_path = Path(source_path) if source_path else data_root / "raw/utility/utility_electricity_mock.csv"
    batch = create_batch(organization, IngestionBatch.SourceType.UTILITY, source_path, uploaded_by, original_filename)
    factor = factor_by_key("us_grid_average_location_based")
    counts = IngestionCounts()
    periods_by_meter = {}

    with source_path.open(newline="") as handle:
        for physical_row_number, row in enumerate(csv.DictReader(handle), start=2):
            flags = {}
            meter = row["Meter_Number"]
            start_date = parse_date(row["Service_Start_Date"])
            end_date = parse_date(row["Service_End_Date"])

            for previous_start, previous_end in periods_by_meter.get(meter, []):
                if start_date < previous_end and end_date > previous_start:
                    flags["billing_period_overlap"] = {
                        "overlaps_start": previous_start.isoformat(),
                        "overlaps_end": previous_end.isoformat(),
                    }
            periods_by_meter.setdefault(meter, []).append((start_date, end_date))

            unit = row["Usage_Unit"]
            total_usage = decimal_from(row["Total_Usage"])
            if unit == "kWh":
                conversion = Decimal("1")
                normalized_quantity = total_usage
            elif unit == "MWh":
                conversion = MWH_TO_KWH
                normalized_quantity = total_usage * conversion
            else:
                conversion = None
                normalized_quantity = None
                flags["unknown_usage_unit"] = unit

            peak_usage = decimal_from(row["Peak_Usage"])
            offpeak_usage = decimal_from(row["OffPeak_Usage"])
            is_tou = "TOU" in row["Tariff_Schedule"].upper() or "TIME OF USE" in row["Tariff_Schedule"].upper()
            if is_tou and (peak_usage is None or offpeak_usage is None):
                flags["tou_missing_peak_or_offpeak"] = True
            if peak_usage is not None and offpeak_usage is not None and total_usage is not None:
                if abs((peak_usage + offpeak_usage) - total_usage) > Decimal("0.01"):
                    flags["tou_total_mismatch"] = {
                        "peak_plus_offpeak": str(peak_usage + offpeak_usage),
                        "total_usage": str(total_usage),
                    }

            record_key = f"{row['Account_Number']}:{meter}:{row['Service_Start_Date']}"
            raw_record = create_raw_record(organization, batch, physical_row_number, record_key, row, flags)
            confidence = EmissionActivity.Confidence.MEDIUM if flags else EmissionActivity.Confidence.HIGH
            activity = create_activity(
                organization=organization,
                batch=batch,
                raw_record=raw_record,
                source_type=EmissionActivity.SourceType.UTILITY,
                activity_type=EmissionActivity.ActivityType.ELECTRICITY,
                scope=2,
                scope3_category=None,
                activity_start_date=start_date,
                activity_end_date=end_date,
                raw_quantity=quantize(total_usage),
                raw_unit=unit,
                normalized_quantity=quantize(normalized_quantity),
                normalized_unit="kWh" if normalized_quantity is not None else "",
                conversion_factor_used=quantize(conversion, DECIMAL_8),
                emission_factor=factor,
                emission_factor_value=factor.factor_value,
                emission_factor_unit=factor.factor_unit,
                co2e_kg=co2e(quantize(normalized_quantity), factor),
                confidence=confidence,
                flags=flags,
                details={
                    "account_number": row["Account_Number"],
                    "meter_number": meter,
                    "tariff_schedule": row["Tariff_Schedule"],
                    "peak_usage": row["Peak_Usage"] or None,
                    "offpeak_usage": row["OffPeak_Usage"] or None,
                    "cost_usd": row["Cost_USD"],
                    "factor_basis": "location_based_us_grid_average",
                },
            )
            counts.raw_records += 1
            counts.activities += 1 if activity else 0
            counts.warnings += 1 if flags else 0

    complete_batch(batch, counts)
    return counts


@transaction.atomic
def ingest_travel(organization: Organization, data_root, uploaded_by=None, source_path=None, original_filename=None):
    data_root = Path(data_root)
    source_path = Path(source_path) if source_path else data_root / "raw/travel/travel_navan_mock.json"
    payload = json.loads(source_path.read_text())
    batch = create_batch(organization, IngestionBatch.SourceType.TRAVEL, source_path, uploaded_by, original_filename)
    counts = IngestionCounts()
    segment_number = 0

    for trip in payload.get("trips", []):
        for segment_index, segment in enumerate(trip.get("segments", []), start=1):
            segment_number += 1
            flags = {}
            activity_kwargs = normalize_travel_segment(trip, segment, flags)
            record_key = f"{trip['bookingId']}:{segment_index}:{segment['type']}"
            raw_record = create_raw_record(organization, batch, segment_number, record_key, segment, flags)
            confidence = EmissionActivity.Confidence.LOW if flags else EmissionActivity.Confidence.HIGH
            activity = create_activity(
                organization=organization,
                batch=batch,
                raw_record=raw_record,
                source_type=EmissionActivity.SourceType.TRAVEL,
                confidence=confidence,
                flags=flags,
                **activity_kwargs,
            )
            counts.raw_records += 1
            counts.activities += 1 if activity else 0
            counts.warnings += 1 if flags else 0

    complete_batch(batch, counts)
    return counts


def normalize_travel_segment(trip, segment, flags):
    segment_type = segment["type"]
    base_details = {
        "booking_id": trip["bookingId"],
        "trip_name": trip.get("tripName"),
        "booking_status": trip.get("bookingStatus"),
        "employee_id": trip.get("employeeId"),
        "segment_type": segment_type,
    }
    if segment_type == "FLIGHT":
        return normalize_flight(segment, base_details, flags)
    if segment_type == "HOTEL":
        return normalize_hotel(segment, base_details, flags)
    if segment_type == "CAR_RENTAL":
        return normalize_car_rental(segment, base_details, flags)
    if segment_type == "RAIL":
        return normalize_rail(segment, base_details, flags)
    flags["unsupported_travel_segment_type"] = segment_type
    return {
        "activity_type": segment_type,
        "scope": 3,
        "scope3_category": 6,
        "raw_quantity": None,
        "raw_unit": "",
        "normalized_quantity": None,
        "normalized_unit": "",
        "conversion_factor_used": None,
        "emission_factor": None,
        "emission_factor_value": None,
        "emission_factor_unit": "",
        "co2e_kg": None,
        "details": base_details,
    }


def normalize_flight(segment, details, flags):
    origin = segment["origin"]
    destination = segment["destination"]
    distance = great_circle_km(origin, destination)
    if distance is None:
        flags["missing_distance"] = {"origin": origin, "destination": destination}

    distance = quantize(distance)
    cabin = segment.get("cabinClass", "").lower()
    factor_key = "flight_short_haul_economy_with_rf"
    if distance is not None and distance >= Decimal("3700"):
        factor_key = "flight_long_haul_business_with_rf" if cabin == "business" else "flight_long_haul_economy_with_rf"
    factor = factor_by_key(factor_key)
    details.update(
        {
            "airline_code": segment.get("airlineCode"),
            "flight_number": segment.get("flightNumber"),
            "origin": origin,
            "destination": destination,
            "cabin_class": segment.get("cabinClass"),
            "departure_time": segment.get("departureTime"),
            "arrival_time": segment.get("arrivalTime"),
            "distance_source": "great_circle_iata",
            "derived_distance_km": str(distance) if distance is not None else None,
        }
    )
    return {
        "activity_type": EmissionActivity.ActivityType.FLIGHT,
        "scope": 3,
        "scope3_category": 6,
        "activity_start_date": parse_datetime_date(segment["departureTime"]),
        "activity_end_date": parse_datetime_date(segment["arrivalTime"]),
        "raw_quantity": None,
        "raw_unit": "",
        "normalized_quantity": distance,
        "normalized_unit": "passenger_km",
        "conversion_factor_used": None,
        "emission_factor": factor,
        "emission_factor_value": factor.factor_value,
        "emission_factor_unit": factor.factor_unit,
        "co2e_kg": co2e(distance, factor),
        "details": details,
    }


def normalize_hotel(segment, details, flags):
    check_in = parse_date(segment["checkInDate"])
    check_out = parse_date(segment["checkOutDate"])
    nights = max((check_out - check_in).days, 0)
    room_count = decimal_from(segment.get("roomCount", 1)) or Decimal("1")
    room_nights = quantize(room_count * Decimal(nights))
    factor = factor_by_key("hotel_uk_london")
    details.update(
        {
            "hotel_name": segment.get("hotelName"),
            "hotel_city": segment.get("city"),
            "room_count": str(room_count),
            "room_nights": str(room_nights),
        }
    )
    if segment.get("city") != "London":
        flags["hotel_factor_city_proxy"] = segment.get("city")
    return {
        "activity_type": EmissionActivity.ActivityType.HOTEL,
        "scope": 3,
        "scope3_category": 6,
        "activity_start_date": check_in,
        "activity_end_date": check_out,
        "raw_quantity": room_count,
        "raw_unit": "rooms",
        "normalized_quantity": room_nights,
        "normalized_unit": "room_night",
        "conversion_factor_used": Decimal("1"),
        "emission_factor": factor,
        "emission_factor_value": factor.factor_value,
        "emission_factor_unit": factor.factor_unit,
        "co2e_kg": co2e(room_nights, factor),
        "details": details,
    }


def normalize_car_rental(segment, details, flags):
    pickup = parse_date(segment["pickupDate"])
    dropoff = parse_date(segment["dropoffDate"])
    rental_days = max((dropoff - pickup).days, 1)
    distance = decimal_from(segment.get("estimatedDistanceKm"))
    if distance is None:
        distance = Decimal(rental_days * 50)
        flags["car_rental_distance_proxy_used"] = {
            "rental_days": rental_days,
            "proxy_km_per_day": 50,
        }
    distance = quantize(distance)
    factor = factor_by_key("car_rental_petrol_medium")
    details.update(
        {
            "vendor": segment.get("vendor"),
            "vehicle_category": segment.get("vehicleCategory"),
            "fuel_type": segment.get("fuelType"),
            "pickup_location": segment.get("pickupLocation"),
            "dropoff_location": segment.get("dropoffLocation"),
            "rental_days": rental_days,
            "amount": segment.get("amount"),
            "currency": segment.get("currency"),
        }
    )
    return {
        "activity_type": EmissionActivity.ActivityType.CAR_RENTAL,
        "scope": 3,
        "scope3_category": 6,
        "activity_start_date": pickup,
        "activity_end_date": dropoff,
        "raw_quantity": quantize(decimal_from(segment.get("estimatedDistanceKm"))),
        "raw_unit": "km" if segment.get("estimatedDistanceKm") is not None else "",
        "normalized_quantity": distance,
        "normalized_unit": "km",
        "conversion_factor_used": Decimal("1"),
        "emission_factor": factor,
        "emission_factor_value": factor.factor_value,
        "emission_factor_unit": factor.factor_unit,
        "co2e_kg": co2e(distance, factor),
        "details": details,
    }


def normalize_rail(segment, details, flags):
    distance = quantize(decimal_from(segment.get("estimatedDistanceKm")))
    if distance is None:
        flags["missing_distance"] = {"origin": segment.get("origin"), "destination": segment.get("destination")}
    factor = factor_by_key("rail_national")
    details.update(
        {
            "operator": segment.get("operator"),
            "train_number": segment.get("trainNumber"),
            "origin": segment.get("origin"),
            "destination": segment.get("destination"),
            "departure_time": segment.get("departureTime"),
            "arrival_time": segment.get("arrivalTime"),
            "amount": segment.get("amount"),
            "currency": segment.get("currency"),
        }
    )
    return {
        "activity_type": EmissionActivity.ActivityType.RAIL,
        "scope": 3,
        "scope3_category": 6,
        "activity_start_date": parse_datetime_date(segment["departureTime"]),
        "activity_end_date": parse_datetime_date(segment["arrivalTime"]),
        "raw_quantity": distance,
        "raw_unit": "km",
        "normalized_quantity": distance,
        "normalized_unit": "passenger_km",
        "conversion_factor_used": Decimal("1"),
        "emission_factor": factor,
        "emission_factor_value": factor.factor_value,
        "emission_factor_unit": factor.factor_unit,
        "co2e_kg": co2e(distance, factor),
        "details": details,
    }
