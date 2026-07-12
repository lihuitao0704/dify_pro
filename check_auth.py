#!/usr/bin/env python3
"""
鉴权诊断脚本 — 一键检查所有端口的角色隔离是否生效
运行: python check_auth.py
"""
import urllib.request
import json
import sys

TESTS = [
    # (端口, 用户名, 密码, 预期结果, 说明)
    (9000, "student1", "123456", True,  "学员在9000学生端登录"),
    (9000, "lisi",     "123456", False, "员工在9000学生端→应被拒绝"),
    (8000, "student1", "123456", True,  "学员在8000学生端登录"),
    (8000, "lisi",     "123456", False, "员工在8000学生端→应被拒绝"),
    (8001, "lisi",     "123456", True,  "员工在8001企业端登录"),
    (8001, "student1", "123456", False, "学员在8001企业端→应被拒绝"),
]

failed = 0
for port, user, pwd, expect_success, desc in TESTS:
    try:
        url = f"http://localhost:{port}/auth/login"
        data = json.dumps({"username": user, "password": pwd}).encode()
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=5)
        result = json.loads(resp.read().decode())
        actual_success = result.get("success", False)
        ok = actual_success == expect_success
        status = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        msg = result.get("message", "")[:60] if not actual_success else ""
        print(f"  [{status}] :{port} {user:10s} -> {'OK' if actual_success else 'BLOCKED'} {msg}")
    except urllib.error.HTTPError as e:
        ok = (e.code >= 400) == (not expect_success)
        if not ok: failed += 1
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] :{port} {user:10s} -> HTTP {e.code} ({'expected OK' if expect_success else 'expected BLOCKED'})")
    except Exception as e:
        print(f"  [SKIP] :{port} {user:10s} -> 端口不可达 ({e})")

print(f"\n  {'全部通过!' if failed == 0 else f'{failed} 项失败 -- 鉴权未生效，服务可能跑了旧代码'}")
print(f"  如果失败，请先: python start_all.py --stop")
print(f"  确认端口清空后: python start_all.py")
sys.exit(0 if failed == 0 else 1)
