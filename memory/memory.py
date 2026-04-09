"""
Memory System - 记忆系统
用于存储和检索会话历史
"""
import json
from pathlib import Path
from datetime import datetime

class Memory:
    def __init__(self, path="memory.json"):
        self.path = Path(path)
        self.data = self._load()
    
    def _load(self):
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {"sessions": [], "facts": []}
    
    def _save(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))
    
    def add_session(self, task, result, agent):
        session = {
            "id": len(self.data["sessions"]) + 1,
            "task": task,
            "result": result[:200],
            "agent": agent,
            "time": datetime.now().isoformat()
        }
        self.data["sessions"].append(session)
        self._save()
        return session
    
    def get_recent(self, n=10):
        return self.data["sessions"][-n:]
    
    def add_fact(self, fact):
        self.data["facts"].append({"fact": fact, "time": datetime.now().isoformat()})
        self._save()
    
    def search(self, keyword):
        return [s for s in self.data["sessions"] if keyword in s.get("task", "")]

# CLI
if __name__ == "__main__":
    import sys
    m = Memory()
    if len(sys.argv) > 1:
        if sys.argv[1] == "recent":
            for s in m.get_recent(5):
                print(f"[{s['time']}] {s['task'][:50]}")
        elif sys.argv[1] == "search" and len(sys.argv) > 2:
            for s in m.search(sys.argv[2]):
                print(f"[{s['time']}] {s['task']}")
        else:
            print("Usage: memory.py recent|search keyword")
    else:
        print(f"Sessions: {len(m.data['sessions'])}, Facts: {len(m.data['facts'])}")
