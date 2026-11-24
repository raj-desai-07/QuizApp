import json
import tempfile
from pathlib import Path
from unittest import mock

from django.test import Client, TestCase, override_settings
from django.urls import reverse

QUIZ = {
    "title": "Test Quiz",
    "questions": [
        {"id": 1, "question": "Q one?", "options": ["a", "b", "c"], "answerIndex": 1},
        {"id": 2, "question": "Q two?", "options": ["a", "b"], "answerIndex": 0},
        {"id": 3, "question": "Q three?", "options": ["a", "b", "c", "d"], "answerIndex": 2},
    ],
}
CORRECT = [1, 0, 2]


class QuizViewTests(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "questions.json"
        self.write(QUIZ)
        override = override_settings(QUESTIONS_FILE=self.path)
        override.enable()
        self.addCleanup(override.disable)
        # Keep file order so the fixed CORRECT list applies; shuffling is tested in test_shuffle.py.
        patcher = mock.patch("quiz.services.quiz_engine.random.shuffle", lambda items: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, payload):
        text = payload if isinstance(payload, str) else json.dumps(payload)
        self.path.write_text(text, encoding="utf-8")

    def state(self):
        return self.client.session["quiz"]

    def start(self, name="Ada"):
        return self.client.post(reverse("quiz:start"), {"player_name": name})

    def answer(self, choice=None, position=None):
        data = {"position": self.state()["position"] if position is None else position}
        if choice is not None:
            data["choice"] = choice
        return self.client.post(reverse("quiz:answer"), data)

    def next(self):
        return self.client.post(reverse("quiz:next"), {"position": self.state()["position"]})

    def test_home_shows_question_count(self):
        response = self.client.get(reverse("quiz:home"))
        self.assertContains(response, "Test Quiz")
        self.assertContains(response, "<strong>3</strong> questions")

    def test_full_quiz_flow(self):
        self.start()
        for i, choice in enumerate([1, 1, 2]):  # question 2 answered wrongly
            response = self.client.get(reverse("quiz:question"))
            self.assertContains(response, f"Question {i + 1} of 3")
            self.answer(choice)
            response = self.client.get(reverse("quiz:question"))
            self.assertContains(response, "Correct!" if choice == CORRECT[i] else "Incorrect")
            self.next()
        response = self.client.get(reverse("quiz:results"))
        self.assertContains(response, "2 / 3")
        self.assertContains(response, "66.7%")
        self.assertContains(response, "PASS")

    def test_failing_result(self):
        self.start()
        for choice in (0, 1, 0):
            self.answer(choice)
            self.next()
        response = self.client.get(reverse("quiz:results"))
        self.assertContains(response, "0 / 3")
        self.assertContains(response, "FAIL")
        self.assertNotContains(response, "PASS")

    def test_correct_answer_hidden_before_submission(self):
        self.start()
        response = self.client.get(reverse("quiz:question"))
        self.assertNotContains(response, "correct")
        self.assertNotContains(response, "wrong")
        self.assertNotIn("Incorrect", response.content.decode())

    def test_submit_requires_selection(self):
        self.start()
        response = self.answer(None)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Please select an answer.", status_code=400)
        self.assertEqual(self.state()["answers"], {})

    def test_out_of_range_choice_rejected(self):
        self.start()
        for choice in ("3", "-1", "abc"):
            with self.subTest(choice=choice):
                self.assertEqual(self.answer(choice).status_code, 400)
        self.assertEqual(self.state()["answers"], {})

    def test_answer_cannot_be_changed(self):
        self.start()
        self.answer(0)  # wrong
        self.answer(1)  # attempt to change to the correct one
        self.assertEqual(self.state()["answers"]["1"], {"selected": 0, "correct": False})

    def test_stale_position_is_ignored(self):
        self.start()
        self.answer(1, position=2)
        self.assertEqual(self.state()["answers"], {})

    def test_client_cannot_inject_score(self):
        self.start()
        self.client.post(
            reverse("quiz:answer"),
            {"position": 0, "choice": 0, "correct": "true", "score": "99", "answerIndex": 0},
        )
        self.assertEqual(self.state()["answers"]["1"]["correct"], False)

    def test_cannot_advance_without_answering(self):
        self.start()
        response = self.next()
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Please answer the question", status_code=400)
        self.assertEqual(self.state()["position"], 0)

    def test_no_navigation_without_active_quiz(self):
        self.assertRedirects(self.client.get(reverse("quiz:question")), reverse("quiz:home"))
        self.assertRedirects(self.client.get(reverse("quiz:results")), reverse("quiz:home"))
        self.assertRedirects(self.client.post(reverse("quiz:answer"), {"choice": 0, "position": 0}), reverse("quiz:home"))
        self.assertRedirects(self.client.post(reverse("quiz:next"), {"position": 0}), reverse("quiz:home"))

    def test_results_blocked_until_complete(self):
        self.start()
        self.assertRedirects(self.client.get(reverse("quiz:results")), reverse("quiz:question"))

    def test_finished_quiz_redirects_question_to_results(self):
        self.start()
        for _ in range(3):
            self.answer(0)
            self.next()
        self.assertRedirects(self.client.get(reverse("quiz:question")), reverse("quiz:results"))

    def test_restart_resets_everything(self):
        self.start()
        self.answer(1)
        self.client.post(reverse("quiz:restart"))
        self.assertNotIn("quiz", self.client.session)
        self.start()
        self.assertEqual(self.state()["position"], 0)
        self.assertEqual(self.state()["answers"], {})

    def test_restart_mid_quiz_then_results_blocked(self):
        self.start()
        self.answer(1)
        self.next()
        self.client.post(reverse("quiz:restart"))
        self.assertRedirects(self.client.get(reverse("quiz:results")), reverse("quiz:home"))

    def test_state_changing_urls_redirect_on_get(self):
        for name in ("start", "answer", "next", "restart"):
            with self.subTest(name=name):
                self.assertRedirects(self.client.get(reverse(f"quiz:{name}")), reverse("quiz:home"))

    def test_bad_questions_file_shows_error_page(self):
        for content in ("", "{bad", {"title": "T", "questions": []}):
            with self.subTest(content=content):
                self.write(content)
                response = self.client.get(reverse("quiz:home"))
                self.assertContains(response, "Something went wrong", status_code=503)

    def test_missing_questions_file_shows_error_page(self):
        self.path.unlink()
        self.assertContains(self.client.get(reverse("quiz:home")), "could not be found", status_code=503)

    def test_malformed_questions_are_skipped_and_reported(self):
        payload = {"title": "T", "questions": QUIZ["questions"] + [{"id": 9, "question": "x", "options": [], "answerIndex": 0}]}
        self.write(payload)
        response = self.client.get(reverse("quiz:home"))
        self.assertContains(response, "<strong>3</strong>")
        self.assertContains(response, "1 malformed question was skipped")

    def test_empty_player_name_is_rejected(self):
        for name in ("", "   "):
            response = self.start(name)
            self.assertContains(response, "Please enter your name", status_code=400)
            self.assertNotIn("quiz", self.client.session)

    def test_overlong_player_name_is_rejected(self):
        self.assertContains(self.start("x" * 41), "40 characters or fewer", status_code=400)

    def test_player_name_shown_and_kept_after_restart(self):
        self.start("  Grace  ")
        self.assertContains(self.client.get(reverse("quiz:question")), "Grace")
        self.client.post(reverse("quiz:restart"))
        self.assertContains(self.client.get(reverse("quiz:home")), 'value="Grace"')

    def test_player_name_is_escaped(self):
        self.start("<b>x</b>")
        self.assertNotContains(self.client.get(reverse("quiz:question")), "<b>x</b>")

    def test_unselected_answer_shows_validation_message(self):
        self.start()
        self.assertContains(self.answer(), "Please select an answer.", status_code=400)

    def test_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse("quiz:start"))
        self.assertContains(response, "Please go back and try again", status_code=403)

    def test_unknown_url_shows_error_page(self):
        self.assertContains(self.client.get("/nope/"), "does not exist", status_code=404)
