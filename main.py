import base64
import json
import os
import datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
import httpx
from google.oauth2 import service_account
from google.cloud import firestore

app = FastAPI()

PROJECT_ID = "myvue3-e45b9"

b64_cred = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_B64")
if not b64_cred:
    raise RuntimeError("請設定環境變數 GOOGLE_APPLICATION_CREDENTIALS_B64")

service_account_info = json.loads(base64.b64decode(b64_cred))

credentials = service_account.Credentials.from_service_account_info(service_account_info)

db = firestore.AsyncClient(project=PROJECT_ID, credentials=credentials)

YOUTUBE_API_KEY = "AIzaSyAUD7ipwX-VAIIgbtw4V6sHKOTfyWoPdMo"


@app.get("/", response_class=PlainTextResponse)
async def root():
    return "Hello FastAPI"


@app.get("/api/hello")
async def api_hello():
    return {
        "message": "Hello World.",
        "message2": "こんにちは、世界。",
        "message3": "世界，你好!",
    }


@app.get("/api/firebasefood")
async def firebase_food():
    try:
        collection_ref = db.collection("myvue3food")
        docs = collection_ref.stream()  # 取得 async generator，不要加 await
        documents = []
        async for doc in docs:          # 用 async for 逐筆取出文件
            doc_dict = doc.to_dict()
            doc_dict["id"] = doc.id
            documents.append(doc_dict)
        return {"myvue3food": documents}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "Failed to fetch data from Firestore", "details": str(e)})


@app.get("/api/youtube/channel/{channel_ids}")
async def youtube_channel(channel_ids: str):
    channel_id_list = [c.strip() for c in channel_ids.split(",") if c.strip()]
    if len(channel_id_list) == 0 or len(channel_id_list) > 50:
        raise HTTPException(status_code=400, detail="頻道 ID 數量需介於 1 到 50 之間")

    params = {
        "part": "snippet,statistics",
        "id": ",".join(channel_id_list),
        "key": YOUTUBE_API_KEY,
    }

    async with httpx.AsyncClient() as client:
        try:
            res = await client.get("https://www.googleapis.com/youtube/v3/channels", params=params)
            res.raise_for_status()
            data = res.json()  # 不要 await
            items = data.get("items", [])
            if len(items) == 0:
                raise HTTPException(status_code=404, detail="找不到任何頻道資料")
            return {"count": len(items), "items": items}
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=500, detail=f"無法取得頻道資料: {str(e)}")


@app.get("/api/youtube/videos/{video_ids}")
async def youtube_videos(video_ids: str):
    video_id_list = [v.strip() for v in video_ids.split(",") if v.strip()]
    if len(video_id_list) == 0 or len(video_id_list) > 50:
        raise HTTPException(status_code=400, detail="影片 ID 數量需介於 1 到 50 之間")

    params = {
        "part": "snippet,statistics",
        "id": ",".join(video_id_list),
        "key": YOUTUBE_API_KEY,
    }

    async with httpx.AsyncClient() as client:
        try:
            res = await client.get("https://www.googleapis.com/youtube/v3/videos", params=params)
            res.raise_for_status()
            data = res.json()  # 這裡不要加 await
            items = data.get("items", [])
            if len(items) == 0:
                raise HTTPException(status_code=404, detail="找不到任何影片資料")
            return {"count": len(items), "items": items}
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=500, detail=f"無法取得影片資料: {str(e)}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"未知錯誤: {str(e)}")

@app.get("/api/countdown/{slug}")
async def countdown(slug: str):
    if not slug or len(slug) < 12:
        raise HTTPException(status_code=400, detail="Invalid slug. Format should be: YYYYMMDDHHMM")
    try:
        slug_iso = f"{slug[0:4]}-{slug[4:6]}-{slug[6:8]}T{slug[8:10]}:{slug[10:12]}:00+08:00"
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
        next_time = datetime.datetime.fromisoformat(slug_iso)
        diff = next_time - now
        diff_sec = int(diff.total_seconds())

        diff_day = diff_sec // 86400
        remaining = diff_sec % 86400
        diff_hour = remaining // 3600
        remaining = remaining % 3600
        diff_minute = remaining // 60
        diff_second = remaining % 60

        return {
            "slug": slug,
            "now": now.isoformat(),
            "slugISO": slug_iso,
            "next": next_time.isoformat(),
            "diffMs": int(diff.total_seconds() * 1000),
            "diffday": diff_day,
            "diffhour": diff_hour,
            "diffminute": diff_minute,
            "diffsecond": diff_second,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "Invalid slug format or date parse error", "details": str(e)})


@app.get("/api/bilibili/proxyimg")
async def bilibili_proxyimg(url: str = Query(...)):
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                url,
                headers={"Referer": "https://www.bilibili.com/"},
                timeout=10.0,
                follow_redirects=True,
            )
            return StreamingResponse(
                resp.aiter_bytes(),
                media_type=resp.headers.get("content-type", "application/octet-stream"),
                headers={"Cache-Control": "public, max-age=86400"},
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail={"error": "圖片代理失敗", "message": str(e)})


@app.get("/api/bilibili/{bvid}")
async def bilibili_bvid(bvid: str):
    headers = {
        "Referer": "https://www.bilibili.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/114.0.0.0 Safari/537.36",
    }
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(
                "https://api.bilibili.com/x/web-interface/view",
                params={"bvid": bvid},
                headers=headers,
            )
            res.raise_for_status()
            data = res.json()
            raw = data.get("data", {})
            newdata = {k: v for k, v in raw.items() if not isinstance(v, (dict, list))}
            pic = raw.get("pic")
            title = raw.get("title")
            owner = raw.get("owner")
            stat = raw.get("stat")
            pages = raw.get("pages")
            return {"pic": pic, "title": title, "owner": owner, "stat": stat, "data": newdata, "pages": pages}
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=500, detail={"error": "無法取得 Bilibili 資料", "message": str(e)})

