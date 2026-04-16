from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from backend.app.database import get_db
from backend.app.models import User, UserRole, Volunteer, VolunteerJoinRequest, Organization, JoinRequestStatus
from backend.app.api.deps import get_current_user
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

router = APIRouter()

# --- Schemas ---

class JoinRequestCreate(BaseModel):
    org_id: int

class JoinRequestRead(BaseModel):
    id: int
    volunteer_id: int
    volunteer_name: str
    org_id: int
    org_name: str
    status: JoinRequestStatus
    created_at: datetime

    class Config:
        from_attributes = True

class JoinRequestAction(BaseModel):
    status: JoinRequestStatus # APPROVED or REJECTED

# --- Endpoints ---

@router.post("/", response_model=JoinRequestRead)
async def create_join_request(
    data: JoinRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Volunteer requests to join an NGO."""
    if current_user.role != UserRole.VOLUNTEER:
        raise HTTPException(status_code=403, detail="Only volunteers can submit join requests")

    # Get volunteer record
    v_stmt = select(Volunteer).where(Volunteer.user_id == current_user.id)
    volunteer = (await db.execute(v_stmt)).scalar_one_or_none()
    if not volunteer:
        raise HTTPException(status_code=404, detail="Volunteer record not found")

    if volunteer.org_id:
        raise HTTPException(status_code=400, detail="You are already associated with an NGO. Leave your current NGO to join a new one.")

    # Enforcement: Only one pending request at a time
    stmt = select(VolunteerJoinRequest).where(
        (VolunteerJoinRequest.volunteer_id == volunteer.id) &
        (VolunteerJoinRequest.status == JoinRequestStatus.PENDING)
    )
    if (await db.execute(stmt)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="You already have a pending join request. Cancel it before applying elsewhere.")

    # Verify Org exists
    org = await db.get(Organization, data.org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    new_request = VolunteerJoinRequest(
        volunteer_id=volunteer.id,
        org_id=data.org_id,
        status=JoinRequestStatus.PENDING
    )
    db.add(new_request)
    await db.commit()
    await db.refresh(new_request)

    return JoinRequestRead(
        id=new_request.id,
        volunteer_id=new_request.volunteer_id,
        volunteer_name=volunteer.name,
        org_id=new_request.org_id,
        org_name=org.name,
        status=new_request.status,
        created_at=new_request.created_at
    )

@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_join_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Volunteer cancels their own pending request."""
    # 1. Get volunteer
    v_stmt = select(Volunteer).where(Volunteer.user_id == current_user.id)
    volunteer = (await db.execute(v_stmt)).scalar_one_or_none()
    
    # 2. Get request
    request = await db.get(VolunteerJoinRequest, request_id)
    if not request or request.volunteer_id != volunteer.id:
        raise HTTPException(status_code=404, detail="Request not found")
    
    if request.status != JoinRequestStatus.PENDING:
        raise HTTPException(status_code=400, detail="Only pending requests can be cancelled")
    
    await db.delete(request)
    await db.commit()
    return None

@router.post("/leave", status_code=status.HTTP_200_OK)
async def leave_ngo(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Volunteer leaves their current NGO to become independent again."""
    if current_user.role != UserRole.VOLUNTEER:
        raise HTTPException(status_code=403, detail="Only volunteers can leave an NGO")

    # Get volunteer record
    v_stmt = select(Volunteer).where(Volunteer.user_id == current_user.id)
    volunteer = (await db.execute(v_stmt)).scalar_one_or_none()
    
    if not volunteer or not volunteer.org_id:
        raise HTTPException(status_code=400, detail="You are not associated with any NGO")

    # Reset membership
    volunteer.org_id = None
    current_user.org_id = None
    
    await db.commit()
    return {"message": "You have successfully left the NGO and are now an independent volunteer."}

@router.get("/my", response_model=List[JoinRequestRead])
async def get_my_requests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Volunteer views their own pending/previous requests."""
    v_stmt = select(Volunteer).where(Volunteer.user_id == current_user.id)
    volunteer = (await db.execute(v_stmt)).scalar_one_or_none()
    
    stmt = select(VolunteerJoinRequest).where(VolunteerJoinRequest.volunteer_id == volunteer.id)
    result = await db.execute(stmt)
    requests = result.scalars().all()
    
    res_list = []
    for r in requests:
        org = await db.get(Organization, r.org_id)
        res_list.append(JoinRequestRead(
            id=r.id,
            volunteer_id=r.volunteer_id,
            volunteer_name=volunteer.name,
            org_id=r.org_id,
            org_name=org.name if org else "Unknown",
            status=r.status,
            created_at=r.created_at
        ))
    return res_list

@router.get("/incoming", response_model=List[JoinRequestRead])
async def get_incoming_requests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """NGO views pending requests from volunteers."""
    if current_user.role != UserRole.NGO_COORDINATOR:
        raise HTTPException(status_code=403, detail="Only NGO staff can view incoming requests")

    stmt = select(VolunteerJoinRequest).where(
        (VolunteerJoinRequest.org_id == current_user.org_id) &
        (VolunteerJoinRequest.status == JoinRequestStatus.PENDING)
    )
    result = await db.execute(stmt)
    requests = result.scalars().all()
    
    res_list = []
    for r in requests:
        v = await db.get(Volunteer, r.volunteer_id)
        org = await db.get(Organization, r.org_id)
        res_list.append(JoinRequestRead(
            id=r.id,
            volunteer_id=r.volunteer_id,
            volunteer_name=v.name if v else "Unknown",
            org_id=r.org_id,
            org_name=org.name if org else "Unknown",
            status=r.status,
            created_at=r.created_at
        ))
    return res_list

@router.patch("/{request_id}", response_model=JoinRequestRead)
async def handle_join_request(
    request_id: int,
    action: JoinRequestAction,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """NGO approves or rejects a volunteer's request."""
    if current_user.role != UserRole.NGO_COORDINATOR:
        raise HTTPException(status_code=403, detail="Only NGO staff can handle requests")

    request = await db.get(VolunteerJoinRequest, request_id)
    if not request or request.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Request not found")

    if request.status != JoinRequestStatus.PENDING:
        raise HTTPException(status_code=400, detail="Request is already processed")

    request.status = action.status
    
    if action.status == JoinRequestStatus.APPROVED:
        # Update volunteer and associated user org_id
        volunteer = await db.get(Volunteer, request.volunteer_id)
        volunteer.org_id = current_user.org_id
        
        user = await db.get(User, volunteer.user_id)
        if user:
            user.org_id = current_user.org_id
            
    await db.commit()
    await db.refresh(request)
    
    v = await db.get(Volunteer, request.volunteer_id)
    org = await db.get(Organization, request.org_id)
    
    return JoinRequestRead(
        id=request.id,
        volunteer_id=request.volunteer_id,
        volunteer_name=v.name if v else "Unknown",
        org_id=request.org_id,
        org_name=org.name if org else "Unknown",
        status=request.status,
        created_at=request.created_at
    )
