# 用户指南：从材料到成品

这份指南走完一次完整任务：收材料 → 提证据 → 两个 Gate → 投影 → 渲染 → 修复。
全程以仓库自带的样例 `runs/sample-cache-latency/`（缓存实验 → 客户汇报）为例。
所有命令都在仓库根目录执行；`--run` 可省略（命令会向上找 `run.yaml`）。

## 0. 准备

```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
# 图形渲染（可选，mermaid 示意图需要）：
export DRAWIO_CLI="/Applications/draw.io.app/Contents/MacOS/draw.io"
export DRAWIO_ACCEPT_VERSION=30.0.4   # 仅当你的 draw.io 版本与上游 pin 不一致
```

## 1. 开工作区、收材料

```bash
.venv/bin/comh init-run runs/my-report
cp ~/experiment/*.csv ~/experiment/*.md runs/my-report/sources/
```

`sources/` 是全部原始材料的家。之后材料的任何增删改都会沿血缘把下游标脏——
这是特性，不是麻烦。

## 2. evidence：把材料变成事实库

AI 按 `stages/evidence.md` 提取：每条事实带出处（文件 + 定位），数字类带
`value: {number, unit}` 结构化锚点。两条铁律：

- **派生数字先落库再用**：`derived:(E001,E002)` 标注来源，否则校验器判 finding；
- **读图是估读**：图上读出的数字标 `extraction: {via: visual, confidence: estimated}`；
  有数据文件时数据文件赢，图降级为佐证。

```bash
.venv/bin/comh save evidence      # 记录"产自当前 sources 快照"
```

## 3. Gate 1：brief——对齐"给谁看、要什么效果"

AI 综合材料概况和你的自然语言描述，推断出 `brief.yaml`：受众、目标、场合、
语言、媒体、期望带走什么（takeaways 是后面读者测试的比对基准）、硬约束/软偏好、
自由发明的 `spec.dimensions`。

**关键规则**：硬约束必须能落到确定性检查（"不要黑底"→亮度级强制；"必须包含:局限性"
→报告存在性检查），落不到的会被提议降级为软偏好。

看摘要、改内容，满意后放行：

```bash
.venv/bin/comh confirm brief
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
.venv/bin/comh confirm narrative
```

两个 Gate 都被 CLI 硬性拦截：未确认时下游 `save`/`render` 直接拒绝；
Gate 后改文件会自动作废确认，需要重新拍板——代价可见是刻意设计。

## 5. projection：同一故事的两种组装

- **deck_plan**：message 式标题（"P99 降低 18.2%"而不是"实验结果"）、
  展开式要点（`{point, detail}` 加粗导语+浅色展开）、大数字卡片与图表
  （`value_from` 渲染时从证据取数）、底部结论条、`reveal`/`emphasis` 动画步骤、
  被裁掉内容的去向登记（demotions）。
- **report_plan**：写作契约——分节、每节展开哪些 claims/evidence、深度。
  报告可以方法前置、合并拆分 beats，与 deck 顺序不同是正当的。

## 6. 渲染

成品和样式调整都**在对话里完成**：你说想要什么，agent 落配置、跑渲染，你看
成品。常见的说法和背后的动作：

| 你说 | agent 在底层做什么 |
|---|---|
| "渲染出来看看" | 渲染三件套：`build/deck.pptx`、`build/deck.html`（reveal.js 单文件：方向键翻页、点击步进动画、`S` 演讲者视图）、`build/report.docx`（`documents/report.md` 是正主） |
| "换个主题" / "要吸睛一点" / "像杂志" | 从内置方向选型（tier1-light / slate-tech / midnight / poster-pop / gallery-noir，学术到创意艺术）或按次微调 token，重渲染 |
| "用我的模板出品牌主题" | 从你的 pptx 提取色板和中英文字体生成 run 级主题，三端贯穿 |
| "定一套'赛博霓虹'主题" | 气质没被内置命中时现场生成 run 级主题（纯数据），自动过对比度/可读性体检，样张对齐后三端贯穿 |
| "这页放张照片" / "去找点素材" | 征得同意后检索，落盘 `assets/` 并登记出处（`assets/manifest.yaml`：来源+许可），出版本对齐 |
| "PPTX 动画打开试试" | deck.style 开 `animations: true`（实验性，**先在真机 PowerPoint 验证再交付**） |

save / confirm / render 都会自动先跑校验、**有 error 直接拒绝**——不需要记得
手动 validate。渲染报告在 `qa/render-deck.yaml` 和 `qa/render-deck-html.yaml`
（几何/布局/主题体检）。HTML 布局守卫需要无头 Chrome：没有时命令会明确提示
"layout check skipped"，不会静默跳过。

底层等价命令（agent 代劳；审计/复现时才需要你亲手跑）：

```bash
.venv/bin/comh validate all       # 先验证：0 error 才继续
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
- **选版本**：不给样本时，AI 会用一条真实内容按 2-3 个风格档各写一版，你选一版
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
（文件没变的层重存即恢复，Gate 存活），受影响的层重新生成——不从头再来。

## 10. 底层命令速查（agent 代劳；审计/进阶用）

日常对话即可，下面是等价的底层开关：

```bash
comh init-run <path>          # 开工作区（--preset cn-official 可出公文模板）
comh status                   # 各层新鲜度 + Gate 状态 + 交付验收状态
comh save <artifact>          # 记录"产自当前上游快照"（自动先校验，有 error 拒存）
comh confirm <brief|narrative># 过 Gate（需要你的明确同意）
comh validate all             # 全量校验 → qa/findings.yaml
comh render deck|deck-html|report   # 有 error 拒渲；渲染报告进 qa/
comh evidence-pack deck P05   # 修复循环取证
comh theme-from-pptx 模板.pptx --name brand   # 从模板提取品牌主题
comh deliver [--note ...]     # 你验收后落记录：钉住成品指纹，重渲染即作废
comh check-schema <file>      # 单文件 schema 校验
```
