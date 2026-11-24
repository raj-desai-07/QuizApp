"""Reads and validates quiz questions from a JSON file. No Django dependency."""
import json
from dataclasses import dataclass
from pathlib import Path

MIN_OPTIONS = 2
MAX_OPTIONS = 6


class QuestionLoadError(Exception):
    """Raised when no usable questions can be loaded. Message is user-safe."""


@dataclass(frozen=True)
class Question:
    id: int
    text: str
    options: tuple
    answer_index: int


@dataclass(frozen=True)
class QuizData:
    title: str
    questions: tuple
    skipped: tuple = ()  # reasons for each malformed question that was skipped


def load_questions(path):
    """Load and validate the file at `path`. Raises QuestionLoadError."""
    try:
        raw = Path(path).read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise QuestionLoadError("The questions file could not be found.") from None
    except (OSError, ValueError):
        raise QuestionLoadError("The questions file could not be read.") from None
    if not raw.strip():
        raise QuestionLoadError("The questions file is empty.")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise QuestionLoadError("The questions file is not valid JSON.") from None
    return parse_quiz(payload)


def parse_quiz(payload):
    """Validate decoded JSON; skip malformed questions, keep the valid ones."""
    if not isinstance(payload, dict):
        raise QuestionLoadError("The questions file must be a JSON object with 'title' and 'questions'.")
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        raise QuestionLoadError("The questions file needs a non-empty 'title'.")
    items = payload.get("questions")
    if not isinstance(items, list):
        raise QuestionLoadError("The questions file needs a 'questions' list.")
    if not items:
        raise QuestionLoadError("The questions file contains no questions.")

    questions, skipped, seen_ids = [], [], set()
    for number, item in enumerate(items, start=1):
        try:
            question = _parse_question(item)
        except ValueError as exc:
            skipped.append(f"Question #{number}: {exc}")
            continue
        if question.id in seen_ids:
            skipped.append(f"Question #{number}: duplicate id {question.id}")
            continue
        seen_ids.add(question.id)
        questions.append(question)

    if not questions:
        raise QuestionLoadError("The questions file has no valid questions.")
    return QuizData(title.strip(), tuple(questions), tuple(skipped))


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_text(value):
    return isinstance(value, str) and bool(value.strip())


def _parse_question(item):
    if not isinstance(item, dict):
        raise ValueError("must be an object")
    if not _is_int(item.get("id")):
        raise ValueError("'id' must be an integer")
    if not _is_text(item.get("question")):
        raise ValueError("'question' must be non-empty text")
    options = item.get("options")
    if not isinstance(options, list) or not MIN_OPTIONS <= len(options) <= MAX_OPTIONS:
        raise ValueError(f"'options' must be a list of {MIN_OPTIONS}-{MAX_OPTIONS} items")
    if not all(_is_text(option) for option in options):
        raise ValueError("every option must be non-empty text")
    answer_index = item.get("answerIndex")
    if not _is_int(answer_index) or not 0 <= answer_index < len(options):
        raise ValueError("'answerIndex' must be a valid option position")
    return Question(
        id=item["id"],
        text=item["question"].strip(),
        options=tuple(option.strip() for option in options),
        answer_index=answer_index,
    )
