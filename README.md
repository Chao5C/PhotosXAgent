# PhotosXAgent

基于多 Agent 的图片管理与智能相册系统。技术栈:Vue 3 + FastAPI + LangGraph + MongoDB + Redis

## 三个 Agent

| Agent | 职责 |
|---|---|
| Agent1 影像理解 | 读取 EXIF（时间、GPS），多模态识别合照/宠物/风景/美食/建筑，人数、情绪、显著物体并打标签 |
| Agent2 推荐顾问 | 根据新地点、天气、相册给出建议 |
| Agent3 助手 | 对话式对接用户需求：查图、问行程、解释推荐 |

行程模拟与相册分类由规则层根据 Agent1 的结构化结果生成。

## 快速开始

```powershell
# 1. 启动 MongoDB / Redis（也可使用本机已有服务）
docker compose up -d

# 2. 后端
copy .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
uvicorn app.main:app --reload --port 8000

# 3. 前端（另开终端）
cd frontend
npm install
npm run dev
```

默认账号：`admin` / `admin123`。前端：http://localhost:3000 ，后端：http://localhost:8000。

配置 `.env` 中的视觉模型 API Key 后，Agent1 才能识别画面内容；未配置时仍会提取 EXIF 并生成基础相册/行程。
