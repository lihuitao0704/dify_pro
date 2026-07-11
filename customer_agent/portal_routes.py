"""
customer_agent/portal_routes.py
通过显式路由统一门户页面（避免 Windows 上 mount 的缓存问题）
"""
import os
from fastapi.responses import FileResponse, HTMLResponse

_unified_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "unified_frontend")


def _serve_static(subpath: str):
    """安全地返回 unified_frontend 下的静态文件"""
    if not subpath or subpath == "/":
        subpath = "index.html"
    # 防止目录遍历
    target = os.path.normpath(os.path.join(_unified_dir, subpath))
    if not target.startswith(_unified_dir):
        return HTMLResponse("Forbidden", status_code=403)
    if not os.path.isfile(target):
        return HTMLResponse(f"Not Found: {subpath}", status_code=404)
    return FileResponse(target)


def register_portal_routes(app):
    """注册 /portal 路由"""
    @app.get("/portal")
    def portal_index():
        return _serve_static("index.html")

    @app.get("/portal/css/{filename}")
    def portal_css(filename: str):
        return _serve_static(f"css/{filename}")

    @app.get("/portal/js/{filename}")
    def portal_js(filename: str):
        return _serve_static(f"js/{filename}")

    @app.get("/portal/student-dashboard")
    def portal_student_dashboard():
        return _serve_static("student-dashboard.html")

    @app.get("/portal/employee-dashboard")
    def portal_employee_dashboard():
        return _serve_static("employee-dashboard.html")

    @app.get("/portal/{full_path:path}")
    def portal_fallback(full_path: str):
        return _serve_static(full_path)
