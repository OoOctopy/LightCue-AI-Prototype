from pathlib import Path
from datetime import datetime, timedelta, timezone
import tempfile
import unittest

from import_health import read_hrv, latest_context


class HealthImportChecks(unittest.TestCase):
    def test_only_hrv_units_validation_and_deduplication(self):
        xml = '''<HealthData>
        <Record type="HKQuantityTypeIdentifierHeartRate" value="70" unit="count/min" />
        <Record type="HKQuantityTypeIdentifierHeartRateVariabilitySDNN" value="0.05" unit="s" startDate="2026-01-01 10:00:00 +0800" endDate="2026-01-01 10:01:00 +0800"><MetadataEntry key="x" value="y"/></Record>
        <Record type="HKQuantityTypeIdentifierHeartRateVariabilitySDNN" value="50" unit="ms" startDate="2026-01-01 10:00:00 +0800" endDate="2026-01-01 10:01:00 +0800"/>
        <Record type="HKQuantityTypeIdentifierHeartRateVariabilitySDNN" value="nan" unit="ms" startDate="2026-01-02 10:00:00 +0800" endDate="2026-01-02 10:01:00 +0800"/>
        <Record type="HKQuantityTypeIdentifierHeartRateVariabilitySDNN" value="50" unit="unknown" startDate="2026-01-02 10:00:00 +0800" endDate="2026-01-02 10:01:00 +0800"/>
        <Record type="HKQuantityTypeIdentifierHeartRateVariabilitySDNN" value="-3" unit="ms" startDate="2026-01-02 10:00:00 +0800" endDate="2026-01-02 10:01:00 +0800"/>
        </HealthData>'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.xml"
            path.write_text(xml, encoding="utf8")
            samples, counts = read_hrv(path)
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0]["hrv_ms"], 50)
        self.assertEqual(counts, {"hrv_records": 5, "invalid_records": 3, "duplicates": 1})

    def test_baseline_excludes_current_future_and_old_readings(self):
        now = datetime(2026, 1, 10, tzinfo=timezone.utc)
        def sample(days, value, duration=0):
            start = now - timedelta(days=days)
            return {"start": start, "end": start + timedelta(days=duration), "hrv_ms": value}
        rows = [sample(10, 1000), sample(6, 49), sample(5, 50), sample(4, 51),
                sample(3, 50), sample(2, 50), sample(1, 900, 2), sample(0, 60)]
        result = latest_context(rows)
        self.assertEqual(result["baseline_sample_count"], 5)
        self.assertEqual(result["baseline_hrv_ms"], 50)
        self.assertAlmostEqual(result["hrv_change_pct"], 20)

    def test_insufficient_history_and_empty_export(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = latest_context([{"start": now, "end": now, "hrv_ms": 50}])
        self.assertIsNone(result["hrv_change_pct"])
        with self.assertRaises(ValueError):
            latest_context([])

    def test_simultaneous_samples_are_not_their_own_baseline(self):
        now = datetime(2026, 1, 10, tzinfo=timezone.utc)
        samples = [{"start": now-timedelta(days=i), "end": now-timedelta(days=i), "hrv_ms": 50}
                   for i in range(5, 0, -1)]
        samples += [{"start": now, "end": now, "hrv_ms": x} for x in (40, 60)]
        result = latest_context(samples)
        self.assertEqual(result["current_hrv_ms"], 50)
        self.assertEqual(result["baseline_sample_count"], 5)


if __name__ == "__main__":
    unittest.main()
