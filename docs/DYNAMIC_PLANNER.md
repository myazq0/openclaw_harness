# OpenClaw Multi-Agent Harness 动态计划执行循环

## 设计文档 v4.0

---

## 1. 需求概述

### 1.1 核心目标

实现一个**动态计划执行循环**,让 Harness 能够:

1. **收到任务** → 询问 LLM 应该用哪个 Agent 拆分计划
2. **拆分计划** → Harness 将任务丢给选中的 Agent,Agent 返回计划
3. **执行计划** → Harness 循环询问 LLM 下一步用什么 Agent,执行并获取结果
4. **循环决策** → 根据执行情况决定继续执行/修正计划/终止
5. **完整展示** → 在页面和日志中展示所有交互过程

### 1.2 执行流程图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        动态计划执行循环                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌──────────────┐                                                       │
│   │ 1. 收到任务  │                                                       │
│   │ "写一个BST"  │                                                       │
│   └──────┬───────┘                                                       │
│          │                                                                │
│          ▼                                                                │
│   ┌─────────────────────────────────────────┐                           │
│   │ 2. 询问 LLM: 用哪个 Agent 拆分计划？     │ ◄── Prompt:               │
│   │                                         │     - 当前任务             │
│   │                                         │     - 可用 Agent 列表     │
│   │                                         │     - 历史决策           │
│   └──────────────┬──────────────────────────┘                           │
│                  │                                                        │
│                  ▼ LLM 返回                                              │
│   ┌─────────────────────────────────────────┐                           │
│   │ 3. Agent 选择: "planner" / "leader"     │                           │
│   └──────────────┬──────────────────────────┘                           │
│                  │                                                        │
│                  ▼                                                        │
│   ┌─────────────────────────────────────────┐                           │
│   │ 4. Harness → Agent: 拆分计划           │ ◄── 消息:               │
│   │    - 原始任务                          │     - task                 │
│   │    - system_prompt                    │     - system_prompt       │
│   │    - context (可选)                   │     - context             │
│   └──��───────────┬──────────────────────────┘                           │
│                  │                                                        │
│                  ▼ Agent 返回                                              │
│   ┌─────────────────────────────────────────┐                           │
│   │ 5. 返回计划: [阶段1, 阶段2, 阶段3...]  │                           │
│   │    - 分析需求 → researcher             │                           │
│   │    - 编写代码 → coder                  │                           │
│   │    - 优化文档 → writer                 │                           │
│   └──────────────┬──────────────────────────┘                           │
│                  │                                                        │
│                  ▼                                                        │
│   ┌──────────────────────────────────┐  ◄── 循环直到计划执行完成       │
│   │ 6. 循环执行计划                   │                              │
│   │    ┌────────────┐                 │                              │
│   │    │ 第 N 步   │                 │                              │
│   │    └────┬─────┘                 │                              │
│   │         │                       │                              │
│   │         ▼                       │                              │
│   │    ┌────────────────────────┐  │                           │
│   │    │ 询问 LLM: 下一步用     │  │                           │
│   │    │ 哪个 Agent 执行？     │  │                           │
│   │    └─────────┬────────────┘  │                           │
│   │              │                 │                              │
│   │              ▼                 │                              │
│   │    ┌────────────────────────┐  │                           │
│   │    │ LLM 返回: "coder"      │  │                           │
│   │    └─────────┬────────────┘  │                           │
│   │              │                 │                              │
│   │              ▼                 │                              │
│   │    ┌────────────────────────┐  │                           │
│   │    │ Harness → Agent 执行 │  │                           │
│   │    └─────────┬────────────┘  │                           │
│   │              │                 │                              │
│   │              ▼                 │                              │
│   │    ┌────────────────────────┐  │                           │
│   │    │ Agent 返回结果         │  │                           │
│   │    └─────────┬────────────┘  │                           │
│   │              │                 │                              │
│   │              ▼                 │                              │
│   │    ┌────────────────��───────┐  │                           │
│   │    │ 询问 LLM: 下一步做什么？│  │                           │
│   │    │ (继续/修正/停止)        │  │                           │
│   │    └─────────┬────────────┘  │                           │
│   │              │                 │                              │
│   └──────────────┼──────────────────┘                              │
│                  │                                                        │
│                  ▼                                                        │
│   ┌──────────────────────────────┐                                    │
│   │ 7. 终止条件满足 → 结束       │                                    │
│   └──────────────────────────────┘                                    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 架构设计

