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

## 更新日志
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

