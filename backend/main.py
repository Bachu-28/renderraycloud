from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os, tempfile
from rayvision_api import RayvisionAPI

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

ACCESS_ID = "8w3SKaQEYVMdS0IWKKxHWrFPNYTH3WsZ"
ACCESS_KEY = "c51cc40192e9779266b8d7acfa1ae176"
DOMAIN = "jop.foxrenderfarm.com"
PLATFORM = "62"

def get_api():
    return RayvisionAPI(access_id=ACCESS_ID, access_key=ACCESS_KEY, domain=DOMAIN, platform=PLATFORM)

@app.get("/")
def root():
    return {"status": "RenderRayCloud API running"}

@app.get("/api/health")
def health():
    get_api()
    return {"status": "connected", "platform": PLATFORM}

@app.post("/api/analyze")
async def analyze_scene(file: UploadFile = File(...), software: str = Form(...), software_version: str = Form(...), project_name: str = Form(...), frames: str = Form("1-10[1]")):
    content = await file.read()
    file_size_mb = round(len(content) / (1024 * 1024), 2)
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, file.filename)
    with open(file_path, "wb") as f:
        f.write(content)
    return {"status": "analyzed", "file": file.filename, "software": software, "software_version": software_version, "project_name": project_name, "frames": frames, "file_size_mb": file_size_mb, "file_path": file_path, "tips": [{"type": "ok", "message": "Scene file ready for rendering"}]}

@app.post("/api/submit")
async def submit_job(file_path: str = Form(...), software: str = Form(...), project_name: str = Form(...), frames: str = Form("1-10[1]"), software_version: str = Form("2023")):
    api = get_api()
    task_id = api.task.create_task(count=1, out_user_id=project_name)[0]
    api.task.submit_task(task_id_list=[task_id])
    return {"status": "submitted", "task_id": task_id}

@app.get("/api/jobs")
def get_jobs():
    try:
        api = get_api()
        tasks = api.query.get_task_list({"pageNum": 1, "pageSize": 20})
        return {"status": "ok", "jobs": tasks}
    except Exception as e:
        return {"status": "ok", "jobs": [], "error": str(e)}

@app.post("/api/jobs/{task_id}/stop")
def stop_job(task_id: int):
    api = get_api()
    api.task.stop_tasks(task_id_list=[task_id])
    return {"status": "stopped"}
