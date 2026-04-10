# 仓库问答 Agent 第一阶段设计

## 背景

当前项目已经具备以下能力：

- 用户提交 GitHub 仓库后生成中文分析报告
- 任务成功后自动构建 `knowledge.db`
- 任务详情页支持继续提问
- 回答可附带代码片段、文件路径与仓库认知图信息

但当前问答主链路仍然更接近“检索增强问答”，核心路径是：

1. 用户提问
2. 基于问题做 `repo_map` 与知识库检索
3. 拼接 `graph_evidence + citations`
4. 交给 LLM 或本地模板回答

这条链路的问题不只是“检索不够强”，而是主脑设计不对。它仍然默认系统先本地分类、再检索、再回答，而不是像 Claude Code / Codex 一样，在收到自然语言问题后直接进入 Agentic Loop，先理解任务，再决定下一步该查什么证据。

用户已经明确要求把 Claude Code 风格的逻辑融合到当前系统中：对于自然语言问题，不先走本地硬分类，而是让大模型先做任务理解和计划生成，再通过受控工具循环逐步收集证据，最后生成中文讲解。

## 用户确认的设计约束

- 第一阶段只做 `分析 + 问答`，不做执行型 Agent
- 用户问题进入系统后，应优先交给大模型做语义分析与初始计划生成
- 本地规则不再充当主脑，只作为失败兜底
- 大模型必须通过受控工具循环收集证据，不能直接自由编造仓库结构
- 所有 AI 输出必须严格使用中文
- 回答必须基于真实仓库证据，不允许脱离文件、函数、路由、调用链自由发挥
- 前端后续应显示：
  - 回答来源：`LLM` / `本地证据`
  - 规划来源：`LLM 规划` / `规则兜底`

## 第一阶段目标

把当前“检索后回答”的链路升级为“LLM 主导规划 -> Agentic Loop -> 定向取证 -> 证据装配 -> 回答 -> 校验”的仓库问答 Agent，使系统能够：

- 直接理解用户自然语言问题，而不是先依赖本地硬分类
- 像代码分析 Agent 一样自主决定下一步该查什么
- 在宽问题场景下主动拆解问题、缩小范围、逐步补足证据
- 让 LLM 负责任务理解、计划生成和中文表达
- 让工具层负责可控取证，让校验层负责接地和质量控制
- 在规划失败、输出异常或证据不足时，自动回退到规则兜底，保证可用性

## 总体架构

### 当前链路

1. 前端提交问题
2. `/api/v1/tasks/{task_id}/chat`
3. `KnowledgeChatService.answer_question()`
4. `repo_map + retriever + citations + LLM/本地 fallback`
5. 返回回答

### 目标链路

1. 前端提交问题
2. `/api/v1/tasks/{task_id}/chat`
3. `TaskChatOrchestrator`
4. `LLMPlanningAgent`
5. `McpToolGateway`
6. `EvidenceAssembler`
7. `AnswerComposer`
8. `AnswerValidator`
9. 返回回答

### 核心思想

不再默认采用“问题分类 -> 检索 -> 回答”静态链路，而是采用：

`问题 -> 语义理解 -> 下一步动作 -> 工具观察结果 -> 继续决策 -> 回答`

这是一条受控的 Agentic Loop。

## 分层职责

### 1. `TaskChatOrchestrator`

职责：

- 驱动整条问答主链
- 管理 loop 次数、状态与失败回退
- 在 `LLMPlanningAgent`、`McpToolGateway`、`EvidenceAssembler`、`AnswerComposer`、`AnswerValidator` 之间协调

### 2. `LLMPlanningAgent`

职责：

- 直接理解用户问题
- 判断用户真正想解决什么
- 输出当前理解、证据缺口和下一步动作
- 在每轮 observation 返回后继续做下一轮决策
- 在证据足够时，声明 `ready_to_answer=true`

### 3. `McpToolGateway`

职责：

- 作为编排层与 MCP 工具层之间的网关
- 通过 MCP client 获取工具列表并发起 `tools/call`
- 限制动作范围和返回量
- 将 MCP 返回结果标准化为 observation

### 4. `EvidenceAssembler`

职责：

- 将多轮循环中累积的 observation、代码片段、调用链和仓库结构证据做整理
- 输出最终 `EvidencePack`

### 5. `AnswerComposer`

职责：

- 基于 `EvidencePack` 生成最终中文回答
- 严格约束输出结构
- 不让回答器再次承担取证责任

