# Model bias audit (Aequitas)

`POST /bias-reports/model-audit` scores a stored model and audits those predictions with [Aequitas](https://github.com/dssg/aequitas), the bias audit toolkit from the Center for Data Science and Public Policy. The package on PyPI is `aequitas` (this API uses the core audit, not the optional `flow` extras).

Aequitas does not open model weights. It compares binary predictions across protected groups: true positive rate, false positive rate, predicted prevalence, and the ratio of each group to a reference group. Significance tests are included when the sample allows them.

## What is reused from the dataset bias check

When `protected_attributes` and `positive_label` are omitted, the endpoint reads the latest dataset bias report:

- `fairness_profile.config.protected_attributes`
- `fairness_profile.config.privileged_groups` as the Aequitas reference group, when that value is still in the evaluation table
- `fairness_profile.config.pos_label` and `report.target_column`

The dataset id defaults to the model's `training_dataset`. The evaluation table is the `test` split when the dataset has one.

## Request

```json
{
  "user_id": "user123",
  "model_id": "model123",
  "dataset_id": "dataset123",
  "dataset_version": "v2",
  "model_version": "v1",
  "positive_label": "1",
  "score_threshold": 0.5
}
```

`GET /bias-reports/model-audit/{user_id}/{model_id}` returns the latest saved audit.

## Limits of this step

- Tabular classification only. The model archive must contain an AutoGluon `predictor.pkl` or a single sklearn `.pkl` / `.joblib` file.
- Vision, audio, and regression models return 422. Aequitas has no multiclass audit; a label with more than two classes is audited as one class versus the rest, and that class has to be `positive_label`.
- Labels that are already 0 and 1 do not need `positive_label`. Any other two-class label does.
- The model must be able to score the raw evaluation columns. An encoded sklearn file that expects different columns will fail with the loader error.
