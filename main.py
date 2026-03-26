import io
import os
import secrets
import threading
from PIL import Image
from rembg import remove, new_session
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Form
from fastapi.responses import Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

MODEL_NAME = os.getenv("REMBG_MODEL", "u2net")
BG_API_SECRET = os.getenv("BG_API_SECRET", "")

app = FastAPI(title="Remove BG API", version="1.0.0")
security = HTTPBearer(auto_error=False)

# Load model in background so the server starts immediately
rembg_session = None
_model_lock = threading.Lock()

def _load_model():
    global rembg_session
    sess = new_session(MODEL_NAME)
    with _model_lock:
        rembg_session = sess
    print(f"Model '{MODEL_NAME}' loaded and ready.")

threading.Thread(target=_load_model, daemon=True).start()


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not BG_API_SECRET:
        return
    if credentials is None or not secrets.compare_digest(credentials.credentials, BG_API_SECRET):
        raise HTTPException(status_code=401, detail="Invalid or missing token")


@app.get("/health")
def health():
    with _model_lock:
        ready = rembg_session is not None
    return {"status": "ok", "model": MODEL_NAME, "ready": ready}


@app.post("/remove-bg")
async def remove_bg(
    image: UploadFile = File(...),
    bg_color: str = Form("ffffff"),
    format: str = Form("jpg"),
    _: None = Depends(verify_token),
):
    with _model_lock:
        sess = rembg_session
    if sess is None:
        raise HTTPException(status_code=503, detail="Model still loading, please retry in 30 seconds")

    data = await image.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image too large (max 20MB)")

    output_bytes = remove(data, session=sess)
    img = Image.open(io.BytesIO(output_bytes)).convert("RGBA")

    hex_color = bg_color.lstrip("#")
    if len(hex_color) == 6:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    else:
        r, g, b = 255, 255, 255

    background = Image.new("RGBA", img.size, (r, g, b, 255))
    background.paste(img, mask=img.split()[3])

    out = io.BytesIO()
    if format.lower() in ("jpg", "jpeg"):
        background.convert("RGB").save(out, format="JPEG", quality=92)
        media_type = "image/jpeg"
    else:
        background.save(out, format="PNG")
        media_type = "image/png"

    return Response(content=out.getvalue(), media_type=media_type)
