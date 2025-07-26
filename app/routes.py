import os
import secrets
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, UploadFile, File, Request, HTTPException
from fastapi.responses import HTMLResponse, Response
from app.encryption import encrypt_file, decrypt_file
from .database import supabase
from app.utils import templates
from dotenv import load_dotenv

router = APIRouter()
load_dotenv(dotenv_path="config/.env")

SUPABASE_BUCKET = os.getenv('SUPABASE_BUCKET')
BASE_URL = os.getenv('BASE_URL')

@router.get("/", response_class=HTMLResponse)
async def upload_form(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})


@router.post("/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    try:
        # Read and encrypt
        file_data = await file.read()
        encrypted_data = encrypt_file(file_data)

        ext = os.path.splitext(file.filename)[1]
        # filename = f"{uuid4()}{ext}"
        filename = f"{uuid4()}-{file.filename}"
        token = secrets.token_urlsafe(16)

        # Upload encrypted file to Supabase
        upload_response = supabase.storage.from_(SUPABASE_BUCKET).upload(
            path=filename,
            file=encrypted_data,
            file_options={"content-type": file.content_type}
        )

        if not upload_response or not upload_response.path:
            raise HTTPException(status_code=500, detail="Upload to Supabase failed")

        # Store metadata
        expiry_time = datetime.utcnow() + timedelta(hours=1)
        supabase.table("files").insert({
            "filename": filename,
            "token": token,
            "status": "active",
            "expiry": expiry_time.isoformat()
        }).execute()

        download_url = f"{BASE_URL}/download/{token}"
        return templates.TemplateResponse("success.html", {"request": request, "download_url": download_url})

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during upload: {str(e)}")


@router.get("/download/{token}")
async def download_file(request: Request, token: str):
    result = supabase.table("files").select("*").eq("token", token).single().execute()

    if not result or not result.data:
        return templates.TemplateResponse("expired.html", {"request": request})

    file_entry = result.data

    # Check if already used
    if file_entry["status"] != "active":
        return templates.TemplateResponse("expired.html", {"request": request})

    # Expiry check
    expiry = file_entry.get("expiry")
    if expiry:
        expiry_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > expiry_dt:
            supabase.table("files").update({"status": "expired"}).eq("token", token).execute()
            return templates.TemplateResponse("expired.html", {"request": request})

    filename = file_entry["filename"]

    # Download file from Supabase
    response = supabase.storage.from_(SUPABASE_BUCKET).download(filename)
    if not response:
        raise HTTPException(status_code=500, detail="File download failed")

    decrypted_data = decrypt_file(response)

    # Delete file from Supabase & update DB
    supabase.storage.from_(SUPABASE_BUCKET).remove(filename)
    supabase.table("files").update({"status": "used"}).eq("token", token).execute()
    file_name = "-".join(filename.split("-")[1:])  # Extract original filename (after the first hyphen)
    return Response(
        content=decrypted_data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={file_name}"}
    )
