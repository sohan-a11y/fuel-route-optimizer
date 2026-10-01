from django.db import models


class FuelStation(models.Model):
    opis_id = models.IntegerField(verbose_name="OPIS Truckstop ID", db_index=True)
    name = models.CharField(max_length=255, verbose_name="Truckstop Name")
    address = models.CharField(max_length=255, verbose_name="Address")
    city = models.CharField(max_length=100, db_index=True)
    state = models.CharField(max_length=10, db_index=True)
    rack_id = models.IntegerField(null=True, blank=True, verbose_name="Rack ID")
    retail_price = models.DecimalField(
        max_digits=7, decimal_places=4, db_index=True, verbose_name="Retail Price ($/gal)"
    )
    latitude = models.FloatField(db_index=True)
    longitude = models.FloatField(db_index=True)

    class Meta:
        verbose_name = "Fuel Station"
        verbose_name_plural = "Fuel Stations"
        indexes = [
            models.Index(fields=["latitude", "longitude"], name="idx_fuelstation_lat_lon"),
            models.Index(fields=["state", "city"], name="idx_fuelstation_state_city"),
            models.Index(fields=["retail_price"], name="idx_fuelstation_price"),
        ]
        ordering = ["retail_price"]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state}) - ${self.retail_price}/gal"
