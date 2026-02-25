from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import os, tempfile, zipfile, re
from rayvision_api import RayvisionAPI

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

ACCESS_ID = "8w3SKaQEYVMdS0IWKKxHWrFPNYTH3WsZ"
ACCESS_KEY = "c51cc40192e9779266b8d7acfa1ae176"
DOMAIN = "jop.foxrenderfarm.com"
PLATFORM = "62"

def get_api():
    return RayvisionAPI(access_id=ACCESS_ID, access_key=ACCESS_KEY, domain=DOMAIN, platform=PLATFORM)

def detect_version(file_path, software):
    try:
        if software.lower() == "blender":
            with open(file_path, 'rb') as f:
                header = f.read(12).decode('ascii', errors='ignore')
                if 'BLENDER' in header:
                    match = re.search(r'v(\d)(\d)(\d)', header)
                    if match:
                        return f"{match.group(1)}.{match.group(2)}"
    except:
        pass
    return None

@app.get("/")
def root():
    return {"status": "RenderRayCloud API running"}

@app.get("/api/health")
def health():
    get_api()
    return {"status": "connected", "platform": PLATFORM}

@app.post("/api/analyze")
async def analyze_scene(file: UploadFile = File(...), software: str = Form(...), software_version: str = Form(""), project_name: str = Form(...), frames: str = Form("1")):
    content = await file.read()
    file_size_mb = round(len(content) / (1024 * 1024), 2)
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, file.filename)
    with open(file_path, "wb") as f:
        f.write(content)
    detected_version = detect_version(file_path, software)
    final_version = software_version or detected_version or "3.6"
    tips = [{"type": "ok", "message": "Scene file ready for rendering"}]
    if detected_version:
        tips.append({"type": "ok", "message": f"Auto-detected version: {detected_version}"})
    return {"status": "analyzed", "file": file.filename, "software": software, "software_version": final_version, "project_name": project_name, "frames": frames, "file_size_mb": file_size_mb, "file_path": file_path, "tips": tips}

@app.post("/api/submit")
async def submit_job(file: UploadFile = File(...), software: str = Form(...), project_name: str = Form(...), frames: str = Form("1"), software_version: str = Form("3.6")):
    try:
        content = await file.read()
        tmp_dir = tempfile.mkdtemp()
        file_path = os.path.join(tmp_dir, file.filename)
        with open(file_path, "wb") as f:
            f.write(content)

        api = get_api()

        # Use rayvision_api task creation with correct params
        task_id_list = api.task.create_task(count=1)
        print(f"Raw create_task response: {task_id_list}")

        # Handle different return formats
        if isinstance(task_id_list, list) and len(task_id_list) > 0:
            task_id = task_id_list[0]
        elif isinstance(task_id_list, dict):
            task_id = task_id_list.get("data", [None])[0] or task_id_list.get("taskId")
        else:
            task_id = task_id_list

        if not task_id or task_id == 0:
            raise Exception(f"Invalid task_id: {task_id_list}")

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

@app.get("/api/jobs/{task_id}/download")
def download_job(task_id: int):
    try:
        api = get_api()
        from rayvision_sync.download import RayvisionDownload
        download = RayvisionDownload(api)
        download_path = f"/tmp/renders/{task_id}"
        os.makedirs(download_path, exist_ok=True)
        download.download(task_id_list=[task_id], local_path=download_path, print_log=False)
        zip_path = f"/tmp/renders/task_{task_id}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(download_path):
                for file in files:
                    fp = os.path.join(root, file)
                    zf.write(fp, os.path.relpath(fp, download_path))
        return FileResponse(zip_path, media_type="application/zip", filename=f"render_{task_id}.zip")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/jobs/{task_id}/stop")
def stop_job(task_id: int):
    api = get_api()
    api.task.stop_tasks(task_id_list=[task_id])
    return {"status": "stopped"}
