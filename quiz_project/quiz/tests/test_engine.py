import json

from django.test import SimpleTestCase

from quiz.services.question_loader import Question
from quiz.services.quiz_engine import (
    AlreadyAnswered,
    InvalidAnswer,
    NotAnswered,
    QuizEngine,
    QuizNotComplete,
    QuizNotInProgress,
)


def make_questions(count):
    # Correct option is always index 1; each question has 3 options.
    return [Question(i, f"Q{i}?", ("a", "b", "c"), 1) for i in range(1, count + 1)]


def play(engine, choices):
    for choice in choices:
        engine.submit_answer(choice)
        engine.next_question()


class EngineTests(SimpleTestCase):
    def started(self, count=3):
        engine = QuizEngine(make_questions(count))
        engine.start()
        return engine

    def test_start_sets_initial_state(self):
        engine = self.started()
        self.assertTrue(engine.is_in_progress)
        self.assertEqual((engine.number, engine.total, engine.correct_count), (1, 3, 0))

    def test_inactive_engine_rejects_actions(self):
        engine = QuizEngine(make_questions(2))
        self.assertFalse(engine.is_active)
        with self.assertRaises(QuizNotInProgress):
            engine.submit_answer(0)

    def test_correct_and_incorrect_answers(self):
        engine = self.started()
        self.assertTrue(engine.submit_answer(1).is_correct)
        engine.next_question()
        result = engine.submit_answer(0)
        self.assertFalse(result.is_correct)
        self.assertEqual((result.selected_index, result.correct_index), (0, 1))
        self.assertEqual(engine.correct_count, 1)

    def test_answer_is_locked(self):
        engine = self.started()
        engine.submit_answer(0)
        with self.assertRaises(AlreadyAnswered):
            engine.submit_answer(1)
        self.assertEqual(engine.correct_count, 0)

    def test_invalid_answer_index(self):
        engine = self.started()
        for bad in (-1, 3, "1", None, True):
            with self.subTest(bad=bad), self.assertRaises(InvalidAnswer):
                engine.submit_answer(bad)
        self.assertEqual(engine.answered_count, 0)

    def test_cannot_advance_or_peek_without_answering(self):
        engine = self.started()
        with self.assertRaises(NotAnswered):
            engine.next_question()
        with self.assertRaises(NotAnswered):
            engine.current_feedback()
        self.assertEqual(engine.number, 1)

    def test_navigation_and_completion(self):
        engine = self.started(2)
        engine.submit_answer(1)
        engine.next_question()
        self.assertEqual(engine.number, 2)
        engine.submit_answer(1)
        engine.next_question()
        self.assertTrue(engine.is_complete)
        with self.assertRaises(QuizNotInProgress):
            engine.current_question()

    def test_results_only_after_completion(self):
        engine = self.started(2)
        with self.assertRaises(QuizNotComplete):
            engine.results()

    def test_pass_threshold_is_60_percent(self):
        cases = {(3, 5): True, (2, 5): False, (6, 10): True, (5, 10): False, (1, 1): True, (0, 1): False}
        for (right, total), expected in cases.items():
            with self.subTest(right=right, total=total):
                engine = self.started(total)
                play(engine, [1] * right + [0] * (total - right))
                results = engine.results()
                self.assertEqual(results.passed, expected)
                self.assertEqual((results.correct, results.incorrect), (right, total - right))

    def test_percentage(self):
        engine = self.started(3)
        play(engine, [1, 1, 0])
        self.assertEqual(engine.results().percentage, 66.7)

    def test_reset_clears_state(self):
        engine = self.started()
        engine.submit_answer(1)
        engine.reset()
        self.assertFalse(engine.is_active)
        engine.start()
        self.assertEqual((engine.number, engine.correct_count, engine.answered_count), (1, 0, 0))

    def test_state_survives_json_round_trip(self):
        engine = self.started()
        engine.submit_answer(1)
        restored = QuizEngine(make_questions(3), json.loads(json.dumps(engine.state)))
        self.assertTrue(restored.is_in_progress)
        self.assertTrue(restored.is_current_answered())
        self.assertEqual(restored.correct_count, 1)

    def test_invalid_or_stale_state_is_ignored(self):
        engine = self.started(3)
        engine.submit_answer(1)
        good = json.loads(json.dumps(engine.state))
        self.assertFalse(QuizEngine(make_questions(2), good).is_active)  # question 3 no longer exists
        bad_states = [
            None,
            {},
            "x",
            {**good, "position": 9},
            {**good, "status": "weird"},
            {**good, "order": []},
            {**good, "answers": {"99": {"selected": 0, "correct": True}}},
            {**good, "status": "complete"},  # complete but unanswered questions
        ]
        for state in bad_states:
            with self.subTest(state=state):
                self.assertFalse(QuizEngine(make_questions(3), state).is_active)
