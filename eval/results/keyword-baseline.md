# Eval results: keyword-baseline

| Metric | Value |
| --- | --- |
| Requests | 12 |
| Decision accuracy | 83% |
| Criterion accuracy | 82% |
| Unsafe approvals (target 0) | 1 |
| Missed approvals | 1 |
| Ungrounded evidence caught | 0 |

| Request | Gold | Predicted | Criterion misses |
| --- | --- | --- | --- |
| PA-1001 | APPROVE | APPROVE | RED_FLAGS: MET (gold NOT_MET) |
| PA-1002 | PEND_CLINICAL_REVIEW | PEND_CLINICAL_REVIEW | CONSERVATIVE_TX: MET (gold NOT_MET) |
| PA-1003 | APPROVE | APPROVE | LBP_DURATION: MET (gold NOT_MET); CONSERVATIVE_TX: NOT_DOCUMENTED (gold NOT_MET) |
| PA-1004 | PEND_CLINICAL_REVIEW | PEND_CLINICAL_REVIEW | - |
| PA-1005 | APPROVE | APPROVE | - |
| PA-2001 | APPROVE | PEND_CLINICAL_REVIEW **x** | NO_MTC_MEN2: NOT_MET (gold MET) |
| PA-2002 | PEND_CLINICAL_REVIEW | APPROVE **x** | BMI_THRESHOLD: MET (gold NOT_MET) |
| PA-2003 | PEND_CLINICAL_REVIEW | PEND_CLINICAL_REVIEW | - |
| PA-2004 | REQUEST_INFO | REQUEST_INFO | - |
| PA-3001 | APPROVE | APPROVE | - |
| PA-3002 | PEND_CLINICAL_REVIEW | PEND_CLINICAL_REVIEW | FUNCTIONAL_LIMITATION: NOT_DOCUMENTED (gold MET) |
| PA-3003 | PEND_CLINICAL_REVIEW | PEND_CLINICAL_REVIEW | - |