### 2.1 整体架构

```
                      ┌─────────────────────────┐
                      │      Web 客户端         │
                      │   (展示 + 日志)         │
                      └───────────┬─────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         新增: ExecutionLoop                             │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │              DynamicPlanner (动态计划器)                       │    │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐    │    │
│  │  │ LoopManager  │  │ DecisionMaker │  │ FlowTracker   │    │    │
│  │  │ (循环管理)   │  │ (LLM 决策)   │  │ (流程追踪)    │    │    │
│  │  └───────────────┘  └───────────────┘  └───────────────┘    │    │
│  └───────────────────────────────────────────────────────────────│    │
└──────────────────────────────┬──────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      OpenClawHarness (现有)                          │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐              │
│  │   Agents    │  │    TaskQueue │  │  MessageBus │              │
│  │  leader    │  │   (队列)     │  │   (消息)    │              │
│  │  coder     │  │              │  │              │              │
│  │  researcher│  │              │  │              │              │
│  │  writer    │  │              │  │              │              │
│  │  analyst   │  │              │  │              │              │
│  │  general   │  │              │  │              │              │
│  └───────────────┘  └───────────────┘  └───────────────┘              │
└──────────────────────────────┬──────────────────────────────────────┘
                                 │
                                 ▼
                        ┌──────────────┐
                        │      LLM     │
                        │  (千问/...） │
                        └──────────────┘
```

### 2.2 核心组件

#### 2.2.1 LoopManager - 循环管理器

**职责**:
- 管理执行循环的启停
- 维护计划状态 (计划阶段 → 执行阶段)
- 控制循环迭代

```python
class LoopManager:
    def __init__(self, harness):
        self.harness = harness
        self.current_plan: List[PlanStage] = []  # 当前计划
        self.execution_index: int = 0           # 当前执行到的阶段
        self.loop_state: LoopState = LoopState.IDLE
    
    def start_execution(self, task: str) -> "ExecutionRecord":
        """开始执行循环"""
    
    def get_next_action(self) -> "ActionDecision":
        """获取下一步动作"""
    
    def execute_step(self, agent_id: str, input_data: str) -> "StepResult":
        """执行一个步骤"""
    
    def should_continue(self) -> bool:
        """判断是否继续循环"""
```

#### 2.2.2 DecisionMaker - LLM 决策器

**职责**:
- 生成询问 LLM 的提示词
- 解析 LLM 的决策响应
- 协调 Agent 选择

```python
class DecisionMaker:
    """LLM 决策器 - 负责生成决策提示词和解析响应"""
    
    # ========== Prompt 模板 ==========
    
    SELECT_AGENT_PROMPT = """你是一个任务规划专家。请根据当前情况选择合适的 Agent。

## 当前任务
{task}

## 可用 Agent
{agents_list}

## 历史决策 (如果有)
{history}

请选择最适合拆分此计划的 Agent，返回格式：
```
Agent: [agent_id]
原因: [简短说明]
```

请用中文回复。"""
    
    EXECUTE_NEXT_PROMPT = """你是一个任务执行协调专家。请决定下一步做什么。

## 原始任务
{original_task}

## 计划阶段
{plan_stages}

## 当前执行进度
- 已完成: {completed}
- 当前: {current}
- 状态: {status}

## 上一步结果
{last_result}

请决定下一步：
```
动作: [execute|revise|stop]
Agent: [agent_id 或 None]
说明: [简短说明]
```

请用中文回复。"""
    
    CONTINUE_PROMPT = """你是一个任务执行协调专家。请决定是否继续执行。

## 当前计划阶段
{remaining_stages}

## 最近执行结果
{recent_result}

## 执行上下文
{context}

请决定：
```
动作: [next|revise|stop]
说明: [简短说明]
```

请用中文回复。"""
    
    # ========== 方法 ==========
    
    def generate_select_agent_prompt(self, task: str, agents: List[str], history: str) -> str:
        """生成选择 Agent 的提示词"""
    
    def generate_execute_next_prompt(self, plan: "ExecutionPlan", context: Dict) -> str:
        """生成下一步执行的提示词"""
    
    def parse_agent_selection(self, response: str) -> "AgentDecision":
        """解析 Agent 选择响应"""
    
    def parse_action_decision(self, response: str) -> "ActionDecision":
        """解析动作决策响应"""
```

