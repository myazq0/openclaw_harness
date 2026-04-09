#!/usr/bin/env python3
"""
DynamicPlanner - 动态计划执行循环
负责：LLM 决策、循环管理、流程追踪

作者: OpenClaw
日期: 2026-04-08
"""

import json
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable

from harness import BaseAgent, LLMAgent, OpenClawHarness, Task


# ========== 枚举定义 ==========

class LoopState(Enum):
    """循环状态"""
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING_DECISION = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


# ========== 数据结构 ==========

@dataclass
class PlanStage:
    """单个计划阶段"""
    stage: int
    name: str
    agent: str  # Agent ID
    input_text: str  # 给 Agent 的输入
    expected_output: str = ""  # 期望输出
    status: str = "pending"  # pending/running/completed/skipped
    
    # 执行结果
    result: Optional[str] = None
    llm_response: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ExecutionStep:
    """单个执行步骤"""
    step_id: int
    decision_type: str  # "select_agent" / "execute_next" / "continue"
    
    # Harness → LLM
    harness_prompt: str = ""
    llm_response: str = ""
    
    # 决策结果
    selected_agent: Optional[str] = None
    action: Optional[str] = None  # "execute" / "revise" / "stop" / "next"
    
    # Agent 执行
    agent_id: Optional[str] = None
    agent_input: str = ""
    agent_result: str = ""
    agent_status: str = "pending"  # pending/running/completed
    
    # 时间
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class LoopDecision:
    """循环决策记录"""
    step: int
    decision_type: str  # "select_agent" / "execute_next" / "continue"
    prompt: str
    response: str
    agent_id: Optional[str] = None
    action: Optional[str] = None
    reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ExecutionRecord:
    """完整执行记录"""
    record_id: str
    original_task: str
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: Optional[str] = None
    duration: float = 0.0
    
    # 计划
    plan: List[PlanStage] = field(default_factory=list)
    plan_prompt: str = ""
    plan_response: str = ""
    
    # 执行阶段
    execution_steps: List[ExecutionStep] = field(default_factory=list)
    
    # 循环决策
    decisions: List[LoopDecision] = field(default_factory=list)
    
    # 状态
    status: str = "running"  # running/completed/failed/stopped
    final_result: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "record_id": self.record_id,
            "original_task": self.original_task,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "plan": [p.to_dict() for p in self.plan],
            "plan_prompt": self.plan_prompt,
            "plan_response": self.plan_response,
            "execution_steps": [s.to_dict() for s in self.execution_steps],
            "decisions": [d.to_dict() for d in self.decisions],
            "status": self.status,
            "final_result": self.final_result
        }
    
    def to_display(self) -> Dict:
        """转换为前端展示格式"""
        flow = []
        
        # 添加计划阶段
        flow.append({
            "type": "harness_llm",
            "title": "询问 LLM: 选择计划 Agent",
            "prompt": self.decisions[0].prompt if self.decisions else "",
            "response": f"Agent: {self.decisions[0].agent_id}\n原因: {self.decisions[0].reason}" if self.decisions else "",
            "timestamp": self.decisions[0].timestamp if self.decisions else ""
        })
        
        flow.append({
            "type": "harness_agent",
            "title": f"Harness → {self.decisions[0].agent_id}: 拆分计划",
            "agent": self.decisions[0].agent_id if self.decisions else "",
            "input": self.plan_prompt,
            "result": self.plan_response,
            "timestamp": self.plan_prompt[:20] if self.plan_prompt else ""
        })
        
        # 添加执行步骤
        for step in self.execution_steps:
            if step.decision_type == "execute_next":
                flow.append({
                    "type": "harness_llm",
                    "title": f"询问 LLM: 选择执行 Agent (第{step.step_id}步)",
                    "prompt": step.harness_prompt,
                    "response": f"Agent: {step.selected_agent}\n动作: {step.action}",
                    "timestamp": step.timestamp
                })
                
                if step.agent_id:
                    flow.append({
                        "type": "harness_agent",
                        "title": f"Harness → {step.agent_id}: 执行",
                        "agent": step.agent_id,
                        "input": step.agent_input,
                        "result": step.agent_result,
                        "timestamp": step.timestamp
                    })
        
        return {
            "execution": {
                "record_id": self.record_id,
                "task": self.original_task,
                "status": self.status,
                "duration": self.duration,
                "start_time": self.start_time,
                "end_time": self.end_time
            },
            "plan": [p.to_dict() for p in self.plan],
            "flow": flow,
            "final_result": self.final_result
        }


