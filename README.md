# DocumentBasedHarness

**把原始材料编译成说服力的沟通编译器。**

Sources in. Conviction out.

你手里有一堆 CSV、实验日志、论文、截图和半成品笔记，六周后要站在客户面前讲清
一件事。普通的做法是打开 PPT 开始搬字——然后数字对不上、逻辑断裂、报告和幻灯片
各说各话。这个项目换一条路：

```text
sources ──► evidence ──► brief ─Gate1─► narrative ─Gate2─► projection ──► render
 材料        事实库       沟通契约      故事结构          两份计划        成品
                          （你拍板）    （你拍板）                        pptx / html / docx / md
                ▲                                                          │
                └──────────── 修复循环：诊断 → 定位归属层 → 修复 ←──────────┘
```

**报告和幻灯片不是互相压缩的版本，它们是同一个故事的两个投影。** 事实先变成
可追溯的证据，证据支撑论断，论断排成故事；你在两个关卡拍板之后，同一份故事
投影成 PPTX、可动画的 HTML、Markdown 报告（DOCX 自动编译）。每一个出现在成品里
的数字，都能沿 ID 链一路回溯到源文件的某一行。

---

## 为什么它不一样

- **证据是一等公民。** `page → beat → claim → evidence → source` 全链 ID 引用。
  图表和大数字卡片在**渲染时**直接从证据库取数——数字物理上不可能漂移。从图上
  估读的数值被显式标注为 estimated，纯估读撑起的结论会被校验器点名。
- **两个 Gate，硬执行。** 沟通契约（给谁看、要什么效果）和故事逻辑链都要你确认，
  CLI 拒绝放行未确认的下游——对齐不靠模型自觉。
- **改了哪层，只重做哪层。** 每层产物记录上游指纹；材料一变全链自动标脏，
  但内容没变的层重存即恢复、Gate 存活。质检 finding 全部标注归属层。
- **动画是语义，不是特效。** "先出结论、再出证据、最后出 so-what" 写在
  deck_plan 里（fragment 模型），HTML 执行它，PPTX（实验性）执行同一份语义。
- **词汇，不是边界。** 主题是 yaml 数据、叙事模式是 markdown 参考——模型可以
  混合、改写、无视、创造。硬约束（"不要黑底"）落到亮度级的确定性检查上。

## 三十秒 workflow

| 阶段 | 谁干活 | 产出 |
|---|---|---|
| intake | 你 | `sources/` 里丢材料 |
| evidence | 模型 | `evidence.yaml`：带出处的事实，数字带结构化锚点 |
| **brief** → Gate 1 | 模型推断，**你拍板** | 受众、目标、硬约束、期望带走什么 |
| **narrative** → Gate 2 | 模型设计，**你拍板** | beats（每个一句话 message）+ claims（诚实标注证据状态） |
| projection | 模型 | `deck_plan.yaml` + `report_plan.yaml`（同一故事的两种组装） |
| render | 纯代码 | `deck.pptx` / `deck.html`（含动画）/ `report.md` + `report.docx` |
| qa | 代码 + 模型 | 引用链、数字一致性、逻辑、标题、读者测试 |

完整走一遍（含命令和样例）见 **[用户指南](docs/user-guide.md)**。

## 快速开始

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'

# 开一个任务工作区，把材料丢进 sources/
.venv/bin/comh init-run runs/my-report

# ……按 stages/*.md 逐阶段产出，用 CLI 记录状态、过 Gate、验证、渲染：
.venv/bin/comh save evidence
.venv/bin/comh confirm brief          # Gate 1：你确认沟通契约
.venv/bin/comh confirm narrative      # Gate 2：你确认故事逻辑链
.venv/bin/comh validate all           # 0 error 才算数
.venv/bin/comh render deck            # → build/deck.pptx（主题、卡片、图表、实测防溢出）
.venv/bin/comh render deck-html       # → build/deck.html（reveal.js 单文件，动画开箱即用）
.venv/bin/comh render report          # → build/report.docx（md 是正主，docx 是编译副产物）
```

现场demo（场景 A：缓存实验 → 客户汇报）就在 `runs/sample-cache-latency/`，
`open runs/sample-cache-latency/build/deck.html` 直接看。

## 能力一览

| | |
|---|---|
| **图标素材** | 5,130 个 tabler-outline 语义图标（MIT，`assets/vendor/`）+ 可搜索索引；HTML 内联 SVG、pptx 经 Chrome 栅格化缓存；Gate 1 显式沟通素材方向 |
| **主题** | `themes/*.yaml`（palette/字号/字体）；run 可自带主题覆盖仓库级；`tokens_override` 按次微调；brief 禁深色 → 亮度级强制浅色 |
| **页面结构** | 展开式要点（加粗导语+浅色展开）、大数字卡片（证据取数）、原生图表（证据取数）、底部结论条、mermaid 示意图（确定性布局）、图片带图注与溯源 |
| **布局** | 真实字形度量 → 确定性换行 → 字号自适应；装不下出 finding，不静默溢出 |
| **动画** | `reveal`/`emphasis` 步骤（元素寻址在验证期解析）；HTML 全量执行；PPTX appear/fade_in（实验性，需真机验证后开 `animations: true`） |
| **报告** | Markdown 为正主；docx-harness 确定性编译 DOCX（原生公式/表格/mermaid），方言写错带行号报错=免费质检 |
| **质检** | ID 链完整性、数字一致性（含日期/序号降噪）、beat 覆盖、硬约束、图语法干跑、估读诚实性、Gate 有效性 |
| **修复循环** | `evidence-pack` 一条命令切出某页的完整溯源切片；六问诊断定归属层；两次修不好自动升级换假设 |

## 用户与开发者

- **使用者**：[docs/user-guide.md](docs/user-guide.md) —— 从材料到成品的完整走法，
  含修复循环和常见任务。
- **AI 操作者**：`skill/SKILL.md` 路由 → `stages/*.md` 是每个阶段的判断力来源。
- **架构与纪律**：`AGENTS.md`；编译器内部设计：`docs/compiler/`。

## 设计原则

1. Content logic before visual design.
2. Report ≠ 字更多的 Presentation；两者是同一 narrative 的投影。
3. Libraries provide vocabulary, not boundaries.
4. User hard constraints > 用户偏好 > 已确认 spec > 模型推断 > preset。
5. 持久化显式推理 artifact，不保存隐藏 Chain-of-Thought。
6. Evidence → Claim → Narrative → Projection → Artifact，每步可回溯。
7. 修复在归属层进行；上游变更只标脏，不自动重生成。
8. 观众是最终消费者——优化他们理解了什么，不是你想倒什么。

## 环境备注

- 图形（mermaid → PNG）渲染需要 draw.io CLI；macOS：
  `export DRAWIO_CLI="/Applications/draw.io.app/Contents/MacOS/draw.io"`
  （版本与上游 pin 不符时再加 `DRAWIO_ACCEPT_VERSION=<你的版本>`，显式放行）。
- 测试与 lint：`.venv/bin/pytest && .venv/bin/ruff check .`
