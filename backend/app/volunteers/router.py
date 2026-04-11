from fastapi import APIRouter
from .admin_endpoints import router as admin_router
from .profile_endpoints import router as profile_router

router = APIRouter()

# Combine both routers
router.include_router(admin_router, tags=["admin-volunteers"])
router.include_router(profile_router, prefix="/profile", tags=["volunteer-profile"])
