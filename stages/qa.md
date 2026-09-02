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

### 说人话检查（owning: deck_plan / narrative）

把每页标题和要点**朗读一遍**：任何"念出来像密码"的句子（名词堆叠、无动词、
术语密度过高）都是 finding。检验标准：这句话你敢不敢在会上直接说出口。
术语没给白话解释的，标出来。

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

## 去 AI 味审稿（二次审稿，必做）

`comh validate` 的 `style:*` findings（破折号金句、比喻标记、对仗句式、英文 tell）
是机器可检测的 AI 腔。流程：**检测 → 改写 → 重跑检测，直到清零**。改写原则：

- 破折号金句：拆成两个陈述句，或只留主句；
- 比喻/拟人：直接说技术事实（"伤害来自缓存共用"改写为"共用缓存时尾延迟升高"）；
- "不是X而是Y"：删掉一半，直接说要的那个；
- brief.voice（用户原话样本）优先于一切风格规则。

## 风格验收（必经的人工步骤）

style lint 只保证下限（机器可检测的 AI 腔清零）。**语言风格的最终验收永远
是用户通读**：交付前把成品逐页/逐节给用户过一遍语言，用户说"就是这个味"
才算过。lint 清零 ≠ 风格合格；用户通读 ≠ 可跳过 lint——两者都要。

## 收尾

机械 + 模型 findings 合并后，有 error 必须修（在归属层修，见 stages/repair.md）；
warn 逐条判断：修、记录不修原因、或降级。全部 error 清零是硬性的：save / confirm /
render 会直接拒绝带 error 的工作区。最后由用户验收：`comh deliver` 把验收落进
run.yaml（钉住成品指纹；此后任何重渲染都会把验收标记为作废，需重新验收）。
