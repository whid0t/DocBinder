# AIM Healthcare Hackathon: Synthetic Laboratory Parsing Test Set

20 standalone PDF laboratory reports: 10 fictional patients x 2 dates.
All values and identities are synthetic, not for clinical decisions.

report_manifest.csv: report / patient / date / scenario.
extracted_observations_ground_truth.csv: correct normalized parsed values, preserving original units.
expected_trends_ground_truth.csv: expected percentage changes across dates and missing values.

Important test conditions:
- P009 second report uses mmol/L glucose and umol/L creatinine: normalize before comparing.
- P010 later report omits eGFR; earlier report omits HbA1c: do not invent values.
- P007 patient uses phenprocoumon; raised INR requires treatment context, not a blanket alarm.
- GFR values are calculated with CKD-EPI 2021 creatinine formula from synthetic age/sex/creatinine values; they are rounded estimates.
- HbA1c percentage changes are relative percentage changes, NOT percentage-point changes.
- A comparison assumes same specimen/assay and adequate provenance; verify in production.
- LOINC and reference ranges are demo mapping examples; check laboratory methods and exact codes in real integration.
- Do not confuse data extraction with medical diagnosis; do not infer etiology from trends.
