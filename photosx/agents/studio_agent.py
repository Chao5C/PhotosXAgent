from __future__ import annotations



import logging

from typing import Any



from langchain_core.messages import HumanMessage, SystemMessage



from photosx.llm.client import create_agent_llm, llm_available

from photosx.studio.skill_runtime import humanize



logger = logging.getLogger(__name__)



SPEECH_SYSTEM = """你是口播稿编剧。根据 content.md 写 45–90 秒口播，口语化，短句，适合念。

只输出口播正文，不要标题与舞台指示。"""



MOMENTS_SYSTEM = """你写微信朋友圈文案。要求：短、有画面感、可配 1-3 张图说明，不硬广。

输出正文即可，可含 2–4 个话题标签。"""



XHS_SYSTEM = """你写小红书笔记。结构：吸睛标题一行 + 正文分段 + 话题标签。

语气真实，少用夸张承诺。"""



WECHAT_SYSTEM = """你写公众号短文开头+正文骨架（800字内）。小标题清晰，结尾给行动建议。"""





async def _gen(system: str, content_md: str, style: str) -> str:

    if not llm_available():

        body = content_md.split("---", 2)[-1].strip()

        return await humanize(body[:1200], style=style)

    try:

        llm = create_agent_llm("agent3", temperature=0.45, vision=False)

        resp = await llm.ainvoke(

            [SystemMessage(content=system), HumanMessage(content=content_md[:10000])]

        )

        raw = (getattr(resp, "content", None) or "").strip()

        return await humanize(raw, style=style)

    except Exception as exc:

        logger.warning("derive script failed: %s", exc)

        return await humanize(content_md[:800], style=style)





async def derive_all(content_md: str, meta: dict[str, Any]) -> dict[str, str]:

    speech = await _gen(SPEECH_SYSTEM, content_md, "口语口播")

    moments = await _gen(MOMENTS_SYSTEM, content_md, "朋友圈")

    xhs = await _gen(XHS_SYSTEM, content_md, "小红书")

    wechat = await _gen(WECHAT_SYSTEM, content_md, "公众号")

    return {

        "speech": speech,

        "moments": moments,

        "xhs": xhs,

        "wechat": wechat,

    }


