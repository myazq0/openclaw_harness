# OpenClaw Multi-Agent Harness 产品设计文档

## 1. 产品概述

### 1.1 产品定位

**OpenClaw Multi-Agent Harness** 是一个多 Agent 协作与任务协调框架，旨在通过多个专业 Agent 的协同工作，完成复杂任务。

### 1.2 核心价值

- **多 Agent 协作**: 6 种专业 Agent，支持任务分解与协同
- **LLM 集成**: 支持千问、OpenAI、Anthropic 等多种大语言模型
- **Web 管理**: 提供 Web 界面进行任务管理和状态监控
- **日志持久化**: 5 分钟切片日志保存，便于问题追踪

### 1.3 目标用户

- 开发者
- 研究人员
- 需要 AI 辅助完成复杂任务的用户

---

## 2. 功能需求

### 2.1 Agent 系统

| Agent | 角色 | 功能 |
|-------|------|------|
| Leader | 领导者 | 任务分解、多 Agent 协调 |
| Coder | 程序员 | 代码编写、程序开发 |
| Researcher | 研究员 | 信息调研、知识检索 |
| Writer | 写作者 | 内容撰写、文章生成 |
| Analyst | 分析师 | 数据分析、趋势预测 |
| General | 通用助手 | 问答、通用任务 |

### 2.2 核心功能

#### 2.2.1 任务执行

- 单 Agent 执行任务
- 多 Agent 协同执行（逗号分隔）
- 自动 Agent 选择（基于关键词匹配）

#### 2.2.2 文件操作

- Agent 可直接创建文件和目录
- 支持 Python 代码执行文件系统操作

#### 2.2.3 状态监控

- 活跃 Agent 数量
- 进行中的任务
- Token 消耗统计

#### 2.2.4 日志系统

- 请求日志（请求级别）
- 协作日志（Agent 协作过程）
- 5 分钟日志切片

### 2.3 API 接口

| 端点 | 方法 | 说明 |
|------|------|------|
| / | GET | Web 界面 |
| /status | GET | 系统状态 |
| /agents | GET | Agent 列表 |
| /logs | GET | 请求日志 |
| /collab | GET | 协作日志 |
| /run | POST | 执行任务 |

---

## 3. 技术架构

### 3.1 系统结构

```
┌─────────────────────────────────────┐
│         Web 界面 (HTTP)              │
├─────────────────────────────────────┤
│       RequestHandler (HTTP处理)        │
├─────────────────────────────────────┤
│         OpenClawHarness             │
│  ┌─────────────────────────────┐    │
│  │      Agent 管理系统       │    │
│  │  ┌────┐ ┌────┐ ┌────┐  │    │
│  │  │Leader│ │Coder│ │... │  │    │
│  │  └────┘ └────┘ └────┘  │    │
│  └─────────────────────────────┘    │
├─────────────────────────────────────┤
│       LLM (千问/OpenAI/...)         │
└─────────────────────────────────────┘
```

### 3.2 消息流

```
用户 → Web → /run → handle_run()
           ↓
    _harness.execute_task()
           ↓
    Agent 选择 (auto/指定)
           ↓
    Agent.execute(task)
           ↓
    _call_qwen() / _call_openai()
           ↓
    LLM API → 响应
           ↓
    返回结果 + 记录日志
```

### 3.3 数据流

| 数据 | 存储 |
|------|------|
| 请求日志 | logs/harness_{slice}.json |
| 协作日志 | logs/harness_{slice}.json |
| Agent 配置 | config/agents.yaml |
| LLM 配置 | config/llm.yaml |
| Prompts | config/prompts/*.txt |

---

## 4. 界面设计

### 4.1 页面结构

```
┌─────────────────────────────────┐
│  Header (标题 + 描述)            │
├─────────────────────────────────┤
│  Stats (4个统计卡片)             │
│  Agent | 活跃 | 进行中 | Token  │
├─────────────────────────────────┤
│  Agent 状态卡片                 │
├─────────────────────────────────┤
│  任务输入表单                   │
├─────────────────────────────────┤
│  结果显示区域                   │
├─────────────────────────────────┤
│  协作日志卡片                   │
├─────────────────────────────────┤
│  请求日志卡片                   │
└─────────────────────────────────┘
```

### 4.2 响应式设计

- 桌面端：4 列统计
- 移动端：2 列统计

### 4.3 状态颜色

- 空闲 (idle): 绿色 (#dcfce7)
- 进行中 (running): 黄色 (#fef3c7)

---

## 5. 配置说明

### 5.1 LLM 配置 (llm.yaml)

```yaml
qwen:
  api_key: "sk-xxx"
  model: "qwen-turbo"
  endpoint: "https://dashscope.aliyuncs.com/..."
  timeout: 60
system:
  provider: "qwen"
```

### 5.2 Agent 配置 (agents.yaml)

```yaml
leader:
  role: "leader"
  prompt: "config/prompts/leader.txt"
coder:
  role: "coder"
  prompt: "config/prompts/coder.txt"
# ...
```

---

## 6. 部署要求

- Python 3.11+
- 无需额外依赖（内置 HTTP Server）
- 千问 API Key（可选）

---

## 7. 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| v1 | 2024-04 | 初始版本 |
| v2 | 2025-04 | 重写前端 + 日志持久化 |

---

## 8. 待实现功能

- [ ] 任务队列和调度
- [ ] Agent 动态创建
- [ ] 更丰富的协作策略
- [ ] OpenAI/Anthropic 支持
- [ ] Webhook 回调