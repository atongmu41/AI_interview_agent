# AI Interview Agent

一个基于 LLM 的智能面试助手，支持简历解析、个性化出题、ReAct 控制面试流程、多维度评估，以及 Web UI 和 RAG 岗位知识检索。

---

## 功能总览

- **LLM 封装**：统一的 `LLMClient`，支持重试、超时控制、从 `.env` 加载配置。
- **面试状态机**：`Supervisor` 负责状态切换与 ReAct 循环，集中处理所有工具调用。
- **面试官 Agent**：`Interviewer` 负责生成自然语言提问和追问。
- **评估 Agent**：`EvaluatorAgent` 对候选人的回答进行多维度评分（技术/沟通/逻辑）、综合评语与置信度。
- **工具系统 (Tool Calling)**：
  - `search`：基于 SerpAPI 的 Web 搜索。
  - `resume_parser`：PDF 简历解析。
  - `skill_extractor`：从简历中抽取技能/项目。
  - `question_matcher`：结合题库与技能匹配合适题目。
  - `knowledge_base`：岗位知识检索（RAG）。
  - 其他占位工具：`timer`、`candidate_db`、`calendar`、`notification` 等。
- **题库与评估配置**：
  - `config/questions.yaml`：按岗位/难度组织的题库。
  - `config/prompts.yaml`：面试官、评估官的 system prompt 配置。
- **向量数据库 (Qdrant)**：
  - `services/vector_db.py`：Qdrant 封装（创建集合、upsert、search、delete）。
- **Embedding 服务**：
  - `services/embedding.py`：对接 DashScope OpenAI 兼容 Embedding 接口（如 `text-embedding-v3`）。
- **RAG 岗位知识检索**：
  - `doc/job_description.md`：互联网常见岗位 JD 汇总。
  - `scripts/index_job_descriptions.py`：将 JD 分块后编码、写入 Qdrant 集合 `job_profiles`。
  - `tools/knowledge_base.py`：对岗位名称做 embedding + 向量检索，返回岗位要求片段。
- **CLI 面试流程**：`main.py` 支持纯文本面试，含 `/interrupt`、`/continue`、`/end` 等命令，并在结束时输出评估报告。
- **Web UI**：
  - 基于 FastAPI 的后端：`ui/web/app.py`。
  - 前端：`ui/web/templates/index.html` + `ui/web/static/main.js` + `ui/web/static/styles.css`。
  - 支持简历上传、简历解析预览、岗位选择 + 自定义岗位、实时对话面试、终止面试 + 展示评估报告。

---

## 项目结构

主要目录（部分）如下：

```text
ai-interview-agent/
├── agents/
│   ├── interviewer.py        # 面试官 Agent
│   ├── evaluator.py          # 评估 Agent（多维度 + 置信度）
│   └── supervisor.py         # 状态机 + ReAct 控制器
├── config/
│   ├── prompts.yaml          # interviewer/evaluator prompt 配置
│   └── questions.yaml        # 题库（按岗位/难度）
├── doc/
│   └── job_description.md    # 岗位 JD 汇总（RAG 数据源）
├── services/
│   ├── llm.py                # LLMClient 封装
│   ├── embedding.py          # EmbeddingClient 封装（DashScope 兼容模式）
│   ├── question_bank.py      # 题库加载与抽题逻辑
│   └── vector_db.py          # Qdrant VectorDB 封装
├── tools/
│   ├── base.py               # ToolSpec / ToolRegistry
│   ├── __init__.py           # 注册所有工具
│   ├── search.py             # SerpAPI 搜索工具
│   ├── resume_parser.py      # PDF 简历解析
│   ├── skill_extractor.py    # 技能/项目抽取
│   ├── question_matcher.py   # 题目匹配（规则 + 可选向量排序占位）
│   └── knowledge_base.py     # 岗位知识库检索（RAG）
├── ui/web/
│   ├── app.py                # FastAPI Web 后端
│   ├── templates/index.html  # Web UI 模板
│   └── static/
│       ├── main.js           # 前端逻辑（简历上传+面试+评估）
│       └── styles.css        # Web 样式
├── scripts/
│   └── index_job_descriptions.py  # JD 入库 Qdrant 脚本
├── main.py                   # CLI 文本版面试入口
├── resume_interview.py       # 简历驱动的 CLI 面试流程（简历→技能→题目→评估）
├── requirements.txt          # 依赖列表
└── env/.env                  # 环境变量（不纳入版本控制）
```

---

## 环境配置

### Python 环境

```bash
# 推荐使用虚拟环境
python -m venv .venv
.\.venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

`requirements.txt` 包含（示例）：

```text
httpx
pyyaml
qdrant-client
pdfplumber
fastapi
uvicorn
python-multipart
```

### 环境变量（env/.env）

在 `env/.env` 中配置：

```env
# LLM 服务（兼容 OpenAI）
OPENAI_API_KEY=你的LLM_API_KEY
OPENAI_BASE_URL=https://api.gemai.cc/v1
MODEL_NAME=gpt-5.1-codex-mini

