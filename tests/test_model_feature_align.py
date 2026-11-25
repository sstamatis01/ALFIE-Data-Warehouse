import pandas as pd

from app.services.model_feature_align import restore_group_columns, select_scoring_frame


def test_selects_mitigated_version_when_requested_table_is_still_categorical():
    raw = pd.DataFrame({"label": [0], "ethnicity": ["Caucasian"], "gender": ["Male"]})
    mitigated = pd.DataFrame(
        {
            "label": [0],
            "ethnicity_Caucasian": [True],
            "ethnicity_Asian": [False],
            "gender_Male": [True],
            "gender_Female": [False],
        }
    )
    expected = [
        "ethnicity_Caucasian",
        "ethnicity_Asian",
        "gender_Male",
        "gender_Female",
    ]

    chosen = select_scoring_frame(
        [("v2", raw), ("v3", mitigated)],
        expected,
        preferred_version="v2",
    )

    assert chosen is not None
    assert chosen[0] == "v3"


def test_restores_group_labels_from_one_hot_columns():
    frame = pd.DataFrame(
        {
            "ethnicity_Caucasian": [True, False],
            "ethnicity_Asian": [False, True],
            "gender_Male": [True, False],
            "gender_Female": [False, True],
        }
    )

    restored_frame, restored = restore_group_columns(frame, ["ethnicity", "gender"])

    assert restored == ["ethnicity", "gender"]
    assert restored_frame["ethnicity"].tolist() == ["Caucasian", "Asian"]
    assert restored_frame["gender"].tolist() == ["Male", "Female"]