#### 2.2.3 FlowTracker - 流程追踪器

**职责**:
- 记录每个循环的详细交互
- 追踪 Harness ↔ Agent 的消息
- 生成可视化的流程展示

```python
class FlowTracker:
    """流程追踪器 - 记录完整交互过程"""
    
    def __init__(self):
        self.current_execution: Optional[ExecutionRecord] = None
        self.executions: List[ExecutionRecord] = []
    
    def start_record(self, task: str) -> "ExecutionRecord":
        """开始记录新的执行"""
    
    def record_llm_decision(self, prompt: str, response: str, decision_type: str):
        """记录 LLM 决策过程"""
    
    def record_harness_to_agent(self, agent_id: str, message: str):
        """记录 Harness → Agent 的消息"""
    
    def record_agent_to_harness(self, agent_id: str, result: str):
        """记录 Agent → Harness 的结果"""
    
    def get_display_data(self) -> Dict:
        """获取前端展示数据"""
```

---

## 3. 数据结构

### 3.1 ExecutionRecord - 执行记录

```python
@dataclass
class ExecutionRecord:
    """完整的执行记录"""
    record_id: str
    original_task: str
    
    # 时间
    start_time: str
    end_time: Optional[str] = None
    duration: float = 0.0
    
    # 计划
    plan: List[PlanStage] = field(default_factory=list)
    plan_prompt: str = ""  # 拆分计划时的 prompt
    plan_response: str = "" # 拆���计划的响应
    
    # 执行阶段
    execution_steps: List[ExecutionStep] = field(default_factory=list)
    
    # 循环决策记录
    decisions: List[LoopDecision] = field(default_factory=list)
    
    # 状态
    status: str = "running"  # running/completed/failed/stopped
    final_result: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """转换为字典 (含 to_display 方法)"""
    
    def to_display(self) -> Dict:
        """转换为前端展示格式"""
```

### 3.2 PlanStage - 计划阶段

```python
@dataclass
class PlanStage:
    """单个计划阶段"""
    stage: int
    name: str
    agent: str  # Agent ID (如 "coder")
    input_text: str  # 给 Agent 的输入
    expected_output: str  # 期望输出
    status: str = "pending"  # pending/running/completed/skipped
    
    # 执行结果
    result: Optional[str] = None
    llm_response: Optional[str] = None
    
    def to_dict(self) -> Dict:
        ...
```

### 3.3 ExecutionStep - 执行步骤

```python
@dataclass
class ExecutionStep:
    """单个执行步骤"""
    step_id: int
    decision_type: str  # "select_agent" / "execute_next" / "continue"
    
    # Harness → LLM
    harness_prompt: str
    llm_response: str
    
    # 决策结果
    selected_agent: Optional[str] = None
    action: Optional[str] = None  # "execute" / "revise" / "stop"
    
    # Agent 执行 (如果选择了执行)
    agent_id: Optional[str] = None
    agent_input: str = ""
    agent_result: str = ""
    agent_status: str = "pending"  # pending/running/completed
    
    # 时间
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        ...
```

### 3.4 LoopDecision - 循环决策

```python
@dataclass
class LoopDecision:
    """循环决策记录"""
    step: int
    decision_type: str  # "select_agent" / "execute_next" / "continue"
    
    # 提示词
    prompt: str
    
    # LLM 响应
    response: str
    
    # 决策结果
    agent_id: Optional[str] = None
    action: Optional[str] = None
    reason: str = ""
    
    # 时间
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
```

### 3.5 LoopState - 循环状态

```python
class LoopState(Enum):
    """循环状态"""
    IDLE = "idle"                    # 空闲
    PLANNING = "planning"            # 正在拆分计划
    EXECUTING = "executing"          # 正在执行计划
    WAITING_DECISION = "waiting"     # 等待 LLM 决策
    COMPLETED = "completed"          # 已完成
    FAILED = "failed"                # 失败
    STOPPED = "stopped"              # 手动停止
```

