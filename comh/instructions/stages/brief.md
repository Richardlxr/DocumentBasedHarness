# Stage: Brief（沟通契约）— Gate 1

## 输入

- `evidence/evidence.yaml`（事实库概况：材料里有什么、没什么）。
- 用户的自然语言描述：给谁看、想干什么、有什么要求。

## 你做什么

先复述已知目标、标明推断与关键未知。只问影响当前决定且无法查清的问题。把用户的话 + 材料概况合成为一份沟通契约，写入
`brief/brief.yaml`，然后把要点摘成一页人类可读的摘要给用户确认。

字段纪律：

- `language`：所有交付物（deck、报告）的语言（如 `zh-CN`、`en`）。显式确认，不许下游
  猜——renderer 选字体、模板选择、各 stage 的写作语言都消费它。
- **语言基调（重要）**：默认**直白易懂**："做了什么、观察到什么、结果是什么"。
  直白 ≠ 修辞：不要比喻类比（"伤害""立尺子"式的话）、不要破折号金句（"——分开，
  就没事"）、"不是X而是Y"对仗句省着用。主谓宾 + 具体数字就是直白。
  只有用户明确要求学术腔/术语密度时才升级措辞；专业术语首次出现必须带一句白话
  解释。宁可朴素准确，不要压缩成密码。
- `voice`（语言风格契约；已有样本或明确要求直接采用，否则给出建议默认或按需出样例）：
  无特别偏好可提议默认值，不必强制选样。需要对齐样例时有两条路：
  1. **样本对齐**：用户贴两三句自己平时的原话（或喜欢的文风）→ 记入
     `voice.samples`，所有写作向它对齐。比任何形容词都准。
  2. **出样例选**：用户希望比较文风时，取一条**真实的 beat 候选 message**，按 2-3
     个风格档各写一版给用户看（如 plain / formal / 带节奏感），用户选一版并口头
     微调（"再正式一点""数字前置"）→ 定稿记入 `voice.style` + `voice.description`。
  显式开关写进 `voice.rules`：`relax`（本 run 放行哪些默认禁令，如 punchy 场景
  放行 em-dash）、`extra_forbidden`（追加禁词）、`extra_metaphor_markers`
  （追加比喻标记）。`comh validate` 的 style 检查**执行选定风格**，不是执行
  室内默认风格。
- `audience`：具体的人，不是标签。"客户方技术负责人，熟悉存储系统但不了解我们的
  缓存方案" 远好于 "technical"。
- `objective`：这次沟通要达成什么决定/行动/认知。
- `delivery_context`：场合与时长（"30 分钟客户评审会" / "异步阅读的周报"）。
- `media`：每个输出 `{medium, surface}` 二元组。当前支持 `pptx/presentation`、
  `markdown/report`（docx 为可选编译副产物）、`docx/report`、
  `html/presentation` 与 `html/data_story`。只生成用户选择的媒介。
- `takeaways`：受众看完应该记住什么。**这是 QA 读者测试的比对基准**，写具体。
- `constraints.hard`：保留所有用户硬要求。推荐结构化对象：
  `{id: limits, text: 必须说明局限性, check: contains, scope: report, value: 局限性}`。
  `check` 为 `contains | forbidden | light_background | manual`；`scope` 为
  `deck | report | all`（默认 all，每个所选媒介都要满足）。contains/forbidden 的
  `value` 是待检查的字面文字。自然语言旧格式仍可用。
  无法机器判断时写 `{id, text, check: manual, acceptance: 人工验收方法}`，保持硬约束，
  在最终 review 中逐项登记通过依据。只有用户明确同意才能改成 soft。
  Gate 1 只检查契约；尚未生成的内容处于待检查状态。投影检查安排，正文检查实现。
- `constraints.soft`：偏好，尽力满足不保证。
- `visual_materials`（素材方向；可明确延期到 projection）：这批成品的视觉素材从哪来——
  纯排版（typography-only 也是显式选择）/ 图标点缀（`assets/vendor/tabler-outline`，
  5 千+语义图标）/ 需要配图（用户提供 or 显式申请外部获取，绝不静默抓取）。
  写成开放字段记进 brief，deck 投影时消费。
- `spec.dimensions`：自由发明的维度表（`technical_rigor`、`storytelling`、
  `evidence_density`、以及任何你觉得能表达这次沟通风格的新词）。代码只透传不解释，
  下游靠你自己在各 stage 里贯彻。
- `open_questions`：保留问题、答案或延期截止阶段；尚未回答的关键问题不能接受契约。
- `alignment`：逐字段记录来源、状态、依据与当前值。格式见 [对话协议](../references/dialogue-protocol.md)；关键字段均需处置，不要求逐项审问。

## 优先级（下游所有 stage 遵守）

```
用户硬约束 > 用户明确偏好 > 已确认的 spec > 你的推断 > preset 默认
```

## Gate 1（硬规则）

给用户看：语言 / 受众 / 目标 / 场合 / 媒介 / 期望带走什么 / 硬约束清单 / spec 摘要。
用户修改后更新文件；先保存、生成展示请求，再等待用户回复：

```
comh save brief
comh present brief
# 将返回的契约、推断和关键未知展示给用户，收到实际回复后：
comh respond D0001 --decision accepted --reply "实际原话" --source "消息引用"
```

未过 Gate 1 时，narrative 及之后所有 stage 的 save 都会被 CLI 拒绝——不要试图绕过。
brief 在 Gate 之后修改会自动作废确认，需要用户重新确认，这是刻意设计的代价可见。
