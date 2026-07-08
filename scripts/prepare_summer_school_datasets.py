#!/usr/bin/env python3
"""
Phase 1: Prepare the summer school datasets into AutoDW-friendly files.

Inputs (repo-relative):
  summer school/

Outputs:
  summer_school_prepared/
    - compas_recidivism.csv
    - adult_census_income.csv
    - german_credit_numeric.csv
    - communities_crime.csv
    - taiwan_credit_default.csv
    - hateval_hate_speech_en.csv
    - asap_essay_scoring.csv
    - hmda_mortgage_lending_sample.csv
    - chicago_tnp_fares_sample.csv
    - catalog_manifest.json

Notes:
  - HMDA (~4GB) and TNP (~1.5GB) are downsampled for workshop use (default 400k rows).
  - Does not upload anything; only prepares local files + a manifest for later ingestion.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd


REPO_DEFAULT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLE_ROWS = 400_000


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _read_text_lines(p: Path) -> list[str]:
    # tolerate odd encodings (UCI datasets often have latin-1 artifacts)
    try:
        return p.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return p.read_text(encoding="latin-1").splitlines()


def _write_manifest(out_path: Path, items: list[dict]) -> None:
    out_path.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _safe_slug(s: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", (s or "").strip().lower()).strip("_")


def _count_csv_data_rows(path: Path) -> int:
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        return max(0, sum(1 for _ in f) - 1)


def _downsample_csv_systematic(
    src: Path,
    out: Path,
    *,
    target_rows: int,
    transform_chunk: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
) -> int:
    """
    Stream a large CSV, optionally transform each chunk, and keep every Nth row
    to reach ~target_rows without loading the full file into memory.
    Returns number of rows written.
    """
    total = _count_csv_data_rows(src)
    if total <= 0:
        raise ValueError(f"No data rows in {src}")
    step = max(1, total // target_rows)

    first = True
    kept = 0
    global_i = 0
    for chunk in pd.read_csv(src, chunksize=100_000, low_memory=False):
        if transform_chunk is not None:
            chunk = transform_chunk(chunk)
        if chunk.empty:
            global_i += 0
            continue

        pick_idx = [j for j in range(len(chunk)) if (global_i + j) % step == 0]
        global_i += len(chunk)
        if not pick_idx:
            continue

        part = chunk.iloc[pick_idx]
        if kept + len(part) > target_rows:
            part = part.iloc[: target_rows - kept]

        part.to_csv(out, mode="w" if first else "a", header=first, index=False)
        kept += len(part)
        first = False
        if kept >= target_rows:
            break

    return kept


def prepare_compas(src_root: Path, out_dir: Path) -> Path:
    src = src_root / "COMPAS" / "1-compas_recidivism_prediction.csv"
    out = out_dir / "compas_recidivism.csv"
    shutil.copyfile(src, out)
    return out


def _parse_adult_names_columns(adult_names_path: Path) -> list[str]:
    """
    adult.names lists attribute definitions like:
      age: continuous.
      workclass: Private, Self-emp-not-inc, ...
    We parse the leading token before ':'.
    """
    cols: list[str] = []
    for line in _read_text_lines(adult_names_path):
        line = line.strip()
        if not line or line.startswith("|"):
            continue
        if ":" in line:
            name = line.split(":", 1)[0].strip()
            if name and " " not in name and name not in cols:
                cols.append(name)
    # The label is not declared as an attribute in the same way; add it.
    cols.append("income")
    return cols


def _parse_adult_data_lines(lines: Iterable[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in lines:
        if not line:
            continue
        if line.startswith("|"):
            # comments in adult.test
            continue
        parts = [p.strip() for p in line.split(",")]
        if not parts or len(parts) < 2:
            continue
        # adult data often ends with a trailing '.' on label in test set (e.g. '<=50K.')
        parts[-1] = parts[-1].rstrip(".").strip()
        rows.append(parts)
    return rows


def prepare_adult_census(src_root: Path, out_dir: Path) -> Path:
    names_p = src_root / "adult census" / "adult.names"
    data_p = src_root / "adult census" / "adult.data"
    test_p = src_root / "adult census" / "adult.test"

    cols = _parse_adult_names_columns(names_p)
    train_rows = _parse_adult_data_lines(_read_text_lines(data_p))
    test_rows = _parse_adult_data_lines(_read_text_lines(test_p))
    rows = train_rows + test_rows

    df = pd.DataFrame(rows, columns=cols)
    df = df.replace("?", pd.NA)

    # Cast obvious numeric columns when possible (helps downstream metadata + split logic).
    numeric_candidates = {
        "age",
        "fnlwgt",
        "education-num",
        "capital-gain",
        "capital-loss",
        "hours-per-week",
    }
    for c in numeric_candidates:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    out = out_dir / "adult_census_income.csv"
    df.to_csv(out, index=False)
    return out


def prepare_german_credit_numeric(src_root: Path, out_dir: Path) -> Path:
    p = src_root / "GCD" / "german.data-numeric"
    df = pd.read_csv(p, sep=r"\s+", header=None, engine="python")
    if df.shape[1] < 2:
        raise ValueError("German numeric dataset: unexpected column count")

    # Last column is the class label (1 good, 2 bad).
    n = df.shape[1]
    cols = [f"f{i}" for i in range(1, n)]
    cols.append("credit_risk")
    df.columns = cols
    df["credit_risk"] = pd.to_numeric(df["credit_risk"], errors="coerce")

    out = out_dir / "german_credit_numeric.csv"
    df.to_csv(out, index=False)
    return out


def _parse_communities_names(communities_names_path: Path) -> list[str]:
    """
    Parse @attribute lines from communities.names (ARFF-like).
    Example: @attribute state numeric
    """
    cols: list[str] = []
    for line in _read_text_lines(communities_names_path):
        line = line.strip()
        if not line.lower().startswith("@attribute"):
            continue
        # @attribute <name> <type>
        parts = line.split()
        if len(parts) >= 3:
            name = parts[1].strip()
            cols.append(name)
    return cols


def prepare_communities_crime(src_root: Path, out_dir: Path) -> Path:
    names_p = src_root / "CCD" / "communities.names"
    data_p = src_root / "CCD" / "communities.data"
    cols = _parse_communities_names(names_p)
    df = pd.read_csv(
        data_p,
        header=None,
        names=cols if cols else None,
        na_values=["?"],
        low_memory=False,
    )
    out = out_dir / "communities_crime.csv"
    df.to_csv(out, index=False)
    return out


def prepare_taiwan_credit(src_root: Path, out_dir: Path) -> Path:
    p = src_root / "DCCCD" / "8-default_of_credit_card_clients.xls"

    # Try header=0 first; fall back to header=1 if the first row is a title row.
    df = pd.read_excel(p, header=0)
    if any(str(c).lower().startswith("unnamed") for c in df.columns):
        df = pd.read_excel(p, header=1)

    # Normalize column names a bit (strip, collapse spaces).
    df.columns = [re.sub(r"\s+", " ", str(c).strip()) for c in df.columns]

    # Heuristic target detection
    target = None
    for c in df.columns:
        c_l = c.lower()
        if "default" in c_l and ("next" in c_l or "month" in c_l):
            target = c
            break
    if target is None:
        # common exact name in this dataset
        for c in df.columns:
            if c.strip().lower() == "default payment next month":
                target = c
                break
    if target is None:
        # fallback: last column
        target = df.columns[-1]

    if target != "default_next_month":
        df = df.rename(columns={target: "default_next_month"})

    out = out_dir / "taiwan_credit_default.csv"
    df.to_csv(out, index=False)
    return out


def prepare_hateval_en(src_root: Path, out_dir: Path) -> Path:
    tweets_p = src_root / "hateval" / "2" / "extended_test" / "test_a_tweets_all.tsv"
    labels_p = src_root / "hateval" / "2" / "extended_test" / "test_a_labels_all.csv"

    tweets = pd.read_csv(tweets_p, sep="\t", quoting=csv.QUOTE_MINIMAL)
    # Labels file has no header: "<id>,<label>"
    labels = pd.read_csv(labels_p, header=None, names=["id", "label"])

    # Normalize ID columns for tweets (expected header: id\tweet)
    if "id" not in tweets.columns:
        tweets.columns = [str(c).strip().lower() for c in tweets.columns]

    df = tweets.merge(labels, on="id", how="inner")
    # Expected columns: id, tweet, label (OFF/NOT)
    if "tweet" not in df.columns:
        # sometimes column could be named "text"
        for cand in ("text", "content"):
            if cand in df.columns:
                df = df.rename(columns={cand: "tweet"})
                break

    if "label" not in df.columns:
        # some label files use OFF as column; last column is the label
        df = df.rename(columns={df.columns[-1]: "label"})

    out = out_dir / "hateval_hate_speech_en.csv"
    df.to_csv(out, index=False)
    return out


def prepare_asap(src_root: Path, out_dir: Path) -> Path:
    asap_dir = src_root / "asap"
    train_p = asap_dir / "training_set_rel3.tsv"
    valid_p = asap_dir / "valid_set.tsv"
    test_p = asap_dir / "test_set.tsv"

    def read_tsv(p: Path) -> pd.DataFrame:
        # Robust decoding: ASAP files may contain mixed encodings / smart quotes.
        # We decode bytes ourselves and replace invalid characters to avoid hard failures.
        import io

        raw = p.read_bytes()
        text = None
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                text = raw.decode(enc, errors="replace")
                break
            except Exception:
                continue
        if text is None:
            text = raw.decode("latin-1", errors="replace")

        return pd.read_csv(
            io.StringIO(text),
            sep="\t",
            quoting=csv.QUOTE_MINIMAL,
            low_memory=False,
        )

    train = read_tsv(train_p)
    train["split"] = "train"
    valid = read_tsv(valid_p)
    valid["split"] = "valid"
    test = read_tsv(test_p)
    test["split"] = "test"

    # Union schema
    all_cols = sorted(set(train.columns) | set(valid.columns) | set(test.columns))
    train = train.reindex(columns=all_cols)
    valid = valid.reindex(columns=all_cols)
    test = test.reindex(columns=all_cols)
    df = pd.concat([train, valid, test], ignore_index=True)

    # Prefer a consistent target name for summer school
    if "domain1_score" in df.columns and "essay_score" not in df.columns:
        df = df.rename(columns={"domain1_score": "essay_score"})

    out = out_dir / "asap_essay_scoring.csv"
    df.to_csv(out, index=False)
    return out


def _transform_hmda_chunk(df: pd.DataFrame) -> pd.DataFrame:
    """Keep numeric / code columns; drop redundant long text *_name fields."""
    keep = [c for c in df.columns if not str(c).endswith("_name")]
    df = df[keep]
    df = df.drop(columns=["respondent_id", "sequence_number"], errors="ignore")
    return df


def prepare_hmda_mortgage_lending(
    src_root: Path, out_dir: Path, *, sample_rows: int = DEFAULT_SAMPLE_ROWS
) -> Path:
    src = src_root / "HMDA" / "mortage_lending_discrimination.csv"
    out = out_dir / "hmda_mortgage_lending_sample.csv"
    if not src.exists():
        raise FileNotFoundError(f"HMDA source not found: {src}")
    kept = _downsample_csv_systematic(
        src,
        out,
        target_rows=sample_rows,
        transform_chunk=_transform_hmda_chunk,
    )
    print(f"  HMDA downsampled to {kept} rows (target {sample_rows})")
    return out


_TNP_DROP = [
    "Trip ID",
    "Taxi ID",
    "Pickup Centroid Location",
    "Dropoff Centroid  Location",
]
_TNP_RENAME = {
    "Trip Start Timestamp": "trip_start",
    "Trip End Timestamp": "trip_end",
    "Trip Seconds": "trip_seconds",
    "Trip Miles": "trip_miles",
    "Pickup Census Tract": "pickup_census_tract",
    "Dropoff Census Tract": "dropoff_census_tract",
    "Pickup Community Area": "pickup_community_area",
    "Dropoff Community Area": "dropoff_community_area",
    "Payment Type": "payment_type",
    "Pickup Centroid Latitude": "pickup_lat",
    "Pickup Centroid Longitude": "pickup_lon",
    "Dropoff Centroid Latitude": "dropoff_lat",
    "Dropoff Centroid Longitude": "dropoff_lon",
}


def _transform_tnp_chunk(df: pd.DataFrame) -> pd.DataFrame:
    df = df.drop(columns=_TNP_DROP, errors="ignore")
    df = df.rename(columns=_TNP_RENAME)
    if "Fare" in df.columns:
        df = df.dropna(subset=["Fare"])
    return df


def prepare_chicago_tnp_fares(
    src_root: Path, out_dir: Path, *, sample_rows: int = DEFAULT_SAMPLE_ROWS
) -> Path:
    src = src_root / "TNP" / "Taxi_Trips_-_2023.csv"
    out = out_dir / "chicago_tnp_fares_sample.csv"
    if not src.exists():
        raise FileNotFoundError(f"TNP source not found: {src}")
    kept = _downsample_csv_systematic(
        src,
        out,
        target_rows=sample_rows,
        transform_chunk=_transform_tnp_chunk,
    )
    print(f"  TNP downsampled to {kept} rows (target {sample_rows})")
    return out


def build_manifest(out_dir: Path) -> Path:
    items = [
        {
            "dataset_id": "compas_recidivism",
            "name": "COMPAS Recidivism Prediction",
            "prepared_filename": "compas_recidivism.csv",
            "task_type": "classification",
            "target_column_name": "two_year_recid",
            "tags": ["summer-school", "public", "criminal-justice"],
            "protected_attributes": ["race", "sex", "age", "age_cat"],
        },
        {
            "dataset_id": "adult_census_income",
            "name": "Adult / Census Income",
            "prepared_filename": "adult_census_income.csv",
            "task_type": "classification",
            "target_column_name": "income",
            "tags": ["summer-school", "public", "employment"],
            "protected_attributes": ["sex", "race", "native-country"],
        },
        {
            "dataset_id": "asap_essay_scoring",
            "name": "ASAP Automated Essay Scoring",
            "prepared_filename": "asap_essay_scoring.csv",
            "task_type": "regression",
            "target_column_name": "essay_score",
            "tags": ["summer-school", "public", "education", "nlp"],
            "protected_attributes": [],
            "notes": "Contains raw essay text; downstream pipeline may require NLP-aware modeling.",
        },
        {
            "dataset_id": "hateval_hate_speech_en",
            "name": "HatEval / OffensEval-style Hate Speech (EN subset)",
            "prepared_filename": "hateval_hate_speech_en.csv",
            "task_type": "classification",
            "target_column_name": "label",
            "tags": ["summer-school", "public", "nlp", "social-media"],
            "protected_attributes": [],
            "notes": "Prepared from hateval/2/extended_test test_a_tweets_all.tsv + test_a_labels_all.csv",
        },
        {
            "dataset_id": "communities_crime",
            "name": "Communities and Crime",
            "prepared_filename": "communities_crime.csv",
            "task_type": "regression",
            "target_column_name": "ViolentCrimesPerPop",
            "tags": ["summer-school", "public", "insurance", "socioeconomic"],
            "protected_attributes": [],
            "notes": "Includes many proxy variables correlated with protected attributes; treat with care.",
        },
        {
            "dataset_id": "german_credit",
            "name": "German Credit (numeric)",
            "prepared_filename": "german_credit_numeric.csv",
            "task_type": "classification",
            "target_column_name": "credit_risk",
            "tags": ["summer-school", "public", "finance"],
            "protected_attributes": [],
            "notes": "credit_risk: 1=good, 2=bad (original encoding).",
        },
        {
            "dataset_id": "taiwan_credit_default",
            "name": "Default of Credit Card Clients (Taiwan)",
            "prepared_filename": "taiwan_credit_default.csv",
            "task_type": "classification",
            "target_column_name": "default_next_month",
            "tags": ["summer-school", "public", "finance"],
            "protected_attributes": ["SEX", "AGE", "EDUCATION", "MARRIAGE"],
        },
        {
            "dataset_id": "hmda_mortgage_lending",
            "name": "HMDA Mortgage Lending (sample)",
            "prepared_filename": "hmda_mortgage_lending_sample.csv",
            "task_type": "classification",
            "target_column_name": "action_taken",
            "tags": ["summer-school", "public", "finance", "housing"],
            "protected_attributes": [
                "applicant_race_1",
                "applicant_ethnicity",
                "applicant_sex",
                "state_code",
                "county_code",
            ],
            "notes": "Downsampled from mortage_lending_discrimination.csv; action_taken is the loan outcome code.",
        },
        {
            "dataset_id": "chicago_tnp_fares",
            "name": "Chicago Taxi Trips 2023 (sample)",
            "prepared_filename": "chicago_tnp_fares_sample.csv",
            "task_type": "regression",
            "target_column_name": "Fare",
            "tags": ["summer-school", "public", "transport", "geographic"],
            "protected_attributes": [
                "pickup_community_area",
                "dropoff_community_area",
                "payment_type",
                "Company",
            ],
            "notes": "Downsampled from Taxi_Trips_-_2023.csv; WKT POINT columns dropped; target is Fare.",
        },
    ]
    out = out_dir / "catalog_manifest.json"
    _write_manifest(out, items)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Prepare summer school datasets (Phase 1)")
    ap.add_argument("--repo", default=str(REPO_DEFAULT), help="Repo root path")
    ap.add_argument("--src", default="summer school", help="Relative path to raw datasets folder")
    ap.add_argument("--out", default="summer_school_prepared", help="Relative output folder")
    ap.add_argument(
        "--sample-rows",
        type=int,
        default=DEFAULT_SAMPLE_ROWS,
        help="Rows to keep when downsampling HMDA/TNP (default 400000)",
    )
    ap.add_argument(
        "--skip-large",
        action="store_true",
        help="Skip HMDA/TNP downsampling (faster; only refresh the 7 smaller datasets)",
    )
    ap.add_argument(
        "--only-large",
        action="store_true",
        help="Only downsample HMDA/TNP and refresh catalog_manifest.json",
    )
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    src_root = (repo / args.src).resolve()
    out_dir = (repo / args.out).resolve()
    _ensure_dir(out_dir)

    if not src_root.exists():
        raise SystemExit(f"Source folder not found: {src_root}")

    written: list[Path] = []
    if not args.only_large:
        written.append(prepare_compas(src_root, out_dir))
        written.append(prepare_adult_census(src_root, out_dir))
        written.append(prepare_german_credit_numeric(src_root, out_dir))
        written.append(prepare_communities_crime(src_root, out_dir))
        written.append(prepare_taiwan_credit(src_root, out_dir))
        written.append(prepare_hateval_en(src_root, out_dir))
        written.append(prepare_asap(src_root, out_dir))
    if not args.skip_large:
        written.append(
            prepare_hmda_mortgage_lending(src_root, out_dir, sample_rows=args.sample_rows)
        )
        written.append(
            prepare_chicago_tnp_fares(src_root, out_dir, sample_rows=args.sample_rows)
        )
    written.append(build_manifest(out_dir))

    # Print a short summary for logs
    for p in written:
        try:
            mb = p.stat().st_size / (1024 * 1024)
            print(f"Wrote {p.relative_to(repo)} ({mb:.2f} MB)")
        except Exception:
            print(f"Wrote {p}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

