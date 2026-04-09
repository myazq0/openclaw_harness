#!/usr/bin/env python3
"""
任务验证模块
提供任务 schema 校验、规则验证
"""

from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import re


class ValidationError(Exception):
    """验证错误"""
    pass


class TaskSchema(Enum):
    """任务 schema 类型"""
    CODE = "code"           # 编程任务
    RESEARCH = "research"  # 研究任务
    WRITE = "write"        # 写作任务
    ANALYSIS = "analysis"  # 分析任务
    GENERAL = "general"   # 通用任务


@dataclass
class ValidationRule:
    """验证规则"""
    name: str
    validate: Callable[[str], bool]
    message: str


# ========== 内置规则 ==========

RULES = {
    "min_length": ValidationRule(
        name="min_length",
        validate=lambda t: len(t.strip()) >= 5,
        message="任务描述至少 5 个字符"
    ),
    "max_length": ValidationRule(
        name="max_length",
        validate=lambda t: len(t.strip()) <= 2000,
        message="任务描述最多 2000 个字符"
    ),
    "no_special_chars": ValidationRule(
        name="no_special_chars",
        validate=lambda t: not re.search(r'[<>{}]', t),
        message="任务描述不能包含特殊符号 <> {}"
    ),
    "not_empty": ValidationRule(
        name="not_empty",
        validate=lambda t: len(t.strip()) > 0,
        message="任务描述不能为空"
    ),
}


# ========== Schema 规则 ==========

SCHEMA_KEYWORDS = {
    TaskSchema.CODE: ["代码", "编程", "写程序", "开发", "实现", "function", "class", "def "],
    TaskSchema.RESEARCH: ["研究", "调研", "查", "找", "分析", "调查", "搜索"],
    TaskSchema.WRITE: ["写", "文章", "文档", "报告", "撰写", "创作"],
    TaskSchema.ANALYSIS: ["分析", "数据", "统计", "对比", "评估"],
    TaskSchema.GENERAL: [],
}


# ========== 验证器 ==========

class TaskValidator:
    """任务验证器"""
    
    def __init__(self):
        self.rules: Dict[str, ValidationRule] = RULES.copy()
        self.custom_rules: List[ValidationRule] = []
    
    def add_rule(self, rule: ValidationRule):
        """添加自定义规则"""
        self.custom_rules.append(rule)
    
    def validate(self, task: str, schema: Optional[TaskSchema] = None) -> Dict[str, Any]:
        """验证任务
        
        Returns:
            {
                "valid": bool,
                "errors": [],
                "schema": TaskSchema,
                "suggested_agent": str
            }
        """
        errors = []
        all_rules = list(self.rules.values()) + self.custom_rules
        
        # 执行规则验证
        for rule in all_rules:
            if not rule.validate(task):
                errors.append({
                    "rule": rule.name,
                    "message": rule.message
                })
        
        # 推断 schema
        detected_schema = schema or self._detect_schema(task)
        
        # 推荐 agent
        suggested_agent = self._suggest_agent(detected_schema)
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "schema": detected_schema.value if detected_schema else None,
            "suggested_agent": suggested_agent,
            "task": task[:100]
        }
    
    def _detect_schema(self, task: str) -> Optional[TaskSchema]:
        """检测任务类型"""
        task_lower = task.lower()
        
        scores = {}
        for schema_type, keywords in SCHEMA_KEYWORDS.items():
            if not keywords:
                scores[schema_type] = 0
                continue
            
            score = sum(1 for kw in keywords if kw.lower() in task_lower)
            scores[schema_type] = score
        
        if not scores:
            return TaskSchema.GENERAL
        
        max_score = max(scores.values())
        if max_score == 0:
            return TaskSchema.GENERAL
        
        for schema_type, score in scores.items():
            if score == max_score:
                return schema_type
        
        return TaskSchema.GENERAL
    
    def _suggest_agent(self, schema: TaskSchema) -> str:
        """推荐 Agent"""
        mapping = {
            TaskSchema.CODE: "coder",
            TaskSchema.RESEARCH: "researcher",
            TaskSchema.WRITE: "writer",
            TaskSchema.ANALYSIS: "analyst",
            TaskSchema.GENERAL: "general",
        }
        return mapping.get(schema, "general")
    
    def validate_batch(self, tasks: List[str]) -> List[Dict[str, Any]]:
        """批量验证"""
        return [self.validate(t) for t in tasks]


# ========== CLI ==========

def main():
    import sys
    
    validator = TaskValidator()
    
    if len(sys.argv) < 2:
        print("用法: python3 task_validator.py <任务描述>")
        sys.exit(1)
    
    task = " ".join(sys.argv[1:])
    result = validator.validate(task)
    
    print(f"任务: {task[:50]}...")
    print(f"验证: {'✅ 通过' if result['valid'] else '❌ 失败'}")
    print(f"Schema: {result['schema']}")
    print(f"推荐 Agent: {result['suggested_agent']}")
    
    if result['errors']:
        print("错误:")
        for e in result['errors']:
            print(f"  - {e['message']}")


if __name__ == '__main__':
    main()