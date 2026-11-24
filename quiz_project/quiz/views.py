from functools import wraps

from django.conf import settings
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from .forms import AnswerForm, PlayerForm
from .models import LeaderboardEntry
from .services.question_loader import QuestionLoadError, load_questions
from .services.quiz_engine import PASS_PERCENT, AlreadyAnswered, NotAnswered, QuizEngine

SESSION_KEY = "quiz"
PLAYER_KEY = "player"
SAVED_KEY = "leaderboard_entry"  # pk of this session's entry; makes saving idempotent


# --- helpers ---------------------------------------------------------------
def error_page(request, message, status=500):
    context = {"message": message, "is_data_error": status == 503, "questions_file": settings.QUESTIONS_FILE}
    return render(request, "quiz/error.html", context, status=status)


def _player(request):
    return request.session.get(PLAYER_KEY, "")


def with_engine(view):
    """Load questions and build an engine from the session; show an error page on load failure."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            data = load_questions(settings.QUESTIONS_FILE)
        except QuestionLoadError as exc:
            return error_page(request, str(exc), status=503)
        engine = QuizEngine(data.questions, request.session.get(SESSION_KEY))
        return view(request, engine, data, *args, **kwargs)

    return wrapper


def post_only(view):
    """State-changing actions accept POST only; other methods go back home."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.method != "POST":
            return redirect("quiz:home")
        return view(request, *args, **kwargs)

    return wrapper


def _fresh_session(request, player_name=""):
    """Flush all quiz data and rotate the session key; keep only the player name."""
    request.session.flush()
    if player_name:
        request.session[PLAYER_KEY] = player_name


def _record_result(request, engine):
    """Save a completed quiz to the leaderboard exactly once per session."""
    if SAVED_KEY in request.session:
        return
    result = engine.results()
    entry = LeaderboardEntry.record(_player(request), result.correct, result.total)
    request.session[SAVED_KEY] = entry.pk if entry else 0


def _save(request, engine):
    if engine.state is None:
        request.session.pop(SESSION_KEY, None)
    else:
        request.session[SESSION_KEY] = engine.state


def _redirect_unless_in_progress(engine):
    if engine.is_complete:
        return redirect("quiz:results")
    if not engine.is_in_progress:
        return redirect("quiz:home")
    return None


def _render_question(request, engine, data, error="", status=200):
    question = engine.current_question()
    feedback = engine.current_feedback() if engine.is_current_answered() else None
    options = []
    for index, text in enumerate(question.options):
        css = ""
        if feedback and index == feedback.correct_index:
            css = "correct"
        elif feedback and index == feedback.selected_index:
            css = "wrong"
        options.append({"index": index, "text": text, "css": css})
    context = {
        "title": data.title,
        "question": question.text,
        "options": options,
        "number": engine.number,
        "total": engine.total,
        "position": engine.position,
        "score": engine.correct_count,
        "progress_percent": engine.answered_count * 100 // engine.total,
        "feedback": feedback,
        "correct_text": question.options[feedback.correct_index] if feedback else "",
        "is_last": engine.number == engine.total,
        "error": error,
        "player": _player(request),
    }
    return render(request, "quiz/question.html", context, status=status)


def _posted_position(request):
    try:
        return int(request.POST.get("position", ""))
    except ValueError:
        return None


# --- views -----------------------------------------------------------------
def _render_home(request, engine, data, error="", player_name="", status=200):
    context = {
        "title": data.title,
        "total": len(data.questions),
        "skipped_count": len(data.skipped),
        "pass_percent": PASS_PERCENT,
        "in_progress": engine.is_in_progress,
        "error": error,
        "player_name": player_name or _player(request),
        "max_name": PlayerForm.MAX_LENGTH,
    }
    return render(request, "quiz/home.html", context, status=status)


@require_GET
@with_engine
def home(request, engine, data):
    return _render_home(request, engine, data)


@post_only
@with_engine
def start(request, engine, data):
    form = PlayerForm(request.POST)
    if not form.is_valid():
        message = next(iter(form.errors.values()))[0]
        return _render_home(
            request, engine, data, error=message, player_name=request.POST.get("player_name", "").strip()[:200], status=400
        )
    _fresh_session(request, form.cleaned_data["player_name"])
    engine.start()
    _save(request, engine)
    return redirect("quiz:question")


@require_GET
@with_engine
def question(request, engine, data):
    response = _redirect_unless_in_progress(engine)
    if response:
        return response
    return _render_question(request, engine, data)


@post_only
@with_engine
def answer(request, engine, data):
    response = _redirect_unless_in_progress(engine)
    if response:
        return response
    form = AnswerForm(request.POST, option_count=len(engine.current_question().options))
    if not form.is_valid():
        message = next(iter(form.errors.values()))[0]
        return _render_question(request, engine, data, error=message, status=400)
    if form.cleaned_data["position"] != engine.position:
        return redirect("quiz:question")  # stale form (e.g. another tab)
    try:
        engine.submit_answer(form.cleaned_data["choice"])
    except AlreadyAnswered:
        return redirect("quiz:question")  # answers are locked
    _save(request, engine)
    return redirect("quiz:question")


@post_only
@with_engine
def next_question(request, engine, data):
    response = _redirect_unless_in_progress(engine)
    if response:
        return response
    if _posted_position(request) != engine.position:
        return redirect("quiz:question")
    try:
        engine.next_question()
    except NotAnswered:
        return _render_question(
            request, engine, data, error="Please answer the question before continuing.", status=400
        )
    _save(request, engine)
    if engine.is_complete:
        _record_result(request, engine)
        return redirect("quiz:results")
    return redirect("quiz:question")


@require_GET
@with_engine
def results(request, engine, data):
    if not engine.is_complete:
        return redirect("quiz:question" if engine.is_in_progress else "quiz:home")
    _record_result(request, engine)  # no-op if already saved
    context = {
        "title": data.title,
        "results": engine.results(),
        "pass_percent": PASS_PERCENT,
        "player": _player(request),
        "leaderboard": LeaderboardEntry.top(),
        "my_entry_id": request.session.get(SAVED_KEY),
    }
    return render(request, "quiz/results.html", context)


@require_GET
def leaderboard(request):
    context = {
        "leaderboard": LeaderboardEntry.top(),
        "my_entry_id": request.session.get(SAVED_KEY),
        "player": _player(request),
    }
    return render(request, "quiz/leaderboard.html", context)


@post_only
def restart(request):
    _fresh_session(request, _player(request))
    return redirect("quiz:home")


# --- error handlers ---------------------------------------------------------
def not_found(request, exception=None):
    return error_page(request, "That page does not exist.", status=404)


def server_error(request):
    return error_page(request, "Something went wrong. Please try again.", status=500)


def csrf_failed(request, reason=""):
    return error_page(request, "Your session expired or the request was invalid. Please go back and try again.", status=403)
