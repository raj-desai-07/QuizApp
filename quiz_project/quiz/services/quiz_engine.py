"""Quiz logic. No Django dependency; all state is one JSON-serialisable dict.

State shape (stored in request.session["quiz"]):
    {"status": "in_progress" | "complete",
     "order": [question ids], "position": int,
     "answers": {"<question id>": {"selected": int, "correct": bool}}}
"""
import random
from dataclasses import dataclass

PASS_PERCENT = 60
IN_PROGRESS = "in_progress"
COMPLETE = "complete"


class QuizError(Exception):
    """Base class for quiz rule violations."""


class QuizNotInProgress(QuizError):
    pass


class QuizNotComplete(QuizError):
    pass


class AlreadyAnswered(QuizError):
    pass


class NotAnswered(QuizError):
    pass


class InvalidAnswer(QuizError):
    pass


@dataclass(frozen=True)
class AnswerResult:
    selected_index: int
    correct_index: int
    is_correct: bool


@dataclass(frozen=True)
class QuizResults:
    correct: int
    incorrect: int
    total: int
    percentage: float
    passed: bool


class QuizEngine:
    def __init__(self, questions, state=None):
        self._questions = {q.id: q for q in questions}
        self.state = state if self._is_valid(state) else None

    # --- state inspection -------------------------------------------------
    @property
    def is_active(self):
        return self.state is not None

    @property
    def is_in_progress(self):
        return self.state is not None and self.state["status"] == IN_PROGRESS

    @property
    def is_complete(self):
        return self.state is not None and self.state["status"] == COMPLETE

    @property
    def total(self):
        return len(self.state["order"])

    @property
    def position(self):
        return self.state["position"]

    @property
    def number(self):
        """1-based position, for display."""
        return self.position + 1

    @property
    def answered_count(self):
        return len(self.state["answers"])

    @property
    def correct_count(self):
        return sum(1 for record in self.state["answers"].values() if record["correct"])

    # --- actions ----------------------------------------------------------
    def start(self):
        """Begin a new session with a freshly shuffled (then fixed) question order.

        Only the question order is shuffled; options keep their positions, so
        answer_index mapping is untouched.
        """
        order = list(self._questions)
        random.shuffle(order)
        self.state = {
            "status": IN_PROGRESS,
            "order": order,
            "position": 0,
            "answers": {},
        }

    def reset(self):
        self.state = None

    def current_question(self):
        self._require_in_progress()
        return self._questions[self.state["order"][self.position]]

    def is_current_answered(self):
        return str(self.current_question().id) in self.state["answers"]

    def submit_answer(self, selected_index):
        question = self.current_question()
        if self.is_current_answered():
            raise AlreadyAnswered("This question has already been answered.")
        if (
            not isinstance(selected_index, int)
            or isinstance(selected_index, bool)
            or not 0 <= selected_index < len(question.options)
        ):
            raise InvalidAnswer("Selected option does not exist.")
        is_correct = selected_index == question.answer_index
        self.state["answers"][str(question.id)] = {"selected": selected_index, "correct": is_correct}
        return AnswerResult(selected_index, question.answer_index, is_correct)

    def current_feedback(self):
        """Correct answer is only available once the question is answered."""
        question = self.current_question()
        record = self.state["answers"].get(str(question.id))
        if record is None:
            raise NotAnswered("Answer the question first.")
        return AnswerResult(record["selected"], question.answer_index, record["correct"])

    def next_question(self):
        if not self.is_current_answered():
            raise NotAnswered("Answer the question first.")
        if self.position == self.total - 1:
            self.state["status"] = COMPLETE
        else:
            self.state["position"] += 1

    def results(self):
        if not self.is_complete:
            raise QuizNotComplete("The quiz is not finished.")
        total, correct = self.total, self.correct_count
        return QuizResults(
            correct=correct,
            incorrect=total - correct,
            total=total,
            percentage=round(correct * 100 / total, 1),
            passed=correct * 100 >= PASS_PERCENT * total,
        )

    # --- internals --------------------------------------------------------
    def _require_in_progress(self):
        if not self.is_in_progress:
            raise QuizNotInProgress("No quiz is in progress.")

    def _is_valid(self, state):
        """Reject missing/corrupt/stale session state (e.g. questions file changed)."""
        try:
            return self._check(state)
        except (TypeError, KeyError, AttributeError):
            return False

    def _check(self, state):
        status, order = state["status"], state["order"]
        position, answers = state["position"], state["answers"]
        if status not in (IN_PROGRESS, COMPLETE):
            return False
        if not isinstance(order, list) or not order or len(set(order)) != len(order):
            return False
        if any(q_id not in self._questions for q_id in order):
            return False
        if not isinstance(position, int) or isinstance(position, bool) or not 0 <= position < len(order):
            return False
        if not isinstance(answers, dict):
            return False
        valid_keys = {str(q_id) for q_id in order}
        for key, record in answers.items():
            if key not in valid_keys or not isinstance(record["selected"], int) or not isinstance(record["correct"], bool):
                return False
            question = self._questions[int(key)]
            # Never trust stored flags: they must agree with the server's own data.
            if not 0 <= record["selected"] < len(question.options):
                return False
            if record["correct"] != (record["selected"] == question.answer_index):
                return False
        if status == IN_PROGRESS and any(
            order.index(int(key)) > position for key in answers
        ):
            return False  # answers recorded ahead of the current position
        if status == COMPLETE and (len(answers) != len(order) or position != len(order) - 1):
            return False
        return True
