from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os, shutil, json, tempfile
from typing import Optional
from rayvision_api import RayvisionAPI

app = FastAPI(title="RenderRayCloud API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ACCESS_ID = "8w3SKaQEYVMdS0IWKKxHWrFPNYTH3WsZ"
ACCESS_KEY = "c51cc40192e9779266b8d7acfa1ae176"
DOMAIN = "jop.foxrenderfarm.com"
PLATFORM = "62"

def get_api():
    return RayvisionAPI(
        access_id=ACCESS_ID,
        access_key=ACCESS_KEY,
        domain=DOMAIN,
        platform=PLATFORM
    )

@app.get("/")
def root():
    return {"status": "RenderRayCloud API running"}

@app.get("/api/health")
def health():
    try:
        api = get_api()
        return {"status": "connected", "platform": PLATFORM}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/jobs")
def get_jobs():
    try:
        api = get_api()
        tasks = api.query.get_task_list({})
        return {"status": "ok", "jobs": tasks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
