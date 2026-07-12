"""
认证相关路由
"""
from fastapi import APIRouter

router = APIRouter()

# 登录接口已在 main.py 中直接定义（/auth/login），
# 此处可扩展 token 刷新、修改密码等。