# SerpAPI（用于 search 工具）
SERPAPI_API_KEY=你的_SERPAPI_KEY

# Qdrant（向量数据库）
QDRANT_URL=你的_QDRANT_URL
QDRANT_API_KEY=你的_QDRANT_API_KEY

# Embedding 服务（DashScope 兼容模式示例）
EMBEDDING_API_KEY=你的_DASHSCOPE_KEY
EMBEDDING_MODEL=text-embedding-v3          # 或 DashScope 文档中的模型名
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

> 注意：`env/.env` 不应提交到版本库，只在本地配置。

---

## 运行方式

### 1. CLI 文本面试

```bash
python main.py
```

- 按提示输入候选人回答；
- 使用如下命令控制流程：
  - `/interrupt`：打断当前轮；
  - `/continue`：跳到评估或下一题；
  - `/end`：终止面试，并根据当前轮 Q/A 输出评估报告。

评估报告由 `EvaluatorAgent` 生成，包含：

- `overall_score`
- 维度评分（技术/沟通/逻辑）及置信度
- 综合评语、优势、改进建议、风险提示。

### 2. 简历驱动的 CLI 面试

```bash
python resume_interview.py --resume path/to/resume.pdf
```

简单流程：

1. `resume_parser` 解析简历；
2. `skill_extractor` 抽取技能/项目；
3. `question_matcher` 从题库中匹配问题；
4. `Supervisor + Interviewer` 进行问答；
5. `EvaluatorAgent` 输出评估报告。

（具体参数和交互可根据代码进一步扩展。）

### 3. Web UI

启动 FastAPI 服务：

```bash
uvicorn ui.web.app:app --reload
```

在浏览器访问：`http://localhost:8000/`

Web 功能包括：

- **简历上传**：上传 PDF，展示解析结果（姓名、联系方式、教育、技能、匹配问题）。
- **岗位选择**：
  - 左侧下拉选固定岗位（如 `后端 - Python`）；
  - 右侧文本框可自由输入岗位名称（如“后端开发工程师（Go）”），用于生成岗位要求画像。
- **岗位要求展示**：RAG 检索 `job_profiles` 集合，给出岗位 JD 段落。
- **实时面试**：
  - 聊天气泡展示问答；
  - 打断/继续/终止面试；
  - 面试结束/中途终止时触发评估，右侧面板展示评估报告（结构化 JSON 已格式化为卡片）。

---

## RAG 岗位知识检索

### 1. 将 job_description.md 入库 Qdrant

先确保 `.env` 中 Embedding 和 Qdrant 配置正常，然后在项目根执行：

```bash
python -m scripts.index_job_descriptions
```

脚本会：

- 从 `doc/job_description.md` 读入所有岗位 JD；
- 按 `###` 分块（每个岗位一块）；
- 使用 `embed_batch` 编码为向量；
- 调用 `VectorDB.upsert("job_profiles", ...)` 写入 Qdrant。

运行成功后，会看到类似输出：

```text
已将 30 个岗位块写入集合 'job_profiles'。
```

### 2. 通过 knowledge_base 查询岗位要求

在 Python 中直接调用：

```python
from tools.knowledge_base import run as kb_run

print(kb_run("Python 后端开发工程师", category="job_profile"))
```

流程：

1. 使用 `services.embedding.embed` 将查询文本编码；
2. 在 `job_profiles` 集合中用 `VectorDB.search` 做相似度检索；
3. 将命中的 JD 片段（title + 原文）拼接为岗位要求说明返回。

Web 和 ReAct 中的岗位画像也是通过该工具实现的。

---

## 开发说明

- 所有工具通过 `tools.base.ToolRegistry` 统一管理，`Supervisor` 在 ReAct 循环中动态选择并调用工具。
- 若需新增工具：
  1. 在 `tools/` 下新建 `<name>.py`，实现 `run(...)` 与 `SPEC = ToolSpec(...)`。
  2. 在 `tools/__init__.py` 中导入并注册到 `get_default_registry()`。
- 若需新增 RAG 数据源：
  1. 准备新的 `.md` / 文本文件；
  2. 编写类似 `index_job_descriptions.py` 的索引脚本，将文本分块后写入 Qdrant；
  3. 在 `knowledge_base.run` 中增加新的 `category` 分支。

---

## 注意事项

- 请妥善管理 `.env` 中的各类 API Key，不要提交到版本库。
- DashScope / Qdrant 的配额、QPS、模型权限等问题，可能导致 4xx/5xx 错误，调试时建议先用 `test_embedding.py` 或最小脚本验证单条 embedding 是否正常。
- 由于项目已经集成了较多功能（CLI + Web + RAG + ReAct），在修改任一核心模块（如 `LLMClient`、`EmbeddingClient`、`VectorDB`）时，建议逐一验证：
  - `test_embedding.py`
  - `scripts/index_job_descriptions.py`
  - `knowledge_base.run(...)`
  - Web 上传简历 & 岗位画像显示

欢迎在此基础上继续扩展，例如增加更多岗位 JD、增加多语言支持、丰富 ReAct 工具链等。

