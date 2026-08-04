# 04 — Tests
| TC-ID | Notes |
|-------|-------|
| TC-NEW-FBS-MARK-001 | PUT sgtin → DB+WB, check_status=new; bad kind/empty → 400; frozen status → 409 |
| TC-NEW-FBS-MARK-002 | sync updates check_status from GET meta |
| TC-NEW-FBS-MARK-003 | existing MarkingCode cis → marking_code_id set; missing → null ok |
| TC-NEW-FBS-MARK-004 | GET list all kinds; empty → [] |
