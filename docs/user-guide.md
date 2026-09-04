# 用户指南：从材料到成品

这份指南走完一次完整任务：轻量 intake → 证据 → 契约确认 → 故事线确认 → 大纲确认 → 适用的样式审阅 → 可选精修 → 渲染 → QA → 验收。
按阶段的自然语言要求、确认范围与修改影响，先看 [README 工作流](../README.md#工作流每个阶段你可以怎样参与)。
全程以仓库自带的样例 `runs/sample-cache-latency/`（缓存实验 → 客户汇报）为例。
所有命令都在仓库根目录执行；`--run` 可省略（命令会向上找 `run.yaml`）。

## 0. 准备

macOS / Linux：

```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
# 图形渲染（可选，mermaid 示意图需要）：
export DRAWIO_CLI="/Applications/draw.io.app/Contents/MacOS/draw.io"
export DRAWIO_ACCEPT_VERSION=30.0.4   # 仅当你的 draw.io 版本与上游 pin 不一致
```

Windows PowerShell：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
# 非标准安装位置才需要：
$env:DRAWIO_CLI = "C:\Tools\draw.io\draw.io.exe"
```

Windows/Linux 的外部程序发现、字体和验证边界见[平台支持说明](platform-support.md)。下文
`.venv/bin/comh` 在 Windows 中对应 `.\.venv\Scripts\comh.exe`。

## 1. 开工作区、收材料

```bash
.venv/bin/comh init-run runs/my-report
cp ~/experiment/*.csv ~/experiment/*.md runs/my-report/sources/
```

`sources/` 是全部原始材料的家。之后材料的任何增删改都会沿血缘把下游标脏——
这是特性，不是麻烦。

先按 [intake 指令](../comh/instructions/stages/intake.md) 写目标草案、材料范围与用户依据，执行
`comh intake .workspace/intake.yaml`。默认关键节点对齐；用户要共同打磨或委托细化时，
用 `comh collaborate collaborative|delegated --reply "实际原话" --source "消息引用"` 记录。
不重复询问已经给出的信息。

## 2. evidence：把材料变成事实库

AI 按 `comh/instructions/stages/evidence.md` 提取：每条事实带出处（文件 + 定位），数字类带
`value: {number, unit}` 结构化锚点。两条铁律：

- **派生数字先落库再用**：`derived:(E001,E002)` 标注来源，否则校验器判 finding；
- **读图是估读**：图上读出的数字标 `extraction: {via: visual, confidence: estimated}`；
  有数据文件时数据文件赢，图降级为佐证。

```bash
.venv/bin/comh save evidence      # 记录"产自当前 sources 快照"
```

另写 `evidence/coverage.yaml`，以 `sources: [{file, status, locator, reason}]` 记录实际覆盖。
status 是 read/partial/unread；read 要有定位，其他要有原因。每个来源文件都需说明，
不能用“已提取部分事实”冒充全量阅读。

## 3. Gate 1：brief——对齐"给谁看、要什么效果"

AI 综合材料概况和你的自然语言描述，推断出 `brief.yaml`：受众、目标、场合、
语言、媒体、期望带走什么（takeaways 是后面读者测试的比对基准）、硬约束/软偏好、
自由发明的 `spec.dimensions`。

**关键规则**：能机械检查的硬约束落到代码；其余保持硬约束并写人工验收方法，
只有用户可以降级。`brief.alignment` 必须说明每项契约的来源、处置和依据；proposed
明确代表本次待接受的建议。关键未知未答不能确认，确实晚些才需要的问题可注明截止阶段。
完整字段及示例见 [对话协议](../comh/instructions/references/dialogue-protocol.md)。

有演示稿时记录 `presentation.setting`：学术默认 academic-rich，其他场合默认 balanced，
用户指定的密度优先，见
[内容预设](../comh/instructions/references/presentation-profiles.md)。交付 PPTX 时还要记录
`appearance` 的模板意向和样张审阅方式。两项均纳入 alignment，随契约一起展示。
实际受众与委托人须区分，文案按
[受众规则](../comh/instructions/references/audience-copy.md) 检查。

看摘要、改内容，满意后放行：

```bash
.venv/bin/comh save brief
.venv/bin/comh present brief
# 展示返回的契约、推断与未知。收到针对该版本的实际回复后：
.venv/bin/comh respond D0001 --decision accepted --reply "实际原话" --source "消息引用"
```

## 4. Gate 2：narrative——对齐"讲什么故事"

AI 产出 `narrative.yaml`：有序的 beats（每个带 purpose + 一句话 message）+
claims 登记表（诚实标注 supported / partial / background / assumption / needs_research）。
你看的人类可读摘要长这样：

```
01 establish_problem — 尾延迟抖动是客户线上体验的第一痛点
02 establish_credibility — 受控环境、固定负载、多轮重复
03 demonstrate_effect — 标准负载下 P99 降低 18.2%，吞吐不受影响
04 concede_limit — 高负载下改善有限，瓶颈可能在磁盘 IO
05 explain_mechanism — 租户级分区隔离了缓存挤占
06 recommend — 建议 staging 灰度 + 高负载瓶颈专项
```

narrative 是**媒介无关**的：不许出现布局、字数、页数。媒介取舍全部留给投影层。

```bash
.venv/bin/comh save narrative
.venv/bin/comh present narrative
# 使用返回的请求 ID，等用户看过故事并回复后再 respond；不要猜 ID 或代填同意
```

两个 Gate 都被 CLI 硬性拦截：未确认时下游 `save`/`render` 直接拒绝；
Gate 后内容或证据依据改变会作废确认，需要重新对齐。以上回复是格式占位，不能原样
作为同意证据。保存不等于展示，展示不等于接受；`继续` 只能对应清楚且唯一的当前提案。
部分支持、假设、待研究的论断需在故事确认时给出限缩边界或删除处置；反证也保留。

## 5. projection：同一故事的两种组装

- **deck_plan**：message 式标题（"P99 降低 18.2%"而不是"实验结果"）、
  展开式要点（`{point, detail}` 加粗导语+浅色展开）、大数字卡片与图表
  （`value_from` 渲染时从证据取数）、底部结论条、`reveal`/`emphasis` 动画步骤、
  被裁掉内容的去向登记（demotions）。
- **report_plan**：写作契约——分节、每节展开哪些 claims/evidence、深度。
  报告可以方法前置、合并拆分 beats，与 deck 顺序不同是正当的。

先保存计划并 `comh present deck_outline` / `report_outline`，展示结构及取舍，收到实际回复
后记录 accepted 或明确的 delegated。粗大纲直接来自计划结构字段，无重复的大纲文件。

关键节点模式接受大纲后自主细化；共同打磨模式逐页/节推进，用
`comh present deck_detail --node P01` / `report_detail --node R01` 记录具体内容的回复。
共同打磨的未确认细节阻止正式渲染和报告正文保存；用户可以随时调整协作档位。
草稿顶层可写 `draft: true`，完成后改为 false。只补正文证据或样式不重问粗结构，
改变标题、顺序、beat 覆盖或取舍则需要新大纲决策。

原生 PPTX 模板的首次适配在粗大纲接受后制作实际样张，再 `present deck_appearance`；
给定模板不等于已接受适配结果，明确的样式审阅委托才可省略这轮。内容精修委托与样式委托分开。
延期到 authoring 的问题也会在报告正文保存前检查，和正式渲染保持一致。

## 6. 渲染

成品和样式调整都**在对话里完成**：你说想要什么，agent 落配置、跑渲染，你看
成品。常见的说法和背后的动作：

| 你说 | agent 在底层做什么 |
|---|---|
| "渲染出来看看" | 根据已选媒介生成 PPTX、HTML 或报告；草案先用 preview，Markdown 可独立交付 |
| "换个主题" / "要吸睛一点" / "像杂志" | 从内置方向选型（tier1-light / slate-tech / midnight / poster-pop / gallery-noir，学术到创意艺术）或按次微调 token，重渲染 |
| "用我的 PPTX 模板" | 检查并导入背景、品牌元素和文字样式，经适用的样张审阅后编译；原生样式不支持 HTML。仅提取色板/字体可用 theme-from-pptx |
| "定一套'赛博霓虹'主题" | 创建演示稿主题 token 并检查可读性，适用于支持的 PPTX/HTML 主题路径；报告有独立 DOCX 模板 |
| "这页放张照片" / "去找点素材" | 未授权时先问；已明确授权则按范围检索，落盘 `assets/`、登记来源与许可，再展示选用结果 |
| "PPTX 动画打开试试" | deck.style 开 `animations: true`（实验性，**先在真机 PowerPoint 验证再交付**） |

save / confirm / render 都会自动先跑校验、**有 error 直接拒绝**——不需要记得
手动 validate。渲染报告在 `qa/render-deck.yaml` 和 `qa/render-deck-html.yaml`
（几何/布局/主题体检）。HTML 布局守卫需要无头 Chrome：没有时命令会明确提示
"layout check skipped"，不会静默跳过。

底层等价命令（agent 代劳；审计/复现时才需要你亲手跑）：

```bash
.venv/bin/comh validate all       # 先验证：0 error 才继续
.venv/bin/comh render deck --preview # 大纲对齐后的草案样张，输出到 .workspace/，不可交付
.venv/bin/comh render deck        # build/deck.pptx
.venv/bin/comh render deck-html   # build/deck.html（reveal.js 单文件，含动画、演讲备注）
.venv/bin/comh render report      # build/report.docx；documents/report.md 是正主
```

## 7. 验证器会帮你抓什么

| 检查 | 抓什么 |
|---|---|
| ref-integrity | 悬空引用：claim 指向不存在的 evidence、页面指向不存在的 beat、卡片/图表/结论条的 value_from |
| number-consistency | 成品里出现证据库没有的数字（claims 级 error；日期、序号自动降噪） |
| claims-grounded | "supported 却无证据"的假引用 |
| visual-estimate-only | 仅靠图表估读支撑的结论 |
| beat-coverage | Gate 2 确认过的故事在投影里静默消失 |
| hard-constraint | 有效背景色是否违反"不要黑底"；"必须包含:X"是否存在 |
| diagram | mermaid 语法干跑（不需要 draw.io） |
| asset-provenance | 检索素材的出处链：登记的文件缺失=error；引用未登记素材=warn；用着素材却没有 manifest=info |
| theme | 定制主题的质量下限：正文/背景对比度 <4.5:1 = error（阻断渲染）；muted/强调色 <3:1、is_light 与实际底色不符、字号低于可读下限 = warn |
| reveal-address | 动画元素地址写错/越界 |
| layout | 实测布局装不下：pptx 几何门禁 + HTML 布局守卫（溢出/遮挡，渲染时无头实测回读） |

每条 finding 标注 owning artifact——修哪层，看这里。

## 8. 不满意怎么办：修复循环

症状在成品，病根在任何一层。诊断 = 沿链下钻找"第一个背叛上一层的层"：

```bash
.venv/bin/comh evidence-pack deck P05   # 切出该页完整溯源：页面→beat→claims→evidence→source
```

六问：渲染忠实吗 → 忠实但丑（换主题）→ 投影弱化了 beat 吗 → beat/claim 本身成立吗
→ 数字有据吗 → 方向对吗（回 Gate 1）。**内容层修改先亮影响面再动手；渲染层直接修。**
同一投诉修两次仍不满意：禁止第三次硬修，换诊断假设并把整条链摊给用户。
每次修复记入 `qa/repair-journal.yaml`。

## 8.4 语言风格也是样式：Gate 1 对齐，不一刀切

默认风格是直白（主谓宾+数字），但风格是**每次任务可选的**：

- **给样本**：贴两三句你平时汇报的原话进 `voice.samples`，全部写作向它对齐；
- **选版本**：没有特别偏好可接受默认建议；需要比较时，AI 用真实内容写 2-3 版，你选一版
  口头微调到满意；
- **显式开关**：`voice.rules.relax`（如 punchy 场景放行破折号金句）、
  `extra_forbidden`（追加禁词）。

`comh validate` 的风格检查执行的是**你选定的风格**——plain 是默认，不是边界。
改风格重做的话术："voice 换成 punchy 档，relax em-dash，重投影 deck，其他不动。"

## 8.5 怎么提出"重做"（话术速查）

说出症状 + 期望，并指明动哪一层（agent 会先亮影响面再动手）：

| 不满意的是 | 这样说 | 影响 |
|---|---|---|
| 措辞表达 | "改成直白说法，**只重投影，narrative 不动**" | deck_plan → 渲染；Gate 2 存活 |
| 某页内容 | "P05 重做：重点讲 X，Y 进备注" | 单页重投影 |
| 故事逻辑 | "先结论后方法；S04/S05 合并，重过 Gate 2" | narrative 级联 |
| 整个方向 | "这是给管理层的，不是给专家的，重来" | 回 Gate 1 全链 |
| 数据材料 | "results.csv 第 3 组重测了" | 重提 evidence 级联 |
| 视觉 | "换 midnight" / "用我的模板出品牌主题" | 仅 style，内容不动 |

底线：同一处修两次不满意，说"换个诊断思路"，禁止第三次硬修。

## 9. 材料更新之后

改了 `sources/` 里的 CSV？`comh status` 会看到 evidence 起全链标脏。逐层重存
并检查覆盖记录。内容可复用，但材料依据变化后旧 Gate 不自动恢复；展示新依据并记录
当前回复。内容和依据均未改变的重存保留确认，纯样式细化保留粗大纲确认。

## 10. 底层命令速查（agent 代劳；审计/进阶用）

日常对话即可，下面是等价的底层开关：

```bash
comh init-run <path>          # 开工作区（--preset cn-official 可出公文模板）
comh status                   # 各层新鲜度 + Gate 状态 + 交付验收状态
comh save <artifact>          # 记录"产自当前上游快照"（自动先校验，有 error 拒存）
comh intake <file>            # 保存目标草案、材料范围和依据
comh next --json              # 当前阶段、允许的下一动作或待回复请求
comh context [--stage deck --node P01]  # 当前指令、全局约束和证据切片
comh instructions intake      # 无 run 时也能读打包指令
comh present <target>         # 展示请求，绑定当前版本；收到实际回复才执行 respond
comh respond D0001 --decision accepted --reply "实际原话" --source "消息引用"
comh confirm brief --request D0001 --reply "实际原话" --source "消息引用"  # 兼容接口
comh validate all             # 全量校验 → qa/findings.yaml
comh render deck|deck-html|report   # 有 error 拒渲；渲染报告进 qa/
comh evidence-pack deck P05   # 修复循环取证
comh theme-from-pptx 模板.pptx --name brand   # 从模板提取品牌主题
comh style-inspect 模板.pptx  # 检查原生背景、品牌资源与文字兼容风险
comh style-import 模板.pptx --name brand   # 导入样式源，随后配置 surfaces 并审阅样张
comh presentation-profiles academic-rich  # 查看内容密度与布局建议
comh review <审稿文件.yaml>   # 记录当前版本审查，格式见 comh/instructions/stages/qa.md
comh present delivery         # 当前审稿通过后展示成品；收到验收回复后 respond
comh deliver [--note ...]     # 钉住已接受的成品、审稿和请求，重渲染即作废
comh check-schema <file>      # 单文件 schema 校验
```

## 校验与旧 run 升级

`comh validate <artifact>` 检查该产物及其上游；`comh validate all` 检查所选媒介并汇总
机械、模型和渲染问题。模型发现写独立审稿文件，通过 `comh review` 导入，不手改汇总文件。
报告计划的 heading 对应正文标题（忽略章节序号）；must_include 是需要字面出现的文字，
evidence 要在本节用 `[Exxx]` 引用。语义要求放进人工检查项。

旧 run 不会自动补造确认依据。先 `next/context`；补 intake、coverage 和 brief.alignment，
保留旧内容与 legacy Gate，逐阶段展示当前版本并接收真实回复，再对齐所选媒介大纲。
随后重渲染、记录当前审稿及真实读者输出、用户验收。样例 run 也按这个规则处理。
独立读者输出通过 review 的 `reader_test: {output, executor, input_scope}` 登记，输出文件
必须留在 run 中；若没有独立执行能力，应报告未完成，不能把自查勾成独立测试。旧 narrative 中的
`projection.status` 移到相应计划顶层 `omissions: [{beat, reason}]`，迁移后重新确认故事。
旧自然语言硬约束保留兼容；无法自动判断的要求仍是硬约束，在 review 中逐项人工验收。
