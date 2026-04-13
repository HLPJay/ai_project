"""
Web 服务器（含进度推送 + 缓存）
启动：uvicorn server:app --reload --port 8000
"""

import os
import json
import sqlite3
import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import asyncio

# ⚠️ CUDA 库路径
os.add_dll_directory(r"D:\claude_code\20260411_youtube_视频分析\venv\Lib\site-packages\nvidia\cublas\bin")
os.add_dll_directory(r"D:\claude_code\20260411_youtube_视频分析\venv\Lib\site-packages\nvidia\cudnn\bin")

from local_transcript import get_transcript, extract_video_id
from generate_report import generate_report

app = FastAPI(title="视频雷达")

DB_PATH = r"D:\claude_code\20260411_youtube_视频分析\reports.db"


# ============================================================
# 数据库初始化
# ============================================================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id    TEXT NOT NULL UNIQUE,
            url         TEXT NOT NULL,
            title       TEXT,
            channel     TEXT,
            source      TEXT,
            word_count  INTEGER,
            transcript  TEXT,
            report_json TEXT,
            created_at  TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()


# ============================================================
# 缓存读写
# ============================================================

def get_cached_report(video_id: str):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT * FROM reports WHERE video_id = ?", (video_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    cols = ['id','video_id','url','title','channel','source',
            'word_count','transcript','report_json','created_at']
    data = dict(zip(cols, row))
    data['report'] = json.loads(data['report_json'])
    return data


def save_cached_report(video_id, url, title, channel,
                        source, word_count, transcript, report):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT OR REPLACE INTO reports
        (video_id, url, title, channel, source, word_count,
         transcript, report_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        video_id, url, title, channel, source, word_count,
        transcript, json.dumps(report, ensure_ascii=False),
        datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    ))
    conn.commit()
    conn.close()


# ============================================================
# SSE 进度推送
# ============================================================

def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def process_with_progress(url: str):
    loop = asyncio.get_event_loop()

    # 步骤1：解析 ID
    yield sse("progress", {"step": 1, "total": 5, "msg": "解析视频链接..."})
    await asyncio.sleep(0.1)

    try:
        video_id = extract_video_id(url)
    except ValueError as e:
        yield sse("error", {"msg": str(e)})
        return

    # 步骤2：检查缓存
    yield sse("progress", {"step": 2, "total": 5, "msg": "检查缓存..."})
    await asyncio.sleep(0.1)

    cached = get_cached_report(video_id)
    if cached:
        yield sse("progress", {"step": 5, "total": 5, "msg": "命中缓存，直接返回"})
        await asyncio.sleep(0.1)
        yield sse("done", {
            "cached": True,
            "title": cached["title"],
            "channel": cached["channel"],
            "source": cached["source"],
            "word_count": cached["word_count"],
            "report": cached["report"],
        })
        return

    # 步骤3：获取视频信息
    yield sse("progress", {"step": 2, "total": 5, "msg": "获取视频标题和频道..."})
    title, channel = "", ""
    try:
        import yt_dlp
        def _get_info():
            with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                return info.get('title', ''), info.get('channel', '')
        title, channel = await loop.run_in_executor(None, _get_info)
    except Exception:
        pass

    # 步骤4：提取字幕
    yield sse("progress", {"step": 3, "total": 5, "msg": "提取视频内容..."})

    def _get_transcript():
        return get_transcript(url)

    transcript_result = await loop.run_in_executor(None, _get_transcript)

    if not transcript_result['success']:
        yield sse("error", {"msg": f"内容获取失败：{transcript_result['error']}"})
        return

    source = transcript_result['source']
    label = "YouTube 字幕" if source == "youtube_captions" else "语音转录"
    yield sse("progress", {
        "step": 3, "total": 5,
        "msg": f"内容获取完成（{label}，{transcript_result['word_count']} 词）"
    })

    # 步骤5：AI 生成报告
    yield sse("progress", {"step": 4, "total": 5, "msg": "AI 分析中，请稍候..."})

    def _generate():
        return generate_report(
            transcript=transcript_result['text'],
            title=title,
            channel=channel,
        )

    report = await loop.run_in_executor(None, _generate)

    if not report.get('success'):
        yield sse("error", {"msg": f"报告生成失败：{report.get('error')}"})
        return

    # 步骤6：存入缓存
    yield sse("progress", {"step": 5, "total": 5, "msg": "保存报告..."})
    await asyncio.sleep(0.1)

    save_cached_report(
        video_id=video_id, url=url, title=title, channel=channel,
        source=source, word_count=transcript_result['word_count'],
        transcript=transcript_result['text'], report=report,
    )

    yield sse("done", {
        "cached": False,
        "title": title,
        "channel": channel,
        "source": source,
        "word_count": transcript_result['word_count'],
        "report": report,
    })


# ============================================================
# API 接口
# ============================================================

@app.get("/api/process")
async def process_video(url: str):
    if not url or "youtube" not in url:
        raise HTTPException(status_code=400, detail="请提供有效的 YouTube 链接")
    return StreamingResponse(
        process_with_progress(url),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/reports")
async def list_reports():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT video_id, url, title, channel, source, created_at, report_json
        FROM reports ORDER BY id DESC LIMIT 20
    """).fetchall()
    conn.close()
    result = []
    for row in rows:
        report = json.loads(row[6])
        result.append({
            "video_id": row[0], "url": row[1],
            "title": row[2] or "未知标题", "channel": row[3] or "",
            "source": row[4], "created_at": row[5],
            "core_thesis": report.get("core_thesis", ""),
        })
    return result


@app.delete("/api/reports/{video_id}")
async def delete_report(video_id: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM reports WHERE video_id = ?", (video_id,))
    conn.commit()
    conn.close()
    return {"success": True}


@app.get("/")
async def index():
    return FileResponse("templates/index.html")
