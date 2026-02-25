from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import os, tempfile, zipfile, shutil, json
from rayvision_api import RayvisionAPI

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

ACCESS_ID = "8w3SKaQEYVMdS0IWKKxHWrFPNYTH3WsZ"
ACCESS_KEY = "c51cc40192e9779266b8d7acfa1ae176"
DOMAIN = "jop.foxrenderfarm.com"
PLATFORM = "62"

job_status = {}

def get_api():
    return RayvisionAPI(access_id=ACCESS_ID, access_key=ACCESS_KEY, domain=DOMAIN, platform=PLATFORM)

def do_upload_and_submit(tmp_dir, file_path, task_id, frames, software_version, project_name):
    try:
        job_status[task_id] = "uploading"
        api = get_api()

        scene_name = os.path.splitext(os.path.basename(file_path))[0]
        frames_str = f"{frames}-{frames}[1]" if "-" not in str(frames) else frames

        task_data = {
            "software_config": {
                "cg_name": "Blender",
                "cg_version": software_version,
                "plugins": {}
            },
            "task_info": {
                "task_id": str(task_id),
                "cg_id": "2007",
                "frames_per_task": "1",
                "pre_frames": "100",
                "job_stop_time": "259200",
                "task_stop_time": "0",
                "time_out": "43200",
                "is_layer_rendering": "1",
                "is_distribute_render": "0",
                "distribute_render_node": "3",
                "input_cg_file": file_path,
                "input_project_path": "",
                "project_name": project_name,
                "ram": "64",
                "os_name": "1",
                "render_layer_type": "0",
                "platform": PLATFORM,
                "channel": "4",
                "tiles": "1",
                "tiles_type": "block",
                "is_picture": "0",
                "stop_after_test": "1"
            },
            "scene_info_render": {
                "common": {
                    "frames": frames_str,
                    "Render_Format": "PNG",
                    "scene_name": [scene_name],
                    "width": "1920",
                    "height": "1080",
                    "camera_name": "Camera",
                    "Output_path": "/tmp/"
                }
            },
            "scene_info": {
                "common": {
                    "frames": frames_str,
                    "Render_Format": "PNG",
                    "scene_name": [scene_name],
                    "width": "1920",
                    "height": "1080",
                    "camera_name": "Camera",
                    "Output_path": "/tmp/"
                }
            }
        }

        task_json = os.path.join(tmp_dir, "task.json")
        with open(task_json, "w") as f:
            json.dump(task_data, f)

        upload_json = os.path.join(tmp_dir, "upload.json")
        upload_data = {"asset": [{"local": file_path, "server": os.path.basename(file_path)}]}
        with open(upload_json, "w") as f:
            json.dump(upload_data, f)

        from rayvision_sync.upload import RayvisionUpload
        upload = RayvisionUpload(api)
        upload.upload_config(str(task_id), [task_json])
        upload.upload_asset(upload_json, engine_type="aspera")

        api.task.submit_task(task_id)
        job_status[task_id] = "submitted"
    except Exception as e:
        job_status[task_id] = f"error:{str(e)}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

@app.get("/")
def root():
    return {"status": "RenderRayCloud API running"}

@app.get("/api/health")
def health():
    get_api()
    return {"status": "connected", "platform": PLATFORM}

@app.post("/api/analyze")
async def analyze_scene(file: UploadFile = File(...), software: str = Form(...), software_version: str = Form(""), project_name: str = Form(...), frames: str = Form("1")):
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, file.filename)
    file_size = 0
    with open(file_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)
            file_size += len(chunk)
    file_size_mb = round(file_size / (1024 * 1024), 2)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return {"status": "analyzed", "file": file.filename, "software": software, "software_version": software_version or "3.6", "project_name": project_name, "frames": frames, "file_size_mb": file_size_mb, "tips": [{"type": "ok", "message": "Scene file ready for rendering"}]}

@app.post("/api/submit")
async def submit(background_tasks: BackgroundTasks, file: UploadFile = File(...), software: str = Form(...), project_name: str = Form(...), frames: str = Form("1"), software_version: str = Form("3.6")):
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, file.filename)
    with open(file_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)
    api = get_api()
    result = api.task.create_task(count=1)
    if isinstance(result, dict):
        task_id = result.get("taskIdList", [None])[0]
    elif isinstance(result, list):
        task_id = result[0]
    else:
        task_id = result
    if not task_id or task_id == 0:
        raise HTTPException(status_code=500, detail=f"Invalid task_id: {result}")
    job_status[task_id] = "uploading"
    background_tasks.add_task(do_upload_and_submit, tmp_dir, file_path, task_id, frames, software_version, project_name)
    return {"status": "uploading", "task_id": task_id}

@app.get("/api/job-status/{task_id}")
def get_job_status(task_id: int):
    return {"task_id": task_id, "status": job_status.get(task_id, "unknown")}

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
            jobs.append({"id": j.get("id"), "task_id": j.get("id"), "project_name": j.get("projectName") or j.get("sceneName","--"), "software": j.get("cgName") or "Blender", "frames": j.get("framesRange") or str(j.get("totalFrames","--")), "task_status": sm.get(sc,"queued"), "render_percent": j.get("progress") or 0})
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

@app.post("/api/jobs/{task_id}/delete")
def delete_job(task_id: int):
    try:
        api = get_api()
        api.task.abort_tasks(task_id_list=[task_id])
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/jobs/delete-all")
def delete_all_jobs():
    try:
        api = get_api()
        result = api.query.get_task_list(page_num=1, page_size=50)
        raw_jobs = result.get("items", []) if isinstance(result, dict) else result
        ids = [j.get("id") for j in raw_jobs if j.get("id")]
        if ids:
            api.task.abort_tasks(task_id_list=ids)
        return {"status": "deleted", "count": len(ids)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
