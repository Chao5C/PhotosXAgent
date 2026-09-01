# 自媒体工作台 Agent · Beta 框架

## 目标

非专业用户也能：定选题 → 自动调研 → 长出口播/朋友圈/小红书/公众号/HTML-PPT →（可选）字幕与成片。

## 数据流

```
选题
  ↓ ① 调研层：联网取事实/金句（带来源）→ 热点筛选
content.md  ← 唯一内容源（SSOT）
  ↓ ② 派生层：注入官方 skills 指令（LLM 执行，不本地重写 skill）
  ├── speech.md / moments.md / xhs.md / wechat.md  ← humanizer
  ├── deck.html                                   ← html-ppt
  ├── podcast.txt + one_liner.md                  ← video-podcast-maker
  ↓ ③ 制作层：TTS → SRT → 画面/配乐 → 合成（完整成片走 video-podcast-maker 脚本）
output/（beta 多为 STATUS 占位）
```

## 文件结构

```
data/topics/{user_id}/2026-08-29-AI自媒体工具/
├── content.md
├── .manifest.json
├── research/
├── scripts/
├── assets/{voice,subtitle,visual,bgm}/
└── output/
```

## Skills（从 GitHub 获取，禁止自写替身）

| Skill | 来源 | 本地路径 |
| --- | --- | --- |
| humanizer | https://github.com/blader/humanizer | `skills/humanizer/` |
| html-ppt | https://github.com/lewislulu/html-ppt-skill | `skills/html-ppt/` |
| video-podcast-maker | https://github.com/Agents365-ai/video-podcast-maker | `skills/video-podcast-maker/` |

- 每个目录含 `ORIGIN.txt`（`do_not_rewrite=true`）与官方 `SKILL.md`。
- Cursor 侧通过 `.cursor/skills/{name}` junction 指向同一目录。
- 更新：`python scripts/fetch_studio_skills.py`，或解压 zip 到 `skills/_vendor` 后按 `ORIGIN` 同步。
- 运行时：`photosx/studio/skill_loader.py` 只加载官方文档；`skill_runtime.py` 把指令注入 LLM / 调用 skill 自带脚本（如 SRT）。

## API

- `POST /api/studio/topics` 创建选题
- `POST /api/studio/topics/{id}/research` 调研 → 写 content.md
- `POST /api/studio/topics/{id}/derive` 派生稿
- `POST /api/studio/topics/{id}/produce` 制作层
- `POST /api/studio/topics/{id}/pipeline` 一键
- `GET /api/studio/skills` 已安装 skill 列表
- `GET /api/studio/skill-assets/{skill}/…` html-ppt 静态资源

## Manifest 增量

`.manifest.json` 记录各产物的 `content_hash` / 文件 hash / 依赖。  
改 `content.md` 后下游标 `stale`，再派生时按指纹重算。

## 可能出现的问题

1. **检索失败**：DuckDuckGo HTML 可能超时/被墙 → `research/sources` 为空，content 会标注风险，需人工粘贴资料到 `research/` 或 content。
2. **SSOT 不同步**：只改了派生稿没改 content → 下次派生会覆盖；应始终改 content.md。
3. **LLM 幻觉**：数字/出处必须以 sources 为准；检查 content 里「风险与待核实」。
4. **TTS 未启用**：默认 `STUDIO_TTS_ENABLED=false`；开启且安装 `edge-tts` 才尝试生成音频。完整 TTS 走 video-podcast-maker。
5. **无 ffmpeg / Remotion**：不产出 `final.mp4`，只有 `output/STATUS.md` 与清单。
6. **声线一致性**：beta 仅记录 `voice_id`，克隆声线需后续接入。
7. **版权/配乐**：用户自备 BGM；不要默认使用受版权保护曲库。
8. **路径安全**：仅允许读写当前用户 `topics` 目录下相对路径。
9. **HTML-PPT 预览**：Deck 内 CSS/JS 走 `/api/studio/skill-assets/html-ppt/...`；前端用鉴权 fetch + blob URL。
10. **耗时**：一键流水线含多次 LLM，超时需提高前端/网关 timeout。
11. **Skill 未安装**：`skills/*/SKILL.md` 缺失时派生会降级/报缺；重新 fetch。

## 环境变量

```
TOPICS_DIR=data/topics
STUDIO_VOICE_ID=default
STUDIO_TTS_ENABLED=false
```
