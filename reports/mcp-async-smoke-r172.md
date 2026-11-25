# round-172：MCP 真作业复冒烟（step 进度帧修复后）（submit / 断连重连 / status / resource）

- initialize: {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}, "resources": {}}, "serverInfo": {"name": "dev-agent", "version": "2.72.0"}}
- tools count: 14
- submit: {"content": [{"type": "text", "text": "{\"job_id\": \"78b7848a7c8a42fdb20d488b4dca0574\", \"state\": \"queued\", \"resource\": \"review://jobs/78b7848a7c8a42fdb20d488b4dca0574\"}"}], "isError": false}
- job_id: 78b7848a7c8a42fdb20d488b4dca0574
- client #1 closed (simulated disconnect)
- poll 0: state=running step=6 progress=0.6
- final status: {"state": "done", "ts": "2026-11-18T13:17:40+0800", "step": 10, "progress": 1.0, "exit_code": 0, "error": null, "findings_url": "review://jobs/78b7848a7c8a42fdb20d488b4dca0574"}
- resource text (head): {"ok": true, "state": "DONE", "run_id": "20261118-131735-9b6e46", "run_dir": "<repo>\\runs\\jobs\\78b7848a7c8a42fdb20d488b4dca0574\\run\\20261118-131735-9b6e46", "report_path": "<repo>\\runs\\jobs\\78b7848a7c8a42fdb20d488b4dca0574\\run\\20261118-131735-9b6e46\\report.md", "inline": [], "findings": [], "uncovered": [{"file": "calc.py", "hunk": 1, "start": 1, "end": 5}], "risk": {"name": "overall", "scale": 1, "coupling": 1, "stability": 2, "score": 1.3, "level": "低"}, "rounds_used": 3, "dynamic_used": 1, "tokens": 0, "gates":
- resources/list count: 2 (has job: True)
