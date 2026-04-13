"""
Web 服务器
启动方式：uvicorn server:app --reload --port 8000
"""

import os
import json
import datetime
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# ⚠️ CUDA 库路径，必须在最前面
os.add_dll_directory(r"D:\claude_code\20260411_youtube_视频分析\venv\Lib\site-packages\nvidia\cublas\bin")
os.add_dll_directory(r"D:\claude_code\20260411_youtube_视频分析\venv\Lib\site-packages\nvidia\cudnn\bin")

from local_transcript import get_transcript
from generate_report import generate_report

app = FastAPI(title="YouTube 视频报告")

REPORTS_DIR = r"D:\claude_code\20260411_youtube_视频分析\reports"


# ============================================================
# 数据模型
# ============================================================

class ReportRequest(BaseModel):
    url: str
    title: str = ""
    channel: str = ""


# ============================================================
# API 接口
# ============================================================

@app.post("/api/report")
async def create_report(req: ReportRequest):
    """
    接收 YouTube URL，返回结构化报告
    """

    if not req.url or "youtube" not in req.url:
        raise HTTPException(status_code=400, detail="请提供有效的 YouTube 链接")

    # 第一步：获取字幕
    transcript_result = get_transcript(req.url)
    if not transcript_result['success']:
        raise HTTPException(status_code=422, detail=f"字幕获取失败：{transcript_result['error']}")

    # 第二步：自动获取视频信息（如果没有传 title）
    title = req.title
    channel = req.channel
    if not title:
        try:
            import yt_dlp
            with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True}) as ydl:
                info = ydl.extract_info(req.url, download=False)
                title = info.get('title', '')
                channel = info.get('channel', '')
        except Exception:
            pass

    # 第三步：生成报告
    report = generate_report(
        transcript=transcript_result['text'],
        title=title,
        channel=channel,
    )
    if not report.get('success'):
        raise HTTPException(status_code=500, detail=f"报告生成失败：{report.get('error')}")

    # 第四步：存档
    os.makedirs(REPORTS_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = {
        'url': req.url,
        'title': title,
        'channel': channel,
        'created_at': timestamp,
        'source': transcript_result.get('source'),
        'word_count': transcript_result.get('word_count'),
        'report': report,
    }
    with open(os.path.join(REPORTS_DIR, f"{timestamp}.json"), 'w', encoding='utf-8') as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)

    return {
        'success': True,
        'title': title,
        'channel': channel,
        'source': transcript_result.get('source'),
        'word_count': transcript_result.get('word_count'),
        'report': report,
    }


@app.get("/api/reports")
async def list_reports():
    """返回历史报告列表"""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    reports = []
    for f in sorted(os.listdir(REPORTS_DIR), reverse=True)[:20]:
        if f.endswith('.json'):
            with open(os.path.join(REPORTS_DIR, f), encoding='utf-8') as fp:
                data = json.load(fp)
                reports.append({
                    'filename': f,
                    'title': data.get('title', '未知标题'),
                    'channel': data.get('channel', ''),
                    'created_at': data.get('created_at', ''),
                    'url': data.get('url', ''),
                    'core_thesis': data.get('report', {}).get('core_thesis', ''),
                })
    return reports


# 前端页面
@app.get("/")
async def index():
    return FileResponse("templates/index.html")
