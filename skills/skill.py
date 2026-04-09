"""
Skill System - 技能系统
用于注册和调用各种技能
"""
import json
from pathlib import Path
from datetime import datetime

class SkillRegistry:
    def __init__(self, path="skills.json"):
        self.path = Path(path)
        self.skills = self._load()
    
    def _load(self):
        if self.path.exists():
            return json.loads(self.path.read_text())
        # 默认技能
        return {
            "coder": {"name": "Code", "prompt": "You are a coder", "enabled": True},
            "writer": {"name": "Writer", "prompt": "You are a writer", "enabled": True},
            "researcher": {"name": "Researcher", "prompt": "You are a researcher", "enabled": True},
            "analyst": {"name": "Analyst", "prompt": "You are an analyst", "enabled": True}
        }
    
    def _save(self):
        self.path.write_text(json.dumps(self.skills, ensure_ascii=False, indent=2))
    
    def register(self, name, prompt, enabled=True):
        self.skills[name] = {"name": name, "prompt": prompt, "enabled": enabled, "registered": datetime.now().isoformat()}
        self._save()
    
    def list(self):
        return {k: v for k, v in self.skills.items() if v.get("enabled", True)}
    
    def get(self, name):
        return self.skills.get(name, {})

# CLI
if __name__ == "__main__":
    import sys
    s = SkillRegistry()
    if len(sys.argv) > 1:
        if sys.argv[1] == "list":
            for k, v in s.list().items():
                print(f"- {k}: {v.get('prompt', '')[:30)}")
        else:
            print("Usage: skill.py list")
    else:
        print(f"Registered skills: {len(s.skills)}")
