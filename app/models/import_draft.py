import uuid
from datetime import datetime,timezone
from sqlalchemy import Column,DateTime,ForeignKey,Integer,String,Index
from sqlalchemy.dialects.postgresql import UUID,JSONB
from app.core.database import Base

class ImportDraft(Base):
    __tablename__='import_drafts'
    __table_args__=(Index('ix_import_drafts_owner','user_id','family_id','expires_at'),)
    id=Column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    family_id=Column(UUID(as_uuid=True),ForeignKey('family_spaces.id',ondelete='CASCADE'),nullable=False)
    user_id=Column(UUID(as_uuid=True),ForeignKey('users.id',ondelete='CASCADE'),nullable=False)
    file_name=Column(String(255),nullable=False)
    preview_payload=Column(JSONB,nullable=False)
    preview_data=Column(JSONB,nullable=False)
    review_state=Column(JSONB,nullable=False,default=dict)
    completed_at=Column(DateTime(timezone=True),nullable=True)
    revision=Column(Integer,nullable=False,default=1)
    created_at=Column(DateTime(timezone=True),nullable=False,default=lambda:datetime.now(timezone.utc))
    updated_at=Column(DateTime(timezone=True),nullable=False,default=lambda:datetime.now(timezone.utc))
    expires_at=Column(DateTime(timezone=True),nullable=False)
