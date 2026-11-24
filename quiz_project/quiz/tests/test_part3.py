"""Part 3 tests: shuffle, leaderboard, security, integration."""
import json
import random
import tempfile
from pathlib import Path

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from quiz.forms import PlayerForm
from quiz.models import LEADERBOARD_SIZE, LeaderboardEntry
from quiz.services.question_loader import Question
from quiz.services.quiz_engine import QuizEngine

N = 8
QUIZ = {
    "title": "Shuffle Quiz",
    "questions": [
        {"id": i, "question": f"Q{i}?", "options": ["w", "x", "y", "z"], "answerIndex": i % 4}
        for i in range(1, N + 1)
    ],
}
ANSWER = {q["id"]: q["answerIndex"] for q in QUIZ["questions"]}


def questions():
    return [Question(q["id"], q["question"], tuple(q["options"]), q["answerIndex"]) for q in QUIZ["questions"]]


class ShuffleEngineTests(TestCase):
    def test_order_is_permutation_and_varies(self):
        orders = set()
        for seed in range(20):
            random.seed(seed)
            engine = QuizEngine(questions())
            engine.start()
            order = engine.state["order"]
            self.assertEqual(sorted(order), sorted(ANSWER))
            orders.add(tuple(order))
        self.assertGreater(len(orders), 1)

    def test_order_stable_during_session(self):
        engine = QuizEngine(questions())
        engine.start()
        order = list(engine.state["order"])
        for _ in range(N):
            engine.submit_answer(0)
            engine.next_question()
        self.assertEqual(engine.state["order"], order)
        rebuilt = QuizEngine(questions(), engine.state)  # as reloaded from the session
        self.assertEqual(rebuilt.state["order"], order)

    def test_correct_mapping_preserved_after_shuffle(self):
        random.seed(3)
        engine = QuizEngine(questions())
        engine.start()
        for q_id in list(engine.state["order"]):
            question = engine.current_question()
            self.assertEqual(question.id, q_id)
            result = engine.submit_answer(ANSWER[q_id])
            self.assertTrue(result.is_correct)
            self.assertEqual(result.correct_index, ANSWER[q_id])
            engine.next_question()
        self.assertEqual(engine.results().correct, N)

    def test_restart_generates_new_order(self):
        engine = QuizEngine(questions())
        seen = set()
        for _ in range(15):
            engine.start()
            seen.add(tuple(engine.state["order"]))
        self.assertGreater(len(seen), 1)

    def test_tampered_state_rejected(self):
        engine = QuizEngine(questions())
        engine.start()
        engine.submit_answer(0)
        state = json.loads(json.dumps(engine.state))
        key = next(iter(state["answers"]))
        state["answers"][key]["correct"] = True  # forged
        state["answers"][key]["selected"] = (ANSWER[int(key)] + 1) % 4
        self.assertFalse(QuizEngine(questions(), state).is_active)
        state["answers"][key] = {"selected": 99, "correct": False}
        self.assertFalse(QuizEngine(questions(), state).is_active)


