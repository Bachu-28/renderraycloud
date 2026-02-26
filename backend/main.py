def detect_software_version(file_path, software):
    """Auto-detect software version from file header/content"""
    try:
        filename = os.path.basename(file_path).lower()
        ext = os.path.splitext(filename)[1]

        # Blender .blend
        if ext == ".blend":
            with open(file_path, "rb") as f:
                header = f.read(20).decode("ascii", errors="ignore")
                if "BLENDER" in header:
                    import re
                    match = re.search(r"v(\d)(\d+)", header)
                    if match:
                        return f"{match.group(1)}.{match.group(2)}", "Blender"

        # 3ds Max .max
        elif ext == ".max":
            with open(file_path, "rb") as f:
                data = f.read(1024)
            # Max files contain version in binary header
            for version, year in [
                (b"\x19\x02", "2022"), (b"\x18\x02", "2021"),
                (b"\x17\x02", "2020"), (b"\x16\x02", "2019"),
                (b"\x15\x02", "2018"), (b"\x14\x02", "2017"),
                (b"\x13\x02", "2016"), (b"\x12\x02", "2015"),
                (b"\x1a\x02", "2023"), (b"\x1b\x02", "2024"),
            ]:
                if version in data:
                    return year, "3dsmax"
            return "2022", "3dsmax"  # default

        # Maya .ma (ASCII)
        elif ext == ".ma":
            with open(file_path, "r", errors="ignore") as f:
                for line in f:
                    if "requires maya" in line.lower():
                        import re
                        match = re.search(r'"(\d+\.\d+)"', line)
                        if match:
                            return match.group(1), "maya"
                    if line.count("//") > 0 and "Maya" in line:
                        import re
                        match = re.search(r"Maya (\d{4})", line)
                        if match:
                            return match.group(1), "maya"

        # Maya .mb (binary)
        elif ext == ".mb":
            with open(file_path, "rb") as f:
                data = f.read(512).decode("ascii", errors="ignore")
                import re
                match = re.search(r"Maya (\d{4})", data)
                if match:
                    return match.group(1), "maya"

        # Cinema 4D .c4d
        elif ext == ".c4d":
            with open(file_path, "rb") as f:
                data = f.read(512).decode("ascii", errors="ignore")
                import re
                match = re.search(r"C4D(\d+)", data)
                if match:
                    v = match.group(1)
                    return f"R{v[:2]}", "cinema4d"

        # Houdini .hip/.hipnc
        elif ext in [".hip", ".hipnc", ".hiplc"]:
            with open(file_path, "rb") as f:
                data = f.read(512).decode("ascii", errors="ignore")
                import re
                match = re.search(r"(\d+\.\d+\.\d+)", data)
                if match:
                    return match.group(1), "houdini"

    except Exception as e:
        pass
    return None, software

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import os, tempfile, zipfile, shutil, json, requests
from rayvision_api import RayvisionAPI

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

ACCESS_ID = "8w3SKaQEYVMdS0IWKKxHWrFPNYTH3WsZ"
ACCESS_KEY = "c51cc40192e9779266b8d7acfa1ae176"
DOMAIN = "jop.foxrenderfarm.com"
PLATFORM = "62"

SUPABASE_URL = "https://iuspabmbuirrtunxbkvg.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml1c3BhYm1idWlycnR1bnhia3ZnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE5MDk5MDMsImV4cCI6MjA4NzQ4NTkwM30.nuA9kr2IIEazvccttdNrdisF2F8UBpFKqLZ54Qbq0eM"
SUPABASE_BUCKET = "foxrender"
SUPABASE_FOLDER = "render"

job_status = {}

def get_api():
    return RayvisionAPI(access_id=ACCESS_ID, access_key=ACCESS_KEY, domain=DOMAIN, platform=PLATFORM)

def upload_to_supabase(file_path, filename):
    url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{SUPABASE_FOLDER}/{filename}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/octet-stream"
    }
    with open(file_path, "rb") as f:
        response = requests.put(url, headers=headers, data=f)
    if response.status_code not in [200, 201]:
        raise Exception(f"Supabase upload failed: {response.text}")
    public_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{SUPABASE_FOLDER}/{filename}"
    return public_url

def download_from_supabase(public_url, dest_path):
    response = requests.get(public_url, stream=True)
    if response.status_code != 200:
        raise Exception(f"Supabase download failed: {response.text}")
    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1024*1024):
            f.write(chunk)

