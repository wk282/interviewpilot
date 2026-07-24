# Answer Critic Feedback Loop

## 目标

在每次候选人提交回答后，将“评价回答”和“生成下一题”拆成独立职责，形成可持久化、可解释、可评测的反馈闭环。

## 角色

1. **Answer Critic**：根据题目、预期要点、候选人回答和参考证据评分，提取回答原文证据与知识缺口，并给出下一步动作。
2. **Plan Reviser**：应用最少题数、能力覆盖、最大题数、连续追问上限等确定性规则，形成新的自适应计划版本。
3. **Conductor**：检索证据并按计划约束生成下一道题，不再自行推翻 Critic 决策。
4. **Final Evaluator**：面试结束后基于完整问答生成最终证据化报告，职责与逐轮 Critic 分离。

## LangGraph 状态流转

```text
候选人回答
  -> answer_critic
       score / evidence / gaps / requested_action
  -> plan_reviser
       effective_action / target_competency / target_difficulty / plan_version
  -> conductor
       CRAG retrieval / question generation
  -> 下一轮或结束
```

统一的 `InterviewState` 同时支持 `PLAN`、`TURN`、`EVALUATE` 三种入口。逐轮回答走
`Answer Critic -> Plan Reviser -> Interviewer`；初始计划和最终评估分别进入 Planner 与
Final Evaluator。状态只保存可序列化 ID 和结构化结果，不保存 ORM 对象。

## 决策动作

- `FOLLOW_UP`：围绕当前能力点继续核实。
- `INCREASE_DIFFICULTY`：当前回答较好，提高难度继续深挖。
- `DECREASE_DIFFICULTY`：当前回答基础薄弱，降低难度确认基础。
- `SWITCH_TOPIC`：切换到尚未覆盖的计划能力点。
- `END_INTERVIEW`：达到最少题数和覆盖率后结束。

Plan Reviser 会覆盖不安全决策：达到最大题数必须结束；不足3题或覆盖率不足70%时拒绝提前结束；同一能力点最多连续处理3次。

## 持久化

- `interview_turn_critique`：每个回答唯一一条评分、证据、知识缺口、动作、模型和 Prompt 版本。
- `interview_plan_revision`：每条 Critic 唯一对应一个计划版本，保存前后快照、字段差异、题目预算、目标能力、目标难度和完整工作流 Trace。
- 下一题的 `decision_metadata` 保存 Critic ID、计划修订 ID、动作和 CRAG Trace。

删除面试会话时，上述记录通过外键级联删除。

当前 PostgreSQL 已持久化业务状态，但 LangGraph Checkpointer 尚未接入；暂停恢复和节点级重放属于后续可靠性阶段。

## 隐私边界

- 个人模拟面试可以实时看到上一轮反馈。
- 企业候选人在面试过程中看不到分数和内部决策。
- 企业成员与个人用户在最终报告中可以查看逐轮 Critic 证据。

## 降级策略

Critic 模型输出经过 Pydantic 校验。模型超时、空响应或格式错误时，系统生成低置信度的 `FALLBACK_RULE` 记录，而不是静默假装模型成功。最终报告可统计规则兜底比例。

## 离线评测

生产 Critic 与离线评测复用 `answer-critic-v1` Prompt 和 `GeneratedCritique` Schema：

```powershell
cd backend
python -m evaluation.runner run-critic
```

指标包括评分区间命中率、下一动作准确率、难度调整准确率、知识缺口 Precision/Recall/F1、完全匹配率和规则兜底率。
