# PhotosXAgent

基于多 Agent（**工具调用 / ReAct**）的图片管理与智能相册系统。技术栈：Vue 3 + FastAPI + LangGraph + MongoDB + Redis。

版本见 `VERSION` 文件。

## Agent 一览

| Agent | 实现 | 职责 |
|---|---|---|
| Agent1 影像理解 | `vision_agent` + `submit_vision_result` | EXIF + 多模态识别，结构化标签/描述 |
| Agent2 推荐 / 攻略 | `recommend_agent` / `analysis_agent` | 天气与行程工具 → 提交推荐/攻略 |
| Agent3 Chat 助手 | `assistant_agent` + 12 个 Chat 工具 | 搜图、细节问答、记忆/提醒、强制推送 |

Chat 两阶段检索：主检索只用短标签 chunk；追问细节时按照片 ID 加载长 chunk。会话状态 ACTIVE / IDLE / DORMANT 控制推送时机（`SessionService` + `push_worker`）。

## 环境要求

- Windows 10/11（一键脚本）或任意可跑 Docker / Python / Node 的环境
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)（MongoDB + Redis）
- Python **3.10+**
- Node.js **18+**（前端）
- 至少一个 LLM API Key（通义 / DeepSeek / 火山等），或本机 Ollama

## 一键部署（推荐）

1. 解压发布包到任意目录。
2. 双击 **`start.bat`**（或 PowerShell：`.\start_dev.ps1`）。
3. 脚本会自动：
   - 启动 Docker 中的 MongoDB / Redis
   - 若无 `.env` 则从 `.env.example` 复制
   - 创建 `.venv` 并 `pip install -e .`
   - 安装前端依赖并启动前后端
4. 浏览器打开：**http://localhost:3000**  
   API：**http://localhost:8000**  
   默认账号：`admin` / `admin123`

首次使用请编辑 `.env`，至少配置一个厂家密钥（如 `DASHSCOPE_API_KEY`），也可在前端「配置管理」中填写。

强制重装依赖：

```powershell
.\start_dev.ps1 -Install
```

只起某一部分：

```powershell
.\start_dev.ps1 docker
.\start_dev.ps1 backend
.\start_dev.ps1 frontend
```

## 手动启动

```powershell
# 1. 基础设施
docker compose up -d

# 2. 环境变量
copy .env.example .env

# 3. 后端
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 4. 前端（另开终端）
cd frontend
npm install
npm run dev
```

## 目录结构（节选）

```
PhotosXAgent/
├── start.bat             # Windows 一键入口
├── start_dev.ps1         # 开发/部署启动脚本
├── docker-compose.yml    # MongoDB + Redis
├── .env.example
├── app/                  # FastAPI 路由与服务
├── photosx/
│   ├── agents/           # Vision / Recommend / Analysis / Chat
│   │   └── tools/        # Chat 工具（RAG / 推送 / 记忆等）
│   ├── graph/            # LangGraph
│   └── llm/
├── frontend/             # Vue 3
├── scripts/
│   ├── pack_release.ps1  # 打发布 zip
│   └── fetch_studio_skills.py
└── skills/               # Studio 技能（可选）
```

## Chat 工具能力（Agent3）

- `search_photos_short` / `search_albums` / `get_search_page`：检索与「查看更多」
- `load_photo_long` / `get_photo_geo` / `get_weather`：单张细节、地点、天气
- `analyze_photos` / `push_guide`：整合分析、主动推送攻略
- `mute_topic` / `add_reminder` / `add_memory_fact` / `get_memory`：偏好与定时提醒

助手还支持：**流式对话**、**出行攻略**（联网搜索 + 天气）、**按需生成攻略海报**（PNG，保存至海报图库）。设置页可配置 **MCP 网关**（网页搜索 / 天气服务）。

人物美丑类问题会直接拒绝评价，不调用外貌分析工具。

## 自媒体工作台 Studio

目前仍在积极开发中，已实现联网搜索，文案撰写，口播稿，社媒文案。

选题 → 调研 → 派生 → 制作。技能从 GitHub 安装到 `skills/`：

