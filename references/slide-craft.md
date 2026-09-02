# Slide craft 词汇（vocabulary, not boundaries）

投影 deck_plan 时的手艺参考。风格词汇不是能力边界——brief 的 spec.dimensions
和硬约束永远优先于本文件。

## 标题（content 页）

标题 = 本页要观众记住的话，不是本页的主题。

- 差：`实验结果` / `测试环境` / `方案对比`
- 好：`Cache partitioning 将 P99 latency 降低 18.2%` / `三套环境的结论一致，
  差异均在噪声区间内` / `方案 B 赢在冷启动，方案 A 赢在稳态`

句式工具：数字结论式、对比式（A 赢在 X，B 赢在 Y）、条件式（在 Y 边界内 X 成立）、
主张式（先给结论，支撑点在页面下方）。

通用底色是**直白**：主谓宾、有动词、念得出声、不修辞。专业感来自数字和对比的
严谨，不来自压缩名词，也不来自比喻和金句。"效应载体是容量重叠"和"争抢的确实是
容量"都不合格——正确写法是"瓶颈确认是容量共用"。"

## 密度与充实

- 由 brief 的 spec.dimensions 决定，没有死字数。executive 场景每页 1-2 个支撑点；
  技术评审可以 3-4 个 + 图。
- **页面主体区至少要有一个展开结构或视觉块**：`{point, detail}` 展开式要点、
  `metric_cards` 大数字卡片、`chart` 图表、或 `callout` 结论条。"三个短 bullet 孤悬
  一页"就是太空——要么展开，要么合并页面。
- 展开优先加宽而不是加多：一个 point 带 detail 比五个裸 bullet 层次好。
- 页面放不下就 demote：细节去 `notes`，证明过程去 `appendix`，长论证去
  `report_only`。**demotions 必须登记**。
- 图 > 表 > 短句 > 长句。能用一张对比图说清的，不要用四个 bullet。
- callout 是"so what"强化条，不是第二个 message；它讲了新事情 = 该拆页。

## 视觉意图词汇（visual.intent）

写给 renderer 的自然语言，例如：

- `对比：基线 vs 优化后的双柱图，差异高亮`
- `趋势：延迟随负载变化折线，优化前后两条线`
- `结构：三层架构示意，改动部分高亮`
- `流程：请求路径时序，瓶颈标红`
- `证据引用：放大关键数字，来源标注在角落`

emphasis/reveal 的正式写法（fragment 模式，renderer 将来执行）：

```yaml
emphasis:
  - {elements: [title], verb: highlight, note: 本页唯一大数字}
reveal:
  - {elements: [support_points[0]], verb: fade_in, trigger: click}
  - {elements: [visual], verb: fade_in, trigger: click}
  - {elements: [callout], verb: fade_in, trigger: click}
```

要点：出场顺序讲的是"论证的展开节奏"（先给结论，再给证据，最后给 so-what），
不是花哨；每页 reveal 步骤通常不超过三步。

## 图标

- 语义名词引用（`icon: trending-down`），来自 vendored 的 tabler-outline 集
  （5,130 个，MIT）。用 `comh.render.icons.search_icons('latency')` 式语义搜索选名。
- 克制：图标是路标不是插画。KPI 卡一枚、要点导语一枚已足够；每页超过三枚就是在
  用图标凑数。
- 图标颜色跟随主题 accent，不要在内容里指定颜色。

## Speaker notes

- 内容：被裁掉的细节与数字、过渡话术、预备 Q&A、给未来重用者的上下文。
- notes 是一等内容，QA 会检查 demote 到 notes 的信息是否真的在 notes 里。

## 诚实性

- 误差/置信区间出现在图或 notes 里，不许消失。
- 对比条件（同负载？同数据集？）在页面或 notes 里可见。
- evidence 只有 partial 支撑的 claim，标题不许写成斩钉截铁。
