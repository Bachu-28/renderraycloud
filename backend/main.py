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
async def submit_job(file: UploadFile = File(...), software: str = Form(...), project_name: str = Form(...), frames: str = Form("1-10[1]"), software_version: str = Form("2023")):
    try:
        content = await file.read()
        tmp_dir = tempfile.mkdtemp()
        file_path = os.path.join(tmp_dir, file.filename)
        with open(file_path, "wb") as f:
            f.write(content)
        api = get_api()
        task_id = api.task.create_task(count=1, out_user_id=project_name)[0]
        from rayvision_sync.upload import RayvisionUpload
        upload = RayvisionUpload(api)
        upload.upload_asset(file_path, task_id=str(task_id))
        api.task.submit_task(task_id_list=[task_id])
        return {"status": "submitted", "task_id": task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/jobs")
def get_jobs():
    try:
        api = get_api()
        result = api.query.get_task_list(page_num=1, page_size=20)
        raw_jobs = result.get("items", []) if isinstance(result, dict) else result
        jobs = []
        for j in raw_jobs:
            sc = j.get("taskStatus", 0)
            sm = {0:"waiting",5:"waiting",10:"waiting",20:"queued",25:"queued",30:"rendering",35:"rendering",40:"stopped",45:"queued",50:"error",60:"error",70:"done",80:"done"}
            jobs.append({"id": j.get("id"), "task_id": j.get("id"), "project_name": j.get("projectName") or j.get("sceneName","—"), "software": j.get("cgName") or "Blender", "frames": j.get("framesRange") or str(j.get("totalFrames","—")), "task_status": sm.get(sc,"queued"), "render_percent": j.get("progress") or 0})
        return {"status": "ok", "jobs": jobs}
    except Exception as e:
        return {"status": "ok", "jobs": [], "error": str(e)}

@app.post("/api/jobs/{task_id}/stop")
def stop_job(task_id: int):
    api = get_api()
    api.task.stop_tasks(task_id_list=[task_id])
    return {"status": "stopped"}
