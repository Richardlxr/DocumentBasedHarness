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

## 版式原型（Layout Archetypes）
- `content`：标准上下/双栏图文排版，最适合通用论点展开。
- `hero_split`：左图右文或左文右图，适合架构图、重大数据可视化、产品截图等 Hero 视觉。
- `fullscreen_backdrop`：全屏图片底图 + 居中悬浮半透明卡片，适合宏观愿景、战略发布或总结升华。
- `timeline`：横向 3-4 个里程碑节点卡片，适合阶段演进、历史回顾、路线图。
- `versus`：双栏并列对比，适合方案评估与选型决策；列名用 `visual.columns: [左, 右]` 指定（缺失会降级成裸 A/B 并出 warning）。

## 动画与微动效（HTML Deck）
- **大数字跳动（Count-up）**：进入页面（或触发 fragment 时）KPI 卡片数字从 0 匀速插值跃升至目标值（800ms，带 easeOutExpo 减速缓动）。
- **柱状图生长（Bar Growth）**：CSS transition 平滑展开宽度。
- **无障碍降级**：当系统开启 `prefers-reduced-motion: reduce` 时，所有动效自动关闭，呈现静态终态。

## 素材与照片

- 图片气质跟主题走：poster-pop 配高对比照片，gallery-noir 配少而精的大图；
  素材和页面气质不一致时，宁可换素材。
- **背景图（`visual.background`）**：支持 `{asset, opacity, overlay}`。PIL 实测 worst-case 动态加深蒙层至 ≥4.5:1，坚守可读性底线。PPTX 端自动降级为半透明实色矩形。
- 图是装饰不是证据：图上读出的数字走 evidence（标估读）；检索来的素材必须
  征得同意、落盘登记出处（协议见 stages/deck.md「素材」）。
- 克制同图标：一页一张主图足够，两张以上就开始互相打架。

## Speaker notes

- 内容：被裁掉的细节与数字、过渡话术、预备 Q&A、给未来重用者的上下文。
- notes 是一等内容，QA 会检查 demote 到 notes 的信息是否真的在 notes 里。

## 诚实性

- 误差/置信区间出现在图或 notes 里，不许消失。
- 对比条件（同负载？同数据集？）在页面或 notes 里可见。
- evidence 只有 partial 支撑的 claim，标题不许写成斩钉截铁。