- [blader/humanizer](https://github.com/blader/humanizer)
- [lewislulu/html-ppt-skill](https://github.com/lewislulu/html-ppt-skill)
- [Agents365-ai/video-podcast-maker](https://github.com/Agents365-ai/video-podcast-maker)

更新技能：`python scripts/fetch_studio_skills.py`。说明见 `docs/studio-beta.md`。


## 打包发布 zip

在项目根目录执行：

```powershell
.\scripts\pack_release.ps1
```

默认输出到上级目录：`PhotosXAgent-v<VERSION>-deploy-<日期>.zip`（不含 `.venv`、`node_modules`、`.env`、上传数据等）。

## 版本发布日志

### v0.3.0（2026-09-01）

**助手与对话**

- 新增 **SSE 流式输出**：助手回复逐字显示，状态提示（检索、生成中等）实时更新
- 修复 **出行攻略误触发搜图**：「想去上海有什么建议」等问句正确走攻略流程，不再误匹配相册检索
- 攻略生成接入 **联网搜索 + 天气**（DuckDuckGo / MCP），输出完整建议与追问引导，去除占位文案
- 修复 **定时提醒**：支持「30 秒后提醒我」等秒级表达；在线用户提醒直接写入聊天并展示提醒卡片

**攻略海报**

- 攻略完成后 **询问是否生成海报**，用户回复「生成海报」后才创建，避免浪费 token
- 海报改为 **PNG 图片**直接返回与预览，移除 HTML 版
- 修复聊天内海报 **无法预览 / 下载**（内联 base64 + 鉴权文件接口）
- 新增 **海报图库** 页面（侧边栏入口）：浏览、下载、删除已保存海报

**MCP 网关**

- 内置 **网页搜索**、**天气查询** 两个 MCP 服务（`photosx/mcp/`）
- 设置页新增 **MCP 网关** 配置与连接测试
- 攻略与助手可通过网关统一调用外部 MCP 工具

**其他**

- 聊天历史持久化时剥离海报 base64，减小 MongoDB 占用
- 依赖新增 `mcp>=1.6.0`

### v0.2.0

- 多 Agent 架构：影像理解、推荐/攻略、Chat 助手（ReAct + 12 个工具）
- 两阶段 RAG 检索、会话 ACTIVE/IDLE/DORMANT 推送控制
- 自媒体工作台 Studio（选题 → 调研 → 派生 → 制作）
- Windows 一键部署脚本 `start.bat` / `start_dev.ps1`

## 更新日志

# 8.29

才发现Agent没有走FunctionCall那一套，思路还是基于python的脚本来实现，这样确实会稳妥一些，但是会增加代码量和维护成本，今天把这些有关工具调用的Agent全部重写优化

# 8.28

分析 / 推送

POST /api/analysis/analyze：只分析、建索引、入库

POST /api/analysis/push：生成攻略并投递

自动触发需同时满足：距常用地 >50km、新地点附近至少 3 张且在 2 小时内、与上一张旧地点间隔 <6 小时、EXIF 设备一致；若这 3 张跨度 >7 天则不触发

ChatAgent

意图：QUERY 短 chunk 向量检索 → QUESTION 按图片 ID 加载长 chunk → COMMAND 改记忆/定时提醒 → REQUEST_PUSH 直接调推送接口

人物美丑类问题会拒绝评价；地点/天气走工具

会话：ACTIVE（5 分钟内）缓存不推；IDLE / DORMANT 立即推，离开较久会合并

到瓶颈期了，对于多Agent相互之间的调用逻辑还需要继续细化

要先确保可用性，再谈性能与效率

# 8.27
新增Ollama模型的一键识别读取

重命名各类Agent，细分工作范畴

修复了地图不会正常显示的bug

MutiAgent之间的协同进一步优化

仍需改进的点：

LLM对嵌入模型的选择

ChatAgent对于另外Agent的接口管理调用还需优化

用户隐私加密问题

识别准确度

识别内容所需调用的数据库

用量统计页面

ChatAgent的推送逻辑

# 8.26
实现了登陆页面的管理

上传图片管理

跑通分析图片流程

添加对各大LLM的支持

添加模型选择功能

添加模型禁用与测试功能

添加对本地Ollama模型的支持

优化了.env的可读性

实现简单的前端页面，后续将对外观进行优化

# 8.25
设计了整体的工作流

初步搭建好所需框架



## 常见问题

| 现象 | 处理 |
|---|---|
| Docker Compose 失败 | 确认 Docker Desktop 已启动 |
| 端口 3000/8000 占用 | 关闭占用进程，或改脚本中的端口 |
| Agent 不识图 / 不调工具 | 检查 `.env` 或前端配置的 API Key；Chat 需支持 function calling 的模型 |
| 仅 EXIF、无画面标签 | 未配置视觉模型时属预期；配好 Key 后重新上传或触发流水线 |