# ========== DecisionMaker ==========

class DecisionMaker:
    """LLM 决策器"""
    
    # 选择 Agent 拆分计划的 Prompt
    SELECT_AGENT_PROMPT = """你是一个任务规划专家。请根据当前任务选择最适合拆分计划的 Agent。

## 当前任务
{task}

## 可用 Agent
{agents_list}

## 职责说明
- leader: 领导 Agent，负责协调和任务分配
- planner: 计划 Agent，专门负责制定执行计划
- researcher: 研究员，负责分析和调研
- coder: 程序员，负责编写代码
- writer: 写作者，负责撰写文档

## 选择标准
1. 任务复杂度
2. 任务类型 (代码/研究/写作/分析)
3. Agent 能力匹配

## 输出格式
请返回以下格式：
```
Agent: [agent_id]
原因: [不超过50字的说明]
```"""
    
    # 执行下一步的 Prompt
    EXECUTE_NEXT_PROMPT = """你是一个任务执行协调专家���请��定下一步用什么 Agent 执行。

## 原始任务
{original_task}

## 执行计划
{plan_summary}

## 当前进度
- 已完成: {completed}
- 当前阶段: {current_stage}
- 剩余: {remaining}

## 上一步结果
{last_result}

## 决策选项
- execute: 执行下一个阶段
- revise: 修正计划
- stop: 停止执行

## 输出格式
```
动作: [execute|revise|stop]
Agent: [agent_id]  # 如果动作是 execute
说明: [简短说明]
```"""
    
    # 继续/停止的 Prompt
    CONTINUE_PROMPT = """你是一个任务执行协调专家。请根据当前执行情况决定下一步。

## 原始任务
{original_task}

## 计划进度
{plan_progress}

## 最近执行结果
{recent_result}

## 上下文
{context}

## 决策选项
- next: 继续执行下一阶段
- revise: 修正计划
- stop: 停止执行

## 输出格式
```
动作: [next|revise|stop]
说明: [简短说明]
```"""
    
    def __init__(self, harness: OpenClawHarness):
        self.harness = harness
    
    def generate_select_agent_prompt(self, task: str, agents: List[str] = None) -> str:
        """生成选择 Agent 的提示词"""
        if agents is None:
            agents = ["planner", "leader", "researcher"]
        
        agents_list = "\n".join([f"- {a}: {self._get_agent_desc(a)}" for a in agents])
        
        return self.SELECT_AGENT_PROMPT.format(
            task=task,
            agents_list=agents_list
        )
    
    def generate_execute_next_prompt(self, plan: List[PlanStage], context: Dict) -> str:
        """生成下一步执行的提示词"""
        completed = [p for p in plan if p.status == "completed"]
        current = [p for p in plan if p.status == "running"]
        remaining = [p for p in plan if p.status == "pending"]
        
        plan_summary = "\n".join([
            f"- 阶段{p.stage}: {p.name} → {p.agent}"
            for p in plan
        ])
        
        current_stage = current[0] if current else (remaining[0] if remaining else None)
        
        return self.EXECUTE_NEXT_PROMPT.format(
            original_task=context.get("original_task", ""),
            plan_summary=plan_summary,
            completed=", ".join([p.name for p in completed]) or "无",
            current_stage=current_stage.name if current_stage else "无",
            remaining=f"{len(remaining)} 个阶段",
            last_result=context.get("last_result", "无")
        )
    
    def generate_continue_prompt(self, plan: List[PlanStage], context: Dict) -> str:
        """生成继续/停止的提示词"""
        completed = [p for p in plan if p.status == "completed"]
        remaining = [p for p in plan if p.status == "pending"]
        
        plan_progress = f"已完成: {len(completed)}/{len(plan)} 阶段"
        
        return self.CONTINUE_PROMPT.format(
            original_task=context.get("original_task", ""),
            plan_progress=plan_progress,
            recent_result=context.get("recent_result", "无"),
            context=context.get("context", "")
        )
    
    def parse_agent_selection(self, response: str) -> Dict:
        """解析 Agent 选择响应"""
        agent_id = None
        reason = ""
        
        # 提取 Agent
        match = re.search(r'Agent:\s*(\w+)', response)
        if match:
            agent_id = match.group(1)
        
        # 提取原因
        match = re.search(r'原因:\s*(.+)', response)
        if match:
            reason = match.group(1).strip()
        
        return {"agent_id": agent_id, "reason": reason}
    
    def parse_action_decision(self, response: str) -> Dict:
        """解析动作决策响应"""
        action = None
        agent_id = None
        reason = ""
        
        # 提取动作
        match = re.search(r'动作:\s*(\w+)', response)
        if match:
            action = match.group(1)
        
        # 提取 Agent
        match = re.search(r'Agent:\s*(\w+)', response)
        if match:
            agent_id = match.group(1)
        
        # 提取说明
        match = re.search(r'说明:\s*(.+)', response)
        if match:
            reason = match.group(1).strip()
        
        return {"action": action, "agent_id": agent_id, "reason": reason}
    
    def _get_agent_desc(self, agent_id: str) -> str:
        """获取 Agent 描述"""
        descs = {
            "leader": "领导 Agent，负责协调和任务分配",
            "planner": "计划 Agent，专门负责制定执行计划",
            "researcher": "研究员，负责分析和调研",
            "coder": "程序员，负责编写代码",
            "writer": "写作者，负责撰写文档",
            "analyst": "分析师，负责数据分析",
            "general": "通用助手"
        }
        return descs.get(agent_id, "通用助手")


