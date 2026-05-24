from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from emissions.models import Organization
from emissions.services.ingestion import (
    ingest_sap,
    ingest_travel,
    ingest_utility,
    load_emission_factors,
)


class Command(BaseCommand):
    help = "Load the assignment sample data into a demo organization."

    def add_arguments(self, parser):
        parser.add_argument(
            "--data-root",
            default=str(settings.PROJECT_ROOT / "data"),
            help="Path to the reorganized data directory.",
        )
        parser.add_argument(
            "--organization",
            default="Demo Enterprise Client",
            help="Organization name to load data into.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete the named demo organization before loading sample data.",
        )

    def handle(self, *args, **options):
        data_root = Path(options["data_root"]).resolve()
        org_name = options["organization"]

        if options["reset"]:
            Organization.objects.filter(name=org_name).delete()

        organization, _ = Organization.objects.get_or_create(name=org_name)
        load_emission_factors(data_root)

        sap_counts = ingest_sap(organization, data_root)
        utility_counts = ingest_utility(organization, data_root)
        travel_counts = ingest_travel(organization, data_root)

        if options["verbosity"] > 0:
            self.stdout.write(self.style.SUCCESS(f"Loaded sample data for {organization.name}"))
            self.stdout.write(
                f"SAP: {sap_counts.activities} activities, {sap_counts.warnings} warnings"
            )
            self.stdout.write(
                f"Utility: {utility_counts.activities} activities, {utility_counts.warnings} warnings"
            )
            self.stdout.write(
                f"Travel: {travel_counts.activities} activities, {travel_counts.warnings} warnings"
            )
