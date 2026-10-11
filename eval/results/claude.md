# Eval results: claude (claude-sonnet-5-5)

| Metric | Value |
| --- | --- |
| Requests | 12 |
| Decision accuracy | 100% |
| Criterion accuracy | 87% |
| Unsafe approvals (target 0) | 0 |
| Missed approvals | 0 |
| Ungrounded evidence caught | 0 |

| Request | Gold | Predicted | Criterion misses |
| --- | --- | --- | --- |
| PA-1001 | APPROVE | APPROVE | - |
| PA-1002 | PEND_CLINICAL_REVIEW | PEND_CLINICAL_REVIEW | - |
| PA-1003 | APPROVE | APPROVE | - |
| PA-1004 | PEND_CLINICAL_REVIEW | PEND_CLINICAL_REVIEW | - |
| PA-1005 | APPROVE | APPROVE | LBP_DURATION: NOT_DOCUMENTED (gold MET) |
| PA-2001 | APPROVE | APPROVE | - |
| PA-2002 | PEND_CLINICAL_REVIEW | PEND_CLINICAL_REVIEW | LIFESTYLE_PROGRAM: NOT_DOCUMENTED (gold MET); NO_MTC_MEN2: NOT_DOCUMENTED (gold MET) |
| PA-2003 | PEND_CLINICAL_REVIEW | PEND_CLINICAL_REVIEW | - |
| PA-2004 | REQUEST_INFO | REQUEST_INFO | - |
| PA-3001 | APPROVE | APPROVE | - |
| PA-3002 | PEND_CLINICAL_REVIEW | PEND_CLINICAL_REVIEW | FAILED_CONSERVATIVE: NOT_DOCUMENTED (gold MET); FUNCTIONAL_LIMITATION: NOT_DOCUMENTED (gold MET) |
| PA-3003 | PEND_CLINICAL_REVIEW | PEND_CLINICAL_REVIEW | - |