def do_upload_and_submit(supabase_url, filename, task_id, frames, software_version, project_name):
    tmp_dir = tempfile.mkdtemp()
    try:
        job_status[task_id] = "uploading"
        api = get_api()

        # Download from Supabase to Railway tmp
        file_path = os.path.join(tmp_dir, filename)
        download_from_supabase(supabase_url, file_path)

        scene_name = os.path.splitext(filename)[0]
        frames_str = f"{frames}-{frames}[1]" if "-" not in str(frames) else frames
        server_path = "C:/users/" + project_name + "/" + os.path.basename(file_path)

        task_data = {
            "software_config": {
                "cg_name": "Blender",
                "cg_version": software_version,
                "plugins": {}
            },
            "task_info": {
                "task_id": str(task_id),
                "cg_id": {"blender":"2007","3dsmax":"2001","maya":"2000","cinema4d":"2002","houdini":"2004","c4d":"2002"}.get(os.path.splitext(filename)[1].lower().lstrip(".").replace("max","3dsmax").replace("blend","blender").replace("ma","maya").replace("mb","maya").replace("hip","houdini").replace("c4d","cinema4d"), "2007"),
                "frames_per_task": "1",
                "pre_frames": "100",
                "job_stop_time": "259200",
                "task_stop_time": "0",
                "time_out": "43200",
                "is_layer_rendering": "1",
                "is_distribute_render": "0",
                "distribute_render_node": "3",
                "input_cg_file": server_path,
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
        upload_data = {"asset": [{"local": file_path, "server": "C:/users/" + project_name + "/" + filename}]}
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
    detected_version, detected_software = detect_software_version(file_path, software)
    final_version = software_version or detected_version or "3.6"
    final_software = detected_software or software
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tips = [{"type": "ok", "message": "Scene file ready for rendering"}]
    if detected_version:
        tips.append({"type": "ok", "message": f"Auto-detected version: {detected_version}"})
    return {"status": "analyzed", "file": file.filename, "software": final_software, "software_version": final_version, "project_name": project_name, "frames": frames, "file_size_mb": file_size_mb, "detected_version": detected_version, "tips": tips}

@app.post("/api/submit")
async def submit(background_tasks: BackgroundTasks, file: UploadFile = File(...), software: str = Form(...), project_name: str = Form(...), frames: str = Form("1"), software_version: str = Form("3.6")):
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, file.filename)
    with open(file_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    # Upload to Supabase first
    try:
        supabase_url = upload_to_supabase(file_path, file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase upload failed: {str(e)}")
    shutil.rmtree(tmp_dir, ignore_errors=True)

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
    background_tasks.add_task(do_upload_and_submit, supabase_url, file.filename, task_id, frames, software_version, project_name)
    threading.Thread(target=poll_and_download, args=(task_id, project_name), daemon=True).start()
    return {"status": "uploading", "task_id": task_id, "supabase_url": supabase_url}

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
            sm = {0:"waiting",5:"waiting",10:"done",20:"done",23:"done",25:"done",30:"rendering",35:"rendering",40:"stopped",45:"done",50:"error",60:"error",70:"done",80:"done"}
            jobs.append({"id": j.get("id"), "task_id": j.get("id"), "project_name": j.get("projectName") or j.get("sceneName","--"), "software": j.get("cgName") or "Blender", "frames": j.get("framesRange") or str(j.get("totalFrames","--")), "task_status": sm.get(sc,"queued"), "render_percent": 100 if sm.get(sc,"queued") == "done" else (j.get("renderingRatio") or j.get("progress") or 0)})
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
    try:
        api = get_api()
        api.task.stop_task(task_id)
        return {"status": "stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/jobs/{task_id}/delete")
def delete_job(task_id: int):
    try:
        api = get_api()
        api.task.delete_task(task_id)
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
        for tid in ids:
            try:
                api.task.abort_task(tid)
            except:
                pass
        return {"status": "deleted", "count": len(ids)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/task-methods")
def task_methods():
    api = get_api()
    return {"methods": [m for m in dir(api.task) if not m.startswith("_")]}


import threading, time

def poll_and_download(task_id, project_name):
    """Poll Fox until job is done, then download and upload to Supabase"""
    api = get_api()
    while True:
        try:
            result = api.query.get_task_list(page_num=1, page_size=50)
            raw_jobs = result.get("items", []) if isinstance(result, dict) else result
            job = next((j for j in raw_jobs if j.get("id") == task_id), None)
            if not job:
                time.sleep(60)
                continue
            status_code = job.get("taskStatus", 0)
            if status_code in [70, 80]:  # done
                # Download from Fox
                from rayvision_sync.download import RayvisionDownload
                download = RayvisionDownload(api)
                download_path = f"/tmp/renders/{task_id}"
                os.makedirs(download_path, exist_ok=True)
                download.download(task_id_list=[task_id], local_path=download_path, print_log=False)
                # Upload each file to Supabase
                output_urls = []
                for root, dirs, files in os.walk(download_path):
                    for file in files:
                        fp = os.path.join(root, file)
                        supabase_path = f"outputs/{task_id}/{file}"
                        url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{supabase_path}"
                        headers = {"Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/octet-stream"}
                        with open(fp, "rb") as f:
                            requests.put(url, headers=headers, data=f)
                        output_urls.append(f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{supabase_path}")
                job_status[task_id] = "done"
                shutil.rmtree(download_path, ignore_errors=True)
                break
            elif status_code in [50, 60]:  # error
                job_status[task_id] = "render_error"
                break
        except Exception as e:
            job_status[task_id] = f"poll_error:{str(e)}"
            break
        time.sleep(60)

@app.get("/api/jobs/raw")
def get_jobs_raw():
    try:
        api = get_api()
        result = api.query.get_task_list(page_num=1, page_size=5)
        return {"raw": result}
    except Exception as e:
        return {"error": str(e)}
