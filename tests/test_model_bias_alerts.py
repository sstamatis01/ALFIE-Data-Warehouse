from app.services.model_bias_alerts import build_model_bias_alerts, user_audit_note


def _row(attr, group, **rates):
    base = {
        "attribute_name": attr,
        "attribute_value": group,
        "pprev": 0.5,
        "tpr": 0.8,
        "fpr": 0.2,
        "ppr": 0.2,
    }
    base.update(rates)
    return base


def test_alerts_match_the_dataset_fairness_band_and_skip_small_groups():
    metrics = [
        _row("ethnicity", "Caucasian", pprev=0.4380165289, tpr=0.8085106383, fpr=0.2027027027, ppr=0.2994350282),
        _row("ethnicity", "Indian", pprev=0.7931034483, tpr=0.9090909091, fpr=0.64, ppr=0.2598870056),
        _row("ethnicity", "Middle Eastern", pprev=0.6515151515, tpr=0.9047619048, fpr=0.2083333333, ppr=0.2429378531),
        _row("ethnicity", "African", pprev=0.6, tpr=0.4, fpr=0.8, ppr=0.0338983051),
        _row("gender", "Male", pprev=0.6084656085, tpr=0.8461538462, fpr=0.387755102, ppr=0.6497175141),
        _row("gender", "Female", pprev=0.5961538462, tpr=0.8983050847, fpr=0.2, ppr=0.3502824859),
    ]
    disparities = [
        {
            "attribute_name": "ethnicity",
            "attribute_value": "Caucasian",
            "pprev_disparity": 1,
            "tpr_disparity": 1,
            "fpr_disparity": 1,
        },
        {
            "attribute_name": "ethnicity",
            "attribute_value": "Indian",
            "pprev_disparity": 1.8106701366,
            "tpr_disparity": 1.1244019139,
            "fpr_disparity": 3.1573333333,
        },
        {
            "attribute_name": "ethnicity",
            "attribute_value": "Middle Eastern",
            "pprev_disparity": 1.4874213836,
            "tpr_disparity": 1.119047619,
            "fpr_disparity": 1.0277777778,
        },
        {
            "attribute_name": "ethnicity",
            "attribute_value": "African",
            "pprev_disparity": 1.3698113208,
            "tpr_disparity": 0.4947368421,
            "fpr_disparity": 3.9466666667,
        },
        {
            "attribute_name": "gender",
            "attribute_value": "Male",
            "pprev_disparity": 1,
            "tpr_disparity": 1,
            "fpr_disparity": 1,
        },
        {
            "attribute_name": "gender",
            "attribute_value": "Female",
            "pprev_disparity": 0.9797658863,
            "tpr_disparity": 1.061633282,
            "fpr_disparity": 0.5157894737,
        },
    ]
    performance = [{"attribute_name": "group_performance", "attribute_value": "all", "pp": 177}]

    alerts = build_model_bias_alerts(
        metrics,
        disparities,
        {"ethnicity": "Caucasian", "gender": "Male"},
        performance,
    )

    assert alerts == [
        "ethnicity: African has fewer than 30 test rows — treat those ratios cautiously",
        "ethnicity: Indian selection rate 1.81 times Caucasian, outside [0.8, 1.25]",
        "ethnicity: Indian false-positive rate 3.16 times Caucasian, outside [0.8, 1.25]",
        "ethnicity: Middle Eastern selection rate 1.49 times Caucasian, outside [0.8, 1.25]",
        "gender: Female false-positive rate 0.52 times Male, outside [0.8, 1.25]",
    ]


def test_user_note_describes_the_mitigated_test_and_the_comparison_groups():
    note = user_audit_note(
        n_rows=293,
        eval_split="test",
        mitigated=True,
        reference_groups={"ethnicity": "Caucasian", "gender": "Male"},
        score_threshold=0.5,
        hard_scores=False,
    )

    assert note == (
        "The model was checked on the 293-row mitigated test set, "
        "with Caucasian for ethnicity and Male for gender as the comparison groups. "
        "A positive prediction means probability at least 0.5."
    )
