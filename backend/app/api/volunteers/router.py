from fastapi import APIRouter
from .admin_endpoints import router as admin_router
from .profile_endpoints import router as profile_router
from .registration_endpoints import router as reg_router
from .join_request_endpoints import router as join_router


router = APIRouter()

# Combine both routers
router.include_router(admin_router, tags=["admin-volunteers"])
router.include_router(profile_router, prefix="/profile", tags=["volunteer-profile"])
router.include_router(reg_router, prefix="/register", tags=["volunteer-registration"])
router.include_router(join_router, prefix="/join-requests", tags=["volunteer-join-requests"])

