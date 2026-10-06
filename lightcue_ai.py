"""LightCue v1: transparent, per-strategy weighted KNN score prediction.

Only synthetic session feedback is used. No health service or hardware connection.
Run with --demo, or --hrv 10 --task "Visual Design" --mode Creative.
"""

import argparse
import csv
from dataclasses import dataclass
import math
from pathlib import Path

TASKS = ("Ideation", "Visual Design", "Writing", "Research")
CANDIDATES = {"Default": ("S1", "S2"), "Creative": ("S3", "S4")}
NAMES = {"S1": "Stable", "S2": "Focus Cue", "S3": "Creative Drift", "S4": "Creative Cue"}
CSV_PATH = Path(__file__).with_name("lightcue_sessions.csv")


@dataclass(frozen=True)
class Session:
    session_id: str
    hrv_change_pct: float
    task_type: str
    mode: str
    strategy: str
    goal_support: float
    data_source: str


def load_sessions(path=CSV_PATH):
    sessions = []
    seen = set()
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = set(Session.__dataclass_fields__)
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("CSV is missing required columns")
        for line, row in enumerate(reader, 2):
            try:
                session = Session(
                    row["session_id"], float(row["hrv_change_pct"]), row["task_type"],
                    row["mode"], row["strategy"], float(row["goal_support"]), row["data_source"]
                )
                validate_context(session.hrv_change_pct, session.task_type, session.mode)
                if session.strategy not in CANDIDATES[session.mode]:
                    raise ValueError("strategy does not belong to mode")
                if not math.isfinite(session.goal_support) or not 1 <= session.goal_support <= 5:
                    raise ValueError("goal_support must be between 1 and 5")
                if session.data_source != "simulated":
                    raise ValueError("v1 accepts only explicitly simulated records")
                if not session.session_id or session.session_id in seen:
                    raise ValueError("empty or duplicate session_id")
                seen.add(session.session_id)
                sessions.append(session)
            except (ValueError, TypeError) as error:
                raise ValueError(f"CSV line {line}: {error}") from error
    if not sessions:
        raise ValueError("CSV contains no sessions")
    return sessions


def validate_context(hrv, task, mode):
    if not math.isfinite(hrv) or hrv <= -100:
        raise ValueError("HRV change must be finite and greater than -100%")
    if task not in TASKS:
        raise ValueError(f"task must be one of {TASKS}")
    if mode not in CANDIDATES:
        raise ValueError(f"mode must be one of {tuple(CANDIDATES)}")


def distance(session, hrv, task):
    # Magnitude is an explicit v1 feature assumption, not a physiological finding.
    # Ten percentage points = one distance unit; task mismatch adds 0.25 squared.
    magnitude_gap = (abs(session.hrv_change_pct) - abs(hrv)) / 10.0
    return math.sqrt(magnitude_gap ** 2 + 0.25 * (session.task_type != task))


def predict_score(sessions, hrv, task, mode, strategy, k=3):
    validate_context(hrv, task, mode)
    if not isinstance(k, int) or k < 1:
        raise ValueError("k must be a positive integer")
    if strategy not in CANDIDATES[mode]:
        raise ValueError("strategy does not belong to mode")
    pool = [s for s in sessions if s.mode == mode and s.strategy == strategy]
    if not pool:
        raise ValueError(f"No history for {mode}/{strategy}")
    ranked = sorted(((distance(s, hrv, task), s) for s in pool),
                    key=lambda item: (item[0], item[1].session_id))[:k]
    neighbors = [(s, d, 1.0 / (d + 0.05)) for d, s in ranked]
    total = sum(w for _, _, w in neighbors)
    score = sum(s.goal_support * w for s, _, w in neighbors) / total
    return score, neighbors


