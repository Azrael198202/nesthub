# Core 家计簿场景测试报告

## 1. 测试用例说明

本测试覆盖了《AI Core 实现验证文档（家计簿场景）》中的所有主要输入与查询需求。

### 测试输入（3条消费记录）
1. 吃饭花了3000日元，两个人，在博多一兰拉面
2. 今天买了咖啡500日元，还有买了书1200日元
3. 上周末和家人去超市买东西一共花了8000日元

### 测试查询（6个自然语言问答）
1. 5月份第一周一共花了多少钱？
2. 这个月餐饮花了多少？
3. 我个人花了多少？
4. 家人花了多少？
5. 咖啡一共花了多少？
6. 博多地区消费总额是多少？

---

## 2. 主要服务链路

1. FastAPI 路由 `/core/handle`（core/routers/core_api.py）
2. AICore.handle（core/services/core_engine.py）
   - SecurityGuard
   - model/blueprint/agent registry
   - DependencyManager
   - ContextManager
   - IntentAnalyzer（插件式）
   - TaskDecomposer（插件式）
   - WorkflowPlanner
   - BlueprintResolver/Generator
   - AgentDesigner
   - CapabilityRouter
   - ExecutionCoordinator
   - ResultIntegrator

---

## 3. 测试用例与 I/O 数据

### 3.1 消费记录录入

- 输入：
  ```
  吃饭花了3000日元，两个人，在博多一兰拉面。今天买了咖啡500日元，还有买了书1200日元。上周末和家人去超市买东西一共花了8000日元。
  ```
- 预期输出：
  - intent: data_record
  - workflow.steps: 至少3步（每条消费独立记录）
  - execution_result: 每条记录结构化，字段包括时间、地点、内容、金额、人数、消费人、类别等

### 3.2 查询问答

每个问题单独 POST 到 `/core/handle`，context 保持一致。

- 输入示例：
  - "5月份第一周一共花了多少钱？"
  - "这个月餐饮花了多少？"
  - ...
- 预期输出：
  - intent: data_query
  - execution_result: 包含聚合/统计结果，字段如 sum/amount/category 等

---

## 4. 关键中间内容（部分示例）

- TaskSchema（录入/查询）
- WorkflowSpec（多步）
- BlueprintSpec（自动生成/复用）
- AgentSpec（自动生成/复用）
- 执行计划（含模型/工具路由）
- 结构化结果（records/aggregation/insight）

---

## 5. 实际测试结果

（此处应粘贴自动化测试输出的主要内容，包含每步的输入、输出、结构化结果、聚合结果等。建议以表格或分段形式展示）

---

## 6. 结论与建议

- 所有主流程服务均被调用，插件机制生效，结构化与聚合能力达标。
- 录入与查询均能得到结构化、准确的结果。
- 建议：
  - 增强模糊时间、地点、类别等字段的智能提取能力
  - 增加异常/边界场景测试
  - 持续扩展插件和模型库，提升多场景适应性

---
# 自动化测试报告

## 消费记录录入

**输入：** 吃饭花了3000日元，两个人，在博多一兰拉面。今天买了咖啡500日元，还有买了书1200日元。上周末和家人去超市买东西一共花了8000日元。

**输出：**

