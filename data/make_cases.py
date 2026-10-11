"""Writes data/requests.jsonl: synthetic prior-authorization requests with gold labels.

Every member, provider and clinical note here is fictional. No real PHI.
"""
import json
from pathlib import Path

CASES = [
    # ---------------- MRI lumbar spine ----------------
    dict(request_id="PA-1001", policy_id="MRI-LSPINE-01", member_id="M-48213", provider="Lakeside Family Medicine",
         note="52-year-old with low back pain radiating to the left buttock for 10 weeks. Completed 6 weeks of physical "
              "therapy twice weekly and scheduled naproxen with minimal improvement. No saddle anesthesia, bowel or "
              "bladder changes. Strength 5/5 bilaterally. Requesting MRI to evaluate for disc herniation.",
         gold={"LBP_DURATION": "MET", "CONSERVATIVE_TX": "MET", "RED_FLAGS": "NOT_MET"}, decision="APPROVE"),
    dict(request_id="PA-1002", policy_id="MRI-LSPINE-01", member_id="M-55190", provider="Northside Urgent Care",
         note="34-year-old warehouse worker with acute low back pain that started 2 weeks ago after lifting boxes. "
              "Taking ibuprofen as needed. Physical therapy was recommended today. Neuro exam normal, no red flags. "
              "Patient requests MRI for reassurance.",
         gold={"LBP_DURATION": "NOT_MET", "CONSERVATIVE_TX": "NOT_MET", "RED_FLAGS": "NOT_MET"}, decision="PEND_CLINICAL_REVIEW"),
    dict(request_id="PA-1003", policy_id="MRI-LSPINE-01", member_id="M-60277", provider="Riverbend Internal Medicine",
         note="67-year-old with history of prostate cancer treated in 2019 presents with new, constant thoracolumbar "
              "back pain for 3 weeks, worse at night. No conservative therapy yet. Requesting MRI to rule out metastasis.",
         gold={"LBP_DURATION": "NOT_MET", "CONSERVATIVE_TX": "NOT_MET", "RED_FLAGS": "MET"}, decision="APPROVE"),
    dict(request_id="PA-1004", policy_id="MRI-LSPINE-01", member_id="M-71034", provider="Lakeside Family Medicine",
         note="45-year-old with chronic low back pain for about 4 months. PT was ordered in the spring, but the patient "
              "never attended because of work conflicts and has not tried NSAIDs due to a history of gastric ulcer. "
              "No red flags on exam.",
         gold={"LBP_DURATION": "MET", "CONSERVATIVE_TX": "NOT_MET", "RED_FLAGS": "NOT_MET"}, decision="PEND_CLINICAL_REVIEW"),
    dict(request_id="PA-1005", policy_id="MRI-LSPINE-01", member_id="M-82451", provider="Summit Spine Associates",
         note="58-year-old with low back pain since August and a new right foot drop noted over the past 10 days, "
              "with progressive weakness of ankle dorsiflexion (now 3/5). Urgent MRI requested.",
         gold={"LBP_DURATION": "MET", "CONSERVATIVE_TX": "NOT_DOCUMENTED", "RED_FLAGS": "MET"}, decision="APPROVE"),
    # ---------------- GLP-1 weight management ----------------
    dict(request_id="PA-2001", policy_id="GLP1-WM-01", member_id="M-33018", provider="Harbor Endocrinology",
         note="41-year-old with BMI 34.2, hypertension controlled on lisinopril. Enrolled in a structured weight "
              "management program with a registered dietitian since February (8 months), lost 3% of body weight. "
              "No personal or family history of medullary thyroid carcinoma or MEN2.",
         gold={"BMI_THRESHOLD": "MET", "LIFESTYLE_PROGRAM": "MET", "NO_MTC_MEN2": "MET"}, decision="APPROVE"),
    dict(request_id="PA-2002", policy_id="GLP1-WM-01", member_id="M-39542", provider="Harbor Endocrinology",
         note="29-year-old with BMI 28.1, no hypertension, diabetes, dyslipidemia or sleep apnea. Has followed a "
              "dietitian-led nutrition program for 5 months. Denies personal or family history of thyroid cancer.",
         gold={"BMI_THRESHOLD": "NOT_MET", "LIFESTYLE_PROGRAM": "MET", "NO_MTC_MEN2": "MET"}, decision="PEND_CLINICAL_REVIEW"),
    dict(request_id="PA-2003", policy_id="GLP1-WM-01", member_id="M-40871", provider="Greenway Primary Care",
         note="55-year-old with BMI 37 and type 2 diabetes (A1c 7.9). Completed a 6-month lifestyle program through "
              "the YMCA. Mother was diagnosed with medullary thyroid carcinoma at age 60.",
         gold={"BMI_THRESHOLD": "MET", "LIFESTYLE_PROGRAM": "MET", "NO_MTC_MEN2": "NOT_MET"}, decision="PEND_CLINICAL_REVIEW"),
    dict(request_id="PA-2004", policy_id="GLP1-WM-01", member_id="M-47716", provider="Greenway Primary Care",
         note="48-year-old with BMI 31.5 and obstructive sleep apnea on CPAP. Counseled on diet and exercise at this "
              "visit. Thyroid history not reviewed.",
         gold={"BMI_THRESHOLD": "MET", "LIFESTYLE_PROGRAM": "NOT_DOCUMENTED", "NO_MTC_MEN2": "NOT_DOCUMENTED"}, decision="REQUEST_INFO"),
    # ---------------- Total knee arthroplasty ----------------
    dict(request_id="PA-3001", policy_id="TKA-01", member_id="M-21907", provider="Midtown Orthopedics",
         note="71-year-old with right knee osteoarthritis. Standing X-rays show bone-on-bone medial compartment, "
              "Kellgren-Lawrence grade 4. Failed 9 months of physical therapy, two corticosteroid injections and "
              "daily meloxicam. Uses a cane and cannot climb stairs. BMI 29.",
         gold={"RADIOGRAPHIC_OA": "MET", "FAILED_CONSERVATIVE": "MET", "FUNCTIONAL_LIMITATION": "MET", "BMI_UNDER_40": "MET"}, decision="APPROVE"),
    dict(request_id="PA-3002", policy_id="TKA-01", member_id="M-26340", provider="Midtown Orthopedics",
         note="63-year-old with left knee pain. X-rays show Kellgren-Lawrence grade 2 changes with mild joint space "
              "narrowing. Completed 4 months of physical therapy and NSAIDs. Difficulty with long walks. BMI 33.",
         gold={"RADIOGRAPHIC_OA": "NOT_MET", "FAILED_CONSERVATIVE": "MET", "FUNCTIONAL_LIMITATION": "MET", "BMI_UNDER_40": "MET"}, decision="PEND_CLINICAL_REVIEW"),
    dict(request_id="PA-3003", policy_id="TKA-01", member_id="M-29875", provider="Bayview Joint Center",
         note="66-year-old with severe right knee OA, KL grade 4 on imaging. Six months of PT and a hyaluronic acid "
              "injection without relief; unable to walk more than one block. BMI 43.6; referred to bariatric clinic.",
         gold={"RADIOGRAPHIC_OA": "MET", "FAILED_CONSERVATIVE": "MET", "FUNCTIONAL_LIMITATION": "MET", "BMI_UNDER_40": "NOT_MET"}, decision="PEND_CLINICAL_REVIEW"),
]

out = Path(__file__).with_name("requests.jsonl")
with out.open("w") as f:
    for c in CASES:
        rec = {
            "request_id": c["request_id"], "policy_id": c["policy_id"], "member_id": c["member_id"],
            "provider": c["provider"], "clinical_note": c["note"],
            "gold": {"criteria": c["gold"], "decision": c["decision"]},
        }
        f.write(json.dumps(rec) + "\n")
print(f"wrote {len(CASES)} cases to {out}")
