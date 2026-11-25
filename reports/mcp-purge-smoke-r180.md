# round-180：阶段 C purge 真作业冒烟

- tools=16 last=code_review_purge
- job final state=done step=10
- precheck PROPOSED=True isError=False
- purge: {"job_id": "922ca8a6078d4f948e774a6bc7f1f9ca", "purged": true, "ledger_ok": true}
- resource after purge: isError=True
