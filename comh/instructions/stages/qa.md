# Stage: QA（质检）

机械检查由 `comh validate all` 完成，按 brief.media 检查所选媒介。
`qa/findings.yaml` 是汇总视图，不直接往里面写新的模型审稿结果。
模型审稿写独立输入文件，再执行 `comh review <文件>`；CLI 将结果与当前输入、成品和
构建记录一起写入 `qa/model-findings.yaml`。机械检查重跑不会覆盖它。
所有 finding 都写 `owning_artifact`，修复在归属层进行。

## 判断型检查清单

### PPTX 模板兼容性（owning: 样式配置或 renderer）

阅读 render report 的 `native_text_diagnostics`，并检查实际 PPTX 渲染：品牌短字、页脚、
边缘装饰与新增正文都要看。字体替代、width_pressure、自适应是检查线索，不是自动确认的缺陷。
遇到错位，用相同软件/字体环境对照原模板与成品，核对源页/图层/shape 的文字、几何和继承。
编译引入的变化修 renderer；源文件也异常时检查替代字体与播放器兼容性。修复后重新预览，
记录软件版本、字体缺失及尚未验证的平台，不能将 XML 原样保留等同于视觉一致。

### Narrative Validator（owning: narrative）

- 问题与结论是否对应？recommendation 能否从前文推出？
- 逻辑跳跃：相邻 beats 之间观众是否能自然跟上？
- `partial` / `assumption` 状态的 claim 在成品里是否被诚实呈现？

### Audience Validator（owning: narrative 或 deck_plan / report_plan）

- 是否假定过多背景知识？关键术语首次出现是否解释？
- 是否直接对实际读者说话？读者、委托人、材料作者有没有混淆？
- 标题、页眉、图注、卡片底注等可见区域是否残留内部策划理由或空标签？
  依照 [受众文案规则](../references/audience-copy.md) 检查，不只重跑关键词检测。
- 每句话增加了什么具体信息？相同结论是否重复填充多个区域？抽象“验证通过”是否说明
  检查了什么及仍不能证明什么？限制条件是否保留且可理解？
- 密度是否符合 presentation_profile 和用户补充偏好？字数仅作信号，不能据此判定信息质量。
  主图页允许少字；文本页应有必要展开；只用小字把页面塞满也不算通过。

### 视线与编辑检查（owning: deck_plan 或 renderer）

按 [研究与技术汇报](../references/research-presentations.md) 在真实页面检查首眼入口、
阅读顺序、比较对齐、解释邻接、分区间距；记录具体页面问题，不以标题醒目代替正文检查。
查 render report 的 editability 清单，复查大图片是否将正文压平；允许原始截图。
抽样修改文字、表格单元格、图节点并保存重开。HTML 不能证明原生 PPTX 编辑或模板兼容。

### 说人话检查（owning: deck_plan / narrative）

把每页标题和要点**朗读一遍**：任何"念出来像密码"的句子（名词堆叠、无动词、
术语密度过高）都是 finding。检验标准：这句话你敢不敢在会上直接说出口。
术语没给白话解释的，标出来。

### Title Validator（owning: deck_plan）

- 结果页标题是否表达有据的 takeaway？背景、机制、架构页是否准确命名对象，避免强造断言？
- `cover/agenda/section_divider/closing/appendix` 页的主题式标题是否正当？
- 标题与该页 `beat.message` 是否一致（投影不得偷换重点）？

### Reader Test（读者模拟，owning: 按 finding 归属）

用一个**不带任何上下文**的子 agent，只给它受众实际能接触的成品（异步阅读只给页面可见文本/图片或
报告；模拟现场讲解时再提供实际会讲的 notes），让它回答：

1. 你认为作者最想让你记住什么？（逐条列出）
2. 哪里没看懂 / 需要更多背景？
3. 哪个结论你觉得证据不足？
4. 看完你下一步会做什么？
5. 第一眼看到哪个区域？随后按什么顺序读？在哪里需要回看或不知道下一步看哪里？

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