def recommend(sessions, hrv, task, mode, k=3):
    validate_context(hrv, task, mode)
    results = {strategy: predict_score(sessions, hrv, task, mode, strategy, k)
               for strategy in CANDIDATES[mode]}
    ordered = sorted(results, key=lambda strategy: results[strategy][0], reverse=True)
    # Abstain outside the magnitude range shared by both candidate histories.
    ranges = []
    for strategy in CANDIDATES[mode]:
        magnitudes = [abs(s.hrv_change_pct) for s in sessions
                      if s.mode == mode and s.strategy == strategy]
        ranges.append((min(magnitudes), max(magnitudes)))
    low, high = max(r[0] for r in ranges), min(r[1] for r in ranges)
    reason = None
    if not low <= abs(hrv) <= high:
        reason = f"Outside shared history range ({low:.1f}-{high:.1f}% magnitude); collect feedback first."
    elif math.isclose(results[ordered[0]][0], results[ordered[1]][0], abs_tol=1e-9):
        reason = "Predicted scores are tied; user chooses."
    return (None if reason else ordered[0]), results, reason


def show_recommendation(sessions, hrv, task, mode, k=3):
    winner, results, reason = recommend(sessions, hrv, task, mode, k)
    print(f"\nCurrent Session | HRV {hrv:+.1f}% | {task} | {mode}")
    for strategy, (score, neighbors) in results.items():
        print(f"  {strategy} {NAMES[strategy]}: predicted {score:.2f}/5")
        total = sum(w for _, _, w in neighbors)
        for s, d, w in neighbors:
            print(f"    #{s.session_id}: HRV {s.hrv_change_pct:+.1f}%, {s.task_type}, "
                  f"feedback {s.goal_support:.1f}, distance {d:.3f}, weight {w/total:.1%}")
    if winner:
        gap = abs(results["S1" if mode == "Default" else "S3"][0]
                  - results["S2" if mode == "Default" else "S4"][0])
        print(f"Recommendation: {winner} {NAMES[winner]} | score gap {gap:.2f}")
    else:
        print(f"Recommendation withheld: {reason}")
    if any(all(s.task_type != task for s, _, _ in neighbors)
           for _, neighbors in results.values()):
        print("Evidence note: at least one candidate relies entirely on other task types.")


def evaluate(sessions, k=3):
    # Each held-out score is predicted without that record. Compare with an equally
    # held-out per-mode/per-strategy mean; this is not recommendation accuracy.
    errors, baseline_errors = [], []
    for held in sessions:
        train = [s for s in sessions if s.session_id != held.session_id]
        score, _ = predict_score(train, held.hrv_change_pct, held.task_type,
                                 held.mode, held.strategy, k)
        pool = [s.goal_support for s in train
                if s.mode == held.mode and s.strategy == held.strategy]
        errors.append(abs(score - held.goal_support))
        baseline_errors.append(abs(sum(pool) / len(pool) - held.goal_support))
    print(f"\nLeave-one-out score prediction ({len(sessions)} held-out records)")
    print(f"KNN mean absolute error: {sum(errors)/len(errors):.3f} score points")
    print(f"Strategy-mean baseline error: {sum(baseline_errors)/len(baseline_errors):.3f}")
    print("Synthetic score reconstruction only; no real-user efficacy or causal validation.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    parser.add_argument("--hrv", type=float, help="relative change in percentage points, e.g. -10.3")
    parser.add_argument("--task", choices=TASKS)
    parser.add_argument("--mode", choices=tuple(CANDIDATES))
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--evaluate", action="store_true")
    args = parser.parse_args()
    if args.k < 1:
        parser.error("--k must be positive")
    context = (args.hrv, args.task, args.mode)
    if any(x is not None for x in context) and not all(x is not None for x in context):
        parser.error("provide --hrv, --task and --mode together")
    try:
        sessions = load_sessions(args.csv)
        print(f"LightCue AI | {len(sessions)} simulated sessions | weighted KNN k={args.k}")
        print("Scores reflect synthetic preferences; HRV direction is not interpreted as good/bad.")
        if args.demo or (not args.evaluate and args.hrv is None):
            for mode in CANDIDATES:
                for hrv in (3.9, 10.0):
                    show_recommendation(sessions, hrv, "Ideation", mode, args.k)
        if args.hrv is not None:
            show_recommendation(sessions, args.hrv, args.task, args.mode, args.k)
        if args.evaluate:
            evaluate(sessions, args.k)
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
