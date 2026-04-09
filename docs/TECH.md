# OpenClaw Multi-Agent Harness 技术设计文档

## 1. 系统架构

### 1.1 整体架构

```
 ┌──────────────────────────────────────────────────────┐
 │                   Web 客户端                        │
 │              (浏览器 + HTTP)                         │
 └────────────────────┬───────────────────────────────┘
                      │ HTTP
 ┌────────────────────▼───────────────────────────────┐
 │             web_server.py                     │
 │  ┌─────────────────────────────────────┐   │
 │  │    RequestHandler (HTTP 处理)        │   │
 │  │  - GET /, /status, /agents,        │   │
 │  │        /logs, /collab             │   │
 │  │  - POST /run                    │   │
 │  └─────────────────────────────────────┘   │
 └────────────────────┬───────────────────────────────┘
                      │
 ┌────────────────────▼───────────────────────────────┐
 │             harness.py                     │
 │  ┌─────────────────────────────────────┐   │
 │  │   OpenClawHarness (核心调度器)         │   │
 │  │  - Agent 管理                      │   │
 │  │  - 任务分配                       │   │
 │  │  - 状态同步                      │   │
 │  └─────────────────────────────────────┘   │
 │                    │                        │
 │  ┌──────────────▼──────────────────┐   │
 │  │   BaseAgent (6个 Agent)          │   │
 │  │  - leader    - coder           │   │
 │  │  - researcher - writer         │   │
 │  │  - analyst  - general         │   │
 │  └──────────────────────────────┘   │
 └────────────────────┬───────────────────────────────┘
                      │ LLM API
 ┌────────────────────▼───────────────────────────────┐
 │                  LLM                         │
 │           (千问 / OpenAI)                    │
 └───────────────────────────────────────────┘
```

---

## 2. 核心模块

### 2.1 OpenClawHarness

**位置**: `src/harness.py`

```python
class OpenClawHarness:
    def __init__(self, config_path="config/agents.yaml"):
        self.agents: Dict[str, BaseAgent] = {}
        self.agent_configs = self._load_agent_configs()
        self._init_default_agents()
    
    def execute_task(self, task: str, agent_config: str = "auto") -> TaskResult:
        """执行任务"""
        
    def get_system_status(self) -> Dict:
        """获取系统状态"""
```

**职责**:
- 加载和管理 Agent
- 任务分发
- 状态聚合

### 2.2 BaseAgent

**位置**: `src/harness.py`

```python
class BaseAgent:
    def __init__(self, agent_id: str, role: AgentRole, prompt_file: Optional[Path]):
        self.agent_id = agent_id
        self.role = role
        self.state = AgentState(...)
        self.system_prompt = self._load_prompt(...)
        self.logs: List[str] = []
    
    def execute(self, task: str, context: Optional[Dict] = None) -> TaskResult:
        """执行任务"""
    
    def _call_qwen(self, task: str) -> str:
        """调用千问 API"""
    
    def _execute_mock(self, task: str) -> str:
        """模拟响应"""
```

**职责**:
- 加载 Agent prompt
- 调用 LLM API
- 记录执行日志

### 2.3 RequestHandler

**位置**: `src/web_server.py`

```python
class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # /         → HTML 页面
        # /status   → 系统状态
        # /agents  → Agent 列表
        # /logs    → 请求日志
        # /collab  → 协作日志
    
    def do_POST(self):
        # /run     → 执行任务
```

---

## 3. 数据结构

### 3.1 TaskStatus

```python
class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
```

### 3.2 AgentRole

```python
class AgentRole(Enum):
    LEADER = "leader"        # 任务分配
    CODER = "coder"         # 代码编写
    RESEARCHER = "researcher"  # 研究调研
    WRITER = "writer"       # 内容撰写
    ANALYST = "analyst"      # 数据分析
    GENERAL = "general"     # 通用任务
```

### 3.3 Task

```python
@dataclass
class Task:
    task_id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    assigned_to: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[str] = None
    tokens_used: int = 0
```

### 3.4 AgentState

```python
@dataclass
class AgentState:
    agent_id: str
    role: str
    status: str = "idle"  # idle/running/waiting
    current_task: Optional[str] = None
    tools_used: List[str] = field(default_factory=list)
    tokens_used: int = 0
    tasks_completed: int = 0
```

### 3.5 TaskResult

```python
@dataclass
class TaskResult:
    task_id: str
    status: str
    result: Optional[str] = None
    duration: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    agent_used: str = ""
    tools_used: List[str] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)
```

---

## 4. API 接口

### 4.1 GET /status

```bash
curl http://localhost:8080/status
```

```json
{
  "status": "running",
  "agents": 6,
  "active": 0,
  "running": 0,
  "tokens": 2257
}
```

### 4.2 GET /agents

```bash
curl http://localhost:8080/agents
```

```json
{
  "agents": [
    {"id": "leader", "role": "leader", "status": "idle"},
    {"id": "coder", "role": "coder", "status": "idle"},
    ...
  ]
}
```

### 4.3 POST /run

