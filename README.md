# DocumentBasedHarness

基于文档与材料的 Communication / Document Authoring Harness。

核心思想：**所有输出媒介都不直接从源材料生成**。材料先变成可追溯的证据（evidence），
证据支撑论断（claim），论断组织成故事（narrative），故事再投影成不同媒介的计划
（projection），最后才渲染成成品。Report 和 Presentation 是同一个 narrative 的两种
投影，而不是互相压缩的产物。

```text
sources → evidence → brief ─Gate1─→ narrative ─Gate2─→ projection → authoring → render → qa → deliver
(材料)    (事实库)   (沟通契约)      (故事结构)           (两份计划)    (写正文)     (编译)   (质检)  (成品)
                    ▲                  ▲                   ▲             ▲           ▲              │
                    └──────────────────┴──── 修复循环：投诉→诊断→定位归属层→修复提案→修 ←──────────┘
```

每层的产物都是磁盘上人类可读、可编辑、可版本化的 artifact（YAML / Markdown），
层与层之间靠 ID 引用链连接：`page → beat → claim → evidence → source`。
任何一个数字、任何一个论断都能沿链回溯到源材料。

## 仓库组成

| 目录 | 职责 |
| --- | --- |
| `comh/` | 沟通层 runtime：run 状态机 CLI、artifact schema、校验器、deck/report 渲染 |
| `docx_harness/` | 搬入的确定性 Markdown/MyST → DOCX 编译器（原样保留，独立演进，见 `docs/compiler/`） |
| `stages/` | 每个 stage 的模型指令（progressive disclosure，模型判断力的注入点） |
| `references/` | 词汇库：叙事模式、slide craft。提供参考，不是能力边界 |
| `skill/` | Agent Skill 打包入口 |
| `runs/<name>/` | 一次沟通任务的工作区（artifact 全部版本化） |
| `tests/` | `tests/runtime/`（沟通层）+ `tests/compiler/`（编译器契约测试） |

## 快速开始

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'

# 初始化一个 run 工作区
.venv/bin/comh init-run runs/demo

# ……模型按 stages/*.md 逐阶段产出 artifact，期间用 CLI 记录状态与过 Gate：
.venv/bin/comh save evidence
.venv/bin/comh confirm brief          # Gate 1：用户确认沟通契约
.venv/bin/comh confirm narrative      # Gate 2：用户确认故事逻辑链
.venv/bin/comh validate all           # 引用链 + 数字一致性 + 硬约束 → qa/findings.yaml
.venv/bin/comh render deck            # projection/deck_plan.yaml → build/deck.pptx
.venv/bin/comh render report          # documents/report.md → build/report.docx（经 docx_harness）

# 诊断工具：抽出某个页面/章节的完整引用链切片（修复循环取证用）
.venv/bin/comh evidence-pack deck P03
```

交付以 **Markdown 报告为主、DOCX 为辅**；展示以 **PPTX 为主、HTML 为辅（后续）**。

## 图形（mermaid → 确定性布局 → PNG）

deck 的 `visual.diagram` 和 report 的 ```` ```mermaid ```` 走同一条编译链：真实字体
测量、碰撞校验的确定性布局，再由 draw.io Desktop CLI 导出 PNG（按内容哈希缓存）。
图语法在 `comh validate` 时干跑检查（纯 Python，不需要 CLI）；导出 PNG 需要 CLI：

```bash
# macOS（已装 draw.io Desktop；版本与上游 pin 不一致时显式放行）
export DRAWIO_CLI="/Applications/draw.io.app/Contents/MacOS/draw.io"
export DRAWIO_ACCEPT_VERSION=30.0.4
# Linux：.venv/bin/docx-harness install-drawio（安装上游钉死的 26.0.16）
```

## 设计原则

1. Content logic before visual design。
2. Report ≠ 字更多的 Presentation；Presentation ≠ 字更少的 Report——它们是同一个
   narrative 的不同投影。
3. Libraries provide vocabulary, not boundaries——`references/` 和 preset 只提供词汇，
   模型可以混合、改写、无视、创造。
4. User hard constraints > 用户明确偏好 > 已确认的 spec > 模型推断 > preset 默认。
5. 持久化显式的推理 artifact，不保存隐藏 Chain-of-Thought。
6. Evidence → Claim → Narrative → Projection → Artifact，每一步可回溯。
7. 修复在归属层进行：质检 finding 必须标注 owning artifact；上游变更只把下游标脏，
   不自动重新生成。

详细设计见 `docs/`（编写中）与 `AGENTS.md`。