### 6. `AnswerValidator`

职责：

- 校验中文、接地性、回答深度与证据覆盖度
- 决定通过、二次生成、补证据还是最终降级

### 7. `RuleFallbackPlanner`

职责：

- 当 `LLMPlanningAgent` 超时、输出非法 JSON、返回非中文、内容空洞时接管
- 提供最小可用的规则规划能力
- 保证第一阶段不因一次模型失败而彻底不可用

## Agentic Loop 设计

### 设计原则

- 每轮由大模型决定下一步动作
- 但动作必须来自受控工具集合
- 每轮 observation 都会回流给大模型
- 直到大模型判定“证据足够回答”，或达到 loop 上限

### 每轮输入

- 用户问题
- 历史对话
- 当前已收集证据摘要
- 上一轮 observation
- 可用工具列表
- 当前 loop 轮次与剩余轮次

### 每轮输出

- `inferred_intent`
- `answer_depth`
- `current_hypothesis`
- `gaps`
- `ready_to_answer`
- `tool_call`

### 每轮过程

#### 第 1 轮

大模型看到用户问题后，不先硬分类，而是先理解：

- 用户到底想问什么
- 当前还缺什么证据
- 下一步最值得做什么动作

例如用户问：

`请你逐行解析该项目登录功能的代码实现`

大模型应该先推理：

- 用户关注的是“登录功能”而不是整个项目
- 用户要求的深度是 `code_walkthrough`
- 当前还没有定位到登录相关文件与调用链
- 下一步应先搜索登录入口或认证相关实现

因此输出动作：

- `tool_call.name = "search_code"`
- `tool_call.arguments = {"query": "login auth signin 登录"}`

#### 中间轮次

每轮 observation 返回后，大模型继续判断：

- 当前结果是否足够支撑回答
- 是否还需要读取文件
- 是否要追调用链
- 是否要锁定后端 route 或 follow-up service

#### 终止条件

当大模型认为证据足够时，输出：

- `ready_to_answer=true`

若达到 loop 上限仍证据不足，则交给 `EvidenceAssembler` 和 `AnswerComposer` 生成“受限回答”，并由 `AnswerValidator` 决定是否降级。

## MCP 工具层设计

第一阶段所有只读工具都必须通过 MCP 协议暴露，不允许再额外新增一套只供内部使用的私有工具协议。

系统内部可以继续保留领域服务实现，但对 `LLMPlanningAgent` 和编排层暴露的能力，必须统一抽象为符合 MCP 规范的工具。

### MCP 分层角色

#### `LLMPlanningAgent`

- 负责决定调用哪个工具
- 只输出工具名、参数和调用原因

#### `McpToolGateway`

- 负责与 MCP server 建立连接
- 调用 `tools/list`
- 按规划结果调用 `tools/call`
- 将返回值整理为内部 `AgentObservation`

#### `Repository QA MCP Server`

- 对外暴露仓库问答所需的只读工具
- 封装当前项目内部的 `repo_map`、知识库检索、源码读取、历史问答读取等能力

### 工具调用必须贴近 MCP 结构

规划阶段不再输出内部私有 `action_type`，而是输出：

```json
{
  "tool_call": {
    "name": "search_code",
    "arguments": {
      "query": "login auth signin 登录"
    },
    "reason": "先定位登录相关源码文件"
  }
}
```

这样编排层就可以直接映射为 MCP 的 `tools/call` 请求。

### 第一阶段 MCP Server 组织方式

首版推荐采用“一个仓库问答 MCP Server”方案，而不是一开始拆成多个 server。

优点：

- 实现成本更低
- 调试链路更短
- 更适合当前项目平滑演进

后续如有必要，再拆分为：

- `repo-graph-mcp`
- `knowledge-db-mcp`
- `task-context-mcp`

### 允许的 MCP 工具

第一阶段只允许只读工具，不允许执行型动作。

#### `load_repo_map`

用途：

- 读取 `repo_map` 骨架
- 返回入口点、调用链摘要、关系边、关键符号

建议输入：

```json
{
  "task_id": "task-123"
}
```

#### `search_code`

用途：

- 做路径、文件名、符号名、关键词级别的仓库搜索
- 返回候选文件与命中摘要

建议输入：

```json
{
  "query": "login auth signin 登录",
  "limit": 10
}
```

#### `open_file`

用途：

- 读取目标文件源码
- 支持按行区间裁剪

建议输入：

