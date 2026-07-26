from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health_view, name="health"),
    path("plan-trip/", views.plan_trip_view, name="plan-trip"),
    path("trips/<int:pk>/", views.trip_detail_view, name="trip-detail"),
    path("trips/<int:pk>/pdf/", views.trip_pdf_view, name="trip-pdf"),
]
