# Stage: QA（质检）

机械检查由 `comh validate all` 完成（schema、引用链、数字一致性、beat 覆盖、硬约束、
Gate 有效性），结果在 `qa/findings.yaml`。**你负责判断型检查**，同样以 finding 记录
（`check` 用 `model:` 前缀），追加进 `qa/findings.yaml` 的 `findings` 列表并同步
`count`。每条 finding 必须写 `owning_artifact`——修复循环靠它定位归属层。

## 判断型检查清单

### Narrative Validator（owning: narrative）

- 问题与结论是否对应？recommendation 能否从前文推出？
- 逻辑跳跃：相邻 beats 之间观众是否能自然跟上？
- `partial` / `assumption` 状态的 claim 在成品里是否被诚实呈现？

### Audience Validator（owning: narrative 或 deck_plan / report_plan）

- 是否假定过多背景知识？关键术语首次出现是否解释？
- 密度是否符合 brief 的 spec.dimensions（不是死字数）？

### Title Validator（owning: deck_plan）

- `content` 页标题是否表达 takeaway，而不是无信息量的话题？
- `cover/agenda/section_divider/closing/appendix` 页的主题式标题是否正当？
- 标题与该页 `beat.message` 是否一致（投影不得偷换重点）？

### Reader Test（读者模拟，owning: 按 finding 归属）

用一个**不带任何上下文**的子 agent，只给它成品（pptx 逐页文本 + notes，或
report.md），让它回答：

1. 你认为作者最想让你记住什么？（逐条列出）
2. 哪里没看懂 / 需要更多背景？
3. 哪个结论你觉得证据不足？
4. 看完你下一步会做什么？

把回答 1 与 `brief.takeaways` 求差：缺失的 takeaway 是 finding（owning 通常是
narrative——故事没承载，而不是页面没写出来）。回答 2/3 的每条都对照 ID 链定位
归属层。

## 收尾

机械 + 模型 findings 合并后，有 error 必须修（在归属层修，见 stages/repair.md）；
warn 逐条判断：修、记录不修原因、或降级。全部 error 清零后才能 deliver。
