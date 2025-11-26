from django.urls import path
from .views import home, search_article

urlpatterns = [
    path("", home, name="home"),
    path("search/", search_article, name="search_article"),
]