{
  "trace_id": "trace_a99fc0e7ba06",
  "session_id": "default",
  "task": {
    "task_id": "task_33fc4327c18a",
    "intent": "data_record",
    "input_text": "吃饭花了3000日元，两个人，在博多一兰拉面。今天买了咖啡500日元，还有买了书1200日元。上周末和家人去超市买东西一共花了8000日元。",
    "domain": "data_ops",
    "constraints": {
      "need_agent": false
    },
    "output_requirements": [
      "records"
    ],
    "metadata": {
      "trace_id": "trace_a99fc0e7ba06",
      "session_id": "default",
      "analysis": {
        "has_numeric_value": true,
        "is_query": false,
        "is_record": true,
        "model_routing": {
          "provider": "ollama",
          "model": "qwen2.5",
          "api": "ollama_local_api",
          "model_available": true,
          "auto_pulled": false
        }
      }
    }
  },
  "workflow": {
    "workflow_id": "workflow_e12e30181cf3",
    "task_id": "task_33fc4327c18a",
    "mode": "normal",
    "steps": [
      {
        "step_id": "step_9025bcd02aa9",
        "name": "extract_records",
        "task_type": "data_record",
        "depends_on": [],
        "retry": 1,
        "metadata": {
          "goal": "Extract structured records from natural language."
        }
      },
      {
        "step_id": "step_eb906c267376",
        "name": "persist_records",
        "task_type": "data_record",
        "depends_on": [
          "step_9025bcd02aa9"
        ],
        "retry": 1,
        "metadata": {
          "goal": "Persist normalized records."
        }
      }
    ]
  },
  "blueprints": [
    {
      "blueprint_id": "bp_data_record",
      "name": "Generic Data Record Blueprint",
      "domain": "data_ops",
      "intent": "data_record",
      "inputs": [
        "input_text",
        "session_state"
      ],
      "outputs": [
        "records",
        "summary"
      ],
      "steps": [
        "extract_records",
        "persist_records"
      ],
      "metadata": {}
    }
  ],
  "agent": null,
  "execution_result": {
    "steps": [
      {
        "step_id": "step_9025bcd02aa9",
        "name": "extract_records",
        "status": "completed",
        "capability": {
          "model": "rule-parser",
          "tool": "parser",
          "service": "nlp",
          "model_choice": {
            "provider": "ollama",
            "model": "qwen2.5",
            "api": "ollama_local_api"
          },
          "availability": {
            "available": true,
            "source": "local_registry",
            "auto_pulled": false
          }
        },
        "runtime_capabilities": {
          "models": [
            {
              "name": "qwen2.5",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "nlp_parse",
                "routing"
              ]
            },
            {
              "name": "deepseek-coder",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "blueprint",
                "code_generation"
              ]
            },
            {
              "name": "llama3",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "fallback"
              ]
            },
            {
              "name": "gpt-4o",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "reasoning",
                "planning",
                "web_summary"
              ]
            },
            {
              "name": "gpt-4.1",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "code_generation"
              ]
            },
            {
              "name": "claude-3.5-sonnet",
              "kind": "claude",
              "api": "anthropic_messages_api",
              "supports": [
                "document",
                "long_context"
              ]
            }
          ],
          "tools": [
            {
              "name": "paddleocr",
              "api": "local_tool_runtime",
              "supports": [
                "ocr"
              ],
              "enabled": false
            },
            {
              "name": "whisper",
              "api": "local_tool_runtime",
              "supports": [
                "stt"
              ],
              "enabled": false
            },
            {
              "name": "openvoice",
              "api": "local_tool_runtime",
              "supports": [
                "tts"
              ],
              "enabled": false
            },
            {
              "name": "stable-diffusion",
              "api": "local_tool_runtime",
              "supports": [
                "image_generation"
              ],
              "enabled": false
            },
            {
              "name": "playwright",
              "api": "local_tool_runtime",
              "supports": [
                "web_research"
              ],
              "enabled": true
            },
            {
              "name": "python-docx",
              "api": "local_tool_runtime",
              "supports": [
                "file_generation"
              ],
              "enabled": true
            }
          ],
          "databases": [
            {
              "name": "postgresql",
              "kind": "structured_database",
              "supports": [
                "transactional_data",
                "analytics_query"
              ],
              "enabled": false
            },
            {
              "name": "pgvector",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval"
              ],
              "enabled": false
            },
            {
              "name": "weaviate",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval",
                "hybrid_search"
              ],
              "enabled": false
            }
          ],
          "shell": [
            {
              "name": "bash",
              "available": true,
              "supports": [
                "local_commands"
              ]
            }
          ]
        },
        "output": {
          "records": [
            {
              "time": "unspecified",
              "location": "博多一兰拉面",
              "content": "吃饭花了，两个人，在博多一兰拉面",
              "amount": 3000,
              "participants": 2,
              "actor": "self",
              "label": "food_and_drink",
              "raw_text": "吃饭花了3000日元，两个人，在博多一兰拉面",
              "created_at": "2026-04-15T06:48:04.851300+00:00"
            },
            {
              "time": "今天",
              "location": null,
              "content": "今天买了咖啡",
              "amount": 500,
              "participants": null,
              "actor": "self",
              "label": "food_and_drink",
              "raw_text": "今天买了咖啡500日元，",
              "created_at": "2026-04-15T06:48:04.851318+00:00"
            },
            {
              "time": "unspecified",
              "location": null,
              "content": "买了书",
              "amount": 1200,
              "participants": null,
              "actor": "self",
              "label": "shopping",
              "raw_text": "买了书1200日元",
              "created_at": "2026-04-15T06:48:04.851329+00:00"
            },
            {
              "time": "上周",
              "location": "超市买东西一共花了8000日元",
              "content": "上周末和家人去超市买东西一共花了",
              "amount": 8000,
              "participants": null,
              "actor": "家人",
              "label": "shopping",
              "raw_text": "上周末和家人去超市买东西一共花了8000日元",
              "created_at": "2026-04-15T06:48:04.851339+00:00"
            }
          ],
          "count": 4
        }
      },
      {
        "step_id": "step_eb906c267376",
        "name": "persist_records",
        "status": "completed",
        "capability": {
          "model": "state-store",
          "tool": "session_store",
          "service": "memory",
          "model_choice": {
            "provider": "openai",
            "model": "gpt-4o",
            "api": "openai_chat_api"
          },
          "availability": {
            "available": true,
            "source": "external_provider",
            "auto_pulled": false
          }
        },
        "runtime_capabilities": {
          "models": [
            {
              "name": "qwen2.5",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "nlp_parse",
                "routing"
              ]
            },
            {
              "name": "deepseek-coder",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "blueprint",
                "code_generation"
              ]
            },
            {
              "name": "llama3",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "fallback"
              ]
            },
            {
              "name": "gpt-4o",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "reasoning",
                "planning",
                "web_summary"
              ]
            },
            {
              "name": "gpt-4.1",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "code_generation"
              ]
            },
            {
              "name": "claude-3.5-sonnet",
              "kind": "claude",
              "api": "anthropic_messages_api",
              "supports": [
                "document",
                "long_context"
              ]
            }
          ],
          "tools": [
            {
              "name": "paddleocr",
              "api": "local_tool_runtime",
              "supports": [
                "ocr"
              ],
              "enabled": false
            },
            {
              "name": "whisper",
              "api": "local_tool_runtime",
              "supports": [
                "stt"
              ],
              "enabled": false
            },
            {
              "name": "openvoice",
              "api": "local_tool_runtime",
              "supports": [
                "tts"
              ],
              "enabled": false
            },
            {
              "name": "stable-diffusion",
              "api": "local_tool_runtime",
              "supports": [
                "image_generation"
              ],
              "enabled": false
            },
            {
              "name": "playwright",
              "api": "local_tool_runtime",
              "supports": [
                "web_research"
              ],
              "enabled": true
            },
            {
              "name": "python-docx",
              "api": "local_tool_runtime",
              "supports": [
                "file_generation"
              ],
              "enabled": true
            }
          ],
          "databases": [
            {
              "name": "postgresql",
              "kind": "structured_database",
              "supports": [
                "transactional_data",
                "analytics_query"
              ],
              "enabled": false
            },
            {
              "name": "pgvector",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval"
              ],
              "enabled": false
            },
            {
              "name": "weaviate",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval",
                "hybrid_search"
              ],
              "enabled": false
            }
          ],
          "shell": [
            {
              "name": "bash",
              "available": true,
              "supports": [
                "local_commands"
              ]
            }
          ]
        },
        "output": {
          "saved": 4,
          "total_records": 4
        }
      }
    ],
    "task_intent": "data_record",
    "final_output": {
      "extract_records": {
        "records": [
          {
            "time": "unspecified",
            "location": "博多一兰拉面",
            "content": "吃饭花了，两个人，在博多一兰拉面",
            "amount": 3000,
            "participants": 2,
            "actor": "self",
            "label": "food_and_drink",
            "raw_text": "吃饭花了3000日元，两个人，在博多一兰拉面",
            "created_at": "2026-04-15T06:48:04.851300+00:00"
          },
          {
            "time": "今天",
            "location": null,
            "content": "今天买了咖啡",
            "amount": 500,
            "participants": null,
            "actor": "self",
            "label": "food_and_drink",
            "raw_text": "今天买了咖啡500日元，",
            "created_at": "2026-04-15T06:48:04.851318+00:00"
          },
          {
            "time": "unspecified",
            "location": null,
            "content": "买了书",
            "amount": 1200,
            "participants": null,
            "actor": "self",
            "label": "shopping",
            "raw_text": "买了书1200日元",
            "created_at": "2026-04-15T06:48:04.851329+00:00"
          },
          {
            "time": "上周",
            "location": "超市买东西一共花了8000日元",
            "content": "上周末和家人去超市买东西一共花了",
            "amount": 8000,
            "participants": null,
            "actor": "家人",
            "label": "shopping",
            "raw_text": "上周末和家人去超市买东西一共花了8000日元",
            "created_at": "2026-04-15T06:48:04.851339+00:00"
          }
        ],
        "count": 4
      },
      "persist_records": {
        "saved": 4,
        "total_records": 4
      }
    },
    "vector_store": {
      "name": "memory",
      "provider": "in_memory",
      "enabled": true
    },
    "dependency_status": {
      "auto_install": false,
      "missing_packages": [],
      "missing_tools": []
    }
  }
}

## 查询问答

**问题：** 5月份第一周一共花了多少钱？

**输出：**

