# 自动化测试报告

## 消费记录录入

**输入：** 吃饭花了3000日元，两个人，在博多一兰拉面。今天买了咖啡500日元，还有买了书1200日元。上周末和家人去超市买东西一共花了8000日元。

**输出：**

{
  "trace_id": "trace_990d776cb09c",
  "session_id": "budget_scene_e2e",
  "task": {
    "task_id": "task_cdf1a0207000",
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
      "trace_id": "trace_990d776cb09c",
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
    "execution_type": "workflow",
    "workflow_state": {
      "user_input": "吃饭花了3000日元，两个人，在博多一兰拉面。今天买了咖啡500日元，还有买了书1200日元。上周末和家人去超市买东西一共花了8000日元。",
      "task_id": "task_6040dbabed53",
      "context": {
        "session_id": "budget_scene_e2e",
        "trace_id": "trace_990d776cb09c",
        "created_at": "2026-04-16T01:49:05.759803+00:00",
        "locale": "ja-JP",
        "timezone": "Asia/Tokyo",
        "session_state": {
          "records": []
        },
        "metadata": {
          "enriched_at": "2026-04-16T01:49:05.759820+00:00",
          "record_count": 0
        }
      },
      "intent": {
        "type": "general_task",
        "confidence": 0.8,
        "needs_agent": false
      },
      "plan": [
        {
          "step": 1,
          "name": "task_1",
          "status": "completed"
        },
        {
          "step": 2,
          "name": "task_2",
          "status": "completed"
        }
      ],
      "current_step": 3,
      "results": [
        {
          "step": 1,
          "result": "success"
        },
        {
          "step": 2,
          "result": "success"
        }
      ],
      "errors": [],
      "should_continue": false,
      "retry_count": 0,
      "timestamp": "2026-04-16T10:49:05.760473",
      "trace_id": "trace_990d776cb09c"
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
  "trace_id": "trace_1c5bd524f5a2",
  "session_id": "budget_scene_e2e",
  "task": {
    "task_id": "task_802d40996d16",
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
      "trace_id": "trace_1c5bd524f5a2",
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
    "execution_type": "workflow",
    "workflow_state": {
      "user_input": "4月份一共花了多少钱？",
      "task_id": "task_04cf16eda86e",
      "context": {
        "session_id": "budget_scene_e2e",
        "trace_id": "trace_1c5bd524f5a2",
        "created_at": "2026-04-16T01:49:05.762401+00:00",
        "locale": "ja-JP",
        "timezone": "Asia/Tokyo",
        "session_state": {
          "records": []
        },
        "metadata": {
          "enriched_at": "2026-04-16T01:49:05.762410+00:00",
          "record_count": 0
        }
      },
      "intent": {
        "type": "general_task",
        "confidence": 0.8,
        "needs_agent": false
      },
      "plan": [
        {
          "step": 1,
          "name": "task_1",
          "status": "completed"
        },
        {
          "step": 2,
          "name": "task_2",
          "status": "completed"
        }
      ],
      "current_step": 3,
      "results": [
        {
          "step": 1,
          "result": "success"
        },
        {
          "step": 2,
          "result": "success"
        }
      ],
      "errors": [],
      "should_continue": false,
      "retry_count": 0,
      "timestamp": "2026-04-16T10:49:05.762661",
      "trace_id": "trace_1c5bd524f5a2"
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
  "trace_id": "trace_88274e650a96",
  "session_id": "budget_scene_e2e",
  "task": {
    "task_id": "task_0f6288511994",
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
      "trace_id": "trace_88274e650a96",
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
    "execution_type": "workflow",
    "workflow_state": {
      "user_input": "这个月餐饮花了多少？",
      "task_id": "task_4b5a7676aee3",
      "context": {
        "session_id": "budget_scene_e2e",
        "trace_id": "trace_88274e650a96",
        "created_at": "2026-04-16T01:49:05.765191+00:00",
        "locale": "ja-JP",
        "timezone": "Asia/Tokyo",
        "session_state": {
          "records": []
        },
        "metadata": {
          "enriched_at": "2026-04-16T01:49:05.765233+00:00",
          "record_count": 0
        }
      },
      "intent": {
        "type": "general_task",
        "confidence": 0.8,
        "needs_agent": false
      },
      "plan": [
        {
          "step": 1,
          "name": "task_1",
          "status": "completed"
        },
        {
          "step": 2,
          "name": "task_2",
          "status": "completed"
        }
      ],
      "current_step": 3,
      "results": [
        {
          "step": 1,
          "result": "success"
        },
        {
          "step": 2,
          "result": "success"
        }
      ],
      "errors": [],
      "should_continue": false,
      "retry_count": 0,
      "timestamp": "2026-04-16T10:49:05.766584",
      "trace_id": "trace_88274e650a96"
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
  "trace_id": "trace_1243219c5388",
  "session_id": "budget_scene_e2e",
  "task": {
    "task_id": "task_03925d60f276",
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
      "trace_id": "trace_1243219c5388",
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
    "execution_type": "workflow",
    "workflow_state": {
      "user_input": "我个人花了多少？",
      "task_id": "task_4433d16f93b3",
      "context": {
        "session_id": "budget_scene_e2e",
        "trace_id": "trace_1243219c5388",
        "created_at": "2026-04-16T01:49:05.771965+00:00",
        "locale": "ja-JP",
        "timezone": "Asia/Tokyo",
        "session_state": {
          "records": []
        },
        "metadata": {
          "enriched_at": "2026-04-16T01:49:05.772006+00:00",
          "record_count": 0
        }
      },
      "intent": {
        "type": "general_task",
        "confidence": 0.8,
        "needs_agent": false
      },
      "plan": [
        {
          "step": 1,
          "name": "task_1",
          "status": "completed"
        },
        {
          "step": 2,
          "name": "task_2",
          "status": "completed"
        }
      ],
      "current_step": 3,
      "results": [
        {
          "step": 1,
          "result": "success"
        },
        {
          "step": 2,
          "result": "success"
        }
      ],
      "errors": [],
      "should_continue": false,
      "retry_count": 0,
      "timestamp": "2026-04-16T10:49:05.772916",
      "trace_id": "trace_1243219c5388"
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
  "trace_id": "trace_109857e7fe32",
  "session_id": "budget_scene_e2e",
  "task": {
    "task_id": "task_aeaceb0524a9",
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
      "trace_id": "trace_109857e7fe32",
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
    "execution_type": "workflow",
    "workflow_state": {
      "user_input": "家人花了多少？",
      "task_id": "task_76bb96a3e12d",
      "context": {
        "session_id": "budget_scene_e2e",
        "trace_id": "trace_109857e7fe32",
        "created_at": "2026-04-16T01:49:05.776840+00:00",
        "locale": "ja-JP",
        "timezone": "Asia/Tokyo",
        "session_state": {
          "records": []
        },
        "metadata": {
          "enriched_at": "2026-04-16T01:49:05.776852+00:00",
          "record_count": 0
        }
      },
      "intent": {
        "type": "general_task",
        "confidence": 0.8,
        "needs_agent": false
      },
      "plan": [
        {
          "step": 1,
          "name": "task_1",
          "status": "completed"
        },
        {
          "step": 2,
          "name": "task_2",
          "status": "completed"
        }
      ],
      "current_step": 3,
      "results": [
        {
          "step": 1,
          "result": "success"
        },
        {
          "step": 2,
          "result": "success"
        }
      ],
      "errors": [],
      "should_continue": false,
      "retry_count": 0,
      "timestamp": "2026-04-16T10:49:05.777762",
      "trace_id": "trace_109857e7fe32"
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
  "trace_id": "trace_87b55b4e34db",
  "session_id": "budget_scene_e2e",
  "task": {
    "task_id": "task_962a1f6df928",
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
      "trace_id": "trace_87b55b4e34db",
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
    "execution_type": "workflow",
    "workflow_state": {
      "user_input": "咖啡一共花了多少？",
      "task_id": "task_d9f5fe244e2f",
      "context": {
        "session_id": "budget_scene_e2e",
        "trace_id": "trace_87b55b4e34db",
        "created_at": "2026-04-16T01:49:05.784441+00:00",
        "locale": "ja-JP",
        "timezone": "Asia/Tokyo",
        "session_state": {
          "records": []
        },
        "metadata": {
          "enriched_at": "2026-04-16T01:49:05.784484+00:00",
          "record_count": 0
        }
      },
      "intent": {
        "type": "general_task",
        "confidence": 0.8,
        "needs_agent": false
      },
      "plan": [
        {
          "step": 1,
          "name": "task_1",
          "status": "completed"
        },
        {
          "step": 2,
          "name": "task_2",
          "status": "completed"
        }
      ],
      "current_step": 3,
      "results": [
        {
          "step": 1,
          "result": "success"
        },
        {
          "step": 2,
          "result": "success"
        }
      ],
      "errors": [],
      "should_continue": false,
      "retry_count": 0,
      "timestamp": "2026-04-16T10:49:05.785072",
      "trace_id": "trace_87b55b4e34db"
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
  "trace_id": "trace_9a244d4985b3",
  "session_id": "budget_scene_e2e",
  "task": {
    "task_id": "task_d59979a74b51",
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
      "trace_id": "trace_9a244d4985b3",
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
  "workflow": {},
  "blueprints": [],
  "agent": null,
  "execution_result": {
    "execution_type": "workflow",
    "workflow_state": {
      "user_input": "博多地区消费总额是多少？",
      "task_id": "task_02aaa26a0e89",
      "context": {
        "session_id": "budget_scene_e2e",
        "trace_id": "trace_9a244d4985b3",
        "created_at": "2026-04-16T01:49:05.789963+00:00",
        "locale": "ja-JP",
        "timezone": "Asia/Tokyo",
        "session_state": {
          "records": []
        },
        "metadata": {
          "enriched_at": "2026-04-16T01:49:05.790005+00:00",
          "record_count": 0
        }
      },
      "intent": {
        "type": "general_task",
        "confidence": 0.8,
        "needs_agent": false
      },
      "plan": [
        {
          "step": 1,
          "name": "task_1",
          "status": "completed"
        },
        {
          "step": 2,
          "name": "task_2",
          "status": "completed"
        }
      ],
      "current_step": 3,
      "results": [
        {
          "step": 1,
          "result": "success"
        },
        {
          "step": 2,
          "result": "success"
        }
      ],
      "errors": [],
      "should_continue": false,
      "retry_count": 0,
      "timestamp": "2026-04-16T10:49:05.790657",
      "trace_id": "trace_9a244d4985b3"
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
