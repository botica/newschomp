from django.urls import path
from .views import home, search_article, fetch_doorcountypulse

urlpatterns = [
    path("", home, name="home"),
    path("search/", search_article, name="search_article"),
    path("fetch-doorcountypulse/", fetch_doorcountypulse, name="fetch_doorcountypulse"),
]
