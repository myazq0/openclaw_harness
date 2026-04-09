#!/usr/bin/env python3
"""
OpenClaw Multi-Agent Harness Web Server v3.0
RESTful API + 简洁前端
"""
import sys
import json
import uuid
import time
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from harness import OpenClawHarness, TaskPriority, Task, TaskStatus
from execution_loop import LoopManager, create_execution_loop

# 全局实例
_harness = None
_loop_manager = None
request_logs = {}

# ========== 前端模板 ==========
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenClaw Multi-Agent Harness v3.0</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        
        :root {
            --primary: #2563eb;
            --success: #16a34a;
            --warning: #f59e0b;
            --danger: #dc2626;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text: #1e293b;
            --text-muted: #64748b;
            --border: #e2e8f0;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            min-height: 100vh;
        }
        
        .container {
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
        }
        
        /* Header */
        .header {
            text-align: center;
            padding: 30px 20px;
            background: linear-gradient(135deg, var(--primary), #1d4ed8);
            color: white;
            border-radius: 12px;
            margin-bottom: 20px;
        }
        
        .header h1 { font-size: 24px; font-weight: 600; }
        .header p { opacity: 0.9; margin-top: 8px; }
        .header .version { 
            display: inline-block; 
            background: rgba(255,255,255,0.2); 
            padding: 2px 8px; 
            border-radius: 4px;
            font-size: 12px;
            margin-top: 8px;
        }
        
        /* Stats */
        .stats {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 12px;
            margin-bottom: 20px;
        }
        
        .stat-card {
            background: var(--card-bg);
            padding: 16px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        
        .stat-value { font-size: 24px; font-weight: 700; color: var(--primary); }
        .stat-label { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
        
        /* Cards */
        .card {
            background: var(--card-bg);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        
        .card-title {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        /* Agents */
        .agents { display: flex; flex-wrap: wrap; gap: 8px; }
        
        .agent-tag {
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 500;
        }
        
        .agent-idle { background: #dcfce7; color: var(--success); }
        .agent-running { background: #fef3c7; color: var(--warning); }
        .agent-waiting { background: #e0e7ff; color: var(--primary); }
        
        /* Form */
        .task-form { display: flex; flex-direction: column; gap: 12px; }
        
        .task-input {
            width: 100%;
            padding: 14px 16px;
            border: 2px solid var(--border);
            border-radius: 8px;
            font-size: 15px;
            transition: border-color 0.2s;
        }
        
        .task-input:focus {
            outline: none;
            border-color: var(--primary);
        }
        
        .form-row { display: flex; gap: 12px; flex-wrap: wrap; }
        
        .form-group { flex: 1; min-width: 150px; }
        
        .agent-select, .priority-select {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid var(--border);
            border-radius: 8px;
            font-size: 15px;
            background: white;
            cursor: pointer;
        }
        
        .run-btn {
            padding: 12px 32px;
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }
        
        .run-btn:hover { background: #1d4ed8; }
        .run-btn:disabled { background: var(--text-muted); cursor: not-allowed; }
        
        /* Result */
        .result {
            background: #f1f5f9;
            padding: 16px;
            border-radius: 8px;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 13px;
            white-space: pre-wrap;
            word-break: break-word;
            max-height: 400px;
            overflow-y: auto;
        }
        
        .result-meta { font-size: 12px; color: var(--text-muted); margin-bottom: 8px; }
        .result-success { color: var(--success); }
        .result-error { color: var(--danger); }
        
        /* Task Queue */
        .task-queue { max-height: 300px; overflow-y: auto; }
        
        .task-item {
            padding: 12px;
            border-bottom: 1px solid var(--border);
            font-size: 13px;
        }
        
        .task-item:last-child { border-bottom: none; }
        
        .task-id { font-weight: 600; color: var(--primary); }
        .task-desc { margin-top: 4px; color: var(--text-muted); }
        
        .task-status {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 500;
            margin-right: 8px;
        }
        
        .status-pending { background: #e0e7ff; color: var(--primary); }
        .status-running { background: #fef3c7; color: var(--warning); }
        .status-completed { background: #dcfce7; color: var(--success); }
        .status-failed { background: #fee2e2; color: var(--danger); }
        .status-waiting { background: #f3e8ff; color: #9333ea; }
        
        /* Steps - 协作流程 */
        .steps { max-height: 400px; overflow-y: auto; }
        
        .step-item {
            padding: 12px;
            margin: 8px 0;
            border-radius: 8px;
            background: #f8fafc;
            border-left: 3px solid var(--primary);
        }
        
        .step-header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 8px;
        }
        
        .step-number {
            display: inline-block;
            width: 24px;
            height: 24px;
            background: var(--primary);
            color: white;
            border-radius: 50%;
            text-align: center;
            line-height: 24px;
            font-size: 12px;
            font-weight: 600;
        }
        
        .step-agent {
            font-weight: 600;
            color: var(--primary);
        }
        
        .step-action {
            font-size: 12px;
            color: var(--text-muted);
        }
        
        .step-status {
            margin-left: auto;
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 4px;
        }
        
        .step-running { background: #fef3c7; color: var(--warning); }
        .step-completed { background: #dcfce7; color: var(--success); }
        
        .step-content {
            font-size: 12px;
            background: #fff;
            padding: 8px;
            border-radius: 4px;
            font-family: monospace;
            white-space: pre-wrap;
            word-break: break-word;
            max-height: 150px;
            overflow-y: auto;
        }
        .logs { max-height: 250px; overflow-y: auto; }
        
        .log-item {
            padding: 8px 12px;
            border-bottom: 1px solid var(--border);
            font-size: 12px;
        }
        
        .log-item:last-child { border-bottom: none; }
        
        .log-empty {
            color: var(--text-muted);
            text-align: center;
            padding: 20px;
        }
        
        .loading {
            text-align: center;
            padding: 20px;
            color: var(--text-muted);
        }
        
        /* Responsive */
        @media (max-width: 600px) {
            .stats { grid-template-columns: repeat(2, 1fr); }
            .form-row { flex-direction: column; }
            .header h1 { font-size: 20px; }
        }
        /* Steps 详情样式 */
        .step-detail { margin: 8px 0; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; }
        .step-header { background: linear-gradient(135deg, #f0f9ff, #e0f2fe); padding: 12px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
        .step-badge { display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }
        .step-badge-1 { background: #fef3c7; color: #92400e; }
        .step-badge-plan { background: #fcd34d; color: #78350f; }
        .step-badge-dispatch { background: #93c5fd; color: #1e40af; } .step-badge-2 { background: #dbeafe; color: #1e40af; } .step-badge-3 { background: #d1fae5; color: #065f46; }
        .step-role { font-weight: 600; color: #1e293b; }
        .step-status-badge { margin-left: auto; padding: 4px 10px; border-radius: 12px; font-size: 11px; }
        .step-running { background: #fef3c7; color: #92400e; } .step-completed { background: #d1fae5; color: #065f46; }
        .step-body { padding: 12px; background: #fff; }
        .step-section { margin-bottom: 12px; } .step-section:last-child { margin-bottom: 0; }
        .step-label { display: flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 600; color: #64748b; margin-bottom: 4px; }
        .step-content-box { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; font-size: 12px; font-family: monospace; white-space: pre-wrap; word-break: break-word; max-height: 250px; overflow-y: auto; line-height: 1.5; }

    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1>🤖 OpenClaw Multi-Agent Harness</h1>
            <p>多 Agent 协作与任务协调框架 v3.0</p>
            <span class="version">任务队列 + 依赖管理 + 消息总线</span>
        </div>
        
        <!-- Stats -->
        <div class="stats">
            <div class="stat-card">
                <div class="stat-value" id="statAgents">-</div>
                <div class="stat-label">Agent</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="statActive">-</div>
                <div class="stat-label">活跃</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="statPending">-</div>
                <div class="stat-label">待执行</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="statRunning">-</div>
                <div class="stat-label">进行中</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="statTokens">-</div>
                <div class="stat-label">Token</div>
            </div>
        </div>
        
        <!-- Task Queue -->
        <div class="card">
            <div class="card-title">📋 任务队列 <span id="queueCount"></span></div>
            <div class="task-queue" id="taskQueue">
                <div class="log-empty">暂无任务</div>
            </div>
        </div>
        
        <!-- Agents -->
        <div class="card">
            <div class="card-title">🤖 Agent 状态</div>
            <div class="agents" id="agentList">
                <div class="loading">加载中...</div>
            </div>
        </div>
        
        <!-- Task Form -->
        <div class="card">
            <div class="card-title">📝 执行任务</div>
            <form class="task-form" id="taskForm">
                <input 
                    type="text" 
                    class="task-input" 
                    id="taskInput" 
                    placeholder="输入任务描述..." 
                    required
                    autocomplete="off"
                >
                <div class="form-row">
                    <div class="form-group">
                        <select class="agent-select" id="agentSelect">
                            <option value="auto">🤖 自动分配</option>
                            <option value="leader">👑 领导者</option>
                            <option value="coder">💻 程序员</option>
                            <option value="researcher">🔍 研究员</option>
                            <option value="writer">✍️ 写作者</option>
                            <option value="analyst">📐 分析师</option>
                            <option value="general">💬 通用</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <select class="priority-select" id="prioritySelect">
                            <option value="1">� Priority: Normal</option>
                            <option value="0">⬇️ Priority: Low</option>
                            <option value="2">⬆️ Priority: High</option>
                            <option value="3">🔥 Priority: Urgent</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <select class="mode-select" id="modeSelect">
                            <option value="single">⚡ 单个</option>
                            <option value="chain">🔗 链式</option>
                            <option value="plan">📋 计划+执行</option>
                        </select>
                    </div>
                    <button type="submit" class="run-btn" id="runBtn">🚀 执行</button>
                </div>
            </form>
        </div>
        
        <!-- Result -->
        <div class="card">
            <div class="card-title">📄 结果</div>
            <div class="result-meta" id="resultMeta"></div>
            <div class="result" id="result">等待执行...</div>
            
            <!-- 协作流程 Steps -->
            <div class="card-title" style="margin-top: 16px;">🔄 协作流程 <span id="stepCount"></span></div>
            <div class="steps" id="stepList">
                <div class="log-empty">执行多 Agent 任务时显示</div>
            </div>
        </div>
        
        <!-- Messages -->
        <div class="card">
            <div class="card-title">🔔 消息 <span id="msgCount"></span></div>
            <div class="logs" id="msgList">
                <div class="log-empty">暂无消息</div>
            </div>
        </div>
        
        <!-- Request Logs -->
        <div class="card">
            <div class="card-title">📜 请求日志 <span id="logCount"></span></div>
            <div class="logs" id="logList">
                <div class="log-empty">暂无日志</div>
            </div>
        </div>
    </div>
    
    <script>
    (function() {
        'use strict';
        
        // ========== DOM ==========
        const $ = (id) => document.getElementById(id);
        
        const taskForm = $('taskForm');
        const taskInput = $('taskInput');
        const agentSelect = $('agentSelect');
        const prioritySelect = $('prioritySelect');
        const modeSelect = $('modeSelect');
        const multiRow = $('multiRow');
        const multiAgents = $('multiAgents');
        const runBtn = $('runBtn');
        const result = $('result');
        const resultMeta = $('resultMeta');
        const agentList = $('agentList');
        const taskQueue = $('taskQueue');
        const logList = $('logList');
        const msgList = $('msgList');
        
        let isRunning = false;
        
        // ========== API ==========
        async function api(endpoint, options = {}) {
            const res = await fetch(endpoint, {
                headers: { 'Content-Type': 'application/json' },
                ...options
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return res.json();
        }
        
        async function executeTask(task, agent, priority, mode, multi) {
            return api('/run', {
                method: 'POST',
                body: JSON.stringify({ 
                    task, 
                    agent, 
                    priority: parseInt(priority),
                    chain: mode === 'chain',
                    plan: mode === 'plan',
                    multi: multi || ''
                })
            });
        }
        
        async function fetchStatus() { return api('/status'); }
        async function fetchTasks() { return api('/tasks'); }
        async function fetchAgents() { return api('/agents'); }
        async function fetchLogs() { return api('/logs'); }
        async function fetchMessages() { return api('/messages'); }
        
        // ========== Render ==========
        function renderStatus(data) {
            $('statAgents').textContent = data.agents ?? 0;
            $('statActive').textContent = data.active ?? 0;
            $('statPending').textContent = data.pending ?? 0;
            $('statRunning').textContent = data.running ?? 0;
            $('statTokens').textContent = data.tokens ?? 0;
        }
        
        function renderTasks(data) {
            const tasks = data.tasks || [];
            $('queueCount').textContent = tasks.length > 0 ? `(${tasks.length})` : '';
            
            if (tasks.length === 0) {
                taskQueue.innerHTML = '<div class="log-empty">暂无任务</div>';
                return;
            }
            
            taskQueue.innerHTML = tasks.map(t => {
                const statusClass = 'status-' + t.status;
                const desc = t.description.length > 60 ? t.description.substring(0, 60) + '...' : t.description;
                return `
                    <div class="task-item">
                        <span class="task-status ${statusClass}">${t.status}</span>
                        <span class="task-id">#${t.task_id}</span>
                        <div class="task-desc">${desc}</div>
                    </div>
                `;
            }).join('');
        }
        
        function renderAgents(data) {
            const agents = data.agents || [];
            
            agentList.innerHTML = agents.map(agent => {
                const statusClass = agent.status === 'idle' ? 'agent-idle' : 
                                  agent.status === 'running' ? 'agent-running' : 'agent-waiting';
                return `<span class="agent-tag ${statusClass}">${agent.id}</span>`;
            }).join('') || '<div class="log-empty">暂无 Agent</div>';
        }
        
        function renderMessages(data) {
            const msgs = data.messages || [];
            $('msgCount').textContent = msgs.length > 0 ? `(${msgs.length})` : '';
            
            if (msgs.length === 0) {
                msgList.innerHTML = '<div class="log-empty">暂无消息</div>';
                return;
            }
            
            msgList.innerHTML = msgs.slice().reverse().slice(0, 20).map(m => {
                const icon = { task_submitted: '📥', task_completed: '✅', task_failed: '❌', 
                           agent_created: '🤖', agent_destroyed: '👋' }[m.type] || '📋';
                return `<div class="log-item">${icon} <strong>${m.type}</strong>: ${JSON.stringify(m.data).substring(0, 50)}</div>`;
            }).join('');
        }
        
        function renderLogs(data) {
            const logs = data.logs || [];
            $('logCount').textContent = logs.length > 0 ? `(${logs.length})` : '';
            
            if (logs.length === 0) {
                logList.innerHTML = '<div class="log-empty">暂无日志</div>';
                return;
            }
            
            logList.innerHTML = logs.slice().reverse().slice(0, 10).map(log => {
                const statusClass = log.status === 'running' ? 'status-running' : 
                                 log.status === 'completed' ? 'status-completed' : 'status-failed';
                const task = log.task.length > 40 ? log.task.substring(0, 40) + '...' : log.task;
                return `
                    <div class="log-item">
                        <span class="log-time">${log.start_time}</span>
                        <span class="task-status ${statusClass}">${log.status}</span>
                        ${task}
                    </div>
                `;
            }).join('');
        }
        
        function renderResult(data) {
            if (data.error) {
                result.className = 'result result-error';
                result.textContent = '❌ 错误: ' + data.error;
                resultMeta.textContent = '';
                return;
            }
            
            result.className = 'result result-success';
            let output = data.result || '';
            if (data.duration) {
                output = `⏱️ ${data.duration.toFixed(2)}s | 📊 ${data.tokens} tokens\n\n` + output;
            }
            result.textContent = output;
            
            // 渲染协作流程 - 强制刷新
            console.log('DEBUG data: ' + JSON.stringify(data).substring(0, 300));
            console.log('DEBUG steps:', data.steps);
            console.log('DEBUG steps length:', data.steps ? data.steps.length : 'no steps');
            if (data.steps && data.steps.length > 0) {
                renderSteps(data.steps);
            } else {
                document.getElementById('stepList').innerHTML = '<div class="log-empty">无步骤数据</div>';
            }
        }
        
        function renderSteps(steps) {
            const stepDiv = $('stepList');
            const stepCount = $('stepCount');
            
            if (!steps || steps.length === 0) {
                stepDiv.innerHTML = '<div class="log-empty">执行多 Agent 任务时显示</div>';
                stepCount.textContent = '';
                return;
            }
            
            stepCount.textContent = `(${steps.length} 步)`;
            
            const roleIcon = {
                'leader': '👑', 'coder': '💻', 'researcher': '🔍',
                'writer': '✍️', 'analyst': '📐', 'general': '💬'
            };
            
            const roleName = {
                'leader': '领导', 'coder': '程序员', 'researcher': '研究员',
                'writer': '写作者', 'analyst': '分析师', 'general': '通用'
            };
            
            stepDiv.innerHTML = steps.map(s => {
                const statusClass = s.status === 'running' ? 'step-running' : 'step-completed';
                const icon = s.status === 'running' ? '🔄' : '✅';
                const badgeClass = 'step-badge-' + s.step;
                
                const isPlan = s.type === 'plan';
                const isDispatch = s.type === 'harness_dispatch' || s.agent;
                const receivedTask = s.received_task || s.input || s.action || '';
                const systemPrompt = s.system_prompt || '';
                const llmResponse = s.llm_response || s.output || '';
                const processed = s.processed || s.raw_plan || '';
                
                let badgeColor = 'step-badge-' + s.step;
                let badgeText = '🔢 步骤 ' + s.step;
                let headerBg = '';
                
                if (isPlan) {
                    badgeText = '📋 计划 ' + s.stage;
                    badgeColor = 'step-badge-plan';
                    headerBg = 'background: linear-gradient(135deg, #fef3c7, #fde68a);';
                } else if (isDispatch) {
                    badgeText = '📤 分发 ' + s.stage;
                    badgeColor = 'step-badge-dispatch';
                    headerBg = 'background: linear-gradient(135deg, #dbeafe, #bfdbfe);';
                }
                
                return `
                    <div class="step-detail">
                        <div class="step-header" style="${headerBg}">
                            <span class="step-badge ${badgeColor}">${badgeText}</span>
                            <span class="step-role">${roleIcon[s.agent] || '🤖'} ${roleName[s.agent] || s.agent}</span>
                            <span class="step-status-badge ${statusClass}">${icon} ${s.status}</span>
                        </div>
                        <div class="step-body">
                            <div class="step-section">
                                <div class="step-label">📥 1. Harness 分配的任务</div>
                                <div class="step-content-box">${escapeHtml(receivedTask)}</div>
                            </div>
                            <div class="step-section">
                                <div class="step-label">🎯 2. Agent 系统提示词</div>
                                <div class="step-content-box" style="max-height:80px">${escapeHtml(systemPrompt)}</div>
                            </div>
                            <div class="step-section">
                                <div class="step-label">🤖 3. 大模型返回结果</div>
                                <div class="step-content-box">${escapeHtml(llmResponse)}</div>
                            </div>
                            <div class="step-section">
                                <div class="step-label">📤 4. 返回给 Harness 的内容</div>
                                <div class="step-content-box">${escapeHtml(processed)}</div>
                            </div>
                        </div>
                    </div>
                `;
            }).join('<div class="flow-arrow">⬇️</div>');
        }
        
        function escapeHtml(text) {
            if (!text) return '';
            return text.replace(/&/g, '&amp;')
                       .replace(/</g, '&lt;')
                       .replace(/>/g, '&gt;')
                       .replace(/"/g, '&quot;')
                       .replace(/'/g, '&#039;');
        }
        async function handleSubmit(e) {
            e.preventDefault();
            
            if (isRunning) return;
            
            const task = taskInput.value.trim();
            if (!task) { alert('请输入任务描述'); return; }
            
            const agent = agentSelect.value;
            const priority = prioritySelect.value;
            const mode = modeSelect ? modeSelect.value : 'single';
            const multi = multiAgents ? multiAgents.value : '';
            
            isRunning = true;
            runBtn.disabled = true;
            runBtn.textContent = '执行中...';
            result.textContent = '⏳ 正在执行: ' + task;
            resultMeta.textContent = '';
            
            try {
                const data = await executeTask(task, agent, priority, mode, multi);
                renderResult(data);
            } catch (e) {
                result.className = 'result result-error';
                result.textContent = '❌ 网络错误: ' + e.message;
            }
            
            isRunning = false;
            runBtn.disabled = false;
            runBtn.textContent = '🚀 执行';
            
            refresh();
        }
        
async function refresh() {
            try {
                const [status, tasks, agents, messages, logs] = await Promise.all([
                    fetchStatus(), fetchTasks(), fetchAgents(), fetchMessages(), fetchLogs()
                ]);
                
                renderStatus(status);
                renderTasks(tasks);
                renderAgents(agents);
                renderMessages(messages);
                renderLogs(logs);
            } catch (e) {
                console.error('刷新失败:', e);
            }
        }
        
function init() {
            taskForm.addEventListener('submit', handleSubmit);
            
            // 模式切换
            if (modeSelect) {
                modeSelect.addEventListener('change', function() {
                    if (this.value === 'chain') {
                        if (multiRow) multiRow.style.display = 'none';
                    } else {
                        if (multiRow) multiRow.style.display = 'none';
                    }
                });
            }
            
            setInterval(refresh, 3000);
            refresh();
        }
        
        init();
    })();
    </script>
</body>
</html>"""


# 日志目录 - 相对路径，基于脚本所在目录
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_SLICE = 5


def get_log_slice():
    now = datetime.now()
    minute = (now.minute // LOG_SLICE) * LOG_SLICE
    return now.strftime(f"%Y%m%d_%H-{minute:02d}")


def save_logs():
    log_file = LOG_DIR / f"harness_{get_log_slice()}.json"
    data = {"requests": list(request_logs.values()), "messages": []}
    log_file.write_text(json.dumps(data, ensure_ascii=False))


# ========== HTTP Handler ==========
class RequestHandler(BaseHTTPRequestHandler):
    
    def log_message(self, format, *args):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]}")
    
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode('utf-8'))
        
        elif self.path == '/status': self.send_json(self.get_status())
        elif self.path == '/tasks': self.send_json(self.get_tasks())
        elif self.path == '/agents': self.send_json(self.get_agents())
        elif self.path == '/logs': self.send_json(self.get_logs())
        elif self.path == '/messages': self.send_json(self.get_messages())
        elif self.path == '/execution': self.send_json(self.get_execution())
        elif self.path.startswith('/execution/'): self.send_json(self.get_execution_detail())
        
        else: self.send_error(404)
    
    def do_POST(self):
        if self.path == '/run':
            self.handle_run()
        elif self.path == '/execute':
            self.handle_execute()
        elif self.path == '/execute-next':
            self.handle_execute_next()
        else: self.send_error(404)
    
    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def get_status(self):
        if not _harness:
            return {"status": "error", "message": "Harness not initialized"}
        
        s = _harness.get_system_status()
        return {
            "status": s.get("status"),
            "version": s.get("version"),
            "agents": s.get("total_agents"),
            "active": s.get("active_agents"),
            "pending": s.get("pending_tasks"),
            "running": s.get("running_tasks"),
            "completed": s.get("completed_tasks"),
            "failed": s.get("failed_tasks"),
            "tokens": s.get("total_tokens")
        }
    
    def get_tasks(self):
        if not _harness:
            return {"tasks": []}
        return {"tasks": _harness.scheduler.list_tasks()}
    
    def get_agents(self):
        if not _harness:
            return {"agents": []}
        s = _harness.get_system_status()
        return {"agents": [
            {"id": aid, "role": st.get("role"), "status": st.get("status"), "current_task": st.get("current_task")}
            for aid, st in s.get("agents", {}).items()
        ]}
    
    def get_logs(self):
        return {"logs": list(request_logs.values())}
    
    def get_messages(self):
        if not _harness:
            return {"messages": []}
        return {"messages": _harness.get_messages()}
    
    def get_execution(self):
        """获取当前执行状态"""
        if not _loop_manager:
            return {"executions": []}
        return {"executions": _loop_manager.flow_tracker.get_all_executions()}
    
    def get_execution_detail(self):
        """获取执行详情"""
        record_id = self.path.split('/')[-1]
        if not _loop_manager:
            return {"error": "Loop manager not initialized"}
        record = _loop_manager.flow_tracker.get_record(record_id)
        if not record:
            return {"error": "Execution not found"}
        return record.to_display()
    
    def handle_execute(self):
        """开始动态执行循环"""
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            self.send_json({"error": "请求为空"})
            return
        
        body = self.rfile.read(content_length).decode('utf-8')
        
        try:
            data = json.loads(body)
        except:
            self.send_json({"error": "JSON 解析失败"})
            return
        
        task = data.get("task", "").strip()
        if not task:
            self.send_json({"error": "任务为空"})
            return
        
        # 开始执行
        record_id = _loop_manager.start(task)
        
        # 拆分计划
        plan = _loop_manager.decompose_plan()
        
        self.send_json({
            "record_id": record_id,
            "status": "planning",
            "task": task,
            "plan": [p.to_dict() for p in plan]
        })
    
    def handle_execute_next(self):
        """执行下一步"""
        result = _loop_manager.execute_next()
        self.send_json(result)
    
    def handle_run(self):
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            self.send_json({"error": "请求为空"})
            return
        
        body = self.rfile.read(content_length).decode('utf-8')
        
        try:
            data = json.loads(body)
        except:
            self.send_json({"error": "JSON 解析失败"})
            return
        
        task = data.get("task", "").strip()
        agent = data.get("agent", "auto")
        priority = data.get("priority", 1)
        is_chain = data.get("chain", False)
        is_plan = data.get("plan", False) or data.get("mode") == "plan"
        multi = data.get("multi", "")  # 逗号分隔的 agents
        
        if not task:
            self.send_json({"error": "任务为空"})
            return
        
        request_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        request_logs[request_id] = {
            "id": request_id,
            "task": task,
            "agent": agent,
            "priority": priority,
            "status": "running",
            "start_time": timestamp,
            "tokens": 0
        }
        
        start_time = time.time()
        
        try:
            # 提交任务
            result = None
            steps = []
            
            try:
                if is_plan:
                    # 计划+执行
                    result = _harness.execute_with_plan(task)
                    steps = result.steps if hasattr(result, 'steps') else []
                    print(f"[DEBUG] is_plan=True, result.steps={len(steps)}")
                elif is_chain:
                    # 链式执行
                    result = _harness.execute_chain(task)
                    if hasattr(result, 'steps'):
                        steps = result.steps
                elif multi:
                    # 多 Agent 执行
                    agents = [a.strip() for a in multi.split(',')]
                    result_dict = _harness.execute_multi_agent(task, agents)
                    # 获取 combined 结果
                    result = result_dict.get('_combined')
                    if result and hasattr(result, 'steps'):
                        steps = result.steps
                else:
                    # 单 Agent 执行
                    task_id = _harness.submit_task(
                        description=task,
                        agent_id=agent,
                        priority=TaskPriority(priority)
                    )
                    result = _harness.execute_task_sync(task_id)
            except Exception as e:
                import traceback
                print(f"[ERROR] 执行失败: {e}")
                print(traceback.format_exc())
                raise
            
            duration = time.time() - start_time
            
            request_logs[request_id].update({
                "status": result.status if result else "failed",
                "duration": duration,
                "result": result.result if result else "No result",
                "tokens": result.output_tokens if result else 0
            })
            
            # 确保 steps 是列表
            if not steps and hasattr(result, 'steps'):
                steps = result.steps
            
            save_logs()
            
            self.send_json({
                "request_id": request_id,
                "task_id": task_id if (not is_chain and not multi and not is_plan) else task[:8],
                "status": result.status if result else "failed",
                "result": result.result if result else "No result",
                "agent": multi if multi else (agent if not is_chain else ("plan" if is_plan else "chain")),
                "priority": priority,
                "duration": duration,
                "tokens": result.output_tokens if result else 0,
                "steps": steps,
                "plan_mode": is_plan
            })
            
        except Exception as e:
            request_logs[request_id].update({"status": "error", "error": str(e)})
            save_logs()
            self.send_json({"request_id": request_id, "error": str(e)})


# ========== Server ==========
def run_server(port: int = 8080):
    global _harness, _loop_manager
    _harness = OpenClawHarness()
    _loop_manager = create_execution_loop(_harness)
    
    print(f"""
=========================================================
  OpenClaw Multi-Agent Harness v3.0
  http://0.0.0.0:{port}
=========================================================
""")
    print("Agents:")
    for aid in _harness.agents:
        print(f"  - {aid}")
    print()
    print(f"Access http://localhost:{port}")
    
    server = HTTPServer(("0.0.0.0", port), RequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped")
        server.shutdown()


if __name__ == '__main__':
    port = 8080
    if len(sys.argv) > 1 and sys.argv[1] == '-p':
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
    run_server(port)