from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.models import Organization
from backend.app.crud.base import CRUDBase
from pydantic import BaseModel

class OrgCreate(BaseModel):
    name: str
    description: Optional[str] = None
    status: str = "pending"

class OrgUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class CRUDOrganization(CRUDBase[Organization, OrgCreate, OrgUpdate]):
    async def get_active(self, db: AsyncSession) -> List[Organization]:
        stmt = select(self.model).where(self.model.status == "active")
        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_by_name(self, db: AsyncSession, *, name: str) -> Optional[Organization]:
        stmt = select(self.model).where(self.model.name == name)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

org_crud = CRUDOrganization(Organization)