```bash
curl -X POST http://localhost:8080/run \
  -H "Content-Type: application/json" \
  -d '{"task":"写一个排序算法","agent":"coder"}'
```

```json
{
  "request_id": "aacc6fff",
  "status": "completed",
  "result": "好的，我来编写...",
  "agent": "coder",
  "duration": 1.86,
  "tokens": 93
}
```

### 4.4 GET /logs

```bash
curl http://localhost:8080/logs
```

```json
{
  "logs": [
    {
      "id": "5873b239",
      "task": "测试",
      "agent": "coder",
      "status": "completed",
      "start_time": "09:22:35",
      "tokens": 89
    }
  ]
}
```

### 4.5 GET /collab

```bash
curl http://localhost:8080/collab
```

```json
{
  "logs": [
    {
      "time": "09:22:35",
      "agent": "coder",
      "action": "start",
      "detail": "测试"
    }
  ]
}
```

---

## 5. 前端架构

### 5.1 HTML 结构

```html
<body>
  <div class="container">
    <div class="header">...</div>
    <div class="stats">...</div>
    <div class="card" id="agentList">...</div>
    <div class="card" id="taskForm">...</div>
    <div class="card" id="result">...</div>
    <div class="card" id="collabList">...</div>
    <div class="card" id="logList">...</div>
  </div>
</body>
```

### 5.2 JavaScript 模块

```javascript
(function() {
    // DOM 元素
    const $ = (id) => document.getElementById(id);
    
    // API 函数
    async function api(endpoint, options) {...}
    async function executeTask(task, agent) {...}
    async function fetchStatus() {...}
    async function fetchAgents() {...}
    async function fetchLogs() {...}
    async function fetchCollab() {...}
    
    // 渲染函数
    function renderStatus(data) {...}
    function renderAgents(data) {...}
    function renderLogs(data) {...}
    function renderCollab(data) {...}
    function renderResult(data) {...}
    
    // 刷新
    async function refresh() {...}
    
    // 提交
    async function handleSubmit(e) {...}
    
    init();
})();
```

---

## 6. 日志系统

### 6.1 日志切片

```python
LOG_SLICE = 5  # 5分钟

def get_log_slice():
    minute = (now.minute // LOG_SLICE) * LOG_SLICE
    return now.strftime(f"%Y%m%d_%H-{minute:02d}")
```

### 6.2 日志格式

```json
{
  "requests": [...],
  "collab": [...]
}
```

### 6.3 文件名

```
logs/harness_20260405_09-00.json
logs/harness_20260405_09-05.json
logs/harness_20260405_09-10.json
```

---

## 7. LLM 集成

### 7.1 千问 API

```python
def _call_qwen(self, task: str) -> str:
    request_data = {
        "model": model,
        "input": {
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": task}
            ]
        }
    }
    
    endpoint = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(request_data).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}"}
    )
```

### 7.2 添加文件操作指令

```python
enhanced_task = task + """
重要：你是一个可以执行代码的Agent。
如果你需要创建文件或目录，请直接用Python代码写入文件。
"""
```

---

## 8. 配置加载

### 8.1 LLM 配置

```yaml
# config/llm.yaml
qwen:
  api_key: "sk-xxx"
  model: "qwen-turbo"
system:
  provider: "qwen"
```

### 8.2 Agent 配置

```yaml
# config/agents.yaml
leader:
  role: "leader"
  prompt: "config/prompts/leader.txt"
coder:
  role: "coder"
  prompt: "config/prompts/coder.txt"
```

---

## 9. 错误处理

### 9.1 服务端错误

```python
try:
    result = _harness.execute_task(task, agent)
except Exception as e:
    self.send_json({"error": str(e)})
```

### 9.2 客户端错误

```javascript
try {
    const data = await executeTask(task, agent);
    renderResult(data);
} catch (e) {
    result.className = 'result result-error';
    result.textContent = '❌ 网络错误: ' + e.message;
}
```

---

## 10. 文件操作

### 10.1 Agent 文件创建能力

Agent 的 system prompt 添加：

```
你可以执行以下操作：
1. 创建目录: os.makedirs('目录路径', exist_ok=True)
2. 写入文件: Path('文件').write_text('内容')
3. 列出文件: list(Path('目录').iterdir())
```

### 10.2 执行结果

Agent 执行后返回实际执行的代码和结果，而不仅仅是代码示例。

---

## 11. 部署

### 11.1 启动

```bash
cd src
python3 web_server.py -p 8080
```

### 11.2 访问

```
http://localhost:8080
http://192.168.31.177:8080
```

---

## 12. 测试

### 12.1 API 测试

```bash
# 状态
curl http://localhost:8080/status

# Agent
curl http://localhost:8080/agents

# 执行任务
curl -X POST http://localhost:8080/run \
  -H "Content-Type: application/json" \
  -d '{"task":"你好","agent":"general"}'
```

---

## 13. 待改进

- [ ] 任务队列
- [ ] Agent 动态创建/销毁
- [ ] 更丰富的协作策略
- [ ] OpenAI/Anthropic 支持
- [ ] Webhook 回调
- [ ] Docker 部署