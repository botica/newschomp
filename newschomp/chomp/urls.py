from django.urls import path
from .views import home, search_article, fetch_doorcountypulse, fetch_urbanmilwaukee, fetch_lataco, fetch_stlmag, fetch_blockclubchicago, fetch_gothamist

urlpatterns = [
    path("", home, name="home"),
    path("search/", search_article, name="search_article"),
    path("fetch-doorcountypulse/", fetch_doorcountypulse, name="fetch_doorcountypulse"),
    path("fetch-urbanmilwaukee/", fetch_urbanmilwaukee, name="fetch_urbanmilwaukee"),
    path("fetch-lataco/", fetch_lataco, name="fetch_lataco"),
    path("fetch-stlmag/", fetch_stlmag, name="fetch_stlmag"),
    path("fetch-blockclubchicago/", fetch_blockclubchicago, name="fetch_blockclubchicago"),
    path("fetch-gothamist/", fetch_gothamist, name="fetch_gothamist"),
]
