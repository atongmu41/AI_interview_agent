# 面试官 Agent 设计说明

## 目标

`Interviewer Agent` 负责**驱动面试对话**：选择题目、提出问题、根据候选人回答进行追问、在需要时总结当前轮次信息，并将结构化上下文交给评估环节。

## 位置与依赖

- **文件**: `agents/interviewer.py`
- **依赖**
  - `services/llm.py`：通过 `LLMClient.chat/achat` 调用模型
  - `config/questions.yaml`：题库（领域/难度/标签/题干/参考要点等）
  - `config/prompts.yaml`：面试官提示词模板（system / few-shot / rubric 等）
  - `agents/supervisor.py`：由 `Supervisor` 状态机驱动调用节奏（QUESTION / FOLLOWUP）

## 职责边界

- **负责**
  - 题目选择（按岗位/技能/难度/进度）
  - 问题表述（清晰、可回答、符合轮次）
  - 追问策略（针对模糊点、关键概念、工程细节、边界条件）
  - 对话礼仪与节奏（控制轮次、提醒时间、允许澄清）
  - 产生结构化的“本题上下文”给评估模块（题目、候选人回答、追问与回答、关键信号）
- **不负责**
  - 给出最终评分与结论（交给 `Evaluator Agent`）
  - 语音输入输出（交给 `services/stt.py` / `services/tts.py`）
  - 持久化落盘（交给 `storage/` 相关写入逻辑，后续实现）

## 典型工作流（与状态机对应）

- **INIT**
  - 准备面试参数（岗位、级别、题量、时长等）
  - 初始化会话上下文（空历史、已问列表等）
- **QUESTION**
  - 从题库选题 → 生成本轮主问题
- **FOLLOWUP**
  - 根据候选人回答生成 0~N 个追问（可配置上限）
  - 追问结束条件：回答充分 / 达到追问上限 / 候选人明确不会 / 时间到
- **EVALUATE**
  - 产出结构化摘要（facts/claims/strengths/risks/unknowns），交给评估 Agent
- **END**
  - 停止继续提问

## 输入与输出（建议数据结构）

### 输入

- **面试上下文**（可由 `Supervisor` 或上层 orchestrator 传入）
  - 岗位/方向/级别
  - 已问题目列表
  - 对话历史（messages）
  - 当前轮题目（若处于 FOLLOWUP/EVALUATE）
  - 候选人最新回答文本

### 输出

- **对候选人的一句话输出**（面试官要说的话）
- **结构化控制信息**（给上层逻辑）
  - `next_state_hint`: `QUESTION | FOLLOWUP | EVALUATE | END`
  - `question_id / tags / difficulty`
  - `need_followup: bool`
  - `round_summary`（供评估）

## 与 LLM 的交互约定

### 消息格式

使用 OpenAI chat messages 形式：

- `system`: 面试官身份、规则、风格、追问策略、禁止事项
- `user`: 上层输入（候选人回答、题目、限制条件等）

### 关键提示词要点（放在 `config/prompts.yaml`）

- **角色与目标**：你是技术面试官，目标是识别真实能力
- **追问策略**：从“概念 → 机制 → 边界 → 工程落地 → 反例/故障排查”
- **输出格式约束**：要求模型输出可解析的结构（例如 JSON 或分段字段）
- **安全与合规**：不泄露题库答案；不输出敏感信息；不做歧视性评判

## 可配置项（建议来自 `config/settings.yaml`）

- 每轮追问最大次数
- 温度 `temperature`
- 最大输出长度 `max_tokens`
- 题库筛选：标签白名单/黑名单、难度曲线
- 面试节奏：每题时间限制、总题数

## 容错与降级策略

- 模型返回不符合格式：自动重试一次（降低温度/加强格式约束）
- 候选人回答为空/离题：给出澄清问题或引导回题目
- 网络/模型错误：提示用户稍后重试，并允许进入 END 或继续下一题

## 扩展点

- 多轮面试策略（按能力矩阵动态选题）
- 结合简历/项目经历生成定制题
- 将 `FOLLOWUP` 细分为：澄清 / 深挖 / 反向验证
- 支持多模态（语音/代码片段输入）后再进 LLM 
