# round-171：MCP 真作业冒烟（submit / 断连重连 / status / resource）

- initialize: {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}, "resources": {}}, "serverInfo": {"name": "dev-agent", "version": "2.72.0"}}
- tools count: 14
- submit: {"content": [{"type": "text", "text": "{\"job_id\": \"7d3620da213a49c9afb07564b6e44416\", \"state\": \"queued\", \"resource\": \"review://jobs/7d3620da213a49c9afb07564b6e44416\"}"}], "isError": false}
- job_id: 7d3620da213a49c9afb07564b6e44416
- client #1 closed (simulated disconnect)
- poll 0: state=running step=None progress=0.01
- final status: {"state": "done", "ts": "2026-11-18T12:45:58+0800", "step": 0, "progress": 1.0, "exit_code": 0, "error": null, "findings_url": "review://jobs/7d3620da213a49c9afb07564b6e44416"}
- resource text (head): {"ok": true, "state": "DONE", "run_id": "20261118-124553-7e231e", "run_dir": "<repo>\\runs\\jobs\\7d3620da213a49c9afb07564b6e44416\\run\\20261118-124553-7e231e", "report_path": "<repo>\\runs\\jobs\\7d3620da213a49c9afb07564b6e44416\\run\\20261118-124553-7e231e\\report.md", "inline": [], "findings": [], "uncovered": [{"file": "calc.py", "hunk": 1, "start": 1, "end": 5}], "risk": {"name": "overall", "scale": 1, "coupling": 1, "stability": 2, "score": 1.3, "level": "低"}, "rounds_used": 3, "dynamic_used": 1, "tokens": 0, "gates":
- resources/list count: 1 (has job: True)
