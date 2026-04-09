#!/usr/bin/env python3
"""
OpenClaw Harness - 核心协调器 v3.0
负责 Agent 管理、任务分配、消息路由、任务队列

作者: OpenClaw
日期: 2024-2026

版本: 3.1 - 新增执行追踪 (Execution Trace)
"""

import json
import threading
import logging
import time
import uuid
import queue
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
from abc import ABC, abstractmethod
import heapq


# ========== 枚举定义 ==========

class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"      # 待执行
    WAITING = "waiting"      # 等待依赖
    RUNNING = "running"      # 执行中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"       # 失败
    CANCELLED = "cancelled"  # 已取消


class TaskPriority(Enum):
    """任务优先级"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


class AgentRole(Enum):
    """Agent 角色"""
    LEADER = "leader"        # 领导 Agent，负责任务分配
    CODER = "coder"         # 程序员
    RESEARCHER = "researcher"  # 研究员
    WRITER = "writer"       # 写作者
    ANALYST = "analyst"      # 分析师
    GENERAL = "general"     # 通用助手


# ========== 执行追踪器 (v3.1 新增) ==========

class ExecutionTracer:
    """
    执行追踪器 - 记录 Harness 与 Agent 之间的每次交互
    用于在 Web 界面上实时展示执行过程
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._traces: List[Dict] = []
        self._lock = threading.Lock()
        self._current_session: str = ""
    
    def start_session(self, session_id: str, task: str):
        """开始新的追踪会话"""
        with self._lock:
            self._current_session = session_id
            self._traces.append({
                "session_id": session_id,
                "task": task,
                "start_time": datetime.now().strftime("%H:%M:%S"),
                "steps": []
            })
    
    def add_step(self, step: Dict):
        """
        添加执行步骤
        
        step 包含:
        - step_index: 步骤序号
        - caller: 调用者 (Harness / Agent名)
        - callee: 被调用者 (Agent名)
        - action: 动作 (plan/execute/chain/call_llm...)
        - prompt: 发送给 LLM 的完整 prompt
        - response: LLM 返回结果
        - config: 配置信息 (model, max_tokens 等)
        - duration: 耗时(秒)
        - timestamp: 时间戳
        """
        with self._lock:
            if self._traces and self._traces[-1].get("session_id") == self._current_session:
                self._traces[-1]["steps"].append(step)
    
    def get_session_traces(self, session_id: str = "") -> List[Dict]:
        """获取指定会话的追踪记录"""
        with self._lock:
            if session_id:
                return [t for t in self._traces if t.get("session_id") == session_id]
            return self._traces
    
    def get_all_sessions(self) -> List[str]:
        """获取所有会话ID"""
        with self._lock:
            return list(set(t.get("session_id", "") for t in self._traces))
    
    def clear(self, session_id: str = ""):
        """清除追踪记录"""
        with self._lock:
            if session_id:
                self._traces = [t for t in self._traces if t.get("session_id") != session_id]
            else:
                self._traces = []


# 全局追踪器实例
tracer = ExecutionTracer()


# ========== 数据结构 ==========

@dataclass
class Task:
    """任务"""
    task_id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    assigned_to: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)  # 依赖的任务 ID
    dependents: List[str] = field(default_factory=list)    # 依赖此任务的任务
    retries: int = 0
    max_retries: int = 3
    timeout: float = 300.0  # 超时时间（秒）
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    tokens_used: int = 0
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        data = asdict(self)
        data['status'] = self.status.value
        data['priority'] = self.priority.value
        return data
    
    def is_ready(self) -> bool:
        """检查是否满足执行条件"""
        return self.status in (TaskStatus.PENDING, TaskStatus.WAITING)


@dataclass
class AgentState:
    """Agent 状态"""
    agent_id: str
    role: str
    status: str = "idle"  # idle/running/waiting/disabled
    current_task: Optional[str] = None
    tools_used: List[str] = field(default_factory=list)
    tokens_used: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    last_active: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class TaskResult:
    """任务执行结果"""
    task_id: str
    status: str
    result: Optional[str] = None
    error: Optional[str] = None
    duration: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    agent_used: str = ""
    tools_used: List[str] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)
    # 新增：协作流程追踪
    steps: List[Dict[str, Any]] = field(default_factory=list)  # 每步详情


# ========== 任务队列 ==========

