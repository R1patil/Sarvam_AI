import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

# Import shared image store — must happen after load_dotenv
from image_store import image_store

# Max image size: 10 MB
MAX_IMAGE_BYTES = 10 * 1024 * 1024

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/bmp",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()


@app.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    """
    Receive an image upload from the browser.
    Stores it in the shared image_store so the vision tool can read it.
    """
    content_type = file.content_type or "image/jpeg"

    # Normalize content-type (some browsers send 'image/jpg')
    if content_type == "image/jpg":
        content_type = "image/jpeg"

    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported image type: {content_type}. Allowed: JPEG, PNG, WebP, GIF, BMP",
        )

    data = await file.read()

    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image too large ({len(data) // 1024} KB). Maximum is 10 MB.",
        )

    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")

    await image_store.set(
        filename=file.filename or "uploaded_image",
        content_type=content_type,
        data=data,
    )

    logger.info(
        f"[Upload] Image stored: {file.filename} "
        f"({len(data) // 1024} KB, {content_type})"
    )

    return JSONResponse(
        {
            "ok": True,
            "filename": file.filename,
            "size_kb": len(data) // 1024,
            "content_type": content_type,
            "message": "Image ready! Now ask me to read it.",
        }
    )


@app.delete("/upload-image")
async def clear_image():
    """Clear the stored image (called when user removes it from the UI)."""
    await image_store.clear()
    return JSONResponse({"ok": True, "message": "Image cleared."})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebRTC signaling + audio relay for Pipecat webrtc transport."""
    await websocket.accept()
    logger.info("[WS] Client connected")

    from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
    from pipecat.runner.types import SmallWebRTCRunnerArguments
    from aiortc.sdp import candidate_from_sdp
    from bot import bot

    connection = None
    bot_task = None

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "offer":
                logger.info("[WS] Received offer SDP")
                # Initialize connection with client's SDP offer
                connection = SmallWebRTCConnection()
                await connection.initialize(sdp=data["sdp"], type="offer")

                # Send answer back to client
                answer = connection.get_answer()
                await websocket.send_json({
                    "type": "answer",
                    "sdp": answer["sdp"]
                })

                # Create the runner arguments for the bot
                runner_args = SmallWebRTCRunnerArguments(
                    webrtc_connection=connection,
                    body={}
                )

                # Callback to send transcripts to client over WebSocket
                async def send_transcript_to_client(role: str, text: str):
                    try:
                        await websocket.send_json({
                            "type": "transcript",
                            "role": role,
                            "text": text
                        })
                    except Exception as e:
                        logger.warning(f"[WS] Failed to send transcript: {e}")

                connection.send_transcript = send_transcript_to_client

                # Start the bot task in the background
                bot_task = asyncio.create_task(bot(runner_args))
                logger.info("[WS] Bot task started in background")

            elif msg_type == "candidate":
                if connection:
                    c = data["candidate"]
                    candidate = candidate_from_sdp(c["candidate"])
                    candidate.sdpMid = c["sdpMid"]
                    candidate.sdpMLineIndex = c["sdpMLineIndex"]
                    await connection.add_ice_candidate(candidate)

    except Exception as e:
        logger.info(f"[WS] Connection closed or error: {e}")
    finally:
        logger.info("[WS] WebSocket closed, cleaning up")
        if connection:
            try:
                await connection.disconnect()
            except Exception:
                pass
        if bot_task:
            bot_task.cancel()
