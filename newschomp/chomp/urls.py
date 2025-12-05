from django.urls import path
from .views import home, search_article, fetch_doorcountypulse, fetch_urbanmilwaukee, fetch_lataco

urlpatterns = [
    path("", home, name="home"),
    path("search/", search_article, name="search_article"),
    path("fetch-doorcountypulse/", fetch_doorcountypulse, name="fetch_doorcountypulse"),
    path("fetch-urbanmilwaukee/", fetch_urbanmilwaukee, name="fetch_urbanmilwaukee"),
    path("fetch-lataco/", fetch_lataco, name="fetch_lataco"),
]
