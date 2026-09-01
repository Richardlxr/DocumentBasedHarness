# Stage: Deck Projection（幻灯片投影）

## 输入

- `narrative/narrative.yaml`（已过 Gate 2）。
- `brief/brief.yaml`：受众、takeaways、硬约束、spec.dimensions。

## 你做什么

把同一个 story 投影为 `projection/deck_plan.yaml`。**这是投影，不是压缩**：报告的
写法和你无关，你只对"现场这 30 分钟观众怎么被带走 message"负责。

页面规则：

- 一页 ≈ 一个主要沟通信息。内容页 `title` 写**观众该记住的那句话**，不写话题所属。
  反例："实验结果"。正例："Cache partitioning 将 P99 latency 降低 18.2%"。
- 但不要机械执行：`page_role` 为 `cover` / `agenda` / `section_divider` /
  `closing` / `appendix` 的页面用主题式标题是正当的。系统按 role 理解页面，QA 也按
  role 分规则检查。
- `beat`：引用 `Sxx`。一 beat 拆多页可以；多 beat 并一页必须写 `merge_rationale`。
- `support_points`：每页 2-4 个支撑点，短句。密度按 `spec.dimensions` 和
  `density_hint` 自己判断，没有死字数规则。
- `visual.intent`：用自然语言描述视觉意图（"对比前后 P99 的双柱图"、"架构示意"），
  具体像素留给 renderer。`asset_refs` 引用 `assets/` 里的已有图片；**引用图片时用
  对象形式 `{ref, caption, evidence}`**——caption 会随图渲染，evidence 把这张图挂进
  溯源链。图不是溯源的盲区：页面上每张图都应该能回答"这图哪来的"。
- `deck.style`：声明这套 deck 的风格/模板意图（`{template: ..., palette_hint: ...}`
  或任何你觉得有用的键）。当前 renderer 不消费它；视觉升级后的 renderer 会读。
  同 emphasis/reveal 一样：语义先立位，消费后到。
- `notes`：演讲备注是一等内容。被你从页面上拿掉的细节、过渡话术、预备的问答，写进
  notes。
- `demotions[]`：凡是从本 beat 里裁掉、去了别处的信息，登记 `{content, to}`，
  `to` ∈ `notes | appendix | report_only`。**内容去向必须可审计**——没有 demotion
  记录的静默丢弃会被 QA 盯上。
- `emphasis` / `reveal`：语义级的强调与出场顺序（"先出基线，再出优化后数字"）。
  当前 renderer 忽略它们；未来的动画词汇表和 HTML surface 会消费。这是沟通决策，
  不是视觉决策，所以属于这里。
- 所有数字必须来自 evidence（派生数字先落库，见 stages/evidence.md）。

## 收尾

```
comh save deck_plan
```

narrative 或 brief 之后有任何变更，deck_plan 自动标脏，需要重新投影。