```json
{
  "path": "web/src/pages/LoginPage.vue",
  "start_line": 1,
  "end_line": 220
}
```

#### `read_symbol`

用途：

- 返回函数、类或符号定义片段
- 尽量附带上下文摘要

建议输入：

```json
{
  "path": "app/api/routes/auth.py",
  "symbol": "login"
}
```

#### `trace_call_chain`

用途：

- 结合 `repo_map` 与关系边追调用链

建议输入：

```json
{
  "entry": "web/src/pages/LoginPage.vue:submitLogin",
  "max_depth": 4
}
```

#### `find_route`

用途：

- 按接口路径和方法定位后端处理函数

建议输入：

```json
{
  "method": "POST",
  "path": "/api/v1/auth/login"
}
```

#### `retrieve_chunks`

用途：

- 作为知识库补充检索工具
- 用于局部证据补足

建议输入：

```json
{
  "query": "token refresh jwt",
  "limit": 6
}
```

#### `read_history`

用途：

- 读取最近历史问答摘要
- 解决“这里”“上面那个函数”类问题

建议输入：

```json
{
  "task_id": "task-123",
  "limit": 6
}
```

### 工具设计原则

- 必须符合 MCP 的 `tools/list` 与 `tools/call` 交互方式
- 全部只读
- 全部输出结构化 JSON
- 每个工具都应返回：
  - `summary`
  - `payload`
  - `success`
- 必须限制返回量，防止上下文膨胀
- 工具应优先返回“摘要 + 可继续追的定位信息”，而不是一次性倾倒全部原文

## 核心状态对象

### `AgentLoopState`

作用：保存多轮规划与观察的中间状态。

建议字段：

- `user_question`
- `normalized_question`
- `history_summary`
- `inferred_intent`
- `answer_depth`
- `current_hypothesis`
- `gathered_files`
- `gathered_symbols`
- `gathered_routes`
- `gathered_call_chains`
- `evidence_notes`
- `gaps`
- `loop_count`
- `ready_to_answer`
- `planning_source`

### `AgentAction`

作用：表示大模型请求执行的下一步 MCP 工具调用。

建议字段：

- `tool_name`
- `arguments`
- `reason`

### `AgentObservation`

作用：表示 MCP 工具执行后的结构化结果。

建议字段：

- `tool_name`
- `success`
- `summary`
- `payload`

### `EvidencePack`

作用：在 loop 结束后，装配为最终回答就绪的证据包。

建议字段：

- `question`
- `planning_source`
- `entrypoints`
- `call_chains`
- `routes`
- `files`
- `symbols`
- `citations`
- `key_findings`
- `reasoning_steps`
- `gaps`
- `confidence_basis`

## LLM Planning Prompt 设计

### 目标

让优秀大模型承担第一阶段最关键的任务：

- 理解用户问题
- 决定下一步动作
- 控制探索顺序
- 判断何时证据足够

### 规划提示词要求

规划提示词必须严格限制模型，不允许它直接进入自由回答模式，同时必须让它输出可直接映射到 MCP `tools/call` 的结构。

#### 核心要求

- 必须使用简体中文
- 首要任务不是回答，而是决定下一步动作
- 不允许编造仓库中不存在的文件、函数、类、接口、调用链
- 只能根据当前问题、历史、已收集证据和 observation 做决策
- 如果证据不足，必须继续请求动作，而不是抢先回答
- 只能选择系统提供的动作类型
- 对“详细讲解”“逐行解析”类问题，应优先收集：
  - 入口文件
  - 关键函数定义
  - 调用链上下游
  - 相关接口与后端处理逻辑
- 输出必须为 JSON

### 规划提示词示例

