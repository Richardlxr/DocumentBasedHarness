# Stage: Deck Projection（幻灯片投影）

## 输入

- `narrative/narrative.yaml`（已过 Gate 2）。
- `brief/brief.yaml`：受众、takeaways、硬约束、spec.dimensions。

## 你做什么

把同一个 story 投影为 `projection/deck_plan.yaml`。**这是投影，不是压缩**：报告的
写法和你无关，你只对"现场这 30 分钟观众怎么被带走 message"负责。

页面规则：

- 一页 ≈ 一个主要沟通信息。内容页 `title` 写**观众该记住的那句话**，不写话题所属。
  反例："实验结果"。正例："Cache Partitioning 将 P99 latency 降低 18.2%"。
- 可选 `kicker`（页眉小标，如"结果 · RESULTS"）：小号强调色，提供编辑级层次；
  不要重复标题内容，每个 section 用一次即可。
- 但不要机械执行：`page_role` 为 `cover` / `agenda` / `section_divider` /
  `closing` / `appendix` 的页面用主题式标题是正当的。系统按 role 理解页面，QA 也按
  role 分规则检查。
- `beat`：引用 `Sxx`。一 beat 拆多页可以；多 beat 并一页必须写 `merge_rationale`。

## 让页面充实（展开结构）

"三个短 bullet 孤悬一页"就是太空。页面主体区至少要有一种展开结构或视觉块：

- **`support_points` 支持 `{point, detail}`**：point 是加粗导语，detail 是下面一行浅色
  展开。这是首选的充实手段——比加第四第五个 bullet 好，信息有层次。
- **`metric_cards`**：数据页的大数字卡片，`{label, value_from: Exxx}`，数值渲染时从
  evidence 取（不会漂移）。适合 2-4 个关键数字。卡片和图表同时用会很挤，二选一。
- **`callout`**：底部"so what"结论条 `{text, evidence?}`。**强化本页信息，不许引入
  第二个 message**——如果 callout 讲的是新事情，说明该拆页了。
- `visual.intent`：用自然语言描述视觉意图，具体像素留给 renderer。落到具体载体时：
  - **数据图优先用 `visual.chart`**：`{type: bar|column|line, series: [{label,
    value_from: Exxx}]}`。数值在渲染时直接从 evidence 的 `value.number` 取——图上的
    数字物理上不可能和证据库漂移。前提：被引用的 evidence 条目必须有 `value`。
  - **示意图用 `visual.diagram`**：`{mermaid: <flowchart 源>, caption, evidence?}`。
    mermaid 经编译器的确定性布局链（真实字体测量、碰撞校验）编译成 PNG，按内容哈希
    缓存。当前只支持 flowchart/graph 子集（subgraph、sequence 等会失败）——
    `comh validate` 会干跑图语法，错误在验证期就报出来。渲染需要 draw.io CLI
    （`DRAWIO_CLI` 指向 draw.io Desktop）。
  - 已有图片用 `asset_refs`，**引用图片时用对象形式 `{ref, caption, evidence}`**——
    caption 随图渲染，evidence 把图挂进溯源链。图不是溯源的盲区。

密度仍按 brief 的 spec.dimensions 判断——没有死字数规则，但"空"和"密"都该是有意
为之的选择，不是默认结果。
- `deck.style`：`template` 选主题（内置 `tier1-light` / `slate-tech` / `midnight`，
  未知名字回退默认并出 finding）；`transition` 选转场（`fade|push|wipe|cut`）；
  其余键（如 `palette_hint`）自由写，代码透传。注意：brief 禁深色时选 midnight 主题
  会被校验器打回、渲染器强制浅色——硬约束赢。
- `notes`：演讲备注是一等内容。被你从页面上拿掉的细节、过渡话术、预备的问答，写进
  notes。
- `demotions[]`：凡是从本 beat 里裁掉、去了别处的信息，登记 `{content, to}`，
  `to` ∈ `notes | appendix | report_only`。**内容去向必须可审计**——没有 demotion
  记录的静默丢弃会被 QA 盯上。
- `emphasis` / `reveal`：**出场顺序和强调是沟通决策，不是视觉决策**——这是动画的
  语义建模（fragment 模式）。正式形式是步骤对象：
  ```yaml
  reveal:
    - elements: [support_points[0]]   # 语义地址：title | callout | visual |
      verb: fade_in                    #   support_points[i] | metric_cards[i]
      trigger: click                   # 动词: appear|fade_in|emphasize|highlight
    - elements: [visual, callout]      # 触发: click|with_previous|after
      verb: fade_in
      trigger: click
  emphasis:
    - elements: [title]
      verb: highlight
  ```
  纯字符串仍然允许（自由备注，renderer 忽略）。地址在 validate 期确定性解析——
  写错名字/越界会直接报 error。**HTML surface（`comh render deck-html`）已执行这份
  语义**（reveal.js fragment：出场顺序/点击步进/强调高亮）；PPTX 动画词汇表后续接入
  同一份语义。
- 所有数字必须来自 evidence（派生数字先落库，见 stages/evidence.md）。

## 收尾

```
comh save deck_plan
```

narrative 或 brief 之后有任何变更，deck_plan 自动标脏，需要重新投影。