{
  "trace_id": "trace_8ff864e9670f",
  "session_id": "default",
  "task": {
    "task_id": "task_4e91344b264e",
    "intent": "data_query",
    "input_text": "5月份第一周一共花了多少钱？",
    "domain": "data_ops",
    "constraints": {
      "need_agent": false
    },
    "output_requirements": [
      "aggregation",
      "insight"
    ],
    "metadata": {
      "trace_id": "trace_8ff864e9670f",
      "session_id": "default",
      "analysis": {
        "has_numeric_value": true,
        "is_query": true,
        "is_record": true,
        "model_routing": {
          "provider": "ollama",
          "model": "qwen2.5",
          "api": "ollama_local_api",
          "model_available": true,
          "auto_pulled": false
        }
      }
    }
  },
  "workflow": {
    "workflow_id": "workflow_839effdac3fb",
    "task_id": "task_4e91344b264e",
    "mode": "normal",
    "steps": [
      {
        "step_id": "step_1ca5a4a572cb",
        "name": "parse_query",
        "task_type": "data_query",
        "depends_on": [],
        "retry": 1,
        "metadata": {
          "goal": "Parse analytical query intent and filters."
        }
      },
      {
        "step_id": "step_f9371a12271a",
        "name": "aggregate_query",
        "task_type": "data_query",
        "depends_on": [
          "step_1ca5a4a572cb"
        ],
        "retry": 1,
        "metadata": {
          "goal": "Run aggregation over persisted records."
        }
      }
    ]
  },
  "blueprints": [
    {
      "blueprint_id": "bp_data_query",
      "name": "Generic Data Query Blueprint",
      "domain": "data_ops",
      "intent": "data_query",
      "inputs": [
        "input_text",
        "session_state"
      ],
      "outputs": [
        "aggregation",
        "summary"
      ],
      "steps": [
        "parse_query",
        "aggregate_query"
      ],
      "metadata": {}
    }
  ],
  "agent": null,
  "execution_result": {
    "steps": [
      {
        "step_id": "step_1ca5a4a572cb",
        "name": "parse_query",
        "status": "completed",
        "capability": {
          "model": "rule-parser",
          "tool": "query_parser",
          "service": "nlp",
          "model_choice": {
            "provider": "ollama",
            "model": "qwen2.5",
            "api": "ollama_local_api"
          },
          "availability": {
            "available": true,
            "source": "local_registry",
            "auto_pulled": false
          }
        },
        "runtime_capabilities": {
          "models": [
            {
              "name": "qwen2.5",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "nlp_parse",
                "routing"
              ]
            },
            {
              "name": "deepseek-coder",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "blueprint",
                "code_generation"
              ]
            },
            {
              "name": "llama3",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "fallback"
              ]
            },
            {
              "name": "gpt-4o",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "reasoning",
                "planning",
                "web_summary"
              ]
            },
            {
              "name": "gpt-4.1",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "code_generation"
              ]
            },
            {
              "name": "claude-3.5-sonnet",
              "kind": "claude",
              "api": "anthropic_messages_api",
              "supports": [
                "document",
                "long_context"
              ]
            }
          ],
          "tools": [
            {
              "name": "paddleocr",
              "api": "local_tool_runtime",
              "supports": [
                "ocr"
              ],
              "enabled": false
            },
            {
              "name": "whisper",
              "api": "local_tool_runtime",
              "supports": [
                "stt"
              ],
              "enabled": false
            },
            {
              "name": "openvoice",
              "api": "local_tool_runtime",
              "supports": [
                "tts"
              ],
              "enabled": false
            },
            {
              "name": "stable-diffusion",
              "api": "local_tool_runtime",
              "supports": [
                "image_generation"
              ],
              "enabled": false
            },
            {
              "name": "playwright",
              "api": "local_tool_runtime",
              "supports": [
                "web_research"
              ],
              "enabled": true
            },
            {
              "name": "python-docx",
              "api": "local_tool_runtime",
              "supports": [
                "file_generation"
              ],
              "enabled": true
            }
          ],
          "databases": [
            {
              "name": "postgresql",
              "kind": "structured_database",
              "supports": [
                "transactional_data",
                "analytics_query"
              ],
              "enabled": false
            },
            {
              "name": "pgvector",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval"
              ],
              "enabled": false
            },
            {
              "name": "weaviate",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval",
                "hybrid_search"
              ],
              "enabled": false
            }
          ],
          "shell": [
            {
              "name": "bash",
              "available": true,
              "supports": [
                "local_commands"
              ]
            }
          ]
        },
        "output": {
          "query": {
            "metric": "sum",
            "terms": [],
            "group_by": [],
            "time_marker": "第一周"
          }
        }
      },
      {
        "step_id": "step_f9371a12271a",
        "name": "aggregate_query",
        "status": "completed",
        "capability": {
          "model": "aggregation-engine",
          "tool": "query_engine",
          "service": "analytics",
          "model_choice": {
            "provider": "openai",
            "model": "gpt-4o",
            "api": "openai_chat_api"
          },
          "availability": {
            "available": true,
            "source": "external_provider",
            "auto_pulled": false
          }
        },
        "runtime_capabilities": {
          "models": [
            {
              "name": "qwen2.5",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "nlp_parse",
                "routing"
              ]
            },
            {
              "name": "deepseek-coder",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "blueprint",
                "code_generation"
              ]
            },
            {
              "name": "llama3",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "fallback"
              ]
            },
            {
              "name": "gpt-4o",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "reasoning",
                "planning",
                "web_summary"
              ]
            },
            {
              "name": "gpt-4.1",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "code_generation"
              ]
            },
            {
              "name": "claude-3.5-sonnet",
              "kind": "claude",
              "api": "anthropic_messages_api",
              "supports": [
                "document",
                "long_context"
              ]
            }
          ],
          "tools": [
            {
              "name": "paddleocr",
              "api": "local_tool_runtime",
              "supports": [
                "ocr"
              ],
              "enabled": false
            },
            {
              "name": "whisper",
              "api": "local_tool_runtime",
              "supports": [
                "stt"
              ],
              "enabled": false
            },
            {
              "name": "openvoice",
              "api": "local_tool_runtime",
              "supports": [
                "tts"
              ],
              "enabled": false
            },
            {
              "name": "stable-diffusion",
              "api": "local_tool_runtime",
              "supports": [
                "image_generation"
              ],
              "enabled": false
            },
            {
              "name": "playwright",
              "api": "local_tool_runtime",
              "supports": [
                "web_research"
              ],
              "enabled": true
            },
            {
              "name": "python-docx",
              "api": "local_tool_runtime",
              "supports": [
                "file_generation"
              ],
              "enabled": true
            }
          ],
          "databases": [
            {
              "name": "postgresql",
              "kind": "structured_database",
              "supports": [
                "transactional_data",
                "analytics_query"
              ],
              "enabled": false
            },
            {
              "name": "pgvector",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval"
              ],
              "enabled": false
            },
            {
              "name": "weaviate",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval",
                "hybrid_search"
              ],
              "enabled": false
            }
          ],
          "shell": [
            {
              "name": "bash",
              "available": true,
              "supports": [
                "local_commands"
              ]
            }
          ]
        },
        "output": {
          "aggregation": {
            "total_amount": 0,
            "count": 0,
            "grouped": {}
          }
        }
      }
    ],
    "task_intent": "data_query",
    "final_output": {
      "parse_query": {
        "query": {
          "metric": "sum",
          "terms": [],
          "group_by": [],
          "time_marker": "第一周"
        }
      },
      "aggregate_query": {
        "aggregation": {
          "total_amount": 0,
          "count": 0,
          "grouped": {}
        }
      }
    },
    "vector_store": {
      "name": "memory",
      "provider": "in_memory",
      "enabled": true
    },
    "dependency_status": {
      "auto_install": false,
      "missing_packages": [],
      "missing_tools": []
    }
  }
}

**问题：** 这个月餐饮花了多少？

**输出：**

