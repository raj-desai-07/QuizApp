# Quiz App (Django)

A server-rendered quiz application built with Django. Questions are loaded from `data/questions.json`, shown one at a time with instant feedback, scored on the server, and the best results are kept on a persistent top-5 leaderboard.

## Features
- Questions loaded from `data/questions.json` on every request (never hard-coded).
- Start page with question count, pass mark and required player name.
- One question at a time, single-choice answers, "Question X of N" and a progress bar, running score.
- Feedback after each answer (correct/incorrect and the correct answer); answers are locked once submitted and duplicate submissions are ignored.
- Results page: score, percentage, PASS (>= 60%) or FAIL.
- Restart from the results page or mid-quiz (with confirmation); state is fully reset and the session key is rotated.
- Graceful handling of a missing, empty or invalid questions file, an empty list, and malformed questions.
- Server-side scoring and validation: invalid indexes, stale or forged forms, premature results access and post-completion submissions are rejected; CSRF protection on all POST views.

## Stretch goals implemented
1. **Shuffle** – question order is shuffled per quiz session with Python's `random` and stays fixed for that session; restart reshuffles. Options are not shuffled, so `answerIndex` stays correct.
2. **High-score list** – top 5 results (name, score, total, percentage, date/time) stored with the Django ORM in SQLite. Ranking: percentage, then score, then earlier completion. Saved once per completed quiz and shown on the results page and at `/leaderboard/`.

The optional timer is **not** implemented.

## Technologies
Python 3.10+, Django 4.2–5.x, SQLite, server-side sessions, plain HTML/CSS/vanilla JS (no external CDN).

## Project structure
```
quiz_project/
├── manage.py
├── requirements.txt
├── data/questions.json            # question file (path: QUESTIONS_FILE in settings)
├── quiz_project/                  # settings, root URLs, wsgi/asgi
└── quiz/
    ├── models.py                  # LeaderboardEntry (top-5 logic)
    ├── views.py, forms.py, urls.py
    ├── migrations/
    ├── services/
    │   ├── question_loader.py     # JSON reading + validation (no Django)
    │   └── quiz_engine.py         # scoring, navigation, shuffle, state (no Django)
    ├── templates/quiz/            # base, home, question, results, leaderboard, error
    ├── static/quiz/               # style.css, quiz.js
    └── tests/                     # loader, engine, views, part 3 (shuffle/leaderboard/security)
```

## Installation (Windows, PowerShell)
```powershell
cd quiz_project
python -m venv .venv
.venv\Scripts\Activate.ps1          # in cmd.exe: .venv\Scripts\activate.bat
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```
Open http://127.0.0.1:8000/. If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process RemoteSigned` first.

macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate`, then the same pip/manage.py commands.

## Tests
```
python manage.py test
python manage.py check
python manage.py makemigrations --check --dry-run
```

## Question file format
```json
{
  "title": "JavaScript Basics",
  "questions": [
    { "id": 1, "question": "Which keyword declares a constant?", "options": ["var", "let", "const", "static"], "answerIndex": 2 }
  ]
}
```
- `title`: non-empty text. `questions`: list of 1 or more items (works with 1 or 50+).
- Each question: unique integer `id`, non-empty `question`, 2–6 non-empty text `options`, zero-based integer `answerIndex` inside `options`.
- To customise, edit `data/questions.json` (or point `QUESTIONS_FILE` in `quiz_project/settings.py` to another file). No restart needed; it is re-read on every request. Avoid editing it in the middle of a running quiz: a session whose questions no longer match is discarded.

## Malformed question policy
Malformed questions (bad `id`, empty text, option count outside 2–6, invalid `answerIndex`, duplicate `id`) are **skipped**; the start page reports how many. If the file is missing, empty, not valid JSON, has no `title`/`questions` list, an empty list, or no valid questions left, an error page with recovery steps is shown (HTTP 503).

## Configuration
| Environment variable | Purpose |
|---|---|
| `DJANGO_DEBUG` | `1` (default) for development; set `0` for production |
| `DJANGO_SECRET_KEY` | Required when `DJANGO_DEBUG=0` (app refuses to start without it) |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts for production |
| `DJANGO_HTTPS` | `1` to mark session/CSRF cookies Secure behind HTTPS |

## Known limitations
- Development server only; production deployment would need a WSGI server and static file serving (e.g. `collectstatic` + WhiteNoise/nginx) – not set up here.
- Player names are not unique or authenticated; anyone can enter any name.
- Leaderboard saves only when a result ranks in the top 5; lower results are discarded.
- Quiz state is per browser session; no accounts or history.
- Options are not shuffled; no timer.

## Future improvements
Option shuffling, per-question timer, per-player history, rate limiting, production static file setup, UI/browser tests.
