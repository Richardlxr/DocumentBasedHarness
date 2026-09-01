# 叙事模式词汇（vocabulary, not boundaries）

这些模式是**参考词汇**，不是模板枚举。你可以使用、混合、改写、无视它们，或发明
系统里不存在的新拓扑。不要让用户"从 A/B/C 里选一个"。

## 常见拓扑

### problem → evidence → mechanism → recommendation
最通用的论证骨架。适合实验汇报、技术评审。
变化：recommendation 前置（结论先行，面向管理者）。

### phenomenon → counter-intuitive question → wrong intuition → experiment → mechanism → application
适合课堂/研究分享：先用反直觉钩子建立张力。

### situation → complication → resolution (SCR)
面向管理者的简短汇报。

### claim → attack → survive（钢人自查）
主动列出对自己的最强反驳并回应，再交给受众。高信任场合（客户技术评审）很有效。

### layered reveal（逐层揭底）
开场给现象，每层 beat 揭一层原因，最后一层给决策。适合复盘。

## purpose 词汇（开放，举例）

establish_problem / stake (为什么值得关心) / establish_credibility /
demonstrate_effect / quantify / concede_limit / explain_mechanism / compare /
address_objection / recommend / next_steps / anticipate_qa / call_to_action

## 设计自查（写 story 时过一遍）

- 前三拍之内，观众知道"为什么我该听"吗？
- 每个 primary claim 有 beat 承载吗？（孤儿 claim 要么给 beat，要么降 importance）
- limitation/concede 的位置放在结论前还是后？这是语气决策：前置更诚实防御，
  后置更自信进攻——按 brief 的 spec 判断。
- 若删掉某 beat 故事仍成立，删掉它（beat-coverage 校验通过 ≠ 不能精简）。