### 3.6 ActionDecision - 动作决策

```python
@dataclass
class ActionDecision:
    """LLM 返回的动作决策"""
    action: str  # "execute" / "revise" / "stop" / "next"
    agent_id: Optional[str] = None
    reason: str = ""
    revised_plan: Optional[List[PlanStage]] = None  # 修正后的计划
```

---

## 4. 执行流程详解

### 4.1 Stage 1: 开始执行

```python
def start_execution(task: str):
    """开始动态执行循环"""
    
    # 1. 创建执行记录
    record = ExecutionRecord(
        record_id=str(uuid.uuid4())[:8],
        original_task=task,
        start_time=datetime.now().isoformat()
    )
    
    # 2. 设置循环状态
    loop_manager.set_state(LoopState.PLANNING)
    
    # 3. 询问 LLM: 用哪个 Agent 拆分计划
    available_agents = ["leader", "planner", "researcher"]
    prompt = decision_maker.generate_select_agent_prompt(
        task=task,
        agents=available_agents,
        history=""
    )
    
    # 4. 调用 LLM
    llm_response = harness.call_llm(prompt)
    
    # 5. 解析决策
    decision = decision_maker.parse_agent_selection(llm_response)
    record.decisions.append(LoopDecision(
        step=1,
        decision_type="select_agent",
        prompt=prompt,
        response=llm_response,
        agent_id=decision.agent_id,
        reason=decision.reason
    ))
    
    # 6. 记录到流程追踪
    flow_tracker.record_llm_decision(
        prompt, llm_response, "select_agent"
    )
```

### 4.2 Stage 2: 拆分计划

```python
def decompose_plan(record: ExecutionRecord):
    """让 Agent 拆分计划"""
    
    agent_id = record.decisions[-1].agent_id
    agent = harness.get_agent(agent_id)
    
    # 1. 构造消息 → Agent
    agent_input = f"""请为以下任务制定执行计划：

任务：{record.original_task}

请按以下格式输出计划：
```
阶段1: [阶段名称]
- Agent: [需要的 Agent 类型]
- 输入: [给 Agent 的具体输入]
- 预期输出: [期望结果]

阶段2: ...
```
"""
    
    # 2. 记录 Harness → Agent
    flow_tracker.record_harness_to_agent(agent_id, agent_input)
    
    # 3. 执行
    result = agent.execute(Task(description=agent_input))
    
    # 4. 记录 Agent → Harness
    flow_tracker.record_agent_to_harness(agent_id, result.result)
    
    # 5. 解析计划
    plan = parse_plan(result.result)
    record.plan = plan.stages
    record.plan_prompt = agent_input
    record.plan_response = result.result
    
    # 6. 设置状态
    loop_manager.set_state(LoopState.EXECUTING)
```

### 4.3 Stage 3: 执行循环

```python
def execution_loop(record: ExecutionRecord):
    """执行循环"""
    
    while record.status == "running":
        # 1. 获取当前阶段
        current_stage = get_current_stage(record)
        
        if current_stage is None:
            # 计划已完成，检查是否继续
            decision = ask_continue(record)
            if decision.action == "stop":
                break
            # 否则可能修正计划继续
        
        # 2. 询问 LLM: 下一步用什么 Agent
        prompt = decision_maker.generate_execute_next_prompt(
            plan=record.plan,
            context={
                "completed": get_completed_stages(record),
                "current": current_stage,
                "status": get_execution_status(record),
                "last_result": get_last_result(record)
            }
        )
        
        llm_response = harness.call_llm(prompt)
        
        # 3. 解析决策
        action_decision = decision_maker.parse_action_decision(llm_response)
        
        if action_decision.action == "execute":
            # 4. 执行 Agent
            agent = harness.get_agent(action_decision.agent_id)
            result = agent.execute(Task(
                description=current_stage.input_text
            ))
            
            # 5. 记录结果
            record.execution_steps.append(ExecutionStep(
                step_id=len(record.execution_steps) + 1,
                decision_type="execute",
                harness_prompt=prompt,
                llm_response=llm_response,
                selected_agent=action_decision.agent_id,
                action="execute",
                agent_id=action_decision.agent_id,
                agent_input=current_stage.input_text,
                agent_result=result.result,
                agent_status="completed"
            ))
            
            current_stage.status = "completed"
            current_stage.result = result.result
        
        elif action_decision.action == "revise":
            # 修正计划
            record.plan = action_decision.revised_plan
        
        elif action_decision.action == "stop":
            record.status = "completed"
            break
```

