""" fast api declaration """

import logging
from typing import List
from fastapi import FastAPI, WebSocket, Form, File, UploadFile
from starlette.websockets import WebSocketDisconnect

from whisperflow import __version__
import whisperflow.streaming as st
import whisperflow.transcriber as ts


app = FastAPI()
sessions = {}


@app.get("/health", response_model=str)
def health():
    """health function on API"""
    return f"Whisper Flow V{__version__}"


@app.post("/transcribe_pcm_chunk", response_model=dict)
def transcribe_pcm_chunk(
    model_name: str = Form(...), files: List[UploadFile] = File(...)
):
    """transcribe chunk"""
    model = ts.get_model(model_name)
    content = files[0].file.read()
    return ts.transcribe_pcm_chunks(model, [content])


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """websocket implementation"""
    session = None
    try:
        await websocket.accept()
        logging.info("WebSocket accepted, loading model...")
        model = ts.get_model()
        logging.info("Model loaded, creating session...")

        async def transcribe_async(chunks: list):
            return await ts.transcribe_pcm_chunks_async(model, chunks)

        async def send_back_async(data: dict):
            await websocket.send_json(data)

        session = st.TranscribeSession(transcribe_async, send_back_async)
        sessions[session.id] = session
        logging.info("Session created, waiting for audio...")

        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("type") == "websocket.receive":
                data = message.get("bytes")
                if data is not None:
                    session.add_chunk(data)
                # ignore text frames (e.g. client ping); wait for next message
    except WebSocketDisconnect:
        logging.info("Client disconnected")
        if session:
            await session.stop()
    except Exception as exception:  # pragma: no cover
        logging.exception("WebSocket error: %s", exception)
        if session:
            await session.stop()
        if websocket.client_state.name != "DISCONNECTED":
            await websocket.close()
