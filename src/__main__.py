#!/usr/bin/env python3
"""
OpenClaw 多 Agent Harness 系统
一个生产级的多 Agent 协作框架，支持任务分解、动态 Agent 创建、状态可视化

核心特性：
- 动态 Agent 管理（Lead Agent 根据任务创建/销毁 Agent）
- 任务状态实时展示
- Token 消耗统计
- 支持命令行和 API 调用
"""

import sys
import os
import logging
from pathlib import Path

# 添加 src 路径
sys.path.insert(0, str(Path(__file__).parent))

from src.harness import OpenClawHarness, TaskResult


def setup_logging(verbose: bool = False) -> logging.Logger:
    """设置日志"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    )
    return logging.getLogger("openclaw")


def run_single_task(harness: OpenClawHarness, task: str, agents: str = "auto"):
    """执行单个任务"""
    print(f"\n📋 任务: {task}\n")
    print("=" * 60)
    
    result = harness.execute_task(task, agent_config=agents)
    
    # 打印结果
    print("\n" + "=" * 60)
    print("📊 执行结果")
    print("-" * 60)
    print(f"状态: {result.status}")
    print(f"耗时: {result.duration:.2f}s")
    print(f"Token: 输入 {result.input_tokens} / 输出 {result.output_tokens}")
    print(f"Agent: {result.agent_used}")
    print(f"工具: {', '.join(result.tools_used) if result.tools_used else '-'}")
    
    if result.result:
        print(f"\n📝 结果:")
        print("-" * 60)
        # 限制输出长度
        output = result.result[:2000]
        if len(result.result) > 2000:
            output += "\n... (truncated)"
        print(output)
    
    if result.logs:
        print(f"\n📜 日志 ({len(result.logs)} 条):")
        print("-" * 60)
        for log in result.logs[-10:]:  # 只显示最后 10 条
            print(f"  {log}")


def run_interactive(harness: OpenClawHarness):
    """交互模式"""
    print("\n🚀 进入交互模式 (输入 'quit' 退出)\n")
    
    while True:
        try:
            task = input("> ").strip()
            if not task:
                continue
            if task.lower() in ["quit", "exit", "q"]:
                break
            
            print()
            result = harness.execute_task(task)
            
            print(f"\n✓ 完成 ({result.duration:.2f}s, {result.output_tokens} tokens)")
            if result.result:
                print(f"  {result.result[:500]}")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ 错误: {e}")
    
    print("\n👋 退出")


def run_monitor(harness: OpenClawHarness):
    """监控模式 - 实时显示所有 Agent 状态"""
    import shutil
    
    terminal_width = shutil.get_terminal_size().columns
    
    print("\n📟 进入监控模式 (Ctrl+C 退出)\n")
    
    def print_status():
        status = harness.get_system_status()
        lines = [
            "╔" + "═" * (terminal_width - 2) + "╗",
            f"║ OpenClaw System Status | {datetime.now().strftime('%H:%M:%S')}" + " " * 20 + "║",
            "╠" + "═" * (terminal_width - 2) + "╣",
        ]
        
        # Agent 状态
        for agent_id, state in status.get("agents", {}).items():
            role = state.get("role", "?")
            task = state.get("current_task", "-")
            tokens = state.get("tokens_used", 0)
            lines.append(f"║ {agent_id:12} | {role:10} | {task[:30]:30} | {tokens:6} tokens ║")
        
        lines.append("╚" + "═" * (terminal_width - 2) + "╝")
        
        print("\n".join(lines))
    
    # 启动状态监控
    harness.start_monitor(callback=print_status)
    
    try:
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        harness.stop_monitor()
        print("\n👋 监控结束")


def run_cli():
    """命令行运行"""
    from datetime import datetime
    import argparse
    
    parser = argparse.ArgumentParser(description="OpenClaw Multi-Agent Harness")
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    
    # run 子命令
    run_parser = subparsers.add_parser("run", help="运行任务")
    run_parser.add_argument("task", nargs="?", help="任务描述", default=None)
    run_parser.add_argument("-a", "--agents", default="auto", help="Agent 选择")
    run_parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")
    
    # status 子命令
    status_parser = subparsers.add_parser("status", help="显示系统状态")
    
    # monitor 子命令
    monitor_parser = subparsers.add_parser("monitor", help="监控模式")
    
    # interactive 子命令
    interactive_parser = subparsers.add_parser("interactive", help="交互模式")
    interactive_parser.add_argument("-a", "--agents", default="auto", help="Agent 选择")
    
    args = parser.parse_args()
    logger = setup_logging(getattr(args, 'verbose', False))
    
    # 初始化 Harness
    harness = OpenClawHarness(verbose=logger.level == logging.DEBUG)
    
    # 执行
    if args.command == "run" or args.command is None:
        task = args.task if args.task else input("任务: ").strip()
        if task:
            run_single_task(harness, task, args.agents if hasattr(args, 'agents') else 'auto')
        else:
            print("请输入任务或使用: python -m src run \"任务描述\"")
    
    elif args.command == "status":
        status = harness.get_system_status()
        print(f"\n📊 系统状态")
        print(f"  Agent: {status['total_agents']}")
        print(f"  活跃: {status['active_agents']}")
        print(f"  任务: {status['total_tasks']}")
        print(f"  Token: {status['total_tokens']}")
    
    elif args.command == "monitor":
        run_monitor(harness)
    
    elif args.command == "interactive":
        run_interactive(harness)
    
    else:
        # 默认：显示状态
        status = harness.get_system_status()
        print(f"\n📊 系统状态")
        print(f"  Agent: {status['total_agents']}")
        print(f"  活跃: {status['active_agents']}")
        print(f"\n💡 使用: python -m src run \"任务\"")


import time
if __name__ == "__main__":
    run_cli()