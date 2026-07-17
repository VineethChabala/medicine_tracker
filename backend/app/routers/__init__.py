from app.routers.auth import router as auth_router
from app.routers.patients import router as patients_router
from app.routers.medications import router as medications_router
from app.routers.ocr import router as ocr_router
from app.routers.webhook import router as webhook_router

__all__ = ["auth_router", "patients_router", "medications_router", "ocr_router", "webhook_router"]