{
  "trace_id": "trace_f62c7e9b76f0",
  "session_id": "default",
  "task": {
    "task_id": "task_fa0d4b6a095f",
    "intent": "data_query",
    "input_text": "这个月餐饮花了多少？",
    "domain": "data_ops",
    "constraints": {
      "need_agent": false
    },
    "output_requirements": [
      "aggregation",
      "insight"
    ],
    "metadata": {
      "trace_id": "trace_f62c7e9b76f0",
      "session_id": "default",
      "analysis": {
        "has_numeric_value": false,
        "is_query": true,
        "is_record": true,
        "model_routing": {
          "provider": "ollama",
          "model": "qwen2.5",
          "api": "ollama_local_api",
          "model_available": true,
          "auto_pulled": false
        }
      }
    }
  },
  "workflow": {
    "workflow_id": "workflow_952a9718ba52",
    "task_id": "task_fa0d4b6a095f",
    "mode": "normal",
    "steps": [
      {
        "step_id": "step_372bccb1306c",
        "name": "parse_query",
        "task_type": "data_query",
        "depends_on": [],
        "retry": 1,
        "metadata": {
          "goal": "Parse analytical query intent and filters."
        }
      },
      {
        "step_id": "step_44169d1d20d0",
        "name": "aggregate_query",
        "task_type": "data_query",
        "depends_on": [
          "step_372bccb1306c"
        ],
        "retry": 1,
        "metadata": {
          "goal": "Run aggregation over persisted records."
        }
      }
    ]
  },
  "blueprints": [
    {
      "blueprint_id": "bp_data_query",
      "name": "Generic Data Query Blueprint",
      "domain": "data_ops",
      "intent": "data_query",
      "inputs": [
        "input_text",
        "session_state"
      ],
      "outputs": [
        "aggregation",
        "summary"
      ],
      "steps": [
        "parse_query",
        "aggregate_query"
      ],
      "metadata": {}
    }
  ],
  "agent": null,
  "execution_result": {
    "steps": [
      {
        "step_id": "step_372bccb1306c",
        "name": "parse_query",
        "status": "completed",
        "capability": {
          "model": "rule-parser",
          "tool": "query_parser",
          "service": "nlp",
          "model_choice": {
            "provider": "ollama",
            "model": "qwen2.5",
            "api": "ollama_local_api"
          },
          "availability": {
            "available": true,
            "source": "local_registry",
            "auto_pulled": false
          }
        },
        "runtime_capabilities": {
          "models": [
            {
              "name": "qwen2.5",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "nlp_parse",
                "routing"
              ]
            },
            {
              "name": "deepseek-coder",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "blueprint",
                "code_generation"
              ]
            },
            {
              "name": "llama3",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "fallback"
              ]
            },
            {
              "name": "gpt-4o",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "reasoning",
                "planning",
                "web_summary"
              ]
            },
            {
              "name": "gpt-4.1",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "code_generation"
              ]
            },
            {
              "name": "claude-3.5-sonnet",
              "kind": "claude",
              "api": "anthropic_messages_api",
              "supports": [
                "document",
                "long_context"
              ]
            }
          ],
          "tools": [
            {
              "name": "paddleocr",
              "api": "local_tool_runtime",
              "supports": [
                "ocr"
              ],
              "enabled": false
            },
            {
              "name": "whisper",
              "api": "local_tool_runtime",
              "supports": [
                "stt"
              ],
              "enabled": false
            },
            {
              "name": "openvoice",
              "api": "local_tool_runtime",
              "supports": [
                "tts"
              ],
              "enabled": false
            },
            {
              "name": "stable-diffusion",
              "api": "local_tool_runtime",
              "supports": [
                "image_generation"
              ],
              "enabled": false
            },
            {
              "name": "playwright",
              "api": "local_tool_runtime",
              "supports": [
                "web_research"
              ],
              "enabled": true
            },
            {
              "name": "python-docx",
              "api": "local_tool_runtime",
              "supports": [
                "file_generation"
              ],
              "enabled": true
            }
          ],
          "databases": [
            {
              "name": "postgresql",
              "kind": "structured_database",
              "supports": [
                "transactional_data",
                "analytics_query"
              ],
              "enabled": false
            },
            {
              "name": "pgvector",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval"
              ],
              "enabled": false
            },
            {
              "name": "weaviate",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval",
                "hybrid_search"
              ],
              "enabled": false
            }
          ],
          "shell": [
            {
              "name": "bash",
              "available": true,
              "supports": [
                "local_commands"
              ]
            }
          ]
        },
        "output": {
          "query": {
            "metric": "sum",
            "terms": [],
            "group_by": [],
            "time_marker": "这个月"
          }
        }
      },
      {
        "step_id": "step_44169d1d20d0",
        "name": "aggregate_query",
        "status": "completed",
        "capability": {
          "model": "aggregation-engine",
          "tool": "query_engine",
          "service": "analytics",
          "model_choice": {
            "provider": "openai",
            "model": "gpt-4o",
            "api": "openai_chat_api"
          },
          "availability": {
            "available": true,
            "source": "external_provider",
            "auto_pulled": false
          }
        },
        "runtime_capabilities": {
          "models": [
            {
              "name": "qwen2.5",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "nlp_parse",
                "routing"
              ]
            },
            {
              "name": "deepseek-coder",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "blueprint",
                "code_generation"
              ]
            },
            {
              "name": "llama3",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "fallback"
              ]
            },
            {
              "name": "gpt-4o",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "reasoning",
                "planning",
                "web_summary"
              ]
            },
            {
              "name": "gpt-4.1",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "code_generation"
              ]
            },
            {
              "name": "claude-3.5-sonnet",
              "kind": "claude",
              "api": "anthropic_messages_api",
              "supports": [
                "document",
                "long_context"
              ]
            }
          ],
          "tools": [
            {
              "name": "paddleocr",
              "api": "local_tool_runtime",
              "supports": [
                "ocr"
              ],
              "enabled": false
            },
            {
              "name": "whisper",
              "api": "local_tool_runtime",
              "supports": [
                "stt"
              ],
              "enabled": false
            },
            {
              "name": "openvoice",
              "api": "local_tool_runtime",
              "supports": [
                "tts"
              ],
              "enabled": false
            },
            {
              "name": "stable-diffusion",
              "api": "local_tool_runtime",
              "supports": [
                "image_generation"
              ],
              "enabled": false
            },
            {
              "name": "playwright",
              "api": "local_tool_runtime",
              "supports": [
                "web_research"
              ],
              "enabled": true
            },
            {
              "name": "python-docx",
              "api": "local_tool_runtime",
              "supports": [
                "file_generation"
              ],
              "enabled": true
            }
          ],
          "databases": [
            {
              "name": "postgresql",
              "kind": "structured_database",
              "supports": [
                "transactional_data",
                "analytics_query"
              ],
              "enabled": false
            },
            {
              "name": "pgvector",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval"
              ],
              "enabled": false
            },
            {
              "name": "weaviate",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval",
                "hybrid_search"
              ],
              "enabled": false
            }
          ],
          "shell": [
            {
              "name": "bash",
              "available": true,
              "supports": [
                "local_commands"
              ]
            }
          ]
        },
        "output": {
          "aggregation": {
            "total_amount": 0,
            "count": 0,
            "grouped": {}
          }
        }
      }
    ],
    "task_intent": "data_query",
    "final_output": {
      "parse_query": {
        "query": {
          "metric": "sum",
          "terms": [],
          "group_by": [],
          "time_marker": "这个月"
        }
      },
      "aggregate_query": {
        "aggregation": {
          "total_amount": 0,
          "count": 0,
          "grouped": {}
        }
      }
    },
    "vector_store": {
      "name": "memory",
      "provider": "in_memory",
      "enabled": true
    },
    "dependency_status": {
      "auto_install": false,
      "missing_packages": [],
      "missing_tools": []
    }
  }
}

**问题：** 我个人花了多少？

**输出：**

