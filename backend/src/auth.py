from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from .database import get_db
from .models import User
from .security import decode_token

bearer = HTTPBearer(auto_error=False)

def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="需要登录")
    try:
        payload = decode_token(credentials.credentials)
        user = db.get(User, int(payload["sub"]))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="登录已失效") from exc
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user

def require_roles(*roles):
    def checker(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="当前角色没有执行该操作的权限")
        return user
    return checker
