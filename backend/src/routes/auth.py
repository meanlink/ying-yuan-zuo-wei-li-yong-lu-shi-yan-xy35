from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..schemas import LoginIn
from ..security import create_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "邮箱或密码错误")
    return {"token": create_token(user.id, user.role, user.name), "user": {"id": user.id, "name": user.name, "role": user.role, "email": user.email}}
