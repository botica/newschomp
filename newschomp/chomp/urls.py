from django.urls import path
from .views import home, refresh_article, get_nearest_source, fetch_from_source

urlpatterns = [
    path("", home, name="home"),
    path("refresh/<str:category>/", refresh_article, name="refresh_article"),
    path("nearest-source/", get_nearest_source, name="nearest_source"),
    path("fetch-local/<str:source_name>/", fetch_from_source, name="fetch_from_source"),
]
