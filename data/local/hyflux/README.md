# Hyflux test data

All four input documents (`doc_001` to `doc_004`) are **synthetic test documents written for this project**. No text in them comes from any real news outlet, review site or company publication. They loosely describe Hyflux Ltd's publicly reported 2018 difficulties so that the pipeline has a realistic credit-stress case to work on.

| File | Style | Purpose |
|------|-------|---------|
| `doc_001_debt_restructuring.json` | news | Debt restructuring application |
| `doc_002_employee_reviews.json` | employee reviews | Morale and management uncertainty |
| `doc_003_tuaspring_sale.json` | news | Difficulty selling the Tuaspring plant |
| `doc_004_company_statement_denial.json` | company statement | **Deliberately fabricated denial** that contradicts doc_001 and doc_003, used to test contradiction detection. Hyflux never issued this statement. |

Each file carries `"_notice": "SYNTHETIC TEST DOCUMENT"` and a `source_name` of the form `synthetic (... style)`. The `source_quality_score` values are test settings chosen to exercise the conflict rules, not ratings of any real source.

## Stored results

The other files are pipeline outputs from running SIS and FRD on these four documents: `extraction_results`, `validation_results`, `verification_results`, `conflict_results`, `sis_output`, `financial_profile`, `frd_score_result`, `pipeline_output`, `model_comparison_results` and `scoring_boundary_results`.

Earlier versions of the test documents named real outlets as their sources. Those names have since been replaced with the synthetic labels above, in both the structured `source_name` fields and the report text. Nothing else in the results was changed, and the evidence character offsets still match the document text.