```text
你是一个“代码仓库分析 Agent”，你的任务不是立刻回答用户，而是先判断为了正确回答用户问题，下一步最应该收集什么证据。

你必须严格遵守以下规则：

1. 必须使用简体中文思考与输出。
2. 你不是自由聊天助手，你的首要任务是“分析问题并决定下一步动作”。
3. 不允许编造仓库中不存在的文件、函数、类、接口、调用链。
4. 你只能根据当前提供的问题、历史对话、已收集证据、工具返回结果来决策。
5. 如果证据不足，不要直接回答用户，必须先请求下一步取证动作。
6. 你只能从系统提供的 MCP 工具列表中选择工具，不能发明工具。
7. 优先收集最关键、最接近用户问题核心的证据，避免无关搜索。
8. 如果用户要求“详细讲解”或“逐行解析”，你应优先收集：
   - 入口文件
   - 关键函数定义
   - 调用链上下游
   - 相关接口与后端处理逻辑
9. 当你认为证据已足够支撑高质量回答时，才可以将 `ready_to_answer` 设为 true。
10. 你的输出必须是 JSON，不允许输出额外解释。

输出 JSON 格式如下：

{
  "inferred_intent": "用户真正想解决的问题",
  "answer_depth": "overview | detailed | code_walkthrough",
  "current_hypothesis": "当前对问题的理解",
  "gaps": ["仍缺少的关键证据"],
  "ready_to_answer": false,
  "tool_call": {
    "name": "search_code | open_file | read_symbol | trace_call_chain | find_route | retrieve_chunks | load_repo_map | read_history",
    "arguments": {},
    "reason": "为什么下一步要做这个动作"
  }
}
```

## Evidence Assembler 设计

### 职责

- 汇总多轮 observation
- 对证据做去重、归一化、分桶、排序
- 自动提炼 `key_findings`
- 自动生成 `reasoning_steps`
- 明确证据缺口与可信度基础

### 关键原则

`EvidenceAssembler` 不负责决定下一步动作，也不负责直接回答用户。它的职责是把 loop 中累积的原始材料变成“回答器可直接使用的证据包”。

### 输出要求

- `project_flow` 类问题至少应有多个阶段性 `key_findings`
- `call_chain` 类问题至少应有一条完整链路
- `file_explain` / `function_explain` 类问题必须带源码片段

## Answer Composer 设计

### 职责

基于 `EvidencePack` 生成最终中文回答。

### 生成原则

- 先直接回答用户问题
- 再按逻辑顺序展开
- 再给文件位置、函数位置和代码依据
- 最后再给补充说明与继续追问方向

### 强约束

- 必须使用简体中文
- 必须严格依据 `EvidencePack`
- 不允许引入 `EvidencePack` 之外的新文件、函数、类、路由
- 如果用户要求“逐行”或“代码级讲解”，应按关键代码块、函数块、调用顺序展开解释，不得谎称已经对整仓逐行解释完毕
- 如果证据仍有缺口，要在最后说明缺口，不能一上来只输出“证据不足”

### 回答提示词示例

```text
你是一个面向初学者的仓库讲解助手。你现在必须基于已经确认的真实证据回答用户问题。

你必须严格遵守以下规则：

1. 必须使用简体中文回答。
2. 必须严格依据提供的 EvidencePack 作答。
3. 不允许引入 EvidencePack 中不存在的文件、函数、类、接口、调用链。
4. 先直接回答用户问题，再展开解释。
5. 如果用户要求“逐行”或“代码级讲解”，应按关键代码块、函数块、调用顺序展开解释，不得谎称已经对整仓逐行讲解完毕。
6. 回答要像有经验的工程师在讲代码，不要像检索系统堆字段。
7. 要明确指出关键文件、关键函数、调用关系和代码位置。
8. 如果证据仍有缺口，要在最后说明缺口，不要在开头只说“证据不足”。
9. 输出必须是 JSON，不允许输出额外文本。

输出 JSON 格式如下：

{
  "answer": "最终中文回答",
  "supplemental_notes": ["补充说明1", "补充说明2"],
  "confidence": "high | medium | low"
}
```

## Answer Validator 设计

### 校验维度

#### 1. 语言与格式校验

- 是否为中文
- 是否为空
- 是否过短
- 是否与用户要求深度明显不符

#### 2. grounded 校验

- 是否引用不存在的文件、函数、类、接口、调用链
- 是否引用了 `EvidencePack` 之外的关键实体
- 是否把推断说成事实

#### 3. 覆盖度校验

- 是否覆盖了用户真正关注的问题
- 是否覆盖了 `EvidencePack` 中的关键证据点
- 是否只是泛泛总结

#### 4. 结构质量校验

- 是否先回答问题，再展开
- 是否具备清晰的解释顺序
- 是否符合当前问题所需的表达形态

### 校验失败后的补救策略

不再一失败就直接本地模板降级，而是：

1. 同证据二次生成
2. 补证据后再次生成
3. 最终才进入本地证据降级回答

### Validator 提示词示例