class BaseViewCase(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "questions.json"
        path.write_text(json.dumps(QUIZ), encoding="utf-8")
        override = override_settings(QUESTIONS_FILE=path)
        override.enable()
        self.addCleanup(override.disable)

    def state(self):
        return self.client.session["quiz"]

    def start(self, name="Ada"):
        return self.client.post(reverse("quiz:start"), {"player_name": name})

    def current_id(self):
        return self.state()["order"][self.state()["position"]]

    def play(self, correct_count, name="Ada"):
        """Complete a quiz answering `correct_count` questions correctly."""
        self.start(name)
        for i in range(N):
            q_id = self.current_id()
            choice = ANSWER[q_id] if i < correct_count else (ANSWER[q_id] + 1) % 4
            self.client.post(reverse("quiz:answer"), {"position": i, "choice": choice})
            self.client.post(reverse("quiz:next"), {"position": i})


class ShuffleViewTests(BaseViewCase):
    def test_shuffled_flow_scores_accurately(self):
        random.seed(1)
        self.play(5)
        self.assertEqual(self.client.get(reverse("quiz:results")).context["results"].correct, 5)

    def test_shown_question_matches_session_order(self):
        self.start()
        for i in range(N):
            response = self.client.get(reverse("quiz:question"))
            self.assertContains(response, f"Q{self.current_id()}?")
            self.assertContains(response, f"Question {i + 1} of {N}")
            self.client.post(reverse("quiz:answer"), {"position": i, "choice": 0})
            self.client.post(reverse("quiz:next"), {"position": i})

    def test_order_stable_on_refresh_and_new_after_restart(self):
        self.start()
        first = self.state()["order"]
        self.client.get(reverse("quiz:question"))
        self.assertEqual(self.state()["order"], first)
        orders = {tuple(first)}
        for _ in range(12):
            self.client.post(reverse("quiz:restart"))
            self.start()
            orders.add(tuple(self.state()["order"]))
        self.assertGreater(len(orders), 1)


class LeaderboardModelTests(TestCase):
    def test_creation_fields(self):
        entry = LeaderboardEntry.record("Ann", 3, 4)
        entry.refresh_from_db()
        self.assertEqual((entry.player_name, entry.score, entry.total_questions, entry.percentage), ("Ann", 3, 4, 75.0))
        self.assertIsNotNone(entry.completed_at)

    def test_ordering_percentage_then_score_then_time(self):
        a = LeaderboardEntry.record("low", 1, 4)  # 25%
        b = LeaderboardEntry.record("tie-early", 2, 4)  # 50%, score 2
        c = LeaderboardEntry.record("tie-late", 2, 4)  # 50%, score 2, later
        d = LeaderboardEntry.record("bigger", 4, 8)  # 50%, score 4
        e = LeaderboardEntry.record("best", 4, 4)  # 100%
        names = [x.player_name for x in LeaderboardEntry.top()]
        self.assertEqual(names, ["best", "bigger", "tie-early", "tie-late", "low"])

    def test_percentage_beats_raw_score(self):
        LeaderboardEntry.record("many", 6, 10)  # 60%
        LeaderboardEntry.record("few", 2, 2)  # 100%
        self.assertEqual(LeaderboardEntry.top()[0].player_name, "few")

    def test_only_top_five_kept(self):
        for score in range(1, 9):
            LeaderboardEntry.record(f"p{score}", score, 8)
        self.assertEqual(LeaderboardEntry.objects.count(), LEADERBOARD_SIZE)
        self.assertEqual(
            sorted(LeaderboardEntry.objects.values_list("score", flat=True)), [4, 5, 6, 7, 8]
        )

    def test_low_score_not_added_when_full(self):
        for _ in range(5):
            LeaderboardEntry.record("top", 8, 8)
        self.assertIsNone(LeaderboardEntry.record("late", 0, 8))
        self.assertFalse(LeaderboardEntry.objects.filter(player_name="late").exists())

    def test_persistence_in_database(self):
        LeaderboardEntry.record("Ann", 3, 4)
        self.assertEqual(LeaderboardEntry.objects.get().player_name, "Ann")  # re-read from SQLite

    def test_score_cannot_exceed_total(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            LeaderboardEntry.objects.create(player_name="x", score=5, total_questions=4, percentage=125)


class LeaderboardViewTests(BaseViewCase):
    def test_leaderboard_page_empty_and_filled(self):
        self.assertContains(self.client.get(reverse("quiz:leaderboard")), "No scores yet")
        self.play(8, "Zed")
        self.assertContains(self.client.get(reverse("quiz:leaderboard")), "Zed")

    def test_completion_saves_once_and_shows_on_results(self):
        self.play(6, "Bea")
        entry = LeaderboardEntry.objects.get()
        self.assertEqual((entry.player_name, entry.score, entry.total_questions, entry.percentage), ("Bea", 6, N, 75.0))
        for _ in range(3):  # repeated requests must not duplicate
            response = self.client.get(reverse("quiz:results"))
        self.assertContains(response, "Bea")
        self.client.post(reverse("quiz:next"), {"position": N - 1})
        self.assertEqual(LeaderboardEntry.objects.count(), 1)

    def test_incomplete_quiz_not_saved(self):
        self.start()
        self.client.post(reverse("quiz:answer"), {"position": 0, "choice": 0})
        self.client.get(reverse("quiz:results"))
        self.assertEqual(LeaderboardEntry.objects.count(), 0)

    def test_leaderboard_updates_after_each_completed_quiz(self):
        self.play(4, "A")
        self.client.post(reverse("quiz:restart"))
        self.play(8, "B")
        self.assertEqual([e.player_name for e in LeaderboardEntry.top()], ["B", "A"])

    def test_invalid_names_rejected_and_no_session(self):
        for bad in ["", "   ", "x" * 41, "!!!", "bad\x00name", "bad\x07"]:
            with self.subTest(name=bad):
                self.assertEqual(self.start(bad).status_code, 400)
                self.assertNotIn("quiz", self.client.session)

    def test_name_normalised_and_escaped(self):
        self.play(8, "  <b>Eve</b>   Jr ")
        page = self.client.get(reverse("quiz:results")).content.decode()
        self.assertIn("&lt;b&gt;Eve&lt;/b&gt; Jr", page)
        self.assertNotIn("<b>Eve", page)

    def test_name_form_unit(self):
        form = PlayerForm({"player_name": "  A   B "})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["player_name"], "A B")


class SecurityAndIsolationTests(BaseViewCase):
    def test_restart_creates_fresh_session_key_and_clears_data(self):
        self.play(8, "Ann")
        old_key = self.client.session.session_key
        self.client.post(reverse("quiz:restart"))
        self.assertNotEqual(self.client.session.session_key, old_key)
        self.assertNotIn("quiz", self.client.session)
        self.assertNotIn("leaderboard_entry", self.client.session)
        self.assertRedirects(self.client.get(reverse("quiz:results")), reverse("quiz:home"))

    def test_start_rotates_session_key(self):
        self.client.get(reverse("quiz:home"))
        self.start()
        first = self.client.session.session_key
        self.start()
        self.assertNotEqual(self.client.session.session_key, first)

    def test_previous_results_do_not_leak(self):
        self.play(8, "Ann")
        self.client.post(reverse("quiz:restart"))
        self.start("Ann")
        self.assertEqual(self.state()["answers"], {})
        self.assertRedirects(self.client.get(reverse("quiz:results")), reverse("quiz:question"))
        self.client.post(reverse("quiz:answer"), {"position": 0, "choice": 0})
        self.assertEqual(LeaderboardEntry.objects.count(), 1)  # only the first, finished run

    def test_other_client_cannot_see_my_session(self):
        self.play(8, "Ann")
        other = self.client_class()
        self.assertRedirects(other.get(reverse("quiz:results")), reverse("quiz:home"))

    def test_post_completion_submissions_ignored(self):
        self.play(3, "Ann")
        before = LeaderboardEntry.objects.count()
        self.client.post(reverse("quiz:answer"), {"position": 0, "choice": 0})
        self.client.post(reverse("quiz:next"), {"position": 0})
        self.assertEqual(LeaderboardEntry.objects.count(), before)
        self.assertEqual(self.client.get(reverse("quiz:results")).context["results"].correct, 3)

    def test_invalid_positions_and_choices(self):
        self.start()
        for data in [{"position": 99, "choice": 0}, {"position": -1, "choice": 0}, {"position": "x", "choice": 0},
                     {"position": 0, "choice": 4}, {"position": 0, "choice": -1}, {"position": 0, "choice": "a"}]:
            with self.subTest(data=data):
                self.client.post(reverse("quiz:answer"), data)
                self.assertEqual(self.state()["answers"], {})
        self.client.post(reverse("quiz:next"), {"position": 99})
        self.assertEqual(self.state()["position"], 0)

    def test_duplicate_submission_locks_first_answer(self):
        self.start()
        right = ANSWER[self.current_id()]
        wrong = (right + 1) % 4
        self.client.post(reverse("quiz:answer"), {"position": 0, "choice": wrong})
        self.client.post(reverse("quiz:answer"), {"position": 0, "choice": right})
        record = self.state()["answers"][str(self.current_id())]
        self.assertEqual(record, {"selected": wrong, "correct": False})

    def test_forged_session_correct_flag_rejected_by_views(self):
        self.start()
        session = self.client.session
        state = session["quiz"]
        state["answers"] = {str(state["order"][0]): {"selected": (ANSWER[state["order"][0]] + 1) % 4, "correct": True}}
        session["quiz"] = state
        session.save()
        self.assertRedirects(self.client.get(reverse("quiz:question")), reverse("quiz:home"))

    def test_correct_answer_not_leaked_before_answering(self):
        self.start()
        page = self.client.get(reverse("quiz:question")).content.decode()
        self.assertNotIn("Correct answer", page)
        self.assertNotIn("answerIndex", page)

    def test_csrf_enforced_on_all_post_views(self):
        from django.test import Client
        strict = Client(enforce_csrf_checks=True)
        for name in ("start", "answer", "next", "restart"):
            with self.subTest(name=name):
                self.assertEqual(strict.post(reverse(f"quiz:{name}"), {"player_name": "A"}).status_code, 403)

    def test_session_cookie_flags(self):
        response = self.start()
        cookie = response.cookies["sessionid"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
