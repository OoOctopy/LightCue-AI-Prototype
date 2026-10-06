"""Behavior checks for the recommendation and input boundaries."""
import csv
import math
from pathlib import Path
import tempfile
import unittest

from lightcue_ai import CANDIDATES, Session, load_sessions, predict_score, recommend


class ModelChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sessions = load_sessions()

    def test_source_dataset_shape(self):
        self.assertEqual([s.session_id for s in self.sessions], [f"{i:03}" for i in range(1, 41)])
        self.assertTrue(all(s.data_source == "simulated" for s in self.sessions))
        for strategy in ("S1", "S2", "S3", "S4"):
            self.assertEqual(sum(s.strategy == strategy for s in self.sessions), 10)

    def test_small_and_large_magnitude_preferences(self):
        for mode, expected in CANDIDATES.items():
            self.assertEqual(recommend(self.sessions, 3.9, "Ideation", mode)[0], expected[0])
            self.assertEqual(recommend(self.sessions, 10, "Ideation", mode)[0], expected[1])

    def test_mode_filter_and_no_direction_diagnosis(self):
        for mode in CANDIDATES:
            for hrv in (-10, 10):
                _, results, _ = recommend(self.sessions, hrv, "Writing", mode)
                self.assertEqual(set(results), set(CANDIDATES[mode]))
                for strategy, (score, neighbors) in results.items():
                    self.assertTrue(1 <= score <= 5)
                    self.assertTrue(all(s.mode == mode and s.strategy == strategy for s, _, _ in neighbors))
            self.assertEqual(recommend(self.sessions, -10, "Writing", mode),
                             recommend(self.sessions, 10, "Writing", mode))

    def test_invalid_and_insufficient_input(self):
        for hrv in (math.nan, math.inf, -100):
            with self.assertRaises(ValueError):
                recommend(self.sessions, hrv, "Ideation", "Creative")
        with self.assertRaises(ValueError):
            recommend(self.sessions, 10, "Unknown", "Creative")
        with self.assertRaises(ValueError):
            recommend(self.sessions, 10, "Ideation", "Creative", k=0)
        with self.assertRaises(ValueError):
            recommend([s for s in self.sessions if s.strategy != "S4"], 10, "Ideation", "Creative")
        self.assertIsNone(recommend(self.sessions, 50, "Ideation", "Creative")[0])

    def test_tie_requires_user_choice(self):
        rows = [Session(str(i), 10, "Writing", "Creative", strategy, 4, "simulated")
                for i, strategy in enumerate(("S3", "S4"))]
        self.assertIsNone(recommend(rows, 10, "Writing", "Creative")[0])

    def test_held_out_session_is_not_its_own_neighbor(self):
        for held in self.sessions:
            train = [s for s in self.sessions if s.session_id != held.session_id]
            _, neighbors = predict_score(train, held.hrv_change_pct, held.task_type,
                                         held.mode, held.strategy)
            self.assertTrue(all(s.session_id != held.session_id for s, _, _ in neighbors))

    def test_malformed_feedback_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            with path.open("w", encoding="utf8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(Session.__dataclass_fields__)
                writer.writerow(("001", 10, "Writing", "Creative", "S3", 6, "simulated"))
            with self.assertRaisesRegex(ValueError, "CSV line 2"):
                load_sessions(path)


if __name__ == "__main__":
    unittest.main()
