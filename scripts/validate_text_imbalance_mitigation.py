#!/usr/bin/env python3
"""
Validate class-imbalance profile + text-safe train resampling on a text+label CSV.

Default input: compliance_alerts_synthetic_30000.csv (or path via --csv).

Usage:
  python scripts/validate_text_imbalance_mitigation.py
  python scripts/validate_text_imbalance_mitigation.py --csv path/to/file.csv --target labels
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.services.class_imbalance import (  # noqa: E402
    build_class_imbalance_profile,
    resample_text_train_balance,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    default_csv = REPO_ROOT / "scripts" / "fixtures" / "compliance_alerts_synthetic_30000.csv"
    if not default_csv.is_file():
        default_csv = (
            Path.home() / "Downloads" / "compliance_alerts_synthetic_30000.csv"
        )
    parser.add_argument(
        "--csv",
        default=str(default_csv),
        help="Path to text+label CSV",
    )
    parser.add_argument("--target", default="labels", help="Target column name")
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "scripts" / "_compliance_imbalance_validation.json"),
        help="Write validation JSON here",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_file():
        print(f"ERROR: CSV not found: {csv_path}", file=sys.stderr)
        return 1

    df = pd.read_csv(csv_path)
    print(f"Loaded {csv_path} shape={df.shape}")

    profile = build_class_imbalance_profile(df, args.target)
    if not profile:
        print("ERROR: no class_imbalance profile (check target column)", file=sys.stderr)
        return 1

    print(
        f"modality={profile['modality']} ratio={profile['imbalance_ratio']} "
        f"extreme={profile['extreme_imbalance']} counts={profile['class_counts']}"
    )
    assert profile["extreme_imbalance"] is True, "expected extreme_imbalance=True"
    assert profile["modality"] == "text_classification", "expected text_classification"
    assert profile["imbalance_ratio"] >= 20, "expected imbalance_ratio >= 20"

    # Simulate 70% train slice (shuffle + head) then resample
    train = df.sample(frac=0.7, random_state=42).reset_index(drop=True)
    balanced, meta = resample_text_train_balance(train, args.target)
    print(f"train before={meta['before']} after={meta['after']}")
    print(f"rows {meta['n_rows_before']} -> {meta['n_rows_after']}")

    after_counts = list(meta["after"].values())
    assert min(after_counts) >= meta["minority_floor"] * 0.9, (
        "minority classes should reach floor after oversample"
    )
    assert max(after_counts) <= meta["majority_cap"] * 1.01, (
        "majority should be capped"
    )
    # Minority must grow vs original train counts for the rarest class
    before_min_label = min(meta["before"], key=meta["before"].get)
    assert meta["after"][before_min_label] > meta["before"][before_min_label], (
        "rarest class should be oversampled"
    )

    # Mitigated train must not be ~95% majority anymore
    after_total = sum(meta["after"].values())
    maj = max(meta["after"], key=meta["after"].get)
    maj_share = meta["after"][maj] / after_total
    print(f"majority share after resample: {maj_share:.4f}")
    assert maj_share < 0.7, "majority share should drop well below 70% after balance"

    out = {
        "csv": str(csv_path),
        "profile": profile,
        "resample": meta,
        "majority_share_after": round(maj_share, 4),
        "ok": True,
    }
    out_path = Path(args.out)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    print("VALIDATION OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