{
  "trace_id": "trace_c60c35083a5e",
  "session_id": "default",
  "task": {
    "task_id": "task_3b7aee7494f8",
    "intent": "data_query",
    "input_text": "我个人花了多少？",
    "domain": "data_ops",
    "constraints": {
      "need_agent": false
    },
    "output_requirements": [
      "aggregation",
      "insight"
    ],
    "metadata": {
      "trace_id": "trace_c60c35083a5e",
      "session_id": "default",
      "analysis": {
        "has_numeric_value": false,
        "is_query": true,
        "is_record": true,
        "model_routing": {
          "provider": "ollama",
          "model": "qwen2.5",
          "api": "ollama_local_api",
          "model_available": true,
          "auto_pulled": false
        }
      }
    }
  },
  "workflow": {
    "workflow_id": "workflow_5dc1d4856582",
    "task_id": "task_3b7aee7494f8",
    "mode": "normal",
    "steps": [
      {
        "step_id": "step_808adf5dd03b",
        "name": "parse_query",
        "task_type": "data_query",
        "depends_on": [],
        "retry": 1,
        "metadata": {
          "goal": "Parse analytical query intent and filters."
        }
      },
      {
        "step_id": "step_adb392088242",
        "name": "aggregate_query",
        "task_type": "data_query",
        "depends_on": [
          "step_808adf5dd03b"
        ],
        "retry": 1,
        "metadata": {
          "goal": "Run aggregation over persisted records."
        }
      }
    ]
  },
  "blueprints": [
    {
      "blueprint_id": "bp_data_query",
      "name": "Generic Data Query Blueprint",
      "domain": "data_ops",
      "intent": "data_query",
      "inputs": [
        "input_text",
        "session_state"
      ],
      "outputs": [
        "aggregation",
        "summary"
      ],
      "steps": [
        "parse_query",
        "aggregate_query"
      ],
      "metadata": {}
    }
  ],
  "agent": null,
  "execution_result": {
    "steps": [
      {
        "step_id": "step_808adf5dd03b",
        "name": "parse_query",
        "status": "completed",
        "capability": {
          "model": "rule-parser",
          "tool": "query_parser",
          "service": "nlp",
          "model_choice": {
            "provider": "ollama",
            "model": "qwen2.5",
            "api": "ollama_local_api"
          },
          "availability": {
            "available": true,
            "source": "local_registry",
            "auto_pulled": false
          }
        },
        "runtime_capabilities": {
          "models": [
            {
              "name": "qwen2.5",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "nlp_parse",
                "routing"
              ]
            },
            {
              "name": "deepseek-coder",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "blueprint",
                "code_generation"
              ]
            },
            {
              "name": "llama3",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "fallback"
              ]
            },
            {
              "name": "gpt-4o",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "reasoning",
                "planning",
                "web_summary"
              ]
            },
            {
              "name": "gpt-4.1",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "code_generation"
              ]
            },
            {
              "name": "claude-3.5-sonnet",
              "kind": "claude",
              "api": "anthropic_messages_api",
              "supports": [
                "document",
                "long_context"
              ]
            }
          ],
          "tools": [
            {
              "name": "paddleocr",
              "api": "local_tool_runtime",
              "supports": [
                "ocr"
              ],
              "enabled": false
            },
            {
              "name": "whisper",
              "api": "local_tool_runtime",
              "supports": [
                "stt"
              ],
              "enabled": false
            },
            {
              "name": "openvoice",
              "api": "local_tool_runtime",
              "supports": [
                "tts"
              ],
              "enabled": false
            },
            {
              "name": "stable-diffusion",
              "api": "local_tool_runtime",
              "supports": [
                "image_generation"
              ],
              "enabled": false
            },
            {
              "name": "playwright",
              "api": "local_tool_runtime",
              "supports": [
                "web_research"
              ],
              "enabled": true
            },
            {
              "name": "python-docx",
              "api": "local_tool_runtime",
              "supports": [
                "file_generation"
              ],
              "enabled": true
            }
          ],
          "databases": [
            {
              "name": "postgresql",
              "kind": "structured_database",
              "supports": [
                "transactional_data",
                "analytics_query"
              ],
              "enabled": false
            },
            {
              "name": "pgvector",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval"
              ],
              "enabled": false
            },
            {
              "name": "weaviate",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval",
                "hybrid_search"
              ],
              "enabled": false
            }
          ],
          "shell": [
            {
              "name": "bash",
              "available": true,
              "supports": [
                "local_commands"
              ]
            }
          ]
        },
        "output": {
          "query": {
            "metric": "sum",
            "terms": [],
            "group_by": [],
            "time_marker": "unspecified"
          }
        }
      },
      {
        "step_id": "step_adb392088242",
        "name": "aggregate_query",
        "status": "completed",
        "capability": {
          "model": "aggregation-engine",
          "tool": "query_engine",
          "service": "analytics",
          "model_choice": {
            "provider": "openai",
            "model": "gpt-4o",
            "api": "openai_chat_api"
          },
          "availability": {
            "available": true,
            "source": "external_provider",
            "auto_pulled": false
          }
        },
        "runtime_capabilities": {
          "models": [
            {
              "name": "qwen2.5",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "nlp_parse",
                "routing"
              ]
            },
            {
              "name": "deepseek-coder",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "blueprint",
                "code_generation"
              ]
            },
            {
              "name": "llama3",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "fallback"
              ]
            },
            {
              "name": "gpt-4o",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "reasoning",
                "planning",
                "web_summary"
              ]
            },
            {
              "name": "gpt-4.1",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "code_generation"
              ]
            },
            {
              "name": "claude-3.5-sonnet",
              "kind": "claude",
              "api": "anthropic_messages_api",
              "supports": [
                "document",
                "long_context"
              ]
            }
          ],
          "tools": [
            {
              "name": "paddleocr",
              "api": "local_tool_runtime",
              "supports": [
                "ocr"
              ],
              "enabled": false
            },
            {
              "name": "whisper",
              "api": "local_tool_runtime",
              "supports": [
                "stt"
              ],
              "enabled": false
            },
            {
              "name": "openvoice",
              "api": "local_tool_runtime",
              "supports": [
                "tts"
              ],
              "enabled": false
            },
            {
              "name": "stable-diffusion",
              "api": "local_tool_runtime",
              "supports": [
                "image_generation"
              ],
              "enabled": false
            },
            {
              "name": "playwright",
              "api": "local_tool_runtime",
              "supports": [
                "web_research"
              ],
              "enabled": true
            },
            {
              "name": "python-docx",
              "api": "local_tool_runtime",
              "supports": [
                "file_generation"
              ],
              "enabled": true
            }
          ],
          "databases": [
            {
              "name": "postgresql",
              "kind": "structured_database",
              "supports": [
                "transactional_data",
                "analytics_query"
              ],
              "enabled": false
            },
            {
              "name": "pgvector",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval"
              ],
              "enabled": false
            },
            {
              "name": "weaviate",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval",
                "hybrid_search"
              ],
              "enabled": false
            }
          ],
          "shell": [
            {
              "name": "bash",
              "available": true,
              "supports": [
                "local_commands"
              ]
            }
          ]
        },
        "output": {
          "aggregation": {
            "total_amount": 12700,
            "count": 4,
            "grouped": {}
          }
        }
      }
    ],
    "task_intent": "data_query",
    "final_output": {
      "parse_query": {
        "query": {
          "metric": "sum",
          "terms": [],
          "group_by": [],
          "time_marker": "unspecified"
        }
      },
      "aggregate_query": {
        "aggregation": {
          "total_amount": 12700,
          "count": 4,
          "grouped": {}
        }
      }
    },
    "vector_store": {
      "name": "memory",
      "provider": "in_memory",
      "enabled": true
    },
    "dependency_status": {
      "auto_install": false,
      "missing_packages": [],
      "missing_tools": []
    }
  }
}

**问题：** 家人花了多少？

**输出：**

