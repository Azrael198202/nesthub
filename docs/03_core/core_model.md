# AI 模型与能力全景清单（用于 Core 模型路由与系统设计）

---

# 1 说明

本文档用于定义 AI Core 可使用的各类能力模型，包括：

* LLM（文本理解/推理）
* OCR（图像文字识别）
* STT（语音转文本）
* TTS（文本转语音）
* 图像生成
* 视频/动画生成
* 文件生成
* Web检索

用于：

* Core 模型路由
* Blueprint 设计
* Agent 能力定义
* 自动代码生成

---

# 2 文本类模型（LLM）

## 本地模型（Ollama）

### Qwen2.5

* 优势：中文/日文强、结构化输出稳定
* 用途：NLP解析、JSON输出、查询解析

### DeepSeek-Coder

* 优势：代码生成强
* 用途：Blueprint生成、代码生成

### LLaMA3

* 优势：通用能力强
* 用途：fallback模型

---

## 外网模型

### GPT-4o

* 优势：综合能力最强
* 用途：推理、Agent生成、Workflow规划

### GPT-4.1

* 优势：代码能力强
* 用途：自动代码生成

### Claude 3.5

* 优势：长文本处理强
* 用途：文档生成、复杂分析

---

# 3 OCR（图像识别）

## 本地

* PaddleOCR

  * 优势：开源、支持中日文
  * 用途：截图识别、票据识别

## 云

* Google Vision OCR
* Azure OCR

---

# 4 STT（语音识别）

## 本地

* Whisper

  * 优势：准确率高、多语言
  * 用途：语音输入

## 云

* Azure Speech to Text
* Google Speech

---

# 5 TTS（语音合成）

## 本地

* OpenVoice

  * 优势：可做声音克隆

## 云

* Azure TTS
* ElevenLabs
* Google TTS

  * 优势：自然度高

---

# 6 图像生成

## 模型

* Stable Diffusion

  * 本地部署

* DALL·E

* Midjourney

## 用途

* UI生成
* 插图
* 产品图

---

# 7 视频 / 动画生成

## 模型

* Runway Gen-2
* Pika

## 用途

* 短视频生成
* AI展示动画

---

# 8 文件生成

## 文档

* Python-docx（Word）
* ReportLab（PDF）

## 表格

* openpyxl
* pandas

## PPT

* python-pptx

---

# 9 Web 检索与自动化

## 工具

* Playwright
* Selenium

## 用途

* 网页抓取
* 自动查询

---

# 10 数据库与存储

## 结构化数据

* PostgreSQL（推荐）

## 向量数据库

* Weaviate
* pgvector

---

# 11 Core 模型路由建议

```python
if task == "nlp_parse":
    use "qwen"

elif task == "reasoning":
    use "gpt4o"

elif task == "code":
    use "gpt4.1"

elif task == "ocr":
    use "paddleocr"

elif task == "stt":
    use "whisper"

elif task == "tts":
    use "openvoice"
```

---

# 12 附加说明
## Core 自动能力选择
    AI 可以根据任务自动选模型

## Blueprint 自动生成
    每个能力都可以映射为：
        blueprint.input
        blueprint.tool
        blueprint.runtime

## Agent 自动生成
    自动组合：LLM + OCR + STT + DB + Web

## 代码自动生成
    直接让 AI 输出：
        adapters/
        services/
        tool registry

# 13 总结

AI Core 应具备多模型、多能力调度能力：

* 文本 → LLM
* 图片 → OCR / Diffusion
* 语音 → STT / TTS
* 视频 → 动画模型
* 文件 → 生成工具
* 数据 → 数据库

核心不是单一模型，而是：

👉 模型组合 + 能力调度 + 工作流执行

---
