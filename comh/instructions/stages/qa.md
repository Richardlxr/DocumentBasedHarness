# Stage: QA（质检）

机械检查由 `comh validate all` 完成，按 brief.media 检查所选媒介。
`qa/findings.yaml` 是汇总视图，不直接往里面写新的模型审稿结果。
模型审稿写独立输入文件，再执行 `comh review <文件>`；CLI 将结果与当前输入、成品和
构建记录一起写入 `qa/model-findings.yaml`。机械检查重跑不会覆盖它。
所有 finding 都写 `owning_artifact`，修复在归属层进行。

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

用一个**不带任何上下文**的子 agent，只给它受众实际能接触的成品（异步阅读只给页面可见文本/图片或
报告；模拟现场讲解时再提供实际会讲的 notes），让它回答：

1. 你认为作者最想让你记住什么？（逐条列出）
2. 哪里没看懂 / 需要更多背景？
3. 哪个结论你觉得证据不足？
4. 看完你下一步会做什么？

把回答 1 与 `brief.takeaways` 求差：缺失的 takeaway 是 finding（owning 通常是
narrative——故事没承载，而不是页面没写出来）。回答 2/3 的每条都对照 ID 链定位
归属层。

## 去 AI 味审稿（二次审稿，必做）

`comh validate` 的 `style:*` findings（破折号金句、比喻标记、对仗句式、英文 tell）
是默认文风的启发式告警。流程：**检测 → 改写或记录有理由的豁免 → 重检**。
显式禁词是 error；默认文风建议是 warn，不得为了清零而扭曲正常术语或用户选定风格。
需要放行比喻检测时通过 brief.voice.rules.relax: [metaphor] 表达。改写原则：

- 破折号金句：拆成两个陈述句，或只留主句；
- 比喻/拟人：直接说技术事实（"伤害来自缓存共用"改写为"共用缓存时尾延迟升高"）；
- "不是X而是Y"：删掉一半，直接说要的那个；
- brief.voice（用户原话样本）优先于一切风格规则。

## 风格验收（必经的人工步骤）

style lint 提供可复查的提示。**语言风格的最终验收永远
是用户通读**：交付前把成品逐页/逐节给用户过一遍语言，用户说"就是这个味"
才算过。机器检查与用户通读都需要完成；默认风格 warn 可以保留并说明理由。

## 记录审查与交付

在 `.workspace/review-input.yaml` 写入（示例格式，不代表已完成审查）：

```yaml
completed_checks: [narrative, audience, reader, style]
reader_test:
  output: qa/reader-output.md
  executor: 实际独立执行任务的 ID 或读者标识
  input_scope: 实际提供给读者的成品及讲解范围
findings: []
manual_constraints:
  - id: tone
    verdict: pass
    detail: 用户已通读当前版本并确认语气符合约定
```

只有实际完成的检查才能记入 completed_checks。reader_test 必须引用 run 内已有的实际读者输出；
CLI 保存其哈希，文件变化后需要重审。路径和执行信息不能证明独立性，不得伪造输出。
没有可用的独立执行能力就报告未完成，不得自填通过。没有人工硬约束时 manual_constraints
可以为空。发现的问题用 `{artifact, check: model:logic, severity: error|warn|info,
verdict: fail, detail, owning_artifact}` 记录。已解决项可保留 `state: resolved, reason: ...`；
warn 可 `state: waived` 并写 reason，error 不得豁免。

顺序：修机械 error → 渲染全部所选成品（Markdown 可独立交付）→ 检查模型清单、
完成读者测试和人工硬约束验收 → `comh review .workspace/review-input.yaml` →
`comh validate all` → `comh present delivery` 展示当前成品，实际验收回复经 respond 记录后 `comh deliver`。

交付必须有当前版本的审稿记录，所有未解决 error 都会阻断。改动输入、输出或重新渲染后，
原审稿/验收失效，需检查变更影响并重新记录；不能机械复制旧的通过结论。
历史手写 model findings 会保留，但因没有版本依据，必须重新审查绑定。
修复期间的 save/render 只执行相关机械检查，旧审稿不会阻塞其自身的修复。
