"""Offline Apple Health XML -> HRV samples -> historical LightCue replay.

Reads only HRV SDNN Record elements. Never adds health samples to feedback history.
"""
import argparse
import csv
from datetime import datetime, timedelta
import json
import math
from pathlib import Path
from statistics import median
import xml.etree.ElementTree as ET

from lightcue_ai import TASKS, CANDIDATES, load_sessions, show_recommendation

HRV_TYPE = "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"
ROOT = Path(__file__).resolve().parent


def read_hrv(path):
    samples = {}
    counts = {"hrv_records": 0, "invalid_records": 0, "duplicates": 0}
    # Remove completed elements from their parent to keep memory bounded even for
    # large exports. Unrelated health measurements are neither stored nor printed.
    stack = []
    for event, element in ET.iterparse(path, events=("start", "end")):
        if event == "start":
            stack.append(element)
            continue
        if element.tag == "Record" and element.get("type") == HRV_TYPE:
            counts["hrv_records"] += 1
            try:
                start = datetime.fromisoformat(element.attrib["startDate"])
                end = datetime.fromisoformat(element.attrib["endDate"])
                if start.utcoffset() is None or end.utcoffset() is None or end < start:
                    raise ValueError("invalid timestamp")
                value = float(element.attrib["value"])
                unit = element.attrib["unit"]
                if unit == "s":
                    value *= 1000
                elif unit != "ms":
                    raise ValueError("unsupported unit")
                if not math.isfinite(value) or value <= 0:
                    raise ValueError("invalid HRV")
                key = (start, end, value)
                if key in samples:
                    counts["duplicates"] += 1
                else:
                    samples[key] = {"start": start, "end": end, "hrv_ms": value}
            except (KeyError, ValueError, OverflowError):
                counts["invalid_records"] += 1
        stack.pop()
        if stack:
            stack[-1].remove(element)
        element.clear()
    return sorted(samples.values(), key=lambda s: (s["start"], s["end"], s["hrv_ms"])), counts


def latest_context(samples, days=7, minimum=5):
    if not samples:
        raise ValueError("No valid HRV SDNN samples in this export")
    latest_time = samples[-1]["start"]
    # Simultaneous readings are aggregated; none enter their own baseline.
    current_samples = [s for s in samples if s["start"] == latest_time]
    current = median(s["hrv_ms"] for s in current_samples)
    lower = latest_time - timedelta(days=days)
    history = [s for s in samples if lower <= s["start"] < latest_time
               and s["end"] <= latest_time]
    baseline = median(s["hrv_ms"] for s in history) if len(history) >= minimum else None
    return {
        "sample_time": latest_time.isoformat(),
        "current_hrv_ms": current,
        "simultaneous_sample_count": len(current_samples),
        "baseline_window_days": days,
        "baseline_sample_count": len(history),
        "baseline_minimum_samples": minimum,
        "baseline_hrv_ms": baseline,
        "hrv_change_pct": None if baseline is None else (current - baseline) / baseline * 100,
        "input_source": "apple_health_export",
        "use": "historical_replay",
        "preference_history_source": "simulated",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path)
    parser.add_argument("--task", choices=TASKS)
    parser.add_argument("--mode", choices=tuple(CANDIDATES))
    parser.add_argument("--baseline-days", type=int, default=7)
    parser.add_argument("--minimum-samples", type=int, default=5)
    args = parser.parse_args()
    if (args.task is None) != (args.mode is None):
        parser.error("provide --task and --mode together")
    if args.baseline_days < 1 or args.minimum_samples < 2:
        parser.error("baseline-days >= 1 and minimum-samples >= 2 required")
    try:
        samples, counts = read_hrv(args.export)
        context = latest_context(samples, args.baseline_days, args.minimum_samples)
        context.update(counts)
        context["valid_unique_samples"] = len(samples)
        context["first_sample_time"] = samples[0]["start"].isoformat()
        if args.task:
            context["demo_task"] = args.task
            context["demo_mode"] = args.mode
        output = ROOT / "health_import"
        output.mkdir(exist_ok=True)
        with (output / "hrv_samples.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(("start_time", "end_time", "hrv_sdnn_ms", "data_source"))
            for sample in samples:
                writer.writerow((sample["start"].isoformat(), sample["end"].isoformat(),
                                 sample["hrv_ms"], "apple_health_export"))
        (output / "latest_context.json").write_text(json.dumps(context, indent=2), encoding="utf8")
        print(f"Imported {len(samples)} unique HRV SDNN samples (ms).")
        print(f"Skipped: {counts['invalid_records']} invalid, {counts['duplicates']} duplicate.")
        print(f"Historical sample time: {context['sample_time']}")
        print(f"Latest HRV: {context['current_hrv_ms']:.2f} ms")
        print(f"Prior {args.baseline_days}-day baseline samples: {context['baseline_sample_count']}")
        if context["baseline_hrv_ms"] is None:
            print("Insufficient baseline history; no recommendation produced.")
        else:
            print(f"Rolling median baseline: {context['baseline_hrv_ms']:.2f} ms")
            print(f"Relative change: {context['hrv_change_pct']:+.2f}%")
            if args.task:
                print("Replay only: task/mode supplied for demo; preference history is simulated.")
                show_recommendation(load_sessions(), context["hrv_change_pct"], args.task, args.mode)
            else:
                print("Supply --task and --mode to replay this context through the prototype.")
        print("No live Watch/HealthKit connection. Export timestamps are not current-state measurements.")
    except (OSError, ValueError, ET.ParseError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