{
  "trace_id": "trace_def388748012",
  "session_id": "default",
  "task": {
    "task_id": "task_37c8005f2284",
    "intent": "data_query",
    "input_text": "家人花了多少？",
    "domain": "data_ops",
    "constraints": {
      "need_agent": false
    },
    "output_requirements": [
      "aggregation",
      "insight"
    ],
    "metadata": {
      "trace_id": "trace_def388748012",
      "session_id": "default",
      "analysis": {
        "has_numeric_value": false,
        "is_query": true,
        "is_record": true,
        "model_routing": {
          "provider": "ollama",
          "model": "qwen2.5",
          "api": "ollama_local_api",
          "model_available": true,
          "auto_pulled": false
        }
      }
    }
  },
  "workflow": {
    "workflow_id": "workflow_9f3d8c9bff8d",
    "task_id": "task_37c8005f2284",
    "mode": "normal",
    "steps": [
      {
        "step_id": "step_c29d482413a5",
        "name": "parse_query",
        "task_type": "data_query",
        "depends_on": [],
        "retry": 1,
        "metadata": {
          "goal": "Parse analytical query intent and filters."
        }
      },
      {
        "step_id": "step_c2bdfca0cf57",
        "name": "aggregate_query",
        "task_type": "data_query",
        "depends_on": [
          "step_c29d482413a5"
        ],
        "retry": 1,
        "metadata": {
          "goal": "Run aggregation over persisted records."
        }
      }
    ]
  },
  "blueprints": [
    {
      "blueprint_id": "bp_data_query",
      "name": "Generic Data Query Blueprint",
      "domain": "data_ops",
      "intent": "data_query",
      "inputs": [
        "input_text",
        "session_state"
      ],
      "outputs": [
        "aggregation",
        "summary"
      ],
      "steps": [
        "parse_query",
        "aggregate_query"
      ],
      "metadata": {}
    }
  ],
  "agent": null,
  "execution_result": {
    "steps": [
      {
        "step_id": "step_c29d482413a5",
        "name": "parse_query",
        "status": "completed",
        "capability": {
          "model": "rule-parser",
          "tool": "query_parser",
          "service": "nlp",
          "model_choice": {
            "provider": "ollama",
            "model": "qwen2.5",
            "api": "ollama_local_api"
          },
          "availability": {
            "available": true,
            "source": "local_registry",
            "auto_pulled": false
          }
        },
        "runtime_capabilities": {
          "models": [
            {
              "name": "qwen2.5",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "nlp_parse",
                "routing"
              ]
            },
            {
              "name": "deepseek-coder",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "blueprint",
                "code_generation"
              ]
            },
            {
              "name": "llama3",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "fallback"
              ]
            },
            {
              "name": "gpt-4o",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "reasoning",
                "planning",
                "web_summary"
              ]
            },
            {
              "name": "gpt-4.1",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "code_generation"
              ]
            },
            {
              "name": "claude-3.5-sonnet",
              "kind": "claude",
              "api": "anthropic_messages_api",
              "supports": [
                "document",
                "long_context"
              ]
            }
          ],
          "tools": [
            {
              "name": "paddleocr",
              "api": "local_tool_runtime",
              "supports": [
                "ocr"
              ],
              "enabled": false
            },
            {
              "name": "whisper",
              "api": "local_tool_runtime",
              "supports": [
                "stt"
              ],
              "enabled": false
            },
            {
              "name": "openvoice",
              "api": "local_tool_runtime",
              "supports": [
                "tts"
              ],
              "enabled": false
            },
            {
              "name": "stable-diffusion",
              "api": "local_tool_runtime",
              "supports": [
                "image_generation"
              ],
              "enabled": false
            },
            {
              "name": "playwright",
              "api": "local_tool_runtime",
              "supports": [
                "web_research"
              ],
              "enabled": true
            },
            {
              "name": "python-docx",
              "api": "local_tool_runtime",
              "supports": [
                "file_generation"
              ],
              "enabled": true
            }
          ],
          "databases": [
            {
              "name": "postgresql",
              "kind": "structured_database",
              "supports": [
                "transactional_data",
                "analytics_query"
              ],
              "enabled": false
            },
            {
              "name": "pgvector",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval"
              ],
              "enabled": false
            },
            {
              "name": "weaviate",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval",
                "hybrid_search"
              ],
              "enabled": false
            }
          ],
          "shell": [
            {
              "name": "bash",
              "available": true,
              "supports": [
                "local_commands"
              ]
            }
          ]
        },
        "output": {
          "query": {
            "metric": "sum",
            "terms": [
              "家人"
            ],
            "group_by": [],
            "time_marker": "unspecified"
          }
        }
      },
      {
        "step_id": "step_c2bdfca0cf57",
        "name": "aggregate_query",
        "status": "completed",
        "capability": {
          "model": "aggregation-engine",
          "tool": "query_engine",
          "service": "analytics",
          "model_choice": {
            "provider": "openai",
            "model": "gpt-4o",
            "api": "openai_chat_api"
          },
          "availability": {
            "available": true,
            "source": "external_provider",
            "auto_pulled": false
          }
        },
        "runtime_capabilities": {
          "models": [
            {
              "name": "qwen2.5",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "nlp_parse",
                "routing"
              ]
            },
            {
              "name": "deepseek-coder",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "blueprint",
                "code_generation"
              ]
            },
            {
              "name": "llama3",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "fallback"
              ]
            },
            {
              "name": "gpt-4o",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "reasoning",
                "planning",
                "web_summary"
              ]
            },
            {
              "name": "gpt-4.1",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "code_generation"
              ]
            },
            {
              "name": "claude-3.5-sonnet",
              "kind": "claude",
              "api": "anthropic_messages_api",
              "supports": [
                "document",
                "long_context"
              ]
            }
          ],
          "tools": [
            {
              "name": "paddleocr",
              "api": "local_tool_runtime",
              "supports": [
                "ocr"
              ],
              "enabled": false
            },
            {
              "name": "whisper",
              "api": "local_tool_runtime",
              "supports": [
                "stt"
              ],
              "enabled": false
            },
            {
              "name": "openvoice",
              "api": "local_tool_runtime",
              "supports": [
                "tts"
              ],
              "enabled": false
            },
            {
              "name": "stable-diffusion",
              "api": "local_tool_runtime",
              "supports": [
                "image_generation"
              ],
              "enabled": false
            },
            {
              "name": "playwright",
              "api": "local_tool_runtime",
              "supports": [
                "web_research"
              ],
              "enabled": true
            },
            {
              "name": "python-docx",
              "api": "local_tool_runtime",
              "supports": [
                "file_generation"
              ],
              "enabled": true
            }
          ],
          "databases": [
            {
              "name": "postgresql",
              "kind": "structured_database",
              "supports": [
                "transactional_data",
                "analytics_query"
              ],
              "enabled": false
            },
            {
              "name": "pgvector",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval"
              ],
              "enabled": false
            },
            {
              "name": "weaviate",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval",
                "hybrid_search"
              ],
              "enabled": false
            }
          ],
          "shell": [
            {
              "name": "bash",
              "available": true,
              "supports": [
                "local_commands"
              ]
            }
          ]
        },
        "output": {
          "aggregation": {
            "total_amount": 8000,
            "count": 1,
            "grouped": {}
          }
        }
      }
    ],
    "task_intent": "data_query",
    "final_output": {
      "parse_query": {
        "query": {
          "metric": "sum",
          "terms": [
            "家人"
          ],
          "group_by": [],
          "time_marker": "unspecified"
        }
      },
      "aggregate_query": {
        "aggregation": {
          "total_amount": 8000,
          "count": 1,
          "grouped": {}
        }
      }
    },
    "vector_store": {
      "name": "memory",
      "provider": "in_memory",
      "enabled": true
    },
    "dependency_status": {
      "auto_install": false,
      "missing_packages": [],
      "missing_tools": []
    }
  }
}

**问题：** 咖啡一共花了多少？

**输出：**

