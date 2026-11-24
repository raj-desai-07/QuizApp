from django.urls import path

from . import views

app_name = "quiz"

urlpatterns = [
    path("", views.home, name="home"),
    path("start/", views.start, name="start"),
    path("question/", views.question, name="question"),
    path("answer/", views.answer, name="answer"),
    path("next/", views.next_question, name="next"),
    path("results/", views.results, name="results"),
    path("leaderboard/", views.leaderboard, name="leaderboard"),
    path("restart/", views.restart, name="restart"),
]
