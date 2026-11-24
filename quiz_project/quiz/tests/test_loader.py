import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from quiz.services.question_loader import QuestionLoadError, load_questions

BUNDLED = Path(__file__).resolve().parents[2] / "data" / "questions.json"


def q(qid=1, options=("a", "b", "c"), answer=1, text="Question?"):
    return {"id": qid, "question": text, "options": list(options), "answerIndex": answer}


class LoaderTests(SimpleTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "questions.json"

    def write(self, payload):
        text = payload if isinstance(payload, str) else json.dumps(payload)
        self.path.write_text(text, encoding="utf-8")
        return self.path

    def test_bundled_file_is_valid(self):
        data = load_questions(BUNDLED)
        self.assertGreaterEqual(len(data.questions), 8)
        self.assertEqual(data.skipped, ())

    def test_loads_valid_questions(self):
        data = load_questions(self.write({"title": "T", "questions": [q(1), q(2, ("x", "y"), 0)]}))
        self.assertEqual(data.title, "T")
        self.assertEqual([x.id for x in data.questions], [1, 2])
        self.assertEqual(data.questions[0].answer_index, 1)

    def test_supports_one_and_fifty_questions(self):
        self.assertEqual(len(load_questions(self.write({"title": "T", "questions": [q(1)]})).questions), 1)
        many = {"title": "T", "questions": [q(i) for i in range(1, 61)]}
        self.assertEqual(len(load_questions(self.write(many)).questions), 60)

    def test_option_count_limits(self):
        data = load_questions(
            self.write(
                {
                    "title": "T",
                    "questions": [
                        q(1, ("a",), 0),
                        q(2, ("a", "b"), 0),
                        q(3, tuple("abcdef"), 5),
                        q(4, tuple("abcdefg"), 0),
                    ],
                }
            )
        )
        self.assertEqual([x.id for x in data.questions], [2, 3])
        self.assertEqual(len(data.skipped), 2)

    def test_skips_malformed_questions(self):
        bad = [
            q(1, answer=3),
            q(2, answer=-1),
            q(3, answer=True),
            q(4, options=()),
            q(5, text=" "),
            {"id": "6", "question": "x", "options": ["a", "b"], "answerIndex": 0},
            q(7, options=("a", "")),
            "not an object",
            q(9),
            q(9),  # duplicate id
        ]
        data = load_questions(self.write({"title": "T", "questions": bad}))
        self.assertEqual([x.id for x in data.questions], [9])
        self.assertEqual(len(data.skipped), 9)

    def test_missing_file(self):
        with self.assertRaisesMessage(QuestionLoadError, "could not be found"):
            load_questions(self.path)

    def test_empty_file(self):
        with self.assertRaisesMessage(QuestionLoadError, "empty"):
            load_questions(self.write("  \n"))

    def test_invalid_json(self):
        with self.assertRaisesMessage(QuestionLoadError, "not valid JSON"):
            load_questions(self.write("{nope"))

    def test_invalid_structure(self):
        for payload in ([], {"questions": [q()]}, {"title": "T"}, {"title": "T", "questions": {}}, {"title": 5, "questions": [q()]}):
            with self.subTest(payload=payload), self.assertRaises(QuestionLoadError):
                load_questions(self.write(payload))

    def test_empty_questions_list(self):
        with self.assertRaisesMessage(QuestionLoadError, "no questions"):
            load_questions(self.write({"title": "T", "questions": []}))

    def test_no_valid_questions_left(self):
        with self.assertRaisesMessage(QuestionLoadError, "no valid questions"):
            load_questions(self.write({"title": "T", "questions": [q(1, answer=9)]}))
