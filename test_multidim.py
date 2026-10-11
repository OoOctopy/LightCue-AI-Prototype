import copy
from pathlib import Path
import tempfile
import unittest

from lightcue_multidim import DIMENSIONS, append_feedback, demo_history, normalize_weights, read_history, recommend_multidim, validate_record


class SixDimensionChecks(unittest.TestCase):
    def setUp(self):
        self.rows = demo_history()
        self.weights = dict.fromkeys(DIMENSIONS, 1)

    def result(self, rows=None, weights=None, hrv=10):
        return recommend_multidim(self.rows if rows is None else rows, hrv,
                                 "Ideation", "Creative", self.weights if weights is None else weights)

    def test_weights_change_real_decision(self):
        comfort = dict.fromkeys(DIMENSIONS, 0)
        comfort.update(visual_comfort=1, stability=1)
        self.assertEqual(self.result()["recommendation"], "S4")
        self.assertEqual(self.result(weights=comfort)["recommendation"], "S3")
        self.assertAlmostEqual(sum(normalize_weights(self.weights).values()), 1)

    def test_invalid_weights(self):
        for weights in ({}, dict.fromkeys(DIMENSIONS, 0), dict(self.weights, acceptance=-1),
                        dict(self.weights, acceptance=float("nan")), dict(self.weights, acceptance=True)):
            with self.assertRaises(ValueError):
                normalize_weights(weights)

    def test_missing_scores_are_not_imputed(self):
        for row in self.rows:
            row["ratings"]["cognitive_balance"] = None
        result = self.result()
        self.assertIsNone(result["recommendation"])
        self.assertEqual(result["predictions"], {})
        weights = dict(self.weights, cognitive_balance=0)
        self.assertIsNotNone(self.result(weights=weights)["recommendation"])

    def test_raw_hrv_does_not_become_cognitive_score(self):
        before = self.result()
        for row in self.rows:
            row["raw_metrics"] = {"hrv_before_ms": 10, "hrv_after_ms": 900}
        self.assertEqual(before, self.result())

    def test_sources_are_not_mixed(self):
        self.rows[0]["data_source"] = "real"
        with self.assertRaises(ValueError):
            self.result()

    def test_tie_and_outside_coverage_withhold(self):
        self.assertIsNone(self.result(hrv=50)["recommendation"])
        for row in self.rows:
            row["ratings"] = dict.fromkeys(DIMENSIONS, 4)
        self.assertIsNone(self.result()["recommendation"])

    def test_all_candidate_neighbors_are_correct_and_explainable(self):
        result = self.result()
        self.assertEqual(set(result["predictions"]), {"S3", "S4"})
        for strategy, prediction in result["predictions"].items():
            self.assertEqual(len(prediction["neighbors"]), 3)
            self.assertAlmostEqual(sum(n["similarity_weight"] for n in prediction["neighbors"]), 1)
            self.assertTrue(all(strategy in n["session_id"] for n in prediction["neighbors"]))
            expected = sum(prediction["dimension_scores"][key] * result["weights"][key] for key in DIMENSIONS)
            self.assertAlmostEqual(prediction["weighted_score"], expected)

    def test_cold_start_and_invalid_k(self):
        self.assertIsNone(self.result(rows=[])["recommendation"])
        with self.assertRaises(ValueError):
            recommend_multidim(self.rows, 10, "Ideation", "Creative", self.weights, 0)

    def test_feedback_append_requires_experience_and_never_overwrites(self):
        row = copy.deepcopy(self.rows[0])
        row["data_source"] = "real"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feedback.jsonl"
            with self.assertRaises(ValueError):
                append_feedback(row, path)
            row["experience_completed"] = True
            append_feedback(row, path)
            self.assertEqual(len(read_history(path)), 1)
            with self.assertRaises(ValueError):
                append_feedback(row, path)
            self.assertEqual(len(read_history(path)), 1)
            row["data_source"] = "simulated"
            with self.assertRaises(ValueError):
                append_feedback(row, path)

    def test_partial_real_feedback_is_saved_but_not_used(self):
        row = copy.deepcopy(self.rows[0])
        row.update(data_source="real", experience_completed=True)
        row["ratings"]["acceptance"] = None
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feedback.jsonl"
            append_feedback(row, path)
            saved = read_history(path)
            self.assertIsNone(saved[0]["ratings"]["acceptance"])
            self.assertIsNone(self.result(rows=saved)["recommendation"])

    def test_bad_feedback_and_legacy_target_are_rejected(self):
        row = copy.deepcopy(self.rows[0])
        row["ratings"]["acceptance"] = 6
        with self.assertRaises(ValueError):
            validate_record(row)
        row = copy.deepcopy(self.rows[0])
        row["mode"] = []
        with self.assertRaises(ValueError):
            validate_record(row)
        row = copy.deepcopy(self.rows[0])
        del row["ratings"]
        row["goal_support"] = 4
        with self.assertRaises(ValueError):
            validate_record(row)
        row = copy.deepcopy(self.rows[0])
        row["raw_metrics"] = {"accuracy_pct": 101}
        with self.assertRaises(ValueError):
            validate_record(row)


if __name__ == "__main__":
    unittest.main()
