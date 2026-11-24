# Bias and transformation report PDF

`GET /bias-reports/{user_id}/{dataset_id}/pdf` renders the stored bias report, and the matching transformation report when one exists, as a single PDF. The front end only has to request the URL and show or download the file. Numbers come from the stored JSON. Missing sections are labelled "not available".

The same route is available under `/autodw` when the API is mounted there.

## Request

```http
GET /bias-reports/{user_id}/{dataset_id}/pdf?version=v2&include_transformation=true&tz=Europe/Bucharest&download=false
```

| Query | Default | Meaning |
|---|---|---|
| `version` | latest bias report | Dataset version of the bias report, same as `GET /bias-reports/{user_id}/{dataset_id}` |
| `include_transformation` | `true` | When false, the transformation section is left out |
| `tz` | `REPORT_TIMEZONE` (UTC) | IANA timezone for displayed timestamps. Unknown values return 400 |
| `download` | `false` | `false` sends `Content-Disposition: inline`. `true` sends `attachment` |

`200` is `application/pdf`. A missing bias report is `404`. A render failure is `500`.

The transformation report is resolved in this order:

1. `report.mitigation.mitigated_dataset_version` → transformation report for that version
2. otherwise `transformation_report_id` on the bias report
3. otherwise the PDF has no transformation section. If mitigation was performed but no report is stored, the PDF includes a "Transformation report: not available" page

## What the PDF contains

1. Status and plain-language alerts
2. Class balance and representation charts
3. Label share per group, fairness gauges, pairwise and intersection views
4. Data quality and technical details
5. Transformation pipeline with before → after charts, when a transformation report was found

Fairness metrics appear when the bias report has a `fairness_profile`. Class distribution appears when it has `class_imbalance`. Alerts that no transformation step addresses are marked "Not addressed".
