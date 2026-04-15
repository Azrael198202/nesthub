# 精简自动化测试报告

## 消费记录录入

**输入：** 吃饭花了3000日元，两个人，在博多一兰拉面。今天买了咖啡500日元，还有买了书1200日元。上周末和家人去超市买东西一共花了8000日元。

**输出：**

{
  "trace_id": "trace_363803d0066f",
  "session_id": "budget_scene_e2e",
  "task": {
    "task_id": "task_71d6111784e2",
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
      "trace_id": "trace_363803d0066f",
      "session_id": "budget_scene_e2e",
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
  "workflow": {},
  "blueprints": [],
  "agent": null,
  "execution_result": {
    "steps": [
      {
        "step_id": "step_316aaa8ac100",
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
              "created_at": "2026-04-15T12:19:20.563178+00:00"
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
              "created_at": "2026-04-15T12:19:20.563202+00:00"
            },
            {
              "time": "unspecified",
              "location": null,
              "content": "买了书",
              "amount": 1200,
              "participants": null,
              "actor": "self",
              "label": "other",
              "raw_text": "买了书1200日元",
              "created_at": "2026-04-15T12:19:20.563221+00:00"
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
              "created_at": "2026-04-15T12:19:20.563238+00:00"
            }
          ],
          "count": 4
        }
      },
      {
        "step_id": "step_de122b9e98ca",
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
            "created_at": "2026-04-15T12:19:20.563178+00:00"
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
            "created_at": "2026-04-15T12:19:20.563202+00:00"
          },
          {
            "time": "unspecified",
            "location": null,
            "content": "买了书",
            "amount": 1200,
            "participants": null,
            "actor": "self",
            "label": "other",
            "raw_text": "买了书1200日元",
            "created_at": "2026-04-15T12:19:20.563221+00:00"
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
            "created_at": "2026-04-15T12:19:20.563238+00:00"
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

**问题：** 这个月餐饮花了多少？

**输出：**

{
  "trace_id": "trace_c1b1a0d7247b",
  "session_id": "budget_scene_e2e",
  "task": {
    "task_id": "task_899aac7b9b55",
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
      "trace_id": "trace_c1b1a0d7247b",
      "session_id": "budget_scene_e2e",
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
  "workflow": {},
  "blueprints": [],
  "agent": null,
  "execution_result": {
    "steps": [
      {
        "step_id": "step_0175c8c90b16",
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
            "time_marker": "这个月",
            "filters": {
              "label": "food_and_drink"
            },
            "query_text": "这个月餐饮花了多少？"
          }
        }
      },
      {
        "step_id": "step_f3eca6aacff7",
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
            "grouped": {},
            "semantic_mode": "local",
            "semantic_confidence": 1.0
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
          "time_marker": "这个月",
          "filters": {
            "label": "food_and_drink"
          },
          "query_text": "这个月餐饮花了多少？"
        }
      },
      "aggregate_query": {
        "aggregation": {
          "total_amount": 0,
          "count": 0,
          "grouped": {},
          "semantic_mode": "local",
          "semantic_confidence": 1.0
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

**问题：** 4月份一共花了多少钱？

**输出：**

{
  "trace_id": "trace_fe49b6e7c010",
  "session_id": "budget_scene_e2e",
  "task": {
    "task_id": "task_2eab5d3b3181",
    "intent": "data_query",
    "input_text": "4月份一共花了多少钱？",
    "domain": "data_ops",
    "constraints": {
      "need_agent": false
    },
    "output_requirements": [
      "aggregation",
      "insight"
    ],
    "metadata": {
      "trace_id": "trace_fe49b6e7c010",
      "session_id": "budget_scene_e2e",
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
  "workflow": {},
  "blueprints": [],
  "agent": null,
  "execution_result": {
    "steps": [
      {
        "step_id": "step_1955aca1b542",
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
              "一共"
            ],
            "group_by": [],
            "time_marker": "unspecified",
            "filters": {},
            "query_text": "4月份一共花了多少钱？"
          }
        }
      },
      {
        "step_id": "step_5288d6b084be",
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
            "grouped": {},
            "semantic_mode": "local",
            "semantic_confidence": 1.0
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
            "一共"
          ],
          "group_by": [],
          "time_marker": "unspecified",
          "filters": {},
          "query_text": "4月份一共花了多少钱？"
        }
      },
      "aggregate_query": {
        "aggregation": {
          "total_amount": 8000,
          "count": 1,
          "grouped": {},
          "semantic_mode": "local",
          "semantic_confidence": 1.0
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
