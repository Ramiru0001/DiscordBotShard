from threading import Thread

from fastapi import FastAPI
import uvicorn
import logging

app = FastAPI()
logging.basicConfig(level=logging.INFO)  # ログレベルを設定

@app.get("/")
async def root():
	return {"message": "Server is Online."}

def start():
	uvicorn.run(app, host="0.0.0.0", port=8000)

def server_thread():
	logging.info("Starting server thread...")
	t = Thread(target=start)
	t.start()
	logging.info("Server thread started successfully.")