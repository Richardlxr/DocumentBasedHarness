# 对话协议与可恢复决策

## 什么时候提问

每个关键决定都有处置，不要求每个字段都有一轮问答。用户明确说过的记录原话；
影响当前目标/结构的缺失信息才问；材料能查清的自行核验；低影响偏好可建议默认值；
下游才需要的选择记录延期和截止阶段；不适用的写明理由。不要虚构问题来表现认真。

## 先展示，再记录实际回复

1. 写好并 `comh save` 当前 artifact。
2. `comh present brief|narrative|deck_outline|report_outline`，可用 `--summary <markdown>` 附短摘要。
3. 将返回的 view、推断、关键未知和取舍以自然语言展示给用户，保留请求 ID；停止相依的下游动作。
4. 收到回复后 `comh respond D0001 --decision accepted --reply '实际原话' --source '消息引用'`。
   修改意见用 changes_requested；大纲/细化的明确委托用 delegated。brief、narrative 和 delivery 需要接受。
5. 运行 `comh next --json`。新会话、压缩后以及接到修改要求时也从这里恢复。

展示只是等待状态。没有用户回复不能运行 respond；“继续”只在明确对应当前唯一提案时解释，
不能确认未来提案。旧回复不能应用到新版本。同一回复重复提交不会重复推进。
修改当前提案后重新 save/present，旧请求会标 superseded；另一个尚待回复的提案不能被静默覆盖。

原确认命令仍可用，但必须带 `--request --reply --source`，不能裸调用。
run.yaml 里的旧 gate 若无请求依据会显示 legacy，内容不删除，但下游需要补当前确认。

## 契约对齐记录

brief.alignment 按字段记录，字段为 language、audience、objective、delivery_context、media、
takeaways、constraints、voice、visual_materials。例：

```yaml
voice: {style: plain}
alignment:
  voice:
    value: {style: plain}
    source: default
    status: proposed
    basis: 用户没有指定文风，建议先用直白书面语
```

value 必须与 brief 的实际字段一致，避免两套契约。source 为 user/material/inference/default；
status 为 provided/confirmed/proposed/delegated/deferred/not_applicable/unresolved。
provided、confirmed、delegated 需要用户依据；proposed 是等待本次 Gate 接受的建议。
非核心字段允许 not_applicable 并写 basis；视觉材料可 deferred 并写 due: projection，届时必须处理。
核心方向、受众、语言、媒介和目标不能延期。constraints 无额外要求可显式写空列表。

open_questions 有答案写 answer；未回答默认阻塞 Gate 1。确实可延期的写
`{question, status: deferred, due: projection, reason}`；不适用写 status: not_applicable 与 reason。
没有未知就写空列表，同时提供简短的目标理解与依据，不需要自报信心百分比。

## 未知论断

partial/assumption/needs_research 必须在故事线摘要展示。
继续使用时加 `resolution: {action: qualify, reason: 原因, boundary: 在成品中说明的边界}`；
删除时用 action: omit，并从 story 引用中移除。action: research 表示仍需调查，会阻塞接受。
反证可写 claim.counterevidence: [E002]，上下文切片保留它；不能只加载支持证据。

## 能力边界

CLI 代录协议只校验版本、顺序和记录完整性，recording: agent_attested 不认证真人身份。
不要声称保存一段 reply 就形成了独立授权。受控宿主若要更强保证，需要独立接收用户事件并
控制生成 agent 无权修改的状态；当前包不提供该宿主。上下文包也不能控制宿主实际如何压缩。
