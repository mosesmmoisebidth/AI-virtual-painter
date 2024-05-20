import socketio
import os
import asyncio
from fastapi import FastAPI, Request
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from dotenv import dotenv_values
import threading
import shlex
import datetime
from exceptions import *
from uvicorn import Config, Server
import subprocess

app = FastAPI()
env_vars = dotenv_values("../.env.example")
DB_URL = env_vars.get("DB_URL")
FILE_PATH = "../live"
sio = socketio.AsyncServer(
    async_mode='asgi',
    logger=True,
    cors_allowed_origins=[],
    engineio_logger=True
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
sio_app = socketio.ASGIApp(
    socketio_server=sio,
    socketio_path='/socket.io'
)
app.mount("/socket.io", app=sio_app)
@sio.event
async def connect(sid, environ, auth):
    print("connected ID: {}".format(sid))
@sio.event
async def disconnect(sid):
    print("disconnected ID: {}".format(sid))

async def generate_hls_streams(rtsp_url: str, output_playlist='stream.m3u8'):
    output_directory = os.path.join(FILE_PATH, 'hls')
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
    command = [
        "ffmpeg", "-v", "verbose", "-i", rtsp_url, "-vf", "scale=1920:1080", "-vcodec", "libx264", "-r", "25",
        "-b:v", "1000000", "-crf", "31", "-acodec", "aac", "-sc_threshold", "0", "-f", "hls", "-hls_time", "120",
        "-segment_time", "120", "-hls_list_size", "10", output_playlist
    ]
    subprocess.run(command, cwd=output_directory)
@app.get("/", tags=["Default"])
async def handle_get():
    return "Welcome to ITMS Stream"
@app.get("/live/{folder}/{file_path:path}", tags=["Live"])
async def handle_hls(folder: str, file_path: str, request: Request):
    content_type="video/mp4"
    folder_path = os.path.join(FILE_PATH, folder)
    full_file_path = os.path.join(folder_path, file_path)
    if not os.path.exists(full_file_path):
        raise HTTPException(status_code=404, detail="File not found")
    if file_path.endswith(".m3u8") or file_path.endswith(".ts"):
        content_type = "application/x-mpegURL"
    else:
        content_type="video/mp4"
    if os.path.getsize(full_file_path) < 10 * 1024 * 1024:
        return FileResponse(full_file_path, media_type=content_type)
    def file_iterator(file_path: str, chunk_size=4096):
        with open(file_path, mode="rb") as file:
            if os.path.getsize(file_path) < chunk_size:
                return FileResponse(file_path, media_type=content_type)
            while chunk := file.read(chunk_size):
                yield chunk
    return StreamingResponse(file_iterator(full_file_path), media_type=content_type)
@app.on_event("startup")
async def startup_event():
    print("SERVER STARTED RUNNING")
    cam_address = "rtsp://admin:1AmZRoo~@192.168.1.64:554/Streaming/Channels/902"
    def asyncio_event_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(generate_hls_streams(cam_address))
        loop.close()
    hls_stream_thread = threading.Thread(target=asyncio_event_loop)
    hls_stream_thread.start()
@app.on_event("shutdown")
async def shutdown_event():
    print("SERVER STOPPED RUNNING")
if __name__ == '__main__':
    config = Config(app, host='127.0.0.1', port=8001, reload=True)
    server = Server(config=config)
    server.run()
