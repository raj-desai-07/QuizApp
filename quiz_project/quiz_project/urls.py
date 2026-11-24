"""Root URL configuration."""
from django.urls import include, path

urlpatterns = [
    path("", include("quiz.urls")),
]

handler404 = "quiz.views.not_found"
handler500 = "quiz.views.server_error"
