#!/usr/bin/env python3
"""
OpenClaw Harness CLI
命令行入口
"""
import sys
import argparse
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent))

from harness import OpenClawHarness, TaskPriority, Task


def run_task(args):
    """执行任务"""
    h = OpenClawHarness(verbose=args.verbose)
    
    priority = TaskPriority(args.priority) if args.priority else TaskPriority.NORMAL
    
    if args.chain:
        # 链式执行
        result = h.execute_chain(args.task)
        print(f"\n{'='*60}")
        print(f"📝 任务: {args.task}")
        print(f"{'='*60}")
        print(result.result)
        print(f"{'='*60}")
        print(f"⏱️  耗时: {result.duration:.2f}s | 📊 {result.output_tokens} tokens")
        
    elif args.multi:
        # 多 Agent 执行
        agents = args.multi.split(',')
        results = h.execute_multi_agent(args.task, agents)
        print(f"\n{'='*60}")
        print(f"📝 任务: {args.task}")
        print(f"🤖 Agent: {agents}")
        print(f"{'='*60}")
        for agent_id, r in results.items():
            print(f"\n--- {agent_id} ---")
            print(r.result)
        print(f"{'='*60}")
        
    else:
        # 单 Agent 执行
        task_id = h.submit_task(
            args.task, 
            agent_id=args.agent or "auto",
            priority=priority,
            timeout=args.timeout
        )
        
        result = h.execute_task_sync(task_id)
        
        print(f"\n{'='*60}")
        print(f"📝 任务: {args.task}")
        print(f"🤖 Agent: {result.agent_used}")
        print(f"{'='*60}")
        print(result.result)
        print(f"{'='*60}")
        print(f"⏱️  耗时: {result.duration:.2f}s | 📊 {result.output_tokens} tokens")
        
    return 0


def status(args):
    """查看状态"""
    h = OpenClawHarness()
    s = h.get_system_status()
    
    print(f"\n{'='*60}")
    print(f"🤖 OpenClaw Harness v{s['version']}")
    print(f"{'='*60}")
    print(f"📊 Agent: {s['total_agents']} (活跃: {s['active_agents']})")
    print(f"📋 任务: {s['total_tasks']} (待执行: {s['pending_tasks']} / 进行中: {s['running_tasks']})")
    print(f"🎯 Token: {s['total_tokens']}")
    
    print(f"\n🤖 Agent 状态:")
    for aid, ast in s['agents'].items():
        status_icon = "🟢" if ast['status'] == 'idle' else "🟡"
        print(f"  {status_icon} {aid:12} ({ast['role']}) - {ast['status']}")
        if ast.get('current_task'):
            print(f"      当前任务: {ast['current_task']}")
    
    return 0


def agents_list(args):
    """列出 Agent"""
    h = OpenClawHarness()
    s = h.get_system_status()
    
    print(f"\n{'='*60}")
    print(f"🤖 可用 Agent")
    print(f"{'='*60}")
    
    role_names = {
        "leader": "👑 领导",
        "coder": "💻 程序员",
        "researcher": "🔍 研究员",
        "writer": "✍️ 写作者",
        "analyst": "📐 分析师",
        "general": "💬 通用",
    }
    
    for aid, ast in s['agents'].items():
        role = role_names.get(ast['role'], ast['role'])
        print(f"  • {aid:12} {role}")
        print(f"      状态: {ast['status']} | 已完成: {ast['tasks_completed']}")
    
    return 0


def queue_list(args):
    """查看队列"""
    h = OpenClawHarness()
    tasks = h.scheduler.list_tasks()
    
    if not tasks:
        print("📋 任务队列为空")
        return 0
    
    print(f"\n{'='*60}")
    print(f"📋 任务队列 ({len(tasks)} 个任务)")
    print(f"{'='*60}")
    
    for t in tasks:
        status_icon = {
            "pending": "⏳",
            "waiting": "🔄", 
            "running": "🔵",
            "completed": "✅",
            "failed": "❌"
        }.get(t['status'], "❓")
        
        print(f"{status_icon} #{t['task_id']} [{t['status']}] {t['description'][:50]}")
        print(f"    分配给: {t['assigned_to']} | 优先级: {t['priority']}")
    
    return 0


def messages(args):
    """查看消息"""
    h = OpenClawHarness()
    msgs = h.get_messages(limit=args.limit)
    
    if not msgs:
        print("📭 暂无消息")
        return 0
    
    print(f"\n{'='*60}")
    print(f"🔔 消息 ({len(msgs)} 条)")
    print(f"{'='*60}")
    
    icon = {
        "task_submitted": "📥",
        "task_completed": "✅",
        "task_failed": "❌",
        "agent_created": "🤖",
        "agent_destroyed": "👋"
    }
    
    for m in msgs:
        ico = icon.get(m['type'], "📋")
        print(f"{ico} [{m['timestamp'][:8]}] {m['type']}")
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="OpenClaw Harness CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 run.py run "编写排序算法"
  python3 run.py run "写一篇文章" -a writer
  python3 run.py run "分析数据" --priority 3
  python3 run.py run "开发项目" -c
  python3 run.py run "复杂任务" -m coder,writer,analyst
  python3 run.py status
  python3 run.py agents
  python3 run.py queue
  python3 run.py messages
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # run 命令
    run_parser = subparsers.add_parser("run", help="执行任务")
    run_parser.add_argument("task", help="任务描述")
    run_parser.add_argument("-a", "--agent", help="指定 Agent")
    run_parser.add_argument("-p", "--priority", type=int, help="优先级 0-3")
    run_parser.add_argument("-t", "--timeout", type=float, default=300, help="超时时间")
    run_parser.add_argument("-c", "--chain", action="store_true", help="链式执行")
    run_parser.add_argument("-m", "--multi", help="多 Agent (逗号分隔)")
    run_parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")
    run_parser.set_defaults(func=run_task)
    
    # status 命令
    status_parser = subparsers.add_parser("status", help="查看系统状态")
    status_parser.set_defaults(func=status)
    
    # agents 命令
    agents_parser = subparsers.add_parser("agents", help="列出 Agent")
    agents_parser.set_defaults(func=agents_list)
    
    # queue 命令
    queue_parser = subparsers.add_parser("queue", help="查看任务队列")
    queue_parser.set_defaults(func=queue_list)
    
    # messages 命令
    msg_parser = subparsers.add_parser("messages", help="查看消息")
    msg_parser.add_argument("-n", "--limit", type=int, default=20, help="限制数量")
    msg_parser.set_defaults(func=messages)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())