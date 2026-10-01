from pathlib import Path
from django.core.management.base import BaseCommand
from routing.services.data_loader import load_fuel_stations_from_csv


class Command(BaseCommand):
    help = "Loads and geocodes fuel prices CSV data into the FuelStation database table."

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv-path",
            type=str,
            default="fuel_prices.csv",
            help="Path to the fuel prices CSV file (defaults to fuel_prices.csv in base dir)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force reload by deleting existing database records",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"])
        force = options["force"]

        self.stdout.write(self.style.NOTICE(f"Loading fuel stations from: {csv_path} (force={force})..."))
        try:
            count = load_fuel_stations_from_csv(csv_path=csv_path, force_reload=force)
            self.stdout.write(self.style.SUCCESS(f"Successfully processed {count} fuel stations in database!"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error loading fuel stations: {e}"))
            raise e
