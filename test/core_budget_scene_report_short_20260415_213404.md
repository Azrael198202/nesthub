# 精简自动化测试报告

## 消费记录录入

**输入：** 吃饭花了3000日元，两个人，在博多一兰拉面。今天买了咖啡500日元，还有买了书1200日元。上周末和家人去超市买东西一共花了8000日元。

**输出：**

{
  "trace_id": "trace_7039dbdb9366",
  "session_id": "budget_scene_e2e",
  "task": {
    "task_id": "task_050a941eb1a0",
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
      "trace_id": "trace_7039dbdb9366",
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
  "workflow": {
    "workflow_id": "workflow_32043c673da6",
    "task_id": "task_050a941eb1a0",
    "mode": "normal",
    "steps": [
      {
        "step_id": "step_abe04d1c1b39",
        "name": "extract_records",
        "task_type": "data_record",
        "depends_on": [],
        "retry": 1,
        "metadata": {
          "goal": "Extract structured records from natural language."
        }
      },
      {
        "step_id": "step_70c407995a2f",
        "name": "persist_records",
        "task_type": "data_record",
        "depends_on": [
          "step_abe04d1c1b39"
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
        "step_id": "step_abe04d1c1b39",
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
              "created_at": "2026-04-15T12:34:03.630781+00:00"
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
              "created_at": "2026-04-15T12:34:03.674061+00:00"
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
              "created_at": "2026-04-15T12:34:03.713587+00:00"
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
              "created_at": "2026-04-15T12:34:03.750443+00:00"
            }
          ],
          "count": 4
        }
      },
      {
        "step_id": "step_70c407995a2f",
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
            "created_at": "2026-04-15T12:34:03.630781+00:00"
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
            "created_at": "2026-04-15T12:34:03.674061+00:00"
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
            "created_at": "2026-04-15T12:34:03.713587+00:00"
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
            "created_at": "2026-04-15T12:34:03.750443+00:00"
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
  "trace_id": "trace_a147ff37aab9",
  "session_id": "budget_scene_e2e",
  "task": {
    "task_id": "task_8843301d9466",
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
      "trace_id": "trace_a147ff37aab9",
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
  "workflow": {
    "workflow_id": "workflow_d9b306f0f936",
    "task_id": "task_8843301d9466",
    "mode": "normal",
    "steps": [
      {
        "step_id": "step_f9393a03c9aa",
        "name": "parse_query",
        "task_type": "data_query",
        "depends_on": [],
        "retry": 1,
        "metadata": {
          "goal": "Parse analytical query intent and filters."
        }
      },
      {
        "step_id": "step_b7b88d2288b3",
        "name": "aggregate_query",
        "task_type": "data_query",
        "depends_on": [
          "step_f9393a03c9aa"
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
        "step_id": "step_f9393a03c9aa",
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
        "step_id": "step_b7b88d2288b3",
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
            "total_amount": 3500,
            "count": 2,
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
          "total_amount": 3500,
          "count": 2,
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
  "trace_id": "trace_5dec26c4b197",
  "session_id": "budget_scene_e2e",
  "task": {
    "task_id": "task_7ee02409972a",
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
      "trace_id": "trace_5dec26c4b197",
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
  "workflow": {
    "workflow_id": "workflow_81f7e730f061",
    "task_id": "task_7ee02409972a",
    "mode": "normal",
    "steps": [
      {
        "step_id": "step_c5d37779ca5c",
        "name": "parse_query",
        "task_type": "data_query",
        "depends_on": [],
        "retry": 1,
        "metadata": {
          "goal": "Parse analytical query intent and filters."
        }
      },
      {
        "step_id": "step_c2607afd6ad9",
        "name": "aggregate_query",
        "task_type": "data_query",
        "depends_on": [
          "step_c5d37779ca5c"
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
        "step_id": "step_c5d37779ca5c",
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
            "time_marker": "unspecified",
            "filters": {
              "label": "food_and_drink"
            },
            "query_text": "4月份一共花了多少钱？"
          }
        }
      },
      {
        "step_id": "step_c2607afd6ad9",
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
            "total_amount": 3500,
            "count": 2,
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
          "time_marker": "unspecified",
          "filters": {
            "label": "food_and_drink"
          },
          "query_text": "4月份一共花了多少钱？"
        }
      },
      "aggregate_query": {
        "aggregation": {
          "total_amount": 3500,
          "count": 2,
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