# ========== FlowTracker ==========

class FlowTracker:
    """流程追踪器"""
    
    def __init__(self):
        self.executions: Dict[str, ExecutionRecord] = {}
        self.current: Optional[ExecutionRecord] = None
    
    def start_record(self, task: str) -> ExecutionRecord:
        """开始记录新的执行"""
        record = ExecutionRecord(
            record_id=str(uuid.uuid4())[:8],
            original_task=task
        )
        self.executions[record.record_id] = record
        self.current = record
        return record
    
    def get_record(self, record_id: str) -> Optional[ExecutionRecord]:
        """获取执行记录"""
        return self.executions.get(record_id)
    
    def add_decision(self, decision: LoopDecision):
        """添加决策"""
        if self.current:
            self.current.decisions.append(decision)
    
    def add_step(self, step: ExecutionStep):
        """添加执行步骤"""
        if self.current:
            self.current.execution_steps.append(step)
    
    def update_plan(self, plan: List[PlanStage]):
        """更新计划"""
        if self.current:
            self.current.plan = plan
    
    def complete(self, final_result: str):
        """完成执行"""
        if self.current:
            self.current.status = "completed"
            self.current.final_result = final_result
            self.current.end_time = datetime.now().isoformat()
            self.current.duration = (
                datetime.fromisoformat(self.current.end_time) - 
                datetime.fromisoformat(self.current.start_time)
            ).total_seconds()
    
    def get_display_data(self) -> Dict:
        """获取前端展示数据"""
        if self.current:
            return self.current.to_display()
        return {}
    
    def get_all_executions(self) -> List[Dict]:
        """获取所有执行记录"""
        return [
            {
                "record_id": r.record_id,
                "task": r.original_task,
                "status": r.status,
                "start_time": r.start_time,
                "duration": r.duration
            }
            for r in self.executions.values()
        ]


# ========== LoopManager ==========

