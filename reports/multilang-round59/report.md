# round-59 多语言编码实跑证据（阶段四 4.2）

> 结论：**TS 与 Go 各一条任务端到端 resolved（2/2）**，满足 ROADMAP 4.2 验收
> 「至少一个 TS 与一个 Go 任务端到端 resolved」。样本 n=2、仓库为合成小样，
> 只证明通路可用，**不外推成功率**（D-030 同口径）。

## 1. 方法与口径

- 驱动：`agent/code-task.py` 走**宿主协议**（`CRA_LLM_PROVIDER=host`）。
  首跑落 `llm-tasks/<sha>.prompt.md` 并返回 `WAIT_HOST_LLM`（rc=1）；宿主
  会话模型把动作 JSON 写入 `.response.md` 后 `--resume`。
- 宿主动作**先手写、由脚本复放**（`host-responses/*.json` 入仓），不是另调
  模型、也不是事后挑结果；每一步的原始返回都在 `tasks/<name>/invoke-*.json`。
- 判 resolved 的合取条件（`run-bench.py` 内写死）：`state=DONE` 且
  `manifest.tests=pass` 且补丁含预期修复行 且 `manifest.test_engine` 等于
  预期引擎。
- 复现：`.venv/Scripts/python reports/multilang-round59/run-bench.py --out reports/multilang-round59`
  （Go 走 `CRA_GO` 或 `reports/_work/tooling/go/bin/go.exe`）。

## 2. 环境

| 组件 | 版本/来源 |
| --- | --- |
| Node | v22.23.3（`node --experimental-strip-types --test`，免安装依赖） |
| Go | go1.23.4 windows/amd64（南京大学镜像 `mirrors.nju.edu.cn`，9.2MB/s） |
| tree-sitter | 0.26.0 + `tree-sitter-python`、`tree-sitter-typescript==0.23.2`、`tree-sitter-go==0.25.0`（均 MIT，已登记 pyproject + licenses.json） |
| Python | .venv 3.12 |

## 3. 结果（bench.json，schema=multilang-bench/1）

| 任务 | 语言 | 测试引擎 | 轮次 | 调用 | 测试 | 补丁 | 耗时 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ts-calc | TS | `node`（自动识别 `*.test.ts`） | 1 | 2 | pass | 333 B，sha256 `92ced63b09df…` | 0.972 s |
| go-stack | Go | `go`（自动识别 `go.mod` → `go test ./...`） | 1 | 2 | pass | 249 B，sha256 `44ad8f82595c…` | 1.360 s |

两条任务都是「首轮 WAIT → 宿主一次 edit → resume 后测试转绿并 DONE」；
`edits.patch` 为干净 `a/ b/` unified diff（见 `tasks/*/edits.patch`），
`task-manifest.json` 均记录 `test_engine`。

## 4. 本轮新增能力（对应的契约测试见 tests/test_agent.py::TestMultiLang）

1. **repo map 多语言**（`agent/repo_map.py`）：TS 的 `function`/箭头函数
   `const f = () => …`/`class`/`interface`/`type`/`enum`、Go 的
   `function_declaration`/`method_declaration`/`type_spec` 都进符号表；
   `node_modules` 在目录级剪枝；Python 行为不变（原有 20 项相关契约全绿）。
2. **语法校验多语言**（`syntax_issues`）：`.py/.ts/.tsx/.js/.jsx/.mjs/.cjs/.go`
   走 tree-sitter；Python 保留 `ast.parse` 第二道网。反向验证：坏 TS/Go 必抓、
   好的不误报。
3. **测试引擎自动识别**（`agent/code-task.py`）：`--test-cmd` 显式覆盖 >
   `go.mod` → `go test ./...` > `package.json`（有 `scripts.test` → `npm test`，
   否则 Node 内置测试器跑 `*.test.ts/js`）> pytest。非 pytest 跑全命令，
   `manifest.test_engine` 记录实际引擎。
4. **搜索定义行识别**：`export function f` / `func F` 计入「定义 > 引用 > 注释」
   排序的第一档；`//` 行注释归第三档。

## 5. 不能证明什么（限制）

- n=2 且为合成 fixture：不覆盖真实仓库规模、类型检查（tsc）、Go 多包依赖。
- TS 走的是 Node 内置测试器，不是 `npm test`+真实依赖安装；npm 分支只做了
  单测级的检测/执行验证（fake repo，`npm test` 真跑转过一次 fail→pass 的
  负向对照），未在带依赖的 TS 工程上实跑。
- 宿主动作由会话模型手写：证明「模型看到多语言材料能产出正确编辑」，不证明
  任意模型/任意任务的命中率。
