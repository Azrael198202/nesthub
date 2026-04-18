问题1 ：
agent_builder.py 中文的prompt
intent_policy.json 
semantic_policy.json
中的业务数据需要保留吗，应该是nesthub运行时产生

问题2：
local_model_registry.json 这个内容过少，应该有很多本地模型

问题3 ：
semantic_policy_memory.sqlite3 里面有业务相关数据吗

问题4 ：
demo_execution_handler_plugin.py 需要保留吗

问题5：
execution_coordinator.py
def _extract_named_actor(self, text: str) -> str | None:
    match = re.match(r"^(?:记录|添加|保存)?([\u4e00-\u9fffA-Za-z]{2,4})(?=今天|昨天|本周|下周|\d{1,2}月\d{1,2}[号日]|去|到|前往)", text.strip())
    if match:
        return match.group(1)
    return None

_extract_explicit_date
_extract_relative_week_date
_normalize_yes_no
出现关键字。


问题6：
information_agent_service.py 
information_profile_signal_analyzer.py 
intent_analyzer.py
的作用是什么，需要保留吗。

问题7：

intent_analyzer.py 意图分析，认为应该建立一个意图的知识库，每次判定是意图的时候，将其写入。而不是应写文字。

总结，文字类的关键字，不要出现在代码中，以为多语言，针对关键字无法在程序中对应。
所以要根据实际需要，nesthub在运行的过程中，将使用的关键字，写入到由他生成的代码中并维护，这样就能保证核心代码不会变，
其他的都是自动，动态生成。

---

2026-04-17 继续进展：

1. `semantic_policy.json` 已经收缩为 schema-only seed，不再内置预算/家庭/提醒等业务词表。
2. `ExecutionCoordinator` 已改为先加载内部 schema 默认值，再叠加 `semantic_policy.json` 和 runtime memory overlay。
3. 预算相关 API / E2E 回归不再依赖仓库主策略文件中的中文语义样本，测试改为显式注入样本语义。
4. `intent_policy.json` 仍保持最小骨架；`intent_analyzer.py` 的 runtime intent knowledge 写入路径已保留并可继续扩展。
5. 当前未完成项：
    - parser rule families 还没有全面做主动学习
    - runtime semantic knowledge 还没有治理机制（decay/dedup/eviction）
    - 新 locale 的首用 bootstrap 还没做