class LoopManager:
    """循环管理器"""
    
    def __init__(self, harness: OpenClawHarness):
        self.harness = harness
        self.decision_maker = DecisionMaker(harness)
        self.flow_tracker = FlowTracker()
        
        self.state = LoopState.IDLE
        self.current_record: Optional[ExecutionRecord] = None
    
    def start(self, task: str) -> str:
        """开始执行循环"""
        # 创建执行记录
        record = self.flow_tracker.start_record(task)
        self.current_record = record
        
        # 设置状态
        self.state = LoopState.PLANNING
        
        # Step 1: 询问 LLM 选择计划 Agent
        prompt = self.decision_maker.generate_select_agent_prompt(task)
        
        # 调用 LLM
        llm_response = self._call_llm(prompt)
        
        # 解析决策
        decision = self.decision_maker.parse_agent_selection(llm_response)
        
        # 记录决策
        record.decisions.append(LoopDecision(
            step=1,
            decision_type="select_agent",
            prompt=prompt,
            response=llm_response,
            agent_id=decision["agent_id"],
            reason=decision["reason"]
        ))
        
        return record.record_id
    
    def decompose_plan(self) -> List[PlanStage]:
        """让 Agent 拆分计划"""
        if not self.current_record:
            return []
        
        record = self.current_record
        agent_id = record.decisions[-1].agent_id
        agent = self.harness.agents.get(agent_id)
        
        if not agent:
            return []
        
        # 构建输入
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
        
        # 执行
        result = agent.execute(Task(
            task_id=f"{record.record_id}_plan",
            description=agent_input
        ))
        
        # 保存
        record.plan_prompt = agent_input
        record.plan_response = result.result
        
        # 解析计划
        plan = self._parse_plan(result.result)
        record.plan = plan
        
        # 设置状态
        self.state = LoopState.EXECUTING
        
        return plan
    
    def execute_next(self) -> Dict:
        """执行下一步"""
        if not self.current_record:
            return {"action": "stop", "reason": "无执行记录"}
        
        record = self.current_record
        plan = record.plan
        
        # 获取当前阶段
        current_stage = None
        for p in plan:
            if p.status == "pending":
                current_stage = p
                p.status = "running"
                break
        
        if current_stage is None:
            # 计划完成，询问是否继续
            context = {
                "original_task": record.original_task,
                "last_result": plan[-1].result if plan else "无",
                "plan": record.original_task,
                "context": "所有阶段已完成"
            }
            prompt = self.decision_maker.generate_continue_prompt(plan, context)
            llm_response = self._call_llm(prompt)
            
            decision = self.decision_maker.parse_action_decision(llm_response)
            
            # 记录步骤
            record.execution_steps.append(ExecutionStep(
                step_id=len(record.execution_steps) + 1,
                decision_type="continue",
                harness_prompt=prompt,
                llm_response=llm_response,
                action=decision["action"],
                agent_result=decision.get("reason", "")
            ))
            
            if decision["action"] in ("stop", "revise"):
                self.state = LoopState.COMPLETED
                self.flow_tracker.complete(plan[-1].result if plan else "")
            
            return decision
        
        # 询问 LLM 用哪个 Agent 执行
        context = {
            "original_task": record.original_task,
            "last_result": plan[-1].result if plan else "无",
            "completed": ", ".join([p.name for p in plan if p.status == "completed"]),
            "current_stage": current_stage.name,
            "remaining": f"{len([p for p in plan if p.status == 'pending'])} 个阶段"
        }
        
        prompt = self.decision_maker.generate_execute_next_prompt(plan, context)
        llm_response = self._call_llm(prompt)
        
        # 解析决策
        decision = self.decision_maker.parse_action_decision(llm_response)
        
        # 如果 LLM 说 execute，用当前阶段的 agent
        agent_id = decision.get("agent_id") or current_stage.agent
        if decision.get("action") == "execute" and not agent_id:
            agent_id = current_stage.agent
        
        # 执行 Agent
        if agent_id and decision.get("action") == "execute":
            agent = self.harness.agents.get(agent_id)
            if agent:
                result = agent.execute(Task(
                    task_id=f"{record.record_id}_{current_stage.stage}",
                    description=current_stage.input_text
                ))
                
                current_stage.status = "completed"
                current_stage.result = result.result
                
                # 记录步骤
                record.execution_steps.append(ExecutionStep(
                    step_id=len(record.execution_steps) + 1,
                    decision_type="execute_next",
                    harness_prompt=prompt,
                    llm_response=llm_response,
                    selected_agent=agent_id,
                    action="execute",
                    agent_id=agent_id,
                    agent_input=current_stage.input_text,
                    agent_result=result.result,
                    agent_status="completed"
                ))
        
        # 检查是否全部完成
        remaining = [p for p in plan if p.status == "pending"]
        if not remaining:
            self.state = LoopState.COMPLETED
            self.flow_tracker.complete(plan[-1].result if plan else "")
        
        return {"action": decision.get("action", "next"), "agent_id": agent_id}
    
    def _call_llm(self, prompt: str) -> str:
        """调用 LLM"""
        # 使用 harness 中的 mock 或真实 LLM
        # 这里直接调用 agent 的方法
        agent = self.harness.agents.get("planner")
        if not agent:
            agent = self.harness.agents.get("leader")
        if not agent:
            agent = list(self.harness.agents.values())[0]
        
        result = agent.execute(Task(
            task_id="llm_call",
            description=prompt
        ))
        
        return result.result
    
    def _parse_plan(self, response: str) -> List[PlanStage]:
        """解析计划"""
        stages = []
        current = None
        stage_num = 0
        
        lines = response.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # 检测阶段开始 (支持 "阶段1:" / "阶段 1:" / "第1阶段" 等格式)
            stage_match = re.match(r'阶段[第]?(\d+)[：:]\s*(.+)', line)
            if stage_match:
                if current:
                    stages.append(current)
                stage_num += 1
                current = PlanStage(
                    stage=stage_num,
                    name=stage_match.group(2).strip(),
                    agent="",
                    input_text=""
                )
                continue
            
            if current:
                # 检测 Agent (支持多种格式)
                # 格式1: "- Agent: coder"
                # 格式2: "- Agent: [算法设计专家]"
                if "- Agent:" in line:
                    agent = line.split("- Agent:")[-1].strip()
                    # 去掉方括号
                    agent = re.sub(r'[\[\]]', '', agent).strip()
                    
                    # 映射中文/角色名到 agent_id
                    agent_map = {
                        "coder": "coder", "编程开发人员": "coder",
                        "researcher": "researcher", "研究员": "researcher",
                        "算法设计专家": "researcher", "研究调研": "researcher",
                        "writer": "writer", "写作者": "writer", "项目经理": "writer",
                        "analyst": "analyst", "分析师": "analyst",
                        "leader": "leader", "领导": "leader",
                        "测试工程师": "general",
                    }
                    
                    for key, val in agent_map.items():
                        if key in agent.lower():
                            current.agent = val
                            break
                    
                    # 如果没映射到，尝试用任务的关键词判断
                    if not current.agent:
                        if any(k in agent.lower() for k in ["代码", "编程", "开发", "程序"]):
                            current.agent = "coder"
                        elif any(k in agent.lower() for k in ["研究", "分析", "设计", "调研"]):
                            current.agent = "researcher"
                        elif any(k in agent.lower() for k in ["文档", "写", "报告", "交付"]):
                            current.agent = "writer"
                        elif any(k in agent.lower() for k in ["测试"]):
                            current.agent = "general"
                        else:
                            current.agent = "general"
                    continue
                
                # 检测输入
                if "- 输入:" in line:
                    current.input_text = line.split("- 输入:")[-1].strip()
                    # 去掉方括号
                    current.input_text = re.sub(r'[\[\]]', '', current.input_text).strip()
                    continue
                
                # 检测预期输出
                if "- 预期输出:" in line:
                    current.expected_output = line.split("- 预期输出:")[-1].strip()
                    # 去掉方括号
                    current.expected_output = re.sub(r'[\[\]]', '', current.expected_output).strip()
                    continue
        
        if current:
            stages.append(current)
        
        # 如果解析失败，生成默认计划
        if not stages:
            task_lower = self.current_record.original_task.lower()
            
            if "代码" in task_lower or "编程" in task_lower or "写" in task_lower or "排序" in task_lower or "算法" in task_lower:
                stages = [
                    PlanStage(1, "分析需求", "researcher", f"分析需求：{self.current_record.original_task}"),
                    PlanStage(2, "编写代码", "coder", f"编写代码：{self.current_record.original_task}"),
                    PlanStage(3, "优化文档", "writer", f"添加文档说明")
                ]
            else:
                stages = [
                    PlanStage(1, "分析任务", "researcher", f"分析任务：{self.current_record.original_task}"),
                    PlanStage(2, "处理任务", "general", f"执行：{self.current_record.original_task}"),
                    PlanStage(3, "总结结果", "writer", f"总结：{self.current_record.original_task}")
                ]
        
        return stages
    
    def get_status(self) -> Dict:
        """获取状态"""
        if self.current_record:
            return {
                "state": self.state.value,
                "record_id": self.current_record.record_id,
                "task": self.current_record.original_task,
                "plan": [p.to_dict() for p in self.current_record.plan],
                "steps": len(self.current_record.execution_steps)
            }
        return {"state": self.state.value}
    
    def get_result(self) -> Optional[ExecutionRecord]:
        """获取结果"""
        return self.current_record
    
    def get_flow(self) -> Dict:
        """获取流程数据"""
        return self.flow_tracker.get_display_data()


# ========== 便捷函数 ==========

def create_execution_loop(harness: OpenClawHarness) -> LoopManager:
    """创建执行循环"""
    return LoopManager(harness)