from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from .models import AuditEvent, EmissionActivity, IngestionBatch, Organization


class SampleDataLoadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_sample_data", reset=True, verbosity=0)

    def test_sample_loader_creates_expected_activity_counts(self):
        self.assertEqual(Organization.objects.count(), 1)
        self.assertEqual(IngestionBatch.objects.count(), 3)
        self.assertEqual(
            EmissionActivity.objects.filter(source_type=EmissionActivity.SourceType.SAP).count(),
            3,
        )
        self.assertEqual(
            EmissionActivity.objects.filter(source_type=EmissionActivity.SourceType.UTILITY).count(),
            4,
        )
        self.assertEqual(
            EmissionActivity.objects.filter(source_type=EmissionActivity.SourceType.TRAVEL).count(),
            5,
        )
        self.assertEqual(AuditEvent.objects.filter(action=AuditEvent.Action.CREATED).count(), 12)

    def test_sap_gallons_are_normalized_to_litres(self):
        activity = EmissionActivity.objects.get(details__material_code="10000203")
        self.assertEqual(activity.raw_quantity, Decimal("150.5000"))
        self.assertEqual(activity.raw_unit, "GAL")
        self.assertEqual(activity.normalized_unit, "L")
        self.assertEqual(activity.conversion_factor_used, Decimal("3.78541000"))
        self.assertEqual(activity.normalized_quantity, Decimal("569.7042"))

    def test_utility_mwh_is_normalized_to_kwh(self):
        activity = EmissionActivity.objects.get(
            source_type=EmissionActivity.SourceType.UTILITY,
            activity_start_date="2026-02-12",
        )
        self.assertEqual(activity.raw_quantity, Decimal("14.2000"))
        self.assertEqual(activity.raw_unit, "MWh")
        self.assertEqual(activity.normalized_quantity, Decimal("14200.0000"))
        self.assertEqual(activity.normalized_unit, "kWh")

    def test_car_rental_uses_proxy_distance_and_is_flagged(self):
        activity = EmissionActivity.objects.get(activity_type=EmissionActivity.ActivityType.CAR_RENTAL)
        self.assertEqual(activity.normalized_quantity, Decimal("200.0000"))
        self.assertEqual(activity.normalized_unit, "km")
        self.assertEqual(activity.confidence, EmissionActivity.Confidence.LOW)
        self.assertIn("car_rental_distance_proxy_used", activity.flags)


class ActivityApiTests(TestCase):
    def setUp(self):
        call_command("load_sample_data", reset=True, verbosity=0)
        self.client = APIClient()

    def test_activity_list_filters_by_status_and_scope(self):
        response = self.client.get("/api/activities/", {"status": "pending_review", "scope": 3})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 5)

    def test_approved_activity_can_be_locked_and_then_not_edited(self):
        activity = EmissionActivity.objects.filter(status=EmissionActivity.Status.PENDING_REVIEW).first()

        approve_response = self.client.post(f"/api/activities/{activity.id}/approve/", {"reason": "Looks right"})
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.data["status"], EmissionActivity.Status.APPROVED)

        lock_response = self.client.post(f"/api/activities/{activity.id}/lock/", {"reason": "Ready for audit"})
        self.assertEqual(lock_response.status_code, 200)
        self.assertEqual(lock_response.data["status"], EmissionActivity.Status.LOCKED)

        patch_response = self.client.patch(
            f"/api/activities/{activity.id}/",
            {"normalized_quantity": "1.0000"},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 400)
        self.assertIn("Locked activities cannot be edited", patch_response.data["detail"])

    def test_batch_endpoint_includes_summary_counts(self):
        response = self.client.get("/api/batches/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 3)
        total_activities = sum(batch["activity_count"] for batch in response.data)
        self.assertEqual(total_activities, 12)

# Create your tests here.
