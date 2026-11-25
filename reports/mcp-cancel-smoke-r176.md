# round-176：MCP 取消 + 配置透传真作业冒烟

- protocol=2025-06-18 tools=15
- job A submitted: 95b1d247f18840aa9ba690dc30ef74ab
- job A before cancel: {"state": "running", "ts": "2026-11-18T15:43:23+0800", "step": null, "progress": 0.01, "findings_url": null}
- cancel result: {"content": [{"type": "text", "text": "{\"job_id\": \"95b1d247f18840aa9ba690dc30ef74ab\", \"state\": \"cancelled\", \"killed_pids\": [49504], \"ledger_ok\": true}"}], "isError": false}
- job A after 2s: {"state": "cancelled", "ts": "2026-11-18T15:43:23+0800", "step": null, "progress": 0.01, "exit_code": null, "error": "cancelled", "findings_url": null}
- job A resource readable: True
- job B submitted: 7ed5cae824c04e48b8471e6ad6db93c9
- job B final: {"state": "done", "ts": "2026-11-18T15:43:30+0800", "step": 10, "progress": 1.0, "exit_code": 0, "error": null, "findings_url": "review://jobs/7ed5cae824c04e48b8471e6ad6db93c9"}
