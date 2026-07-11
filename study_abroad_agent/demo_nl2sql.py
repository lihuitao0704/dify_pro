# -*- coding: utf-8 -*-
"""NL2SQL 演示：启动临时服务器并执行一系列自然语言查询示例。"""
import io
import json
import subprocess
import sys
import time
import urllib.request
import urllib.error

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = "http://127.0.0.1:5000"
# (question, include_sql)
QUESTIONS = [
    ("新加坡有哪些课程？", True),
    ("每个国家有多少门课程，按数量降序", True),
    ("GPA 3.0 以上能申请的留学方案，按最低 GPA 降序", True),
    ("用户的姓名、学历和目标国家", True),
    ("新增一门课程：名称=演示新增课程，category=语言课程，sub_category=演示，country=新加坡，target_education=本科，min_gpa=2.5，duration=1个月，price=5678，description=demo_nl2sql 演示新增，is_active=1", True),
]


def query(question, include_sql=True):
    body = json.dumps(
        {"question": question, "include_sql": include_sql}
    ).encode()
    r = urllib.request.Request(
        BASE + "/api/v1/nl2sql/query", data=body, method="POST"
    )
    r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())


def check_server():
    try:
        r = urllib.request.urlopen(BASE + "/api/v1/health", timeout=2)
        return r.status == 200
    except Exception:
        return False


def main():
    server = None
    if not check_server():
        print("[启动临时服务器...]")
        server = subprocess.Popen(
            [sys.executable, "run.py"],
            stdout=subprocess.DEVIO,
            stderr=subprocess.DEVIO,
        )
        for _ in range(30):
            time.sleep(0.5)
            if check_server():
                break

    if not check_server():
        print("服务器启动失败")
        sys.exit(1)

    try:
        for i, (q, show_sql) in enumerate(QUESTIONS, 1):
            print(f"\n{'='*60}")
            print(f"[{i}] 自然语言: {q}")
            resp = query(question=q, include_sql=show_sql)
            if resp.get("code") != 0:
                print(f"    错误: {resp.get('message')}")
                continue
            d = resp["data"]
            if d.get("sql"):
                print(f"    SQL : {d['sql']}")
            if d.get("action") == "insert":
                print(f"    inserted_id: {d.get('inserted_id')}  affected_rows: {d.get('affected_rows')}  耗时: {d.get('elapsed_ms')} ms")
            else:
                print(f"    行数: {d.get('row_count')}  耗时: {d.get('elapsed_ms')} ms")
                # 打印前两行作为示例
                for row in (d.get("rows") or [])[:3]:
                    print(f"      {row}")

        # 写操作防护演示
        print(f"\n{'='*60}")
        print("[防护] 尝试让模型生成 DELETE 语句")
        resp = query(question="帮我把 id=1 的课程删掉", include_sql=True)
        print(f"    HTTP 返回 code={resp.get('code')}  message={resp.get('message')}")
        if resp.get("code") == 400 or "禁止" in resp.get("message", ""):
            print("    [OK] 写操作被 NL2SQL 防护层拦截")

    finally:
        if server:
            print("\n[关闭临时服务器]")
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
