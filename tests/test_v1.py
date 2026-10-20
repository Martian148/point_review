import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from app import ai, db, points, review


class V1FlowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.sqlite3"
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.old_path
        self.temp.cleanup()

    def fake_question(self, point):
        node_id = point["nodes"][0]["id"]
        return ai.validate_question({
            "pointId": point["id"], "targetNodeId": node_id,
            "context": f"Researchers should {point['title']} their findings in a broader social context.",
            "question": f"{point['title']} 在句中的含义最接近：",
            "options": [
                {"key": "A", "text": "传授"}, {"key": "B", "text": "忽略"},
                {"key": "C", "text": "限制"}, {"key": "D", "text": "替换"},
            ],
            "correctOption": "A", "explanation": "该词在句中表示传授。",
        }, point)

    def test_point_markdown_and_soft_delete(self):
        point = points.create_point("Perspective", [{"content": "观点", "children": [{"content": "从不同角度", "children": []}]}])
        self.assertIsNone(point["mastery"])
        self.assertEqual(point["nodes"][0]["children"][0]["content"], "从不同角度")
        self.assertEqual(len(points.list_points("pers")), 1)
        with self.assertRaises(points.InputError):
            points.create_point(" perspective ", [{"content": "视角", "children": []}])
        preview = points.preview_markdown("- perspective\n  - 视角\n- impart\n  - 传授\n- IMPART\n  - 告知")
        self.assertEqual([p["duplicate"] for p in preview], [True, False, True])
        result = points.import_markdown("- perspective\n  - 视角\n- impart\n  - 传授\n- IMPART\n  - 告知")
        self.assertEqual(len(result["createdIds"]), 1)
        self.assertEqual(len(result["skippedTitles"]), 2)
        updated = points.update_point(point["id"], "Perspective", [{"content": "看法", "children": []}])
        self.assertEqual(updated["nodes"][0]["content"], "看法")
        self.assertTrue(points.delete_point(point["id"]))
        self.assertIsNone(points.get_point(point["id"]))
        self.assertIsNotNone(points.create_point("perspective", [{"content": "新释义", "children": []}]))

    def test_review_closed_loop_and_answer_privacy(self):
        for title in ("impart", "perspective"):
            points.create_point(title, [{"content": "传授", "children": []}])
        with patch.object(review, "configured", return_value=True), patch.object(review, "generate_question", side_effect=self.fake_question):
            session = review.create_session()
        self.assertEqual(session["status"], "READY")
        self.assertEqual(len(session["questions"]), 2)
        self.assertNotIn("correctOption", session["questions"][0])
        first, second = session["questions"]
        answer1 = review.answer(session["id"], first["id"], "A", 1000)
        self.assertTrue(answer1["isCorrect"])
        self.assertFalse(answer1["completed"])
        self.assertIsNone(points.get_point(first["pointId"])["mastery"])
        with self.assertRaises(points.InputError):
            review.answer(session["id"], first["id"], "B")
        answer2 = review.answer(session["id"], second["id"], "B", 1500)
        self.assertFalse(answer2["isCorrect"])
        self.assertTrue(answer2["completed"])
        result = review.result(session["id"])
        self.assertEqual((result["total"], result["correct"], result["wrong"], result["accuracy"]), (2, 1, 1, 50))
        self.assertEqual(points.get_point(first["pointId"])["mastery"], 3)
        self.assertEqual(points.get_point(second["pointId"])["mastery"], 1)
        first_state = points.get_point(first["pointId"])
        second_state = points.get_point(second["pointId"])
        self.assertEqual((datetime.fromisoformat(first_state["next_review_at"]) - datetime.fromisoformat(first_state["last_reviewed_at"])).days, 4)
        self.assertEqual((datetime.fromisoformat(second_state["next_review_at"]) - datetime.fromisoformat(second_state["last_reviewed_at"])).days, 1)
        self.assertEqual(review.get_session(session["id"])["status"], "COMPLETED")
        with self.assertRaises(points.InputError):
            review.answer(session["id"], second["id"], "A")

    def test_generation_retry_and_replacement(self):
        for title in ("alpha", "beta", "gamma"):
            points.create_point(title, [{"content": "含义", "children": []}])
        calls = {}
        def generator(point):
            calls[point["title"]] = calls.get(point["title"], 0) + 1
            if point["title"] == "alpha":
                raise ai.GenerationError("无效题目")
            return self.fake_question(point)
        with patch.object(review, "configured", return_value=True), patch.object(review, "generate_question", side_effect=generator):
            session = review.create_session()
        self.assertEqual(calls["alpha"], 2)
        self.assertEqual(session["actual_question_count"], 2)
        self.assertEqual(session["status"], "READY")

    def test_question_validation_rejects_wrong_point(self):
        point = points.create_point("impart", [{"content": "传授", "children": []}])
        question = self.fake_question(point)
        question["context"] = "The sentence does not include the target word."
        with self.assertRaises(ai.GenerationError):
            ai.validate_question(question, point)

    def test_dictionary_placeholder_phrase_uses_natural_context(self):
        point = points.create_point("be accustomed to doing sth.", [{"content": "习惯于做某事", "children": []}])
        raw = {
            "pointId": point["id"], "targetNodeId": point["nodes"][0]["id"],
            "context": "Students are accustomed to getting feedback from several sources before making a decision.",
            "question": "be accustomed to doing sth. 在句中的含义最接近：",
            "options": [{"key": k, "text": t} for k, t in zip("ABCD", ("习惯于", "避免", "拒绝", "尝试"))],
            "correctOption": "A", "explanation": "表示已经习惯于某事。",
        }
        self.assertEqual(ai.validate_question(raw, point)["correctOption"], "A")


if __name__ == "__main__":
    unittest.main()
