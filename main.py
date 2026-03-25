import io
import os
import secrets
from PIL import Image
from rembg import remove, new_session
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Form
from fastapi.responses import Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

app = FastAPI(title="Remove BG API", version="1.0.0")

# Load model once at startup (downloads ~200MB on first run, cached after)
MODEL_NAME = os.getenv("REMBG_MODEL", "birefnet-general")
session = new_session(MODEL_NAME)

BG_API_SECRET = os.getenv("BG_API_SECRET", "")
security = HTTPBearer(auto_error=False)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not BG_API_SECRET:
        return  # No secret configured — open access
    if credentials is None or not secrets.compare_digest(credentials.credentials, BG_API_SECRET):
        raise HTTPException(status_code=401, detail="Invalid or missing token")


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME}


@app.post("/remove-bg")
async def remove_bg(
    image: UploadFile = File(...),
    bg_color: str = Form("ffffff"),
    format: str = Form("jpg"),
    _: None = Depends(verify_token),
):
    data = await image.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image too large (max 20MB)")

    # Remove background → RGBA PNG
    output_bytes = remove(data, session=session)
    img = Image.open(io.BytesIO(output_bytes)).convert("RGBA")

    # Composite onto solid background color
    hex_color = bg_color.lstrip("#")
    if len(hex_color) == 6:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    else:
        r, g, b = 255, 255, 255

    background = Image.new("RGBA", img.size, (r, g, b, 255))
    background.paste(img, mask=img.split()[3])  # use alpha as mask

    out = io.BytesIO()
    fmt = format.lower()
    if fmt in ("jpg", "jpeg"):
        background.convert("RGB").save(out, format="JPEG", quality=92)
        media_type = "image/jpeg"
    else:
        background.save(out, format="PNG")
        media_type = "image/png"

    return Response(content=out.getvalue(), media_type=media_type)
