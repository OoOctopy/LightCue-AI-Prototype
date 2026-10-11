"""Six-dimensional feedback prediction; no inferred stress or fabricated feedback."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from lightcue_ai import CANDIDATES, NAMES, TASKS, Session, distance, validate_context

ROOT = Path(__file__).resolve().parent
DIMENSIONS = {
    "task_effectiveness": "任务效能",
    "cognitive_balance": "认知投入体验",
    "intervention_timing": "干预契机",
    "visual_comfort": "视觉舒适",
    "stability": "稳定性",
    "acceptance": "接受度",
}
DEFAULT_WEIGHTS = ROOT / "preference_weights.json"
REAL_HISTORY = ROOT / "data" / "feedback_v2.jsonl"
RAW_FIELDS = {
    "completion_time_minutes", "accuracy_pct", "output_count",
    "hrv_before_ms", "hrv_after_ms", "manual_adjustment_count",
    "lighting_adjustment_count", "total_brightness_change_pct",
    "total_temperature_change_k",
}


def normalize_weights(weights):
    if not isinstance(weights, dict) or set(weights) != set(DIMENSIONS):
        raise ValueError("Weights must contain exactly the six dimension keys")
    for key, value in weights.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"Invalid weight: {key}")
    total = sum(weights.values())
    if not math.isfinite(total) or total <= 0:
        raise ValueError("Weights must have a finite positive sum")
    return {key: weights[key] / total for key in DIMENSIONS}


def validate_record(record):
    if not isinstance(record, dict):
        raise ValueError("Feedback must be a JSON object")
    required = {"session_id", "hrv_change_pct", "task_type", "mode", "strategy", "data_source", "ratings"}
    if not required.issubset(record):
        raise ValueError("Missing required feedback fields")
    if not isinstance(record["session_id"], str) or not record["session_id"].strip():
        raise ValueError("session_id must be a nonempty string")
    if any(not isinstance(record[key], str) for key in ("task_type", "mode", "strategy", "data_source")):
        raise ValueError("task_type, mode, strategy and data_source must be strings")
    hrv = record["hrv_change_pct"]
    if isinstance(hrv, bool) or not isinstance(hrv, (int, float)):
        raise ValueError("hrv_change_pct must be numeric")
    validate_context(hrv, record["task_type"], record["mode"])
    if record["strategy"] not in CANDIDATES[record["mode"]]:
        raise ValueError("Strategy does not belong to mode")
    if record["data_source"] not in ("real", "simulated"):
        raise ValueError("data_source must be real or simulated")
    ratings = record["ratings"]
    if not isinstance(ratings, dict) or set(ratings) != set(DIMENSIONS):
        raise ValueError("ratings must contain all six keys; use null for uncollected feedback")
    for key, value in ratings.items():
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                  or not math.isfinite(value) or not 1 <= value <= 5):
            raise ValueError(f"Rating {key} must be 1-5 or null")
    raw = record.get("raw_metrics", {})
    if not isinstance(raw, dict) or set(raw) - RAW_FIELDS:
        raise ValueError("Unknown raw_metrics field")
    for key, value in raw.items():
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"Invalid raw metric {key}")
        if key == "accuracy_pct" and value > 100:
            raise ValueError("accuracy_pct cannot exceed 100")
        if key in ("hrv_before_ms", "hrv_after_ms") and value <= 0:
            raise ValueError("HRV must be positive")
        if key.endswith("_count") and value != int(value):
            raise ValueError(f"{key} must be an integer")
    return record


def read_history(path=REAL_HISTORY, source="real"):
    path = Path(path)
    if not path.exists():
        return []
    rows, seen = [], set()
    with path.open(encoding="utf-8-sig") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = validate_record(json.loads(line))
                if row["data_source"] != source:
                    raise ValueError("Real and simulated feedback must use separate histories")
                if row["session_id"] in seen:
                    raise ValueError("Duplicate session_id")
                seen.add(row["session_id"])
                rows.append(row)
            except (ValueError, TypeError) as error:
                raise ValueError(f"History line {line_no}: {error}") from error
    return rows


def append_feedback(record, path=REAL_HISTORY):
    validate_record(record)
    if record["data_source"] != "real":
        raise ValueError("Only actual experience feedback may be saved to real history")
    if record.get("experience_completed") is not True:
        raise ValueError("Set experience_completed=true only after actual lighting experience")
    if all(value is None for value in record["ratings"].values()):
        raise ValueError("At least one actual feedback rating is required")
    existing = read_history(path)
    if any(row["session_id"] == record["session_id"] for row in existing):
        raise ValueError("Duplicate session_id; existing feedback was not overwritten")
    saved = dict(record, recorded_at=datetime.now(timezone.utc).isoformat())
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf8") as stream:
        stream.write(json.dumps(saved, ensure_ascii=False, allow_nan=False) + "\n")


def recommend_multidim(rows, hrv, task, mode, weights, k=3):
    validate_context(hrv, task, mode)
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError("k must be a positive integer")
    weights = normalize_weights(weights)
    active = [key for key, weight in weights.items() if weight > 0]
    sources, seen = set(), set()
    for row in rows:
        validate_record(row)
        if row["session_id"] in seen:
            raise ValueError("Duplicate session_id")
        seen.add(row["session_id"])
        sources.add(row["data_source"])
    if len(sources) > 1:
        raise ValueError("Cannot mix real and simulated preference history")
    pools, results, ranges = {}, {}, []
    # Use complete observations for the same active dimensions for both candidates.
    # Never substitute legacy goal_support or HRV for an uncollected rating.
    for strategy in CANDIDATES[mode]:
        pool = [row for row in rows if row["mode"] == mode and row["strategy"] == strategy
                and all(row["ratings"][key] is not None for key in active)]
        pools[strategy] = pool
    insufficient = {s: len(pool) for s, pool in pools.items() if len(pool) < k}
    if insufficient:
        return {"recommendation": None, "reason": f"Need {k} complete feedback records per candidate; available: {insufficient}",
                "weights": weights, "predictions": {}, "source": next(iter(sources), "none")}
    for strategy, pool in pools.items():
        neighbors = []
        for row in pool:
            context = Session(row["session_id"], row["hrv_change_pct"], row["task_type"],
                              row["mode"], strategy, 1, row["data_source"])
            gap = distance(context, hrv, task)
            neighbors.append((gap, row))
        neighbors = sorted(neighbors, key=lambda item: (item[0], item[1]["session_id"]))[:k]
        total = sum(1 / (gap + .05) for gap, _ in neighbors)
        explanation = [{"session_id": row["session_id"], "task_type": row["task_type"],
                        "distance": gap, "similarity_weight": (1 / (gap + .05)) / total}
                       for gap, row in neighbors]
        scores = {key: sum(row["ratings"][key] * (1 / (gap + .05)) / total
                           for gap, row in neighbors) if key in active else None for key in DIMENSIONS}
        utility = sum(weights[key] * scores[key] for key in active)
        results[strategy] = {"dimension_scores": scores, "weighted_score": utility, "neighbors": explanation,
                             "cross_task_only": all(row["task_type"] != task for _, row in neighbors)}
        magnitudes = [abs(row["hrv_change_pct"]) for row in pool]
        ranges.append((min(magnitudes), max(magnitudes)))
    low, high = max(r[0] for r in ranges), min(r[1] for r in ranges)
    ranked = sorted(results, key=lambda s: results[s]["weighted_score"], reverse=True)
    reason = None
    if not low <= abs(hrv) <= high:
        reason = f"Outside shared complete-feedback magnitude range ({low:.1f}-{high:.1f}%)"
    elif math.isclose(results[ranked[0]]["weighted_score"], results[ranked[1]]["weighted_score"], abs_tol=1e-9):
        reason = "Scores tied; user chooses"
    return {"recommendation": None if reason else ranked[0], "reason": reason,
            "weights": weights, "predictions": results, "source": next(iter(sources))}


def demo_history():
    """Separate 16-record six-rating fixture, not a conversion of the old 40 records."""
    rows = []
    for mode, strategies in CANDIDATES.items():
        for strategy_index, strategy in enumerate(strategies):
            for magnitude in (3.0, 5.0, 9.0, 11.0):
                high = magnitude >= 9
                good_match = high == bool(strategy_index)
                # Designed conflict: cue can support performance while low intervention
                # can support comfort/stability. Synthetic demonstration only.
                ratings = dict(zip(DIMENSIONS, (
                    4.5 if good_match else 2.8,
                    4.2 if good_match else 3.0,
                    4.4 if good_match else 2.6,
                    4.6 if strategy_index == 0 else 3.2,
                    4.7 if strategy_index == 0 else 3.1,
                    4.3 if good_match else 2.9,
                )))
                rows.append({"session_id": f"demo-{strategy}-{magnitude:g}", "hrv_change_pct": magnitude,
                             "task_type": "Ideation", "mode": mode, "strategy": strategy,
                             "ratings": ratings, "data_source": "simulated"})
    return rows


def show_result(result, hrv, task, mode):
    print(f"Six-dimensional prototype | {task} | {mode} | HRV {hrv:+.1f}%")
    print(f"Preference history: {result['source']}; weights are design settings, not learned weights.")
    for strategy, prediction in result["predictions"].items():
        print(f"\n{strategy} {NAMES[strategy]} | weighted score {prediction['weighted_score']:.2f}/5")
        for key, score in prediction["dimension_scores"].items():
            print(f"  {key}: {'disabled' if score is None else f'{score:.2f}/5'} | weight {result['weights'][key]:.1%}")
        for neighbor in prediction["neighbors"]:
            print(f"  #{neighbor['session_id']} | distance {neighbor['distance']:.3f} | similarity {neighbor['similarity_weight']:.1%}")
        if prediction["cross_task_only"]:
            print("  Evidence limitation: all neighbors use other task types.")
    print(f"\nRecommendation: {result['recommendation'] or 'withheld'}")
    if result["reason"]:
        print(result["reason"])
    print("HRV is context only; cognitive rating requires subjective feedback, not inferred psychological stress.")
    print("No hardware control or live HealthKit connection.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    parser.add_argument("--history", type=Path, default=REAL_HISTORY)
    parser.add_argument("--record", type=Path, help="append an actual experience feedback JSON")
    parser.add_argument("--demo", action="store_true", help="use separate synthetic six-dimensional fixture")
    parser.add_argument("--hrv", type=float)
    parser.add_argument("--task", choices=TASKS)
    parser.add_argument("--mode", choices=tuple(CANDIDATES))
    parser.add_argument("--k", type=int, default=3)
    args = parser.parse_args(argv)
    if args.record and (args.demo or any(x is not None for x in (args.hrv, args.task, args.mode))):
        parser.error("--record cannot be combined with demo or prediction context")
    if not args.record and any(x is not None for x in (args.hrv, args.task, args.mode)) and not all(x is not None for x in (args.hrv, args.task, args.mode)):
        parser.error("provide --hrv, --task and --mode together")
    try:
        if args.record:
            append_feedback(json.loads(args.record.read_text(encoding="utf-8-sig")), args.history)
            print("Actual experience feedback saved. Missing dimensions remain null.")
            return
        weights = json.loads(args.weights.read_text(encoding="utf-8-sig"))
        if args.demo:
            rows = demo_history()
            print("DEMO ONLY: 16 newly constructed six-rating records, independent of legacy 40-session dataset.")
        else:
            rows = read_history(args.history)
        if args.hrv is None:
            if not args.demo:
                parser.error("provide --hrv, --task and --mode, or run --demo")
            contexts = ((3.9, "Ideation", "Creative"), (10.0, "Ideation", "Creative"))
        else:
            contexts = ((args.hrv, args.task, args.mode),)
        for hrv, task, mode in contexts:
            show_result(recommend_multidim(rows, hrv, task, mode, weights, args.k), hrv, task, mode)
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