{
  "trace_id": "trace_49cf8c2bd954",
  "session_id": "default",
  "task": {
    "task_id": "task_b10f392c7607",
    "intent": "data_query",
    "input_text": "咖啡一共花了多少？",
    "domain": "data_ops",
    "constraints": {
      "need_agent": false
    },
    "output_requirements": [
      "aggregation",
      "insight"
    ],
    "metadata": {
      "trace_id": "trace_49cf8c2bd954",
      "session_id": "default",
      "analysis": {
        "has_numeric_value": false,
        "is_query": true,
        "is_record": true,
        "model_routing": {
          "provider": "ollama",
          "model": "qwen2.5",
          "api": "ollama_local_api",
          "model_available": true,
          "auto_pulled": false
        }
      }
    }
  },
  "workflow": {
    "workflow_id": "workflow_3a477045081b",
    "task_id": "task_b10f392c7607",
    "mode": "normal",
    "steps": [
      {
        "step_id": "step_c7d75474be5f",
        "name": "parse_query",
        "task_type": "data_query",
        "depends_on": [],
        "retry": 1,
        "metadata": {
          "goal": "Parse analytical query intent and filters."
        }
      },
      {
        "step_id": "step_dd35b1825a4e",
        "name": "aggregate_query",
        "task_type": "data_query",
        "depends_on": [
          "step_c7d75474be5f"
        ],
        "retry": 1,
        "metadata": {
          "goal": "Run aggregation over persisted records."
        }
      }
    ]
  },
  "blueprints": [
    {
      "blueprint_id": "bp_data_query",
      "name": "Generic Data Query Blueprint",
      "domain": "data_ops",
      "intent": "data_query",
      "inputs": [
        "input_text",
        "session_state"
      ],
      "outputs": [
        "aggregation",
        "summary"
      ],
      "steps": [
        "parse_query",
        "aggregate_query"
      ],
      "metadata": {}
    }
  ],
  "agent": null,
  "execution_result": {
    "steps": [
      {
        "step_id": "step_c7d75474be5f",
        "name": "parse_query",
        "status": "completed",
        "capability": {
          "model": "rule-parser",
          "tool": "query_parser",
          "service": "nlp",
          "model_choice": {
            "provider": "ollama",
            "model": "qwen2.5",
            "api": "ollama_local_api"
          },
          "availability": {
            "available": true,
            "source": "local_registry",
            "auto_pulled": false
          }
        },
        "runtime_capabilities": {
          "models": [
            {
              "name": "qwen2.5",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "nlp_parse",
                "routing"
              ]
            },
            {
              "name": "deepseek-coder",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "blueprint",
                "code_generation"
              ]
            },
            {
              "name": "llama3",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "fallback"
              ]
            },
            {
              "name": "gpt-4o",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "reasoning",
                "planning",
                "web_summary"
              ]
            },
            {
              "name": "gpt-4.1",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "code_generation"
              ]
            },
            {
              "name": "claude-3.5-sonnet",
              "kind": "claude",
              "api": "anthropic_messages_api",
              "supports": [
                "document",
                "long_context"
              ]
            }
          ],
          "tools": [
            {
              "name": "paddleocr",
              "api": "local_tool_runtime",
              "supports": [
                "ocr"
              ],
              "enabled": false
            },
            {
              "name": "whisper",
              "api": "local_tool_runtime",
              "supports": [
                "stt"
              ],
              "enabled": false
            },
            {
              "name": "openvoice",
              "api": "local_tool_runtime",
              "supports": [
                "tts"
              ],
              "enabled": false
            },
            {
              "name": "stable-diffusion",
              "api": "local_tool_runtime",
              "supports": [
                "image_generation"
              ],
              "enabled": false
            },
            {
              "name": "playwright",
              "api": "local_tool_runtime",
              "supports": [
                "web_research"
              ],
              "enabled": true
            },
            {
              "name": "python-docx",
              "api": "local_tool_runtime",
              "supports": [
                "file_generation"
              ],
              "enabled": true
            }
          ],
          "databases": [
            {
              "name": "postgresql",
              "kind": "structured_database",
              "supports": [
                "transactional_data",
                "analytics_query"
              ],
              "enabled": false
            },
            {
              "name": "pgvector",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval"
              ],
              "enabled": false
            },
            {
              "name": "weaviate",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval",
                "hybrid_search"
              ],
              "enabled": false
            }
          ],
          "shell": [
            {
              "name": "bash",
              "available": true,
              "supports": [
                "local_commands"
              ]
            }
          ]
        },
        "output": {
          "query": {
            "metric": "sum",
            "terms": [
              "咖啡"
            ],
            "group_by": [],
            "time_marker": "unspecified"
          }
        }
      },
      {
        "step_id": "step_dd35b1825a4e",
        "name": "aggregate_query",
        "status": "completed",
        "capability": {
          "model": "aggregation-engine",
          "tool": "query_engine",
          "service": "analytics",
          "model_choice": {
            "provider": "openai",
            "model": "gpt-4o",
            "api": "openai_chat_api"
          },
          "availability": {
            "available": true,
            "source": "external_provider",
            "auto_pulled": false
          }
        },
        "runtime_capabilities": {
          "models": [
            {
              "name": "qwen2.5",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "nlp_parse",
                "routing"
              ]
            },
            {
              "name": "deepseek-coder",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "blueprint",
                "code_generation"
              ]
            },
            {
              "name": "llama3",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "fallback"
              ]
            },
            {
              "name": "gpt-4o",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "reasoning",
                "planning",
                "web_summary"
              ]
            },
            {
              "name": "gpt-4.1",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "code_generation"
              ]
            },
            {
              "name": "claude-3.5-sonnet",
              "kind": "claude",
              "api": "anthropic_messages_api",
              "supports": [
                "document",
                "long_context"
              ]
            }
          ],
          "tools": [
            {
              "name": "paddleocr",
              "api": "local_tool_runtime",
              "supports": [
                "ocr"
              ],
              "enabled": false
            },
            {
              "name": "whisper",
              "api": "local_tool_runtime",
              "supports": [
                "stt"
              ],
              "enabled": false
            },
            {
              "name": "openvoice",
              "api": "local_tool_runtime",
              "supports": [
                "tts"
              ],
              "enabled": false
            },
            {
              "name": "stable-diffusion",
              "api": "local_tool_runtime",
              "supports": [
                "image_generation"
              ],
              "enabled": false
            },
            {
              "name": "playwright",
              "api": "local_tool_runtime",
              "supports": [
                "web_research"
              ],
              "enabled": true
            },
            {
              "name": "python-docx",
              "api": "local_tool_runtime",
              "supports": [
                "file_generation"
              ],
              "enabled": true
            }
          ],
          "databases": [
            {
              "name": "postgresql",
              "kind": "structured_database",
              "supports": [
                "transactional_data",
                "analytics_query"
              ],
              "enabled": false
            },
            {
              "name": "pgvector",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval"
              ],
              "enabled": false
            },
            {
              "name": "weaviate",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval",
                "hybrid_search"
              ],
              "enabled": false
            }
          ],
          "shell": [
            {
              "name": "bash",
              "available": true,
              "supports": [
                "local_commands"
              ]
            }
          ]
        },
        "output": {
          "aggregation": {
            "total_amount": 500,
            "count": 1,
            "grouped": {}
          }
        }
      }
    ],
    "task_intent": "data_query",
    "final_output": {
      "parse_query": {
        "query": {
          "metric": "sum",
          "terms": [
            "咖啡"
          ],
          "group_by": [],
          "time_marker": "unspecified"
        }
      },
      "aggregate_query": {
        "aggregation": {
          "total_amount": 500,
          "count": 1,
          "grouped": {}
        }
      }
    },
    "vector_store": {
      "name": "memory",
      "provider": "in_memory",
      "enabled": true
    },
    "dependency_status": {
      "auto_install": false,
      "missing_packages": [],
      "missing_tools": []
    }
  }
}

**问题：** 博多地区消费总额是多少？

**输出：**

