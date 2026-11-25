## Protocol notes

- You have a total budget of N rounds; each round you output exactly one action object.
- Use search/list and ranged reads (path:start-end or path#Symbol) to locate precisely; avoid repeated whole-file or overlapping reads.
- Read-only exploration budget: at most N/3 rounds. Once you know the target code, EDIT immediately; do not keep reading.
- If you notice you have read many files without editing, stop exploring and act on what you have.
- The repository test suite is already seeded with failing tests that encode the requested behavior; it is the completion criterion. After edits the loop runs the suite automatically and reports failures back to you — read the failure output carefully and fix the failing tests one by one.
- The failing tests live in <tests/...>::<node-id> (read them early; name the files and, where known, the failing node ids — round-79 experiment: this pointer alone lifted a 0-edit floor case to resolved).
- Prefer the smallest change that makes the failing tests pass without breaking others.