```text
你是一个“代码问答质量校验器”。

你的任务不是改写答案，而是判断下面这份回答是否满足要求。

请根据以下标准检查：

1. 是否使用简体中文
2. 是否直接回答了用户问题
3. 是否覆盖了用户要求的解释深度
4. 是否引用了证据中不存在的文件、函数、类、接口或调用链
5. 是否明显空泛、过短或只在重复证据字段
6. 是否遗漏了关键证据点

请输出 JSON：

{
  "passed": true,
  "issues": [],
  "retryable": false,
  "should_expand_context": false,
  "confidence_override": null
}
```

## 规则兜底策略

### 触发条件

以下情况应自动回退到 `RuleFallbackPlanner`：

- 规划模型超时
- 输出非法 JSON
- 输出非中文
- 输出内容空洞或无法执行

### 兜底职责

- 做最小可用的问题识别
- 给出保守的取证方向
- 维持第一阶段可用性

### 设计原则

规则层不再负责“主导智能分析”，只负责兜底和稳定性。

## 前端展示建议

在现有任务详情页问答面板基础上，增加：

- 回答来源：
  - `LLM`
  - `本地证据`
- 规划来源：
  - `LLM 规划`
  - `规则兜底`
- 本次是否经过多轮探索
- 本次是否触发补证据重试

## 与现有代码的关系

### 保持不变的入口

- `web/src/components/TaskChatPanel.vue`
- `web/src/services/api.ts`
- `app/api/routes/tasks.py`

### 现有服务的迁移方向

#### `app/services/llm/knowledge_chat.py`

短期保留，但不再作为“大一统问答器”。后续应逐步演进为 `TaskChatOrchestrator` 的过渡壳层。

#### `app/services/knowledge/retriever.py`

继续保留，但角色下降为只读工具层的一部分，用于：

- `retrieve_chunks`
- 路径或符号补充检索

#### MCP 工具服务层

第一阶段应新增一个仓库问答专用 MCP Server，用于统一暴露只读工具。这样后续无论切换到 GLM-5 还是其他支持 MCP 的模型编排层，都不需要重写工具协议。

#### `app/services/knowledge/repo_map_builder.py`

继续保留，作为静态仓库认知基础设施，用于：

- 入口点识别
- 调用链基础图谱
- 路由映射
- 前后端链路骨架

#### `app/services/knowledge/question_planner.py`

不再作为主规划器，后续只保留为规则兜底层或兼容层的一部分。

## 首版支持的问题范围

第一阶段建议只稳定支持以下 6 类问题：

- 项目整体流程
- 前端到后端调用链
- 页面或组件如何触发请求
- 某个接口进入后端后的处理流程
- 某个模块或文件的职责
- 某个函数或类的详细解释

暂不纳入首版范围：

- 自动运行命令
- 自动改代码
- 自动修 bug
- 多 Agent 并行执行

## 验证标准

当第一阶段实现完成后，系统至少应稳定回答以下问题：

- 用户粘贴 GitHub 地址后，整个项目会做什么
- 前端请求如何进入后端
- 这个按钮点击后为什么会触发分析
- 任务时间线的数据从哪里来
- 某个接口进入后端后又调用了什么
- 某个文件或函数的职责与执行流程是什么

同时，系统在这类问题上应体现出以下行为特征：

- 不先死板做本地硬分类
- 能通过多轮取证逐步逼近答案
- 能说明自己为什么去读某个文件或追某条链路
- 宽问题下回答明显更像“先理解，再讲解”，而不是“命中几个字段就输出”

## 推荐实施顺序

1. 新增 `AgentLoopState`、`AgentAction`、`AgentObservation`、`EvidencePack`
2. 新增 `LLMPlanningAgent`
3. 新增 `McpToolGateway`
4. 新增 `EvidenceAssembler`
5. 新增 `AnswerComposer`
6. 新增 `AnswerValidator`
7. 新增 `RuleFallbackPlanner`
8. 新增仓库问答 MCP Server
9. 将现有 `KnowledgeChatService` 改造成 `TaskChatOrchestrator` 过渡入口
10. 在前端展示“回答来源 + 规划来源 + loop 元信息”

## 非目标

第一阶段不追求：

- 完整复刻 Claude Code / Codex 的全部执行能力
- 执行型工具调用
- 自动改代码
- 自动运行部署命令
- 多仓库统一知识图谱

第一阶段的重点是先把“LLM 主导规划 + 受控工具循环 + 证据回答 + 校验兜底”的主链做扎实，让现有项目从检索型问答系统升级为更接近 Claude Code 风格的仓库理解型问答 Agent。
