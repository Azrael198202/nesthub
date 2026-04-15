# 自动化测试报告

## 消费记录录入

**输入：** 吃饭花了3000日元，两个人，在博多一兰拉面。今天买了咖啡500日元，还有买了书1200日元。上周末和家人去超市买东西一共花了8000日元。

**输出：**

{
  "trace_id": "trace_68e2ffca0b1a",
  "session_id": "budget_scene_e2e",
  "task": {
    "task_id": "task_54f0e2116934",
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
      "trace_id": "trace_68e2ffca0b1a",
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
    "workflow_id": "workflow_dcf3a9a145c1",
    "task_id": "task_54f0e2116934",
    "mode": "normal",
    "steps": [
      {
        "step_id": "step_33041840922b",
        "name": "extract_records",
        "task_type": "data_record",
        "depends_on": [],
        "retry": 1,
        "metadata": {
          "goal": "Extract structured records from natural language."
        }
      },
      {
        "step_id": "step_43612cac4fb0",
        "name": "persist_records",
        "task_type": "data_record",
        "depends_on": [
          "step_33041840922b"
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
        "step_id": "step_33041840922b",
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
              "created_at": "2026-04-15T08:17:42.801572+00:00"
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
              "created_at": "2026-04-15T08:17:42.801598+00:00"
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
              "created_at": "2026-04-15T08:17:42.801621+00:00"
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
              "created_at": "2026-04-15T08:17:42.801637+00:00"
            }
          ],
          "count": 4
        }
      },
      {
        "step_id": "step_43612cac4fb0",
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
            "created_at": "2026-04-15T08:17:42.801572+00:00"
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
            "created_at": "2026-04-15T08:17:42.801598+00:00"
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
            "created_at": "2026-04-15T08:17:42.801621+00:00"
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
            "created_at": "2026-04-15T08:17:42.801637+00:00"
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

**问题：** 4月份一共花了多少钱？

**输出：**

{
  "trace_id": "trace_fe3c7b5aa87a",
  "session_id": "budget_scene_e2e",
  "task": {
    "task_id": "task_115fa6d5cab9",
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
      "trace_id": "trace_fe3c7b5aa87a",
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
    "workflow_id": "workflow_60b48707d33c",
    "task_id": "task_115fa6d5cab9",
    "mode": "normal",
    "steps": [
      {
        "step_id": "step_60ba8f1ea361",
        "name": "parse_query",
        "task_type": "data_query",
        "depends_on": [],
        "retry": 1,
        "metadata": {
          "goal": "Parse analytical query intent and filters."
        }
      },
      {
        "step_id": "step_58aac72abcb8",
        "name": "aggregate_query",
        "task_type": "data_query",
        "depends_on": [
          "step_60ba8f1ea361"
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
        "step_id": "step_60ba8f1ea361",
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
            "filters": {},
            "query_text": "4月份一共花了多少钱？"
          }
        }
      },
      {
        "step_id": "step_58aac72abcb8",
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
          "filters": {},
          "query_text": "4月份一共花了多少钱？"
        }
      },
      "aggregate_query": {
        "aggregation": {
          "total_amount": 12700,
          "count": 4,
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

**问题：** 这个月餐饮花了多少？

**输出：**

{
  "trace_id": "trace_8d9ae6fc1eab",
  "session_id": "budget_scene_e2e",
  "task": {
    "task_id": "task_09d2a9bb7be0",
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
      "trace_id": "trace_8d9ae6fc1eab",
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
    "workflow_id": "workflow_21c2c93388b2",
    "task_id": "task_09d2a9bb7be0",
    "mode": "normal",
    "steps": [
      {
        "step_id": "step_4f71bc38b277",
        "name": "parse_query",
        "task_type": "data_query",
        "depends_on": [],
        "retry": 1,
        "metadata": {
          "goal": "Parse analytical query intent and filters."
        }
      },
      {
        "step_id": "step_479b9493e75f",
        "name": "aggregate_query",
        "task_type": "data_query",
        "depends_on": [
          "step_4f71bc38b277"
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
        "step_id": "step_4f71bc38b277",
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
        "step_id": "step_479b9493e75f",
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

**问题：** 我个人花了多少？

**输出：**

{
  "trace_id": "trace_74d9496f4c88",
  "session_id": "budget_scene_e2e",
  "task": {
    "task_id": "task_ae79e3c01500",
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
      "trace_id": "trace_74d9496f4c88",
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
    "workflow_id": "workflow_4a26f84fb204",
    "task_id": "task_ae79e3c01500",
    "mode": "normal",
    "steps": [
      {
        "step_id": "step_56c657831ccb",
        "name": "parse_query",
        "task_type": "data_query",
        "depends_on": [],
        "retry": 1,
        "metadata": {
          "goal": "Parse analytical query intent and filters."
        }
      },
      {
        "step_id": "step_d61e23e77c3a",
        "name": "aggregate_query",
        "task_type": "data_query",
        "depends_on": [
          "step_56c657831ccb"
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
        "step_id": "step_56c657831ccb",
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
              "actor": "self"
            },
            "query_text": "我个人花了多少？"
          }
        }
      },
      {
        "step_id": "step_d61e23e77c3a",
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
            "total_amount": 4700,
            "count": 3,
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
            "actor": "self"
          },
          "query_text": "我个人花了多少？"
        }
      },
      "aggregate_query": {
        "aggregation": {
          "total_amount": 4700,
          "count": 3,
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

**问题：** 家人花了多少？

**输出：**

{
  "trace_id": "trace_637ee2f7d907",
  "session_id": "budget_scene_e2e",
  "task": {
    "task_id": "task_bf3d310a3a5e",
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
      "trace_id": "trace_637ee2f7d907",
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
    "workflow_id": "workflow_e757749f237f",
    "task_id": "task_bf3d310a3a5e",
    "mode": "normal",
    "steps": [
      {
        "step_id": "step_fb60e711d207",
        "name": "parse_query",
        "task_type": "data_query",
        "depends_on": [],
        "retry": 1,
        "metadata": {
          "goal": "Parse analytical query intent and filters."
        }
      },
      {
        "step_id": "step_4f8fcd26d302",
        "name": "aggregate_query",
        "task_type": "data_query",
        "depends_on": [
          "step_fb60e711d207"
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
        "step_id": "step_fb60e711d207",
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
            "time_marker": "unspecified",
            "filters": {
              "actor": "家人"
            },
            "query_text": "家人花了多少？"
          }
        }
      },
      {
        "step_id": "step_4f8fcd26d302",
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
            "家人"
          ],
          "group_by": [],
          "time_marker": "unspecified",
          "filters": {
            "actor": "家人"
          },
          "query_text": "家人花了多少？"
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

**问题：** 咖啡一共花了多少？

**输出：**

{
  "trace_id": "trace_2946c9ec5ee1",
  "session_id": "budget_scene_e2e",
  "task": {
    "task_id": "task_bd0ce434f966",
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
      "trace_id": "trace_2946c9ec5ee1",
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
    "workflow_id": "workflow_fcf5c1bce4cc",
    "task_id": "task_bd0ce434f966",
    "mode": "normal",
    "steps": [
      {
        "step_id": "step_5cd990afddf8",
        "name": "parse_query",
        "task_type": "data_query",
        "depends_on": [],
        "retry": 1,
        "metadata": {
          "goal": "Parse analytical query intent and filters."
        }
      },
      {
        "step_id": "step_36f6c12f330d",
        "name": "aggregate_query",
        "task_type": "data_query",
        "depends_on": [
          "step_5cd990afddf8"
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
        "step_id": "step_5cd990afddf8",
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
            "time_marker": "unspecified",
            "filters": {
              "label": "food_and_drink"
            },
            "query_text": "咖啡一共花了多少？"
          }
        }
      },
      {
        "step_id": "step_36f6c12f330d",
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
            "咖啡"
          ],
          "group_by": [],
          "time_marker": "unspecified",
          "filters": {
            "label": "food_and_drink"
          },
          "query_text": "咖啡一共花了多少？"
        }
      },
      "aggregate_query": {
        "aggregation": {
          "total_amount": 500,
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

**问题：** 博多地区消费总额是多少？

**输出：**

{
  "trace_id": "trace_216817630fcf",
  "session_id": "budget_scene_e2e",
  "task": {
    "task_id": "task_8b2e8ea5b0f2",
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
      "trace_id": "trace_216817630fcf",
      "session_id": "budget_scene_e2e",
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
    "workflow_id": "workflow_3cbb37482537",
    "task_id": "task_8b2e8ea5b0f2",
    "mode": "normal",
    "steps": [
      {
        "step_id": "step_a9a8d421a484",
        "name": "parse_query",
        "task_type": "data_query",
        "depends_on": [],
        "retry": 1,
        "metadata": {
          "goal": "Parse analytical query intent and filters."
        }
      },
      {
        "step_id": "step_d7f910063309",
        "name": "aggregate_query",
        "task_type": "data_query",
        "depends_on": [
          "step_a9a8d421a484"
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
        "step_id": "step_a9a8d421a484",
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
              "location_keyword": "博多"
            },
            "query_text": "博多地区消费总额是多少？"
          }
        }
      },
      {
        "step_id": "step_d7f910063309",
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
            "total_amount": 3000,
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
          "terms": [],
          "group_by": [],
          "time_marker": "unspecified",
          "filters": {
            "location_keyword": "博多"
          },
          "query_text": "博多地区消费总额是多少？"
        }
      },
      "aggregate_query": {
        "aggregation": {
          "total_amount": 3000,
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
