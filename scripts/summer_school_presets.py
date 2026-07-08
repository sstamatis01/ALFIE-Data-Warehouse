"""
Summer-school dataset presets for manual Kafka trigger scripts.

See summer_school_prepared/catalog_manifest.json for catalog metadata.
"""

from __future__ import annotations

# Bias step: run on split v2 (or v1 if no split). AutoML step: mitigated v3 after bias.
# time_budget_seconds (optional): AutoML training budget passed via Kafka (seconds).
SUMMER_SCHOOL_PRESETS: dict[str, dict[str, str | int]] = {
    "compas_recidivism": {
        "dataset_id": "compas_recidivism",
        "bias_version": "v2",
        "automl_version": "v3",
        "target_column": "two_year_recid",
        "task_type": "classification",
        "task_category": "tabular",
    },
    "adult_census_income": {
        "dataset_id": "adult_census_income",
        "bias_version": "v2",
        "automl_version": "v3",
        "target_column": "income",
        "task_type": "classification",
        "task_category": "tabular",
    },
    "german_credit": {
        "dataset_id": "german_credit",
        "bias_version": "v2",
        "automl_version": "v3",
        "target_column": "credit_risk",
        "task_type": "classification",
        "task_category": "tabular",
    },
    "communities_crime": {
        "dataset_id": "communities_crime",
        "bias_version": "v2",
        "automl_version": "v3",
        "target_column": "ViolentCrimesPerPop",
        "task_type": "regression",
        "task_category": "tabular",
    },
    "taiwan_credit_default": {
        "dataset_id": "taiwan_credit_default",
        "bias_version": "v2",
        "automl_version": "v3",
        "target_column": "default_next_month",
        "task_type": "classification",
        "task_category": "tabular",
    },
    "hateval_hate_speech_en": {
        "dataset_id": "hateval_hate_speech_en",
        "bias_version": "v2",
        "automl_version": "v3",
        "target_column": "label",
        "task_type": "classification",
        "task_category": "tabular",
        "time_budget_seconds": 300,
    },
    "asap_essay_scoring": {
        "dataset_id": "asap_essay_scoring",
        "bias_version": "v2",
        "automl_version": "v3",
        "target_column": "essay_score",
        "task_type": "regression",
        "task_category": "tabular",
        "time_budget_seconds": 300,
    },
    "hmda_mortgage_lending": {
        "dataset_id": "hmda_mortgage_lending",
        "bias_version": "v2",
        "automl_version": "v3",
        "target_column": "action_taken",
        "task_type": "classification",
        "task_category": "tabular",
    },
    "chicago_tnp_fares": {
        "dataset_id": "chicago_tnp_fares",
        "bias_version": "v2",
        "automl_version": "v3",
        "target_column": "Fare",
        "task_type": "regression",
        "task_category": "tabular",
    },
}

PRESET_NAMES = sorted(SUMMER_SCHOOL_PRESETS.keys())