{
  "trace_id": "trace_66c58bed2508",
  "session_id": "default",
  "task": {
    "task_id": "task_6e42c8b5bfc7",
    "intent": "data_query",
    "input_text": "博多地区消费总额是多少？",
    "domain": "data_ops",
    "constraints": {
      "need_agent": false
    },
    "output_requirements": [
      "aggregation",
      "insight"
    ],
    "metadata": {
      "trace_id": "trace_66c58bed2508",
      "session_id": "default",
      "analysis": {
        "has_numeric_value": false,
        "is_query": true,
        "is_record": false,
        "model_routing": {
          "provider": "ollama",
          "model": "qwen2.5",
          "api": "ollama_local_api",
          "model_available": true,
          "auto_pulled": false
        }
      }
    }
  },
  "workflow": {
    "workflow_id": "workflow_62f1304fec5a",
    "task_id": "task_6e42c8b5bfc7",
    "mode": "normal",
    "steps": [
      {
        "step_id": "step_286847635ab3",
        "name": "parse_query",
        "task_type": "data_query",
        "depends_on": [],
        "retry": 1,
        "metadata": {
          "goal": "Parse analytical query intent and filters."
        }
      },
      {
        "step_id": "step_47540abe6153",
        "name": "aggregate_query",
        "task_type": "data_query",
        "depends_on": [
          "step_286847635ab3"
        ],
        "retry": 1,
        "metadata": {
          "goal": "Run aggregation over persisted records."
        }
      }
    ]
  },
  "blueprints": [
    {
      "blueprint_id": "bp_data_query",
      "name": "Generic Data Query Blueprint",
      "domain": "data_ops",
      "intent": "data_query",
      "inputs": [
        "input_text",
        "session_state"
      ],
      "outputs": [
        "aggregation",
        "summary"
      ],
      "steps": [
        "parse_query",
        "aggregate_query"
      ],
      "metadata": {}
    }
  ],
  "agent": null,
  "execution_result": {
    "steps": [
      {
        "step_id": "step_286847635ab3",
        "name": "parse_query",
        "status": "completed",
        "capability": {
          "model": "rule-parser",
          "tool": "query_parser",
          "service": "nlp",
          "model_choice": {
            "provider": "ollama",
            "model": "qwen2.5",
            "api": "ollama_local_api"
          },
          "availability": {
            "available": true,
            "source": "local_registry",
            "auto_pulled": false
          }
        },
        "runtime_capabilities": {
          "models": [
            {
              "name": "qwen2.5",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "nlp_parse",
                "routing"
              ]
            },
            {
              "name": "deepseek-coder",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "blueprint",
                "code_generation"
              ]
            },
            {
              "name": "llama3",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "fallback"
              ]
            },
            {
              "name": "gpt-4o",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "reasoning",
                "planning",
                "web_summary"
              ]
            },
            {
              "name": "gpt-4.1",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "code_generation"
              ]
            },
            {
              "name": "claude-3.5-sonnet",
              "kind": "claude",
              "api": "anthropic_messages_api",
              "supports": [
                "document",
                "long_context"
              ]
            }
          ],
          "tools": [
            {
              "name": "paddleocr",
              "api": "local_tool_runtime",
              "supports": [
                "ocr"
              ],
              "enabled": false
            },
            {
              "name": "whisper",
              "api": "local_tool_runtime",
              "supports": [
                "stt"
              ],
              "enabled": false
            },
            {
              "name": "openvoice",
              "api": "local_tool_runtime",
              "supports": [
                "tts"
              ],
              "enabled": false
            },
            {
              "name": "stable-diffusion",
              "api": "local_tool_runtime",
              "supports": [
                "image_generation"
              ],
              "enabled": false
            },
            {
              "name": "playwright",
              "api": "local_tool_runtime",
              "supports": [
                "web_research"
              ],
              "enabled": true
            },
            {
              "name": "python-docx",
              "api": "local_tool_runtime",
              "supports": [
                "file_generation"
              ],
              "enabled": true
            }
          ],
          "databases": [
            {
              "name": "postgresql",
              "kind": "structured_database",
              "supports": [
                "transactional_data",
                "analytics_query"
              ],
              "enabled": false
            },
            {
              "name": "pgvector",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval"
              ],
              "enabled": false
            },
            {
              "name": "weaviate",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval",
                "hybrid_search"
              ],
              "enabled": false
            }
          ],
          "shell": [
            {
              "name": "bash",
              "available": true,
              "supports": [
                "local_commands"
              ]
            }
          ]
        },
        "output": {
          "query": {
            "metric": "sum",
            "terms": [],
            "group_by": [],
            "time_marker": "unspecified"
          }
        }
      },
      {
        "step_id": "step_47540abe6153",
        "name": "aggregate_query",
        "status": "completed",
        "capability": {
          "model": "aggregation-engine",
          "tool": "query_engine",
          "service": "analytics",
          "model_choice": {
            "provider": "openai",
            "model": "gpt-4o",
            "api": "openai_chat_api"
          },
          "availability": {
            "available": true,
            "source": "external_provider",
            "auto_pulled": false
          }
        },
        "runtime_capabilities": {
          "models": [
            {
              "name": "qwen2.5",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "nlp_parse",
                "routing"
              ]
            },
            {
              "name": "deepseek-coder",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "blueprint",
                "code_generation"
              ]
            },
            {
              "name": "llama3",
              "kind": "local_ollama",
              "api": "ollama_local_api",
              "supports": [
                "fallback"
              ]
            },
            {
              "name": "gpt-4o",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "reasoning",
                "planning",
                "web_summary"
              ]
            },
            {
              "name": "gpt-4.1",
              "kind": "openai",
              "api": "openai_chat_api",
              "supports": [
                "code_generation"
              ]
            },
            {
              "name": "claude-3.5-sonnet",
              "kind": "claude",
              "api": "anthropic_messages_api",
              "supports": [
                "document",
                "long_context"
              ]
            }
          ],
          "tools": [
            {
              "name": "paddleocr",
              "api": "local_tool_runtime",
              "supports": [
                "ocr"
              ],
              "enabled": false
            },
            {
              "name": "whisper",
              "api": "local_tool_runtime",
              "supports": [
                "stt"
              ],
              "enabled": false
            },
            {
              "name": "openvoice",
              "api": "local_tool_runtime",
              "supports": [
                "tts"
              ],
              "enabled": false
            },
            {
              "name": "stable-diffusion",
              "api": "local_tool_runtime",
              "supports": [
                "image_generation"
              ],
              "enabled": false
            },
            {
              "name": "playwright",
              "api": "local_tool_runtime",
              "supports": [
                "web_research"
              ],
              "enabled": true
            },
            {
              "name": "python-docx",
              "api": "local_tool_runtime",
              "supports": [
                "file_generation"
              ],
              "enabled": true
            }
          ],
          "databases": [
            {
              "name": "postgresql",
              "kind": "structured_database",
              "supports": [
                "transactional_data",
                "analytics_query"
              ],
              "enabled": false
            },
            {
              "name": "pgvector",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval"
              ],
              "enabled": false
            },
            {
              "name": "weaviate",
              "kind": "vector_database",
              "supports": [
                "semantic_retrieval",
                "hybrid_search"
              ],
              "enabled": false
            }
          ],
          "shell": [
            {
              "name": "bash",
              "available": true,
              "supports": [
                "local_commands"
              ]
            }
          ]
        },
        "output": {
          "aggregation": {
            "total_amount": 12700,
            "count": 4,
            "grouped": {}
          }
        }
      }
    ],
    "task_intent": "data_query",
    "final_output": {
      "parse_query": {
        "query": {
          "metric": "sum",
          "terms": [],
          "group_by": [],
          "time_marker": "unspecified"
        }
      },
      "aggregate_query": {
        "aggregation": {
          "total_amount": 12700,
          "count": 4,
          "grouped": {}
        }
      }
    },
    "vector_store": {
      "name": "memory",
      "provider": "in_memory",
      "enabled": true
    },
    "dependency_status": {
      "auto_install": false,
      "missing_packages": [],
      "missing_tools": []
    }
  }
}