### 4.4 终止条件 (待讨论)

```
终止条件 (待实现):
- 用户手动停止
- 执行超时
- 达到最大循环次数
- 所有计划阶段完成
- LLM 返回 "stop"
- 执行失败
```

---

## 5. 提示词设计

### 5.1 选择 Agent 拆分计划

```
## Prompt: 选择 Agent 拆分计划

你是一个任务规划专家。请根据当前任务选择最适合拆分计划的 Agent。

### 当前任务
{task}

### 可用 Agent 列表
- leader: 领导 Agent，负责协调和任务分配
- planner: 计划 Agent，专门负责制定执行计划
- researcher: 研究员，负责分析和调研

### 选择标准
1. 任务复杂度
2. 任务类型 (代码/研究/写作/分析)
3. Agent 能力匹配

### 输出格式
请返回以下格式：
```
Agent: [agent_id]
原因: [不超过50字的说明]
```
```

### 5.2 选择 Agent 执行

```
## Prompt: 选择 Agent 执行下一步

你是一个任务执行协调专家。请决定下一步用什么 Agent 执行。

### 原始任务
{original_task}

### 执行计划
{plan_summary}

### 当前进度
- 已完成阶段: {completed_stages}
- 当前阶段: {current_stage}
- 剩余阶段: {remaining_stages}

### 上一步执行结果
{last_result}

### 选择标准
1. 当前阶段需要的 Agent 类型
2. Agent 可用状态
3. 执行上下文

### 输出格式
```
Agent: [agent_id]
原因: [不超过30字的说明]
```
```

### 5.3 下一步做什么

```
## Prompt: 下一步做什么

你是一个任务执行协调专家。请根据当前执行情况决定下一步。

### 执行计划
{plan_summary}

### 最近执行结果
{recent_result}

### 上下文
{context}

### 决策选项
- next: 继续执行下一个阶段
- revise: 修正当前计划
- stop: 停止执行

### 输出格式
```
动作: [next|revise|stop]
说明: [简短说明]
```
```

---

## 6. 前端展示

### 6.1 页面布局

```html
<div class="container">
    <!-- 头部统计 -->
    <div class="header">...</div>
    
    <!-- 执行进度 -->
    <div class="card" id="executionProgress">
        <div class="card-title">🔄 执行进度</div>
        <div class="progress-steps" id="progressSteps"></div>
    </div>
    
    <!-- 流程详情 -->
    <div class="card" id="flowDetails">
        <div class="card-title">📋 协作流程</div>
        <div class="flow-timeline" id="flowTimeline"></div>
    </div>
    
    <!-- 最终结果 -->
    <div class="card" id="finalResult">
        <div class="card-title">✅ 执行结果</div>
        <pre class="result-content" id="resultContent"></pre>
    </div>
</div>
```

### 6.2 流程时间线

```javascript
// 流程展示数据结构
{
    "execution": {
        "record_id": "abc123",
        "task": "写一个二叉排序树",
        "status": "completed",
        "duration": 12.5
    },
    
    // 完整流程
    "flow": [
        {
            "type": "harness_llm",
            "title": "询问 LLM: 选择计划 Agent",
            "prompt": "请选择合适的 Agent 拆分计划...",
            "response": "Agent: planner\n原因: 专门制定计划",
            "timestamp": "10:09:15"
        },
        {
            "type": "harness_agent",
            "title": "Harness → planner: 拆分计划",
            "agent": "planner",
            "input": "请为任务制定执行计划...",
            "result": "阶段1: 分析需求 → researcher\n阶段2: 编写代码 → coder\n阶段3: 优化文档 → writer",
            "timestamp": "10:09:16"
        },
        {
            "type": "harness_llm",
            "title": "询问 LLM: 执行第一阶段",
            "prompt": "请选择 Agent 执行第一阶段...",
            "response": "Agent: researcher\n原因: 分析需求",
            "timestamp": "10:09:18"
        },
        {
            "type": "harness_agent", 
            "title": "Harness → researcher: 分析需求",
            "agent": "researcher",
            "input": "分析用户需求：写一个二叉排序树",
            "result": "需求分析：需要实现插入、查找、删除、中序遍历",
            "timestamp": "10:09:20"
        },
        // ... 更多步骤
    ]
}
```

