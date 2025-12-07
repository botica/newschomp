from django.urls import path
from .views import home, search_article, fetch_article_from_source

urlpatterns = [
    path("", home, name="home"),
    path("search/", search_article, name="search_article"),
    path("fetch/<str:source_name>/", fetch_article_from_source, name="fetch_article"),
]
