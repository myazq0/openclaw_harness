# OpenClaw Multi-Agent Harness v3.0

多 Agent 协作与任务协调框架

## 新特性 (v3.0)

- ✅ **任务队列** - 优先级队列，支持 priority 管理
- ✅ **依赖管理** - 任务依赖关系，Task.dependencies
- ✅ **消息总线** - Agent 间事件订阅/发布
- ✅ **状态机** - 完整任务生命周期
- ✅ **重试机制** - Task.max_retries

## 快速开始

```bash
cd ~/.openclaw/workspace/openclaw_harness/src
python3 web_server.py -p 8080
# 浏览器打开: http://localhost:8080
```

## CLI 用法

```bash
# 执行任务
python3 -m src run "任务描述"

# 指定 Agent
python3 -m src run "任务" -a coder

# 链式执行
python3 -m src run "任务" -c
```

## 架构

```
/
├── src/
│   ├── harness.py      # 核心引擎 v3.0
│   └── web_server.py # HTTP 服务器
├── config/
│   ├── agents.yaml  # Agent 配置
│   ├── llm.yaml  # LLM 配置
│   └── prompts/   # Agent prompts
├── logs/         # 日志
└── docs/         # 文档
```

## Agent 类型

| Agent | 角色 | 说明 |
|-------|------|------|
| leader | 领导 | 任务分配和协调 |
| coder | 程序员 | 编写代码 |
| researcher | 研究员 | 调研和分析 |
| writer | 写作者 | 撰写内容 |
| analyst | 分析师 | 数据分析 |
| general | 通用 | 基础助手 |

## API

| 端点 | 方法 | 说明 |
|------|------|------|
| / | GET | 页面 |
| /status | GET | 系统状态 |
| /tasks | GET | 任务队列 |
| /agents | GET | Agent 列表 |
| /logs | GET | 请求日志 |
| /messages | GET | 消息总线 |
| /run | POST | 执行任务 |

## 任务队列

```python
from harness import OpenClawHarness, TaskPriority, Task, TaskStatus

harness = OpenClawHarness()

# 提交任务（自动进入队列）
task_id = harness.submit_task(
    description="编写排序算法",
    agent_id="coder",
    priority=TaskPriority.HIGH,
    dependencies=["task_001"],  # 依赖其他任务
    timeout=300.0
)

# 同步执行
result = harness.execute_task_sync(task_id)
```

## 消息总线

```python
# 订阅事件
harness.message_bus.subscribe("task_completed", lambda data: print(f"完成: {data['task_id']}"))

# 发布事件
harness.message_bus.publish("task_submitted", {"task_id": "xxx"})
```

## 依赖管理

```python
# 创建依赖任务
task1_id = harness.submit_task("分析需求", "researcher")
task2_id = harness.submit_task("编写代码", "coder", dependencies=[task1_id])
```

## 配置

修改 `config/llm.yaml`:

```yaml
qwen:
  api_key: "your-api-key"
  model: "qwen-turbo"
system:
  provider: "qwen"
```

## 日志

日志保存在 `logs/harness_YYYYMMDD_HH-MM.json`

```json
{
  "requests": [...],
  "messages": [...]
}
```

## 技术栈

- Python 3.11+
- 内置 HTTP Server
- 千问 API (阿里云)

## License

MIT