### 6.3 展示样式

```css
/* 流程步骤 */
.flow-step {
    margin: 12px 0;
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid #e2e8f0;
}

.flow-step-header {
    padding: 12px;
    background: linear-gradient(135deg, #f0f9ff, #e0f2fe);
    display: flex;
    align-items: center;
    gap: 10px;
}

.flow-step-type {
    padding: 4px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
}

.flow-step-type-harness-llm { background: #fef3c7; color: #92400e; }
.flow-step-type-harness-agent { background: #dbeafe; color: #1e40af; }
.flow-step-type-agent-harness { background: #d1fae5; color: #065f46; }

.flow-step-title {
    font-weight: 600;
    color: #1e293b;
}

.flow-step-time {
    margin-left: auto;
    font-size: 11px;
    color: #64748b;
}

.flow-step-body {
    padding: 12px;
    background: #fff;
}

.flow-step-section {
    margin-bottom: 10px;
}

.flow-step-section:last-child {
    margin-bottom: 0;
}

.flow-step-label {
    font-size: 11px;
    font-weight: 600;
    color: #64748b;
    margin-bottom: 4px;
    text-transform: uppercase;
}

.flow-step-content {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 10px;
    font-size: 12px;
    font-family: monospace;
    white-space: pre-wrap;
    max-height: 200px;
    overflow-y: auto;
}
```

---

## 7. API 接口

### 7.1 POST /execute

开始动态执行循环

```bash
curl -X POST http://localhost:8080/execute \
  -H "Content-Type: application/json" \
  -d '{"task": "写一个二叉排序树"}
```

```json
{
    "record_id": "abc12345",
    "status": "started",
    "original_task": "写一个二叉排序树",
    "start_time": "2026-04-08T10:09:15"
}
```

### 7.2 GET /execution/:id

获取执行状态和结果

```bash
curl http://localhost:8080/execution/abc12345
```

```json
{
    "record_id": "abc12345",
    "status": "completed",
    "original_task": "写一个二叉排序树",
    "duration": 12.5,
    "plan": [
        {"stage": 1, "name": "分析需求", "agent": "researcher", "status": "completed"},
        {"stage": 2, "name": "编写代码", "agent": "coder", "status": "completed"},
        {"stage": 3, "name": "优化文档", "agent": "writer", "status": "completed"}
    ],
    "steps": [
        // 完整步骤详情
    ],
    "final_result": "代码已完成..."
}
```

### 7.3 GET /execution/:id/flow

获取流程详情

```bash
curl http://localhost:8080/execution/abc12345/flow
```

```json
{
    "record_id": "abc12345",
    "flow": [
        {
            "type": "harness_llm",
            "title": "询问 LLM: 选择计划 Agent",
            "prompt": "...",
            "response": "Agent: planner",
            "timestamp": "10:09:15"
        },
        {
            "type": "harness_agent",
            "title": "Harness → planner",
            "agent": "planner",
            "input": "...",
            "result": "...",
            "timestamp": "10:09:16"
        }
        // ...
    ]
}
```

### 7.4 GET /executions

列出所有执行记录

```bash
curl http://localhost:8080/executions
```

```json
{
    "executions": [
        {
            "record_id": "abc12345",
            "task": "写一个二叉排序树",
            "status": "completed",
            "start_time": "10:09:15",
            "duration": 12.5
        }
    ]
}
```

---

## 8. 日志格式

### 8.1 控制台日志

