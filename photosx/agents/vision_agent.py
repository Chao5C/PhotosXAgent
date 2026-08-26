from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.services.exif_service import extract_exif, image_to_jpeg_bytes
from photosx.graph.state import PhotoAgentState
from photosx.llm.client import create_agent_llm, extract_json, image_data_url, llm_available

logger = logging.getLogger(__name__)

VISION_SYSTEM = """你是 PhotosXAgent 的影像理解 Agent。根据图片内容和已有 EXIF，输出严格 JSON，不要 Markdown。
字段：
{
  "scene_type": "group|pet|scenery|food|architecture|other",
  "people_count": 0,
  "mood": "happy|calm|solemn|playful|unknown",
  "objects": ["显著物体"],
  "tags": ["合照","宠物","风景","美食","建筑", "..."],
  "caption": "一句话中文描述",
  "landmark_hint": "若能认出地点则填写，否则空字符串"
}
规则：合照指两人及以上；不确定时用 other / unknown；tags 用中文短词。
"""


def _fallback_vision(metadata: dict) -> dict:
    tags = ["未识别"]
    scene = "other"
    if metadata.get("lat") and metadata.get("lng"):
        tags = ["有定位", "待识别"]
        scene = "scenery"
    return {
        "scene_type": scene,
        "people_count": 0,
        "mood": "unknown",
        "objects": [],
        "tags": tags,
        "caption": "已提取拍摄信息，视觉模型未配置或调用失败。",
        "landmark_hint": "",
        "source": "fallback",
    }


async def run_vision_agent(state: PhotoAgentState) -> PhotoAgentState:
    file_path = Path(state["file_path"])
    metadata = extract_exif(file_path)
    vision: dict[str, Any] = _fallback_vision(metadata)

    if llm_available():
        try:
            jpeg = image_to_jpeg_bytes(file_path)
            llm = create_agent_llm("agent1", temperature=0.1, vision=True)
            exif_hint = (
                f"拍摄时间: {metadata.get('taken_at') or '未知'}; "
                f"GPS: {metadata.get('lat')},{metadata.get('lng')}; "
                f"设备: {metadata.get('camera') or '未知'}"
            )
            message = HumanMessage(
                content=[
                    {"type": "text", "text": f"请分析这张照片。EXIF 提示：{exif_hint}"},
                    {"type": "image_url", "image_url": {"url": image_data_url(jpeg)}},
                ]
            )
            response = await llm.ainvoke([SystemMessage(content=VISION_SYSTEM), message])
            parsed = extract_json(getattr(response, "content", "") or str(response))
            if parsed:
                vision = {
                    "scene_type": parsed.get("scene_type") or "other",
                    "people_count": int(parsed.get("people_count") or 0),
                    "mood": parsed.get("mood") or "unknown",
                    "objects": parsed.get("objects") or [],
                    "tags": parsed.get("tags") or [],
                    "caption": parsed.get("caption") or "",
                    "landmark_hint": parsed.get("landmark_hint") or "",
                    "source": "vision_llm",
                }
        except Exception as exc:
            logger.warning("Vision agent LLM failed: %s", exc)
            vision["error"] = str(exc)

    return {**state, "metadata": metadata, "vision": vision}
