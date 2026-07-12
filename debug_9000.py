#!/usr/bin/env python3
"""快速诊断 9000 端口跑的是新代码还是旧代码"""
import urllib.request, json, subprocess, sys

print("=" * 50)
print("1. 检查 9000 端口上跑的进程")
print("=" * 50)
result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
for line in result.stdout.splitlines():
    if ":9000" in line and "LISTENING" in line:
        pid = line.strip().split()[-1]
        print(f"  端口 9000 -> PID {pid}")
        # 看看这个进程的命令行
        try:
            r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/V", "/FO", "CSV"],
                               capture_output=True, text=True)
            print(f"  {r.stdout.strip()[:200]}")
        except:
            pass

print()
print("=" * 50)
print("2. 测试登录端点是否包含角色校验代码")
print("=" * 50)

# 检查登录端点返回的 message 内容
url = "http://localhost:9000/auth/login"
for user, pwd in [("student1", "123456"), ("lisi", "123456")]:
    data = json.dumps({"username": user, "password": pwd}).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        result = json.loads(resp.read().decode())
        msg = result.get("message", "")
        # 新代码的拒绝消息特征
        has_auth = "员工" in msg or "学员" in msg or "入口" in msg
        print(f"  {user}: success={result['success']} msg={msg[:80]}")
        if result['success'] and 'lisi' in user:
            print(f"  >>> 结论: 9000 端口跑的旧代码，未加载鉴权！")
    except Exception as e:
        print(f"  {user}: 错误 {e}")

print()
print("=" * 50)
print("3. 检查本地的 customer_agent/main.py 是否包含角色校验")
print("=" * 50)
try:
    import customer_agent.main
    with open(customer_agent.main.__file__, encoding='utf-8') as f:
        code = f.read()
    if 'actual_type = (user.get("user_type") or "").strip()' in code:
        print("  本地文件包含角色校验代码 -> 文件最新")
    else:
        print("  本地文件不包含角色校验代码 -> 文件是旧的！git pull 没拉到最新")
except Exception as e:
    print(f"  import 失败: {e}")
