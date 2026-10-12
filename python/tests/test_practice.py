from __future__ import annotations

import json
import tempfile
import unittest
import urllib.request
from pathlib import Path

from assistant.classes import ClassWorkspace, add_course, catalog
from assistant.errors import AssistantError
from assistant.library import start_library
from assistant.practice import parse_questions, save_practice_test

SAMPLE = """
ID: q1
TYPE: MC
PROMPT: What is the capital of France?
CHOICES:
A) London
B) Paris
C) Berlin
D) Madrid
ANSWER: B
EXPLANATION: Paris is the capital and largest city of France.

ID: q2
TYPE: TF
PROMPT: The sky is blue.
ANSWER: TRUE

ID: q3
TYPE: SALL
PROMPT: Pick the vowels.
CHOICES:
A) A
B) B
C) E
ANSWER: A,C
"""


class PracticeTestTests(unittest.TestCase):
    def test_a_class_can_hold_several_practice_tests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            add_course(root, "American Institutions")
            workspace = ClassWorkspace(root)
            created = workspace.dispatch(
                "create_practice_test",
                {"class_folder": "american-institutions", "title": "Unit 1", "questions": SAMPLE},
            )
            self.assertIn("Created american-institutions/practice-tests/unit-1/questions.txt", created)
            self.assertIn("3 questions", created)
            second = """
ID: mid1
TYPE: TF
PROMPT: The Constitution is the supreme law.
ANSWER: TRUE
"""
            midterm = workspace.dispatch(
                "create_practice_test",
                {"class_folder": "american-institutions", "title": "Midterm", "questions": second},
            )
            self.assertIn("practice-tests/midterm/questions.txt", midterm)
            listed = catalog(root)
            self.assertIn("unit-1", listed)
            self.assertIn("midterm", listed)
            questions = parse_questions(SAMPLE)
            self.assertEqual(questions[0].answers, frozenset({"B"}))
            self.assertTrue(questions[1].is_correct({"A"}))
            self.assertTrue(questions[2].is_correct({"A", "C"}))
            self.assertFalse(questions[2].is_correct({"A"}))
            with self.assertRaises(AssistantError):
                save_practice_test(root, "american-institutions", "Broken", "ID: q1\nTYPE: MC\nPROMPT: Hi\nANSWER: B\n")

    def test_quiz_hides_the_answer_until_submit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            add_course(root, "History")
            save_practice_test(root, "history", "Unit 1", SAMPLE)
            server = start_library(root)
            self.addCleanup(server.shutdown)
            self.addCleanup(server.server_close)
            base = f"http://127.0.0.1:{server.server_address[1]}"

            with urllib.request.urlopen(base + "/class/history", timeout=2) as response:
                course = response.read().decode("utf-8")
            self.assertIn("Unit 1", course)
            self.assertIn("3 questions", course)

            with urllib.request.urlopen(base + "/class/history/practice/unit-1/questions", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["questions"][0]["prompt"], "What is the capital of France?")
            self.assertNotIn("largest city", json.dumps(payload))
            self.assertNotIn("answer", json.dumps(payload).lower())

            def grade(selected: list[str], review: bool = False) -> dict[str, object]:
                request = urllib.request.Request(
                    base + "/class/history/practice/unit-1/grade",
                    data=json.dumps({"id": "q1", "selected": selected, "review": review}).encode(),
                    method="POST",
                )
                request.add_header("Content-Type", "application/json")
                with urllib.request.urlopen(request, timeout=2) as response:
                    return json.loads(response.read().decode("utf-8"))

            wrong = grade(["A"])
            self.assertFalse(wrong["correct"])
            self.assertIn("Paris", str(wrong["answer_text"]))
            right = grade(["B"], review=True)
            self.assertTrue(right["correct"])
            self.assertIn("largest city", str(right["explanation"]))
            review = (root / "history" / "practice-tests" / "unit-1" / "review.txt").read_text(encoding="utf-8")
            self.assertIn("ID: q1", review)


if __name__ == "__main__":
    unittest.main()