class TaskQueue:
    """优先级任务队列"""
    
    def __init__(self):
        self._heap: List[tuple] = []  # (priority, timestamp, task_id, task)
        self._tasks: Dict[str, Task] = {}
        self._lock = threading.Lock()
        self._counter = 0
    
    def enqueue(self, task: Task) -> str:
        """添加任务到队列"""
        with self._lock:
            self._counter += 1
            # heapq 是最小堆，优先级数值越小越先出队
            # 所以用负数让高优先级先出队
            priority = -task.priority.value
            timestamp = self._counter
            heapq.heappush(self._heap, (priority, timestamp, task.task_id, task))
            self._tasks[task.task_id] = task
        return task.task_id
    
    def dequeue(self) -> Optional[Task]:
        """取出最高优先级的任务"""
        with self._lock:
            if not self._heap:
                return None
            _, _, _, task = heapq.heappop(self._heap)
            return task
    
    def get(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        return self._tasks.get(task_id)
    
    def update(self, task: Task):
        """更新任务"""
        with self._lock:
            if task.task_id in self._tasks:
                self._tasks[task.task_id] = task
    
    def remove(self, task_id: str) -> bool:
        """删除任务"""
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                return True
            return False
    
    def list_all(self) -> List[Task]:
        """列出所有任务"""
        with self._lock:
            return list(self._tasks.values())
    
    def list_by_status(self, status: TaskStatus) -> List[Task]:
        """按状态列出任务"""
        with self._lock:
            return [t for t in self._tasks.values() if t.status == status]
    
    def size(self) -> int:
        """队列大小"""
        with self._lock:
            return len(self._tasks)


# ========== 消息总线 ==========

class MessageBus:
    """Agent 间消息总线"""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()
        self._message_queue: queue.Queue = queue.Queue()
        self._running = False
        self._thread: Optional[threading.Thread] = None
    
    def subscribe(self, event_type: str, callback: Callable):
        """订阅事件"""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)
    
    def unsubscribe(self, event_type: str, callback: Callable):
        """取消订阅"""
        with self._lock:
            if event_type in self._subscribers:
                self._subscribers[event_type].remove(callback)
    
    def publish(self, event_type: str, data: Dict[str, Any]):
        """发布事件"""
        # 先同步处理
        with self._lock:
            callbacks = self._subscribers.get(event_type, []).copy()
        
        for cb in callbacks:
            try:
                cb(data)
            except Exception as e:
                logging.error(f"MessageBus callback error: {e}")
        
        # 再异步放入队列（用于日志等）
        self._message_queue.put({
            "type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        })
    
    def get_recent_messages(self, limit: int = 100) -> List[Dict]:
        """获取 recent messages"""
        messages = []
        while not self._message_queue.empty():
            try:
                messages.append(self._message_queue.get_nowait())
            except queue.Empty:
                break
        return messages[-limit:]


# ========== Agent 实现 ==========

class BaseAgent(ABC):
    """Agent 基类"""
    
    def __init__(self, agent_id: str, role: AgentRole, prompt_file: Optional[Path] = None):
        self.agent_id = agent_id
        self.role = role
        self.state = AgentState(agent_id=agent_id, role=role.value)
        self.system_prompt = self._load_prompt(role, prompt_file)
        self.logger = logging.getLogger(f"agent.{agent_id}")
        self.logs: List[str] = []
        self._lock = threading.Lock()
    
    def _load_prompt(self, role: AgentRole, prompt_file: Optional[Path]) -> str:
        """加载 prompt"""
        if prompt_file and prompt_file.exists():
            return prompt_file.read_text()
        
        prompts = {
            AgentRole.LEADER: """你是一个领导 Agent，负责协调其他 Agent 完成复杂任务。
你的职责：
1. 分析任务需求，决定需要哪些 Agent
2. 将任务分解为子任务
3. 分配任务给合适的 Agent
4. 汇总结果，返回给用户

你必须用中文回复。""",
            
            AgentRole.CODER: """你是一个专业程序员，负责编写代码。
你的职责：
1. 理解需求，编写代码
2. 使用合适的工具和库
3. 确保代码可运行
4. 提供完整的解决方案

你必须用中文回复。""",
            
            AgentRole.RESEARCHER: """你是一个研究员，负责研究和分析。
你的职责：
1. 收集相关信息
2. 分析和整理数据
3. 提供有价值的见解

你必须用中文回复。""",
            
            AgentRole.WRITER: """你是一个写作者，负责撰写内容。
你的职责：
1. 根据需求撰写文章
2. 用清晰、有吸引力的语言
3. 确保内容有逻辑、有价值

你必须用中文回复。""",
            
            AgentRole.ANALYST: """你是一个分析师，负责数据分析。
你的职责：
1. 分析数据，找出规律
2. 提供专业的分析报告
3. 给出建议

你必须用中文回复。""",
            
            AgentRole.GENERAL: """你是一个通用助手，负责回答问题。
你的职责：
1. 理解用户需求
2. 提供有用的帮助
3. 清晰表达

你必须用中文回复。""",
        }
        
        return prompts.get(role, prompts[AgentRole.GENERAL])
    
    def log(self, message: str):
        """记录日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {self.agent_id}: {message}"
        self.logger.info(log_msg)
        with self._lock:
            self.logs.append(log_msg)
    
    @abstractmethod
    def execute(self, task: Task) -> TaskResult:
        """执行任务 - 子类必须实现"""
        pass
    
    def get_logs(self) -> List[str]:
        """获取日志"""
        with self._lock:
            return self.logs.copy()


class LLMAgent(BaseAgent):
    """LLM Agent - 调用大语言模型"""
    
    def __init__(self, agent_id: str, role: AgentRole, prompt_file: Optional[Path] = None):
        super().__init__(agent_id, role, prompt_file)
        self._config = self._load_llm_config()
    
    def _load_llm_config(self) -> Dict:
        """加载 LLM 配置 - 支持 yaml 和手动解析"""
        config_paths = [
            Path(__file__).parent.parent / "config" / "llm.yaml",
            Path(__file__).parent / "config" / "llm.yaml",
            Path("../config/llm.yaml"),
            Path("config/llm.yaml"),
        ]
        
        for config_file in config_paths:
            if config_file.exists():
                # 尝试 yaml
                try:
                    import yaml
                    with open(config_file, encoding='utf-8') as f:
                        return yaml.safe_load(f) or {}
                except ImportError:
                    # 手动解析
                    with open(config_file, encoding='utf-8') as f:
                        content = f.read()
                    
                    import re
                    api_key_match = re.search(r'api_key:\s*"([^"]+)"', content)
                    provider_match = re.search(r'provider:\s*"([^"]+)"', content)
                    model_match = re.search(r'model:\s*"([^"]+)"', content)
                    
                    qwen_config = {}
                    if api_key_match:
                        qwen_config['api_key'] = api_key_match.group(1)
                    if model_match:
                        qwen_config['model'] = model_match.group(1)
                    
                    return {
                        'qwen': qwen_config,
                        'system': {'provider': provider_match.group(1) if provider_match else 'mock'}
                    }
        
        return {"system": {"provider": "mock"}}
    
    def execute(self, task: Task) -> TaskResult:
        """执行任务"""
        start_time = time.time()
        
        self.state.status = "running"
        self.state.current_task = task.task_id
        self.log(f"🔵 开始执行: {task.description[:50]}...")
        
        # 调用 LLM
        result_text = self._call_llm(task.description)
        
        duration = time.time() - start_time
        self.state.status = "idle"
        self.state.current_task = None
        self.state.tasks_completed += 1
        self.state.last_active = datetime.now().isoformat()
        
        self.log(f"✅ 完成，耗时 {duration:.2f}s")
        
        return TaskResult(
            task_id=task.task_id,
            status="completed",
            result=result_text,
            duration=duration,
            input_tokens=len(task.description) // 4,
            output_tokens=len(result_text) // 4,
            agent_used=self.agent_id,
            tools_used=self.state.tools_used.copy(),
            logs=self.logs.copy()
        )
    
    def _call_llm(self, prompt: str) -> str:
        """
        调用 LLM
        v3.1: 添加执行追踪
        """
        start_time = time.time()
        provider = self._config.get("system", {}).get("provider", "mock")
        
        # 构建 LLM 配置信息（用于追踪显示）
        llm_config = {
            "provider": provider,
            "model": self._config.get(provider, {}).get("model", "mock"),
            "max_tokens": self._config.get(provider, {}).get("max_tokens", 2000),
            "temperature": self._config.get(provider, {}).get("temperature", 0.7),
        }
        
        # 记录发送的 prompt（完整上下文）
        send_prompt = prompt
        if self.system_prompt:
            send_prompt = f"[System]\n{self.system_prompt}\n\n[User]\n{prompt}"
        
        # 调用 LLM
        if provider == "qwen":
            response = self._call_qwen(prompt)
        elif provider == "openai":
            response = self._call_openai(prompt)
        elif provider == "anthropic":
            response = self._call_anthropic(prompt)
        else:
            response = self._execute_mock(prompt)
        
        # 记录执行步骤
        duration = time.time() - start_time
        tracer.add_step({
            "step_index": len(tracer.get_session_traces(tracer._current_session)) + 1 if tracer._current_session else 1,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "caller": "Harness",
            "callee": self.agent_id,
            "agent_role": self.role.value,
            "action": "call_llm",
            "prompt": send_prompt[:2000],  # 截断过长 prompt
            "prompt_tokens": len(send_prompt),
            "response": response[:2000],
            "response_tokens": len(response),
            "llm_config": llm_config,
            "duration": round(duration, 2),
            "status": "success" if response else "empty"
        })
        
        return response
    
    def _execute_mock(self, task: str) -> str:
        """模拟响应"""
        responses = {
            AgentRole.LEADER: f"【{self.role.value}】我来分析这个任务并分配给合适的 Agent。",
            AgentRole.CODER: f"【{self.role.value}】正在编写代码解决: {task[:30]}...",
            AgentRole.RESEARCHER: f"【{self.role.value}】正在研究: {task[:30]}...",
            AgentRole.WRITER: f"【{self.role.value}】正在撰写: {task[:30]}...",
            AgentRole.ANALYST: f"【{self.role.value}】正在分析: {task[:30]}...",
            AgentRole.GENERAL: f"【{self.role.value}】好的，我来帮你: {task[:30]}...",
        }
        return responses.get(self.role, responses[AgentRole.GENERAL])
    
    def _call_qwen(self, task: str) -> str:
        """调用千问 API"""
        import urllib.request
        import urllib.parse
        import json
        import ssl
        
        qwen_config = self._config.get("qwen", {})
        api_key = qwen_config.get("api_key", "")
        model = qwen_config.get("model", "qwen-turbo")
        
        if not api_key or api_key == "your-api-key-here":
            return self._execute_mock(task)
        
        request_data = {
            "model": model,
            "input": {
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": task},
                ]
            },
            "parameters": {"result_format": "message"}
        }
        
        endpoint = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
        
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(request_data).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-DashScope-Async": "disable"
            },
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            
            if "output" in result and "choices" in result["output"]:
                return result["output"]["choices"][0]["message"]["content"]
            
            return json.dumps(result, ensure_ascii=False)
        
        except Exception as e:
            return f"❌ API 错误: {str(e)}"
    
    def _call_openai(self, prompt: str) -> str:
        """调用 OpenAI API - TODO"""
        return self._execute_mock(prompt)
    
    def _call_anthropic(self, prompt: str) -> str:
        """调用 Anthropic API - TODO"""
        return self._execute_mock(prompt)


class DynamicAgent(LLMAgent):
    """动态 Agent - 可被 Leader 创建/销毁"""
    
    def __init__(self, agent_id: str, role: AgentRole, parent_id: str, prompt_file: Optional[Path] = None):
        super().__init__(agent_id, role, prompt_file)
        self.parent_id = parent_id
        self.created_at = datetime.now().isoformat()
        self.is_dynamic = True


# ========== 任务调度器 ==========

class TaskScheduler:
    """任务调度器 - 管理任务队列和依赖"""
    
    def __init__(self, message_bus: Optional[MessageBus] = None):
        self.queue = TaskQueue()
        self.message_bus = message_bus or MessageBus()
        self._lock = threading.Lock()
        self._workers: Dict[str, threading.Thread] = {}
        self._running = False
    
    def submit(self, task: Task) -> str:
        """提交任务"""
        # 检查依赖
        self._check_dependencies(task)
        
        task_id = self.queue.enqueue(task)
        self.message_bus.publish("task_submitted", {"task": task.to_dict()})
        return task_id
    
    def _check_dependencies(self, task: Task):
        """检查并更新依赖状态"""
        if task.dependencies:
            for dep_id in task.dependencies:
                dep_task = self.queue.get(dep_id)
                if dep_task and dep_task.status != TaskStatus.COMPLETED:
                    task.status = TaskStatus.WAITING
                    break
    
    def schedule_next(self) -> Optional[Task]:
        """调度下一个可执行的任务"""
        task = self.queue.dequeue()
        
        if task and task.status == TaskStatus.WAITING:
            # 重新检查依赖
            self._check_dependencies(task)
            if task.status == TaskStatus.WAITING:
                # 仍需等待，放回队列
                self.queue.enqueue(task)
                return None
        
        return task
    
    def mark_completed(self, task_id: str, result: TaskResult):
        """标记任务完成"""
        task = self.queue.get(task_id)
        if task:
            task.status = TaskStatus.COMPLETED if result.status == "completed" else TaskStatus.FAILED
            task.result = result.result
            task.completed_at = datetime.now().isoformat()
            self.queue.update(task)
            
            # 通知依赖此任务的任务
            for dependent_id in task.dependents:
                dependent = self.queue.get(dependent_id)
                if dependent and dependent.status == TaskStatus.WAITING:
                    dependent.status = TaskStatus.PENDING
                    self.queue.update(dependent)
            
            self.message_bus.publish("task_completed", {"task_id": task_id, "result": asdict(result)})
    
    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """获取任务状态"""
        task = self.queue.get(task_id)
        return task.to_dict() if task else None
    
    def list_tasks(self, status: Optional[TaskStatus] = None) -> List[Dict]:
        """列出任务"""
        if status:
            return [t.to_dict() for t in self.queue.list_by_status(status)]
        return [t.to_dict() for t in self.queue.list_all()]


# ========== OpenClaw Harness ==========

class OpenClawHarness:
    """OpenClaw Harness - 核心协调器 v3.0"""
    
    def __init__(self, config_path: str = "config/agents.yaml", verbose: bool = False):
        self.config_path = Path(config_path)
        self.verbose = verbose
        self.logger = logging.getLogger("harness")
        
        # 组件
        self.message_bus = MessageBus()
        self.scheduler = TaskScheduler(self.message_bus)
        
        # Agent 管理
        self.agents: Dict[str, BaseAgent] = {}
        self.agent_configs = self._load_agent_configs()
        
        # 初始化默认 Agent
        self._init_default_agents()
        
        # Token 统计
        self.total_tokens = 0
        
        # 订阅事件
        self._subscribe_events()
        
        self.logger.info("OpenClaw Harness v3.0 初始化完成")
        self._print_banner()
    
    def _print_banner(self):
        """Print banner"""
        print("""
=========================================================
  OpenClaw Multi-Agent Harness v3.0
=========================================================
""")
        print(f"Initialized {len(self.agents)} Agents:")
        for agent in self.agents.values():
            print(f"  - {agent.agent_id:12} ({agent.role.value})")
        print()

    def _load_agent_configs(self) -> Dict[str, Any]:
        """加载 Agent 配置"""
        default_configs = {
            "leader": {"role": "leader", "prompt": "config/prompts/leader.txt"},
            "coder": {"role": "coder", "prompt": "config/prompts/coder.txt"},
            "researcher": {"role": "researcher", "prompt": "config/prompts/researcher.txt"},
            "writer": {"role": "writer", "prompt": "config/prompts/writer.txt"},
            "analyst": {"role": "analyst", "prompt": "config/prompts/analyst.txt"},
            "general": {"role": "general", "prompt": "config/prompts/general.txt"},
        }
        
        config_path = Path(self.config_path)
        if config_path.exists():
            try:
                import yaml
                with open(config_path) as f:
                    data = yaml.safe_load(f)
                    if data and "agents" in data:
                        return data["agents"]
            except ImportError:
                pass
        
        return default_configs
    
    def _init_default_agents(self):
        """初始化默认 Agent"""
        role_map = {
            "leader": AgentRole.LEADER,
            "coder": AgentRole.CODER,
            "researcher": AgentRole.RESEARCHER,
            "writer": AgentRole.WRITER,
            "analyst": AgentRole.ANALYST,
            "general": AgentRole.GENERAL,
        }
        
        for agent_id, config in self.agent_configs.items():
            role_str = config.get("role", "general")
            role = role_map.get(role_str, AgentRole.GENERAL)
            
            prompt_file = config.get("prompt")
            if prompt_file:
                prompt_file = Path(prompt_file)
            
            agent = LLMAgent(agent_id, role, prompt_file)
            self.agents[agent_id] = agent
        
        self.logger.info(f"已创建 {len(self.agents)} 个 Agent")
    
    def _subscribe_events(self):
        """订阅消息总线事件"""
        self.message_bus.subscribe("task_submitted", self._on_task_submitted)
        self.message_bus.subscribe("task_completed", self._on_task_completed)
        self.message_bus.subscribe("task_failed", self._on_task_failed)
    
    def _on_task_submitted(self, data: Dict):
        """任务提交回调"""
        task = data.get("task", {})
        self.logger.info(f"📥 任务提交: {task.get('task_id')} - {task.get('description', '')[:30]}")
    
    def _on_task_completed(self, data: Dict):
        """任务完成回调"""
        task_id = data.get("task_id")
        self.logger.info(f"✅ 任务完成: {task_id}")
    
    def _on_task_failed(self, data: Dict):
        """任务失败回调"""
        task_id = data.get("task_id")
        error = data.get("error", "unknown")
        self.logger.error(f"❌ 任务失败: {task_id} - {error}")
    
    def submit_task(self, description: str, agent_id: str = "auto", 
                priority: TaskPriority = TaskPriority.NORMAL,
                dependencies: Optional[List[str]] = None,
                timeout: float = 300.0,
                tags: Optional[List[str]] = None) -> str:
        """提交任务"""
        # 选择 Agent
        target_agent_id = self._select_agent(description, agent_id)
        
        # 创建任务
        task = Task(
            task_id=str(uuid.uuid4())[:8],
            description=description,
            priority=priority,
            assigned_to=target_agent_id,
            dependencies=dependencies or [],
            timeout=timeout,
            tags=tags or []
        )
        
        # 提交到调度器
        return self.scheduler.submit(task)
    
    def _select_agent(self, task: str, config: str = "auto") -> str:
        """选择 Agent"""
        task_lower = task.lower()
        
        if config == "auto":
            if any(k in task_lower for k in ["写一篇", "写作", "文章", "文档", "报告"]):
                return "writer"
            elif any(k in task_lower for k in ["代码", "编程", "写一个", "写程序", "开发"]):
                return "coder"
            elif any(k in task_lower for k in ["研究", "调研", "查", "找"]):
                return "researcher"
            elif any(k in task_lower for k in ["分析", "数据", "统计"]):
                return "analyst"
            elif any(k in task_lower for k in ["协调", "管理", "分配"]):
                return "leader"
            else:
                return "general"
        elif config in self.agents:
            return config
        else:
            return "general"
    
    def execute_task_sync(self, task_id: str) -> TaskResult:
        """同步执行任务"""
        task = self.scheduler.get_task_status(task_id)
        if not task:
            return TaskResult(task_id=task_id, status="failed", error="Task not found")
        
        # 获取 Agent
        agent = self.agents.get(task["assigned_to"])
        if not agent:
            return TaskResult(task_id=task_id, status="failed", error="Agent not found")
        
        # 开始追踪会话 v3.1
        session_id = f"{task_id}"
        tracer.start_session(session_id, task["description"])
        
        # 记录任务分配步骤
        tracer.add_step({
            "step_index": 1,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "caller": "Harness",
            "callee": "Scheduler",
            "action": "assign_task",
            "prompt": f"任务: {task['description']}\n分配给: {agent.agent_id}",
            "response": f"已分配给 {agent.agent_id} ({agent.role.value})",
            "config": {"task_id": task_id, "priority": task.get("priority", "normal")},
            "duration": 0,
            "status": "success"
        })
        
        # 创建 Task 对象
        task_obj = Task(
            task_id=task["task_id"],
            description=task["description"],
            status=TaskStatus.RUNNING,
            assigned_to=task["assigned_to"]
        )
        
        # 执行
        result = agent.execute(task_obj)
        
        # 记录执行完成步骤
        tracer.add_step({
            "step_index": 2,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "caller": agent.agent_id,
            "callee": "LLM",
            "action": "execute",
            "prompt": task["description"],
            "response": result.result if result else "",
            "config": {},
            "duration": result.duration if result else 0,
            "status": result.status if result else "failed"
        })
        
        return result
    
    def submit_and_wait(self, description: str, agent_id: str = "auto",
                    timeout: float = 300.0) -> TaskResult:
        """提交任务并等待结果"""
        task_id = self.submit_task(description, agent_id, timeout=timeout)
        
        # 等待完成（简单轮询）
        start_time = time.time()
        while time.time() - start_time < timeout:
            task_status = self.scheduler.get_task_status(task_id)
            if task_status and task_status["status"] in ("completed", "failed"):
                # 获取结果
                agent = self.agents.get(task_status["assigned_to"])
                if agent:
                    result = agent.execute(Task(
                        task_id=task_id,
                        description=description,
                        status=TaskStatus.RUNNING,
                        assigned_to=task_status["assigned_to"]
                    ))
                    return result
                break
            time.sleep(0.5)
        
        return TaskResult(task_id=task_id, status="failed", error="Timeout")
    
    def execute_multi_agent(self, task: str, agents: List[str]) -> Dict[str, TaskResult]:
        """多 Agent 协同执行 - 带流程追踪
        
        每一步记录：
        - step: 步骤序号
        - agent: Agent ID
        - action: 执行的操作
        - input: 输入内容
        - output: 输出结果
        """
        results = {}
        steps = []
        
        # 发布任务开始
        self.message_bus.publish("multi_agent_start", {
            "task": task[:50], 
            "agents": agents
        })
        
        context = task  # 传递给下一个 Agent 的上下文
        
        for i, agent_id in enumerate(agents):
            if agent_id not in self.agents:
                continue
            
            agent = self.agents[agent_id]
            step_start = time.time()
            
            # 记录步骤开始
            step_info = {
                "step": i + 1,
                "agent": agent_id,
                "role": agent.role.value,
                "action": f"将任务分发给 {agent_id}",
                # 详细信息
                "received_task": context[:200] + "..." if len(context) > 200 else context,
                "system_prompt": agent.system_prompt[:150] + "..." if len(agent.system_prompt) > 150 else agent.system_prompt,
                "llm_response": result.result[:300] + "..." if result.result and len(result.result) > 300 else (result.result or ""),
                "processed": f"分析任务 '{context[:50]}...' 并生成结果",
                "sent_back": result.result[:200] + "..." if result.result and len(result.result) > 200 else (result.result or ""),
                "status": "running"
            }
            steps.append(step_info)
            
            # 发布步骤开始
            self.message_bus.publish("step_start", {
                "step": i + 1,
                "agent": agent_id,
                "task": context[:50]
            })
            
            # 构建任务（第一个用原始任务，后续用上下文）
            task_obj = Task(
                task_id=f"{task[:8]}_{i}",
                description=context,
                assigned_to=agent_id
            )
            
            # 执行
            result = agent.execute(task_obj)
            step_duration = time.time() - step_start
            
            # 更新步骤结果
            step_info.update({
                "status": "completed",
                "output": result.result if result else "",
                "llm_response": result.result if result else "",
                "processed": f"分析任务并返回结果 ({len(result.result) if result.result else 0} 字符)",
                "duration": step_duration,
                "tokens": result.output_tokens
            })
            
            results[agent_id] = result
            
            # 更新上下文传递
            context = result.result or context
            
            # 发布步骤完成
            self.message_bus.publish("step_complete", {
                "step": i + 1,
                "agent": agent_id,
                "result": result.result[:100] if result.result else ""
            })
        
        # 最终结果
        final_result = context if len(context) < 500 else context[:500] + "..."
        
        # 合并结果
        combined = TaskResult(
            task_id=task[:8],
            status="completed",
            result=final_result,
            duration=sum(r.duration for r in results.values()),
            input_tokens=sum(r.input_tokens for r in results.values()),
            output_tokens=sum(r.output_tokens for r in results.values()),
            agent_used=",".join(agents),
            steps=steps  # 包含完整流程
        )
        
        # 发布完成
        self.message_bus.publish("multi_agent_complete", {
            "task": task[:50],
            "agents": agents,
            "steps": len(steps)
        })
        
        return {**{aid: r for aid, r in results.items()}, "_combined": combined}
    
    def decommission_task(self, task_id: str) -> TaskResult:
        """任务分发"""
        task_status = self.scheduler.get_task_status(task_id)
        if not task_status:
            return TaskResult(task_id=task_id, status="failed", error="Task not found")
        
        # 更新任务状态
        task = self.scheduler.queue.get(task_id)
        if task:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now().isoformat()
            self.scheduler.queue.update(task)
        
        # 调度执行
        return self.execute_task_sync(task_id)
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        agent_states = {}
        
        for agent_id, agent in self.agents.items():
            agent_states[agent_id] = AgentState(
                agent_id=agent.agent_id,
                role=agent.role.value,
                status=agent.state.status,
                current_task=agent.state.current_task,
                tools_used=agent.state.tools_used.copy(),
                tokens_used=agent.state.tokens_used,
                tasks_completed=agent.state.tasks_completed,
                last_active=agent.state.last_active
            ).to_dict()
        
        tasks = self.scheduler.list_tasks()
        
        return {
            "status": "running",
            "version": "3.0",
            "total_agents": len(self.agents),
            "active_agents": len([a for a in self.agents.values() if a.state.status == "running"]),
            "total_tasks": len(tasks),
            "pending_tasks": len([t for t in tasks if t["status"] == "pending"]),
            "running_tasks": len([t for t in tasks if t["status"] == "running"]),
            "completed_tasks": len([t for t in tasks if t["status"] == "completed"]),
            "failed_tasks": len([t for t in tasks if t["status"] == "failed"]),
            "total_tokens": self.total_tokens,
            "agents": agent_states,
            "tasks": tasks
        }
    
    def create_dynamic_agent(self, role: AgentRole, parent_id: str, agent_id: Optional[str] = None) -> BaseAgent:
        """动态创建 Agent"""
        if not agent_id:
            agent_id = f"dynamic_{len([a for a in self.agents.values() if getattr(a, 'is_dynamic', False)])}"
        
        agent = DynamicAgent(agent_id, role, parent_id)
        self.agents[agent_id] = agent
        
        self.logger.info(f"动态创建 Agent: {agent_id} ({role.value})")
        self.message_bus.publish("agent_created", {"agent_id": agent_id, "role": role.value})
        
        return agent
    
    def destroy_dynamic_agent(self, agent_id: str):
        """销毁动态 Agent"""
        if agent_id in self.agents:
            agent = self.agents[agent_id]
            if getattr(agent, "is_dynamic", False):
                del self.agents[agent_id]
                self.logger.info(f"销毁动态 Agent: {agent_id}")
                self.message_bus.publish("agent_destroyed", {"agent_id": agent_id})
    
    def get_messages(self, limit: int = 100) -> List[Dict]:
        """获取消息"""
        return self.message_bus.get_recent_messages(limit)
    
    def decompose_task(self, task: str) -> List[Dict[str, str]]:
        """任务分解"""
        subtasks = []
        task_lower = task.lower()
        
        # 更多关键字匹配
        code_keywords = ["代码", "编程", "写", "开发", "程序", "系统", "算法", "项目", "设计", "实现", "冒泡", "排序", "快速", "归并", "函数", "class", "def "]
        research_keywords = ["研究", "调研", "查", "找", "分析", "调查", "搜索"]
        
        # 判断是否需要代码
        is_code_task = any(k in task_lower for k in code_keywords)
        is_research_task = any(k in task_lower for k in research_keywords)
        
        if is_code_task:
            # 需要编写代码的项目
            if any(k in task_lower for k in ["分析需求", "开发", "项目", "系统"]):
                subtasks = [
                    {"description": f"分析需求: {task}", "role": "researcher"},
                    {"description": f"设计方案: {task}", "role": "analyst"},
                    {"description": f"编写代码: {task}", "role": "coder"},
                    {"description": f"撰写文档: {task}", "role": "writer"},
                ]
            else:
                # 简单的编码任务
                subtasks = [
                    {"description": f"理解需求: {task}", "role": "researcher"},
                    {"description": f"编写代码: {task}", "role": "coder"},
                    {"description": f"优化和文档: {task}", "role": "writer"},
                ]
        elif is_research_task:
            subtasks = [
                {"description": f"收集资料: {task}", "role": "researcher"},
                {"description": f"分析数据: {task}", "role": "analyst"},
                {"description": f"撰写报告: {task}", "role": "writer"},
            ]
        else:
            # 默认也分解为多步
            subtasks = [
                {"description": f"分析: {task}", "role": "researcher"},
                {"description": f"处理: {task}", "role": "general"},
                {"description": f"总结: {task}", "role": "writer"},
            ]
        
        return subtasks
    
    def execute_chain(self, task: str) -> TaskResult:
        """链式执行 - 带流程追踪"""
        start = time.time()
        subtasks = self.decompose_task(task)
        
        steps = []
        results = []
        
        self.message_bus.publish("chain_start", {
            "task": task[:50],
            "steps": len(subtasks)
        })
        
        for i, st in enumerate(subtasks):
            role = st.get("role", "general")
            agent = self.agents.get(role)
            
            step_info = {
                "step": i + 1,
                "agent": role,
                "action": f"拆分任务: {st.get('description', '')[:30]}",
                # 详细信息
                "received_task": st.get("description", "")[:200],
                "system_prompt": agent.system_prompt[:150] + "..." if len(agent.system_prompt) > 150 else agent.system_prompt,
                "llm_response": "",
                "processed": "",
                "status": "running"
            }
            steps.append(step_info)
            
            if agent:
                # 执行
                task_obj = Task(
                    task_id=f"{task[:8]}_{i}",
                    description=st.get("description", ""),
                    assigned_to=role
                )
                
                self.message_bus.publish("step_start", {
                    "step": i + 1,
                    "agent": role,
                    "task": st.get("description", "")[:50]
                })
                
                result = agent.execute(task_obj)
                results.append(result.result)
                
                # 更新步骤详情
                step_info.update({
                    "status": "completed",
                    "llm_response": result.result if result and result.result else "",
                    "processed": f"执行 {role} 角色任务，返回 {len(result.result) if result and result.result else 0} 字符",
                    "duration": result.duration
                })
                
                self.message_bus.publish("step_complete", {
                    "step": i + 1,
                    "agent": role,
                    "result": result.result[:50] if result.result else ""
                })
        
        final = "\n\n".join([r[:200] for r in results if r])
        duration = time.time() - start
        
        result = TaskResult(
            task_id=task[:8],
            status="completed",
            result=final,
            duration=duration,
            input_tokens=len(task),
            output_tokens=len(final),
            agent_used="chain",
            steps=steps
        )
        
        self.message_bus.publish("chain_complete", {
            "task": task[:50],
            "steps": len(steps)
        })
        
        return result

    def execute_with_plan(self, task: str) -> TaskResult:
        """使用 PlanAgent 执行任务 - 先规划再执行"""
        # 初始化 PlanAgent
        planner = PlanAgent()
        
        # 1. 先让 Planner 分析任务，制定计划
        plan_result = planner._call_llm(f"请为以下任务制定执行计划：{task}")
        plan = planner._parse_plan(plan_result, task)
        
        # 记录计划阶段
        plan_stages = []
        for stage in plan.get("stages", []):
            plan_stages.append({
                "type": "plan",
                "stage": stage.get("stage"),
                "name": stage.get("name"),
                "agent": stage.get("agent"),
                "input": stage.get("input"),
                "expected_output": stage.get("expected_output"),
                "analysis": plan.get("analysis", ""),
                "raw_plan": plan.get("raw_response", "")[:300],
                "status": "completed"
            })
        
        # 2. 执行计划
        execution_result = execute_plan(self, plan)
        
        # 3. 合并所有阶段
        all_stages = plan_stages + execution_result.get("stages", [])
        
        # 计算总耗时
        total_duration = sum(
            s.get("duration", 0) for s in all_stages 
            if isinstance(s, dict) and "duration" in s
        )
        
        return TaskResult(
            task_id=task[:8],
            status="completed",
            result=execution_result.get("final_result", ""),
            duration=total_duration,
            input_tokens=len(task),
            output_tokens=len(execution_result.get("final_result", "")),
            agent_used="planner",
            steps=all_stages
        )


# ========== CLI 入口 ==========

def main():
    """CLI 入口"""
    import sys
    
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    port = 8080
    
    for i, arg in enumerate(sys.argv):
        if arg == "-p" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
    
    # 启动 Web 服务器
    from web_server import run_server
    run_server(port)


if __name__ == '__main__':
    main()

# ========== PlanAgent ==========

class PlanAgent(LLMAgent):
    """计划 Agent - 负责任务分析和计划制定"""
    
    PLANNER_PROMPT = """你是一个任务规划专家，负责分析用户需求并制定执行计划。

请分析用户任务，输出以下格式的计划：

## 任务分析
[简短的1-2句话理解]

## 执行计划
请按以下格式输出：
```
阶段1: [阶段名称]
- Agent: [应该调用的Agent类型: coder/researcher/writer/analyst]
- 输入: [给Agent的具体输入]
- 预期输出: [期望得到什么]

阶段2: xxx
...
```

注意：
- 每个阶段必须有明确的 Agent 类型
- 输入要具体，不是简单重复用户需求
- 一般2-4个阶段即可

请用中文回复。"""

    def __init__(self):
        super().__init__("planner", AgentRole.LEADER)
        self.system_prompt = self.PLANNER_PROMPT
    
    def plan(self, user_task: str) -> Dict[str, Any]:
        """分析任务并制定计划"""
        # 调用 LLM 获取计划
        response = self._call_llm(user_task)
        
        # 解析计划
        return self._parse_plan(response, user_task)
    
    def _parse_plan(self, response: str, user_task: str) -> Dict[str, Any]:
        """解析 LLM 返回的计划"""
        import re
        
        # 提取阶段
        stages = []
        lines = response.split('\n')
        current_stage = None
        
        for line in lines:
            # 检测阶段开始
            stage_match = re.match(r'阶段(\d+):\s*(.+)', line)
            if stage_match:
                if current_stage:
                    stages.append(current_stage)
                current_stage = {
                    "stage": int(stage_match.group(1)),
                    "name": stage_match.group(2).strip(),
                    "agent": "",
                    "input": "",
                    "expected_output": ""
                }
                continue
            
            # 检测 Agent
            if current_stage and "- Agent:" in line:
                agent = line.split("- Agent:")[-1].strip()
                # 映射到具体 Agent
                agent_map = {
                    "coder": "coder",
                    "程序员": "coder",
                    "researcher": "researcher",
                    "研究员": "researcher", 
                    "writer": "writer",
                    "写作者": "writer",
                    "analyst": "analyst",
                    "分析师": "analyst",
                    "leader": "leader",
                    "领导": "leader",
                }
                for key, val in agent_map.items():
                    if key in agent.lower():
                        current_stage["agent"] = val
                        break
                continue
            
            # 检测输入
            if current_stage and "- 输入:" in line:
                current_stage["input"] = line.split("- 输入:")[-1].strip()
                continue
            
            # 检测预期输出
            if current_stage and "- 预期输出:" in line:
                current_stage["expected_output"] = line.split("- 预期输出:")[-1].strip()
                continue
        
        if current_stage:
            stages.append(current_stage)
        
        # 如果解析失败，生成默认计划
        if not stages:
            stages = self._default_plan(user_task)
        
        return {
            "task": user_task,
            "analysis": response.split("## 执行计划")[0] if "## 执行计划" in response else response[:200],
            "stages": stages,
            "raw_response": response
        }
    
    def _default_plan(self, task: str) -> List[Dict]:
        """生成默认计划"""
        task_lower = task.lower()
        
        if "代码" in task or "编程" in task or "写" in task:
            return [
                {"stage": 1, "name": "理解需求", "agent": "researcher", "input": f"分析用户需求：{task}", "expected_output": "需求分析文档"},
                {"stage": 2, "name": "编写代码", "agent": "coder", "input": f"根据需求编写代码：{task}", "expected_output": "完整代码实现"},
                {"stage": 3, "name": "优化文档", "agent": "writer", "input": f"为代码添加文档和说明", "expected_output": "完整的文档说明"},
            ]
        else:
            return [
                {"stage": 1, "name": "分析任务", "agent": "researcher", "input": f"分析任务：{task}", "expected_output": "任务分析"},
                {"stage": 2, "name": "处理任务", "agent": "general", "input": f"执行：{task}", "expected_output": "处理结果"},
                {"stage": 3, "name": "总结结果", "agent": "writer", "input": f"总结：{task}", "expected_output": "总结报告"},
            ]


# ========== 执行计划 ==========

def execute_plan(harness, plan: Dict[str, Any]) -> Dict[str, Any]:
    """执行计划"""
    stages = plan.get("stages", [])
    results = []
    context = plan.get("task", "")
    
    harness_stages = []  # 记录 Harness 每个环节
    
    for stage in stages:
        stage_info = {
            "stage": stage.get("stage", 0),
            "name": stage.get("name", ""),
            "action": f"Harness 调用 {stage.get('agent', 'unknown')} Agent",
            "received_task": stage.get("input", ""),
            "system_prompt": "",
            "llm_response": "",
            "processed": "",
            "status": "running"
        }
        
        agent_id = stage.get("agent", "general")
        agent = harness.agents.get(agent_id)
        
        if agent:
            # 添加到 Harness 记录
            harness_stages.append({
                "type": "harness_dispatch",
                "stage": stage.get("stage"),
                "name": stage.get("name"),
                "agent": agent_id,
                "input": stage.get("input", ""),
                "action": f"根据计划调用 {agent_id} Agent"
            })
            
            # 执行
            task_obj = Task(
                task_id=f"{plan.get('task', '')[:8]}_{stage.get('stage')}",
                description=stage.get("input", ""),
                assigned_to=agent_id
            )
            
            result = agent.execute(task_obj)
            
            stage_info.update({
                "status": "completed",
                "system_prompt": agent.system_prompt[:150] + "..." if len(agent.system_prompt) > 150 else agent.system_prompt,
                "llm_response": result.result or "",
                "processed": f"执行 {agent_id} 完成，返回 {len(result.result or '')} 字符",
                "duration": result.duration
            })
            
            results.append(result.result or "")
            context = result.result or context
            
            # 添加完成记录
            harness_stages.append({
                "type": "agent_complete",
                "stage": stage.get("stage"),
                "agent": agent_id,
                "result": result.result[:100] if result.result else ""
            })
        else:
            stage_info.update({
                "status": "failed",
                "processed": f"Agent {agent_id} 不存在"
            })
        
        harness_stages.append(stage_info)
    
    return {
        "stages": harness_stages,
        "results": results,
        "final_result": "\n\n".join([r[:300] for r in results if r])
    }

    def execute_with_plan(self, task: str) -> TaskResult:
        """使用 PlanAgent 执行任务 - 先规划再执行"""
        # 初始化 PlanAgent
        planner = PlanAgent()
        
        # 1. 先让 Planner 分析任务，制定计划
        plan_result = planner._call_llm(f"请为以下任务制定执行计划：{task}")
        plan = planner._parse_plan(plan_result, task)
        
        # 记录计划阶段
        plan_stages = []
        for stage in plan.get("stages", []):
            plan_stages.append({
                "type": "plan",
                "stage": stage.get("stage"),
                "name": stage.get("name"),
                "agent": stage.get("agent"),
                "input": stage.get("input"),
                "expected_output": stage.get("expected_output"),
                "analysis": plan.get("analysis", ""),
                "raw_plan": plan.get("raw_response", "")[:300],
                "status": "completed"
            })
        
        # 2. 执行计划
        execution_result = execute_plan(self, plan)
        
        # 3. 合并所有阶段
        all_stages = plan_stages + execution_result.get("stages", [])
        
        # 计算总耗时
        total_duration = sum(
            s.get("duration", 0) for s in all_stages 
            if isinstance(s, dict) and "duration" in s
        )
        
        return TaskResult(
            task_id=task[:8],
            status="completed",
            result=execution_result.get("final_result", ""),
            duration=total_duration,
            input_tokens=len(task),
            output_tokens=len(execution_result.get("final_result", "")),
            agent_used="planner",
            steps=all_stages
        )
