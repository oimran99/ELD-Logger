from django.db import models


class Trip(models.Model):
    """A planned trip and its computed HOS result (stored for history/audit)."""

    current_location = models.CharField(max_length=255)
    pickup_location = models.CharField(max_length=255)
    dropoff_location = models.CharField(max_length=255)
    current_cycle_used = models.FloatField(help_text="Cycle hours already used (70/8).")
    start_time = models.DateTimeField(null=True, blank=True)

    result = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Log-sheet header details (filled in by the driver for the PDF export).
    driver_name = models.CharField(max_length=255, blank=True, default="")
    co_driver_name = models.CharField(max_length=255, blank=True, default="")
    carrier_name = models.CharField(max_length=255, blank=True, default="")
    main_office_address = models.CharField(max_length=255, blank=True, default="")
    home_terminal_address = models.CharField(max_length=255, blank=True, default="")
    truck_trailer_numbers = models.CharField(max_length=255, blank=True, default="")
    shipping_document = models.CharField(max_length=255, blank=True, default="")
    shipper_commodity = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.current_location} → {self.dropoff_location} ({self.created_at:%Y-%m-%d})"