```
[10:09:15] ═══════════════════════════════════════════════════
[10:09:15] 🔄 开始执行循环: 写一个二叉排序树
[10:09:15]
[10:09:15] 📋 Step 1: 询问 LLM 选择计划 Agent
[10:09:15]    Prompt: 请选择合适的 Agent 拆分计划...
[10:09:15]    Response: Agent: planner
[10:09:15]
[10:09:16] 📋 Step 2: Harness → planner 拆分计划
[10:09:16]    Input: 请为任务制定执行计划...
[10:09:16]    Result: 阶段1: 分析需求 → researcher
[10:09:16]           阶段2: 编写代码 → coder
[10:09:16]           阶段3: 优化文档 → writer
[10:09:16]
[10:09:18] 📋 Step 3: 询问 LLM 选择执行 Agent (阶段1)
[10:09:18]    Prompt: 请选择 Agent 执行第一阶段...
[10:09:18]    Response: Agent: researcher
[10:09:18]
[10:09:20] 📋 Step 4: Harness → researcher 执行
[10:09:20]    Input: 分析用户需求：写一个二叉排序树
[10:09:20]    Result: 需求分析文档...
[10:09:20]
[10:09:22] 📋 Step 5: 询问 LLM 下一步做什么
[10:09:22]    Prompt: 下一步做什么？
[10:09:22]    Response: 动作: next
[10:09:22]
[10:09:25] 📋 Step 6: Harness → coder 执行
[10:09:25]    Input: 编写代码...
[10:09:25]    Result: Java 代码实现...
[10:09:25]
[10:09:28] 📋 Step 7: 询问 LLM 下一步做什么
[10:09:28]    Prompt: 下一步做什么？
[10:09:28]    Response: 动作: stop
[10:09:28]
[10:09:28] ✅ 执行完成 (12.5s)
[10:09:28] ═══════════════════════════════════════════════════
```

### 8.2 文件日志

日志保存位置: `logs/execution_{date}.json`

```json
{
    "record_id": "abc12345",
    "original_task": "写一个二叉排序树",
    "start_time": "2026-04-08T10:09:15",
    "end_time": "2026-04-08T10:09:28",
    "duration": 12.5,
    "status": "completed",
    "plan": [...],
    "flow": [
        {
            "step": 1,
            "type": "harness_llm",
            "title": "询问 LLM: 选择计划 Agent",
            "prompt": "...",
            "response": "..."
        },
        {
            "step": 2,
            "type": "harness_agent",
            "title": "Harness → planner",
            "agent": "planner",
            "input": "...",
            "result": "..."
        }
        // ...
    ],
    "final_result": "..."
}
```

---

## 9. 文件结构

```
openclaw_harness/
├── src/
│   ├── harness.py           # 现有 harness
│   ├── web_server.py       # 现有 web 服务器
│   ├── execution_loop.py  # ✨ 新增: 动态执行循环
│   ├── loop_manager.py  # ✨ 新增: 循环管理器
│   ├── decision_maker.py # ✨ 新增: LLM 决策器
│   └── flow_tracker.py # ✨ 新增: 流程追踪器
├── config/
│   ├── agents.yaml
│   └── prompts/
│       ├── select_agent.txt    # 选择 Agent 的 prompt
│       ├── execute_next.txt   # 下一步执行的 prompt
│       └── continue.txt     # 继续/停止的 prompt
├── logs/
│   └── execution_2026-04-08.json
└── docs/
    └── TECH.md
```

---

## 10. 待讨论事项

### 10.1 终止条件

需要确定在什么条件下循环终止:

1. **完成所有计划** - 计划的所有阶段都执行完成
2. **手动停止** - 用户主动停止
3. **执行失败** - Agent 执行出错
4. **超时** - 达到最大执行时间
5. **循环上限** - 达到最大循环次数
6. **LLM 决策** - LLM 返回 "stop"

### 10.2 错误处理

- LLM 调用失败怎么办？
- Agent 执行超时怎么办？
- 计划解析失败怎么办？

### 10.3 持久化

- 执行记录是否需要持久化？
- 断线重连如何处理？

---

## 11. 实现优先级

### P0 - 核心功能

1. `DecisionMaker` - LLM 决策器
2. `LoopManager` - 循环管理器
3. `FlowTracker` - 流程追踪
4. 执行循环主逻辑

### P1 - 集成

5. Web API 接口
6. 前端展示
7. 日志记录

### P2 - 优化

8. 错误处理
9. 持久化
10. 监控

---

_Document Version: 4.0_
_Last Updated: 2026-04-08_