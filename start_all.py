#!/usr/bin/env python3
"""
dify_pro — 粤教留学 AI 智能助手平台
一键启动所有微服务

启动方式: python start_all.py [服务名]
  - 无参数: 启动所有服务
  - 参数可以是: customer, student, enterprise, assessment, report
     (customer 已包含课程推荐 + 活动讲座报名, 不再作为独立服务启动)
  - --frontend-only: 仅启动统一前端 (customer_agent:9000)
"""

import os
import sys
import subprocess
import time
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent

SERVICES = {
    "student": {
        "name": "学生智能助手",
        "module": "student_agent.main_jb",
        "port": 8000,
        "dir": ".",
        "cmd": ["python", "-m", "student_agent.main_jb"],
    },
    "enterprise": {
        "name": "企业智能助手",
        "module": "enterprise_agent.main",
        "port": 8001,
        "dir": ".",
        "cmd": ["python", "-m", "enterprise_agent.main"],
    },
    "assessment": {
        "name": "研判服务",
        "module": "Assessment.main_ass",
        "port": 8002,
        "dir": "Assessment",
        "cmd": ["python", "main_ass.py"],
    },
    "report": {
        "name": "智能报告",
        "module": "summary_report.main",
        "port": 8003,
        "dir": ".",
        "cmd": ["python", "-m", "summary_report.main"],
    },
    "customer": {
        "name": "客服Agent + 统一前端",
        "module": "customer_agent.main",
        "port": 9000,
        "dir": ".",
        "cmd": ["python", "-m", "customer_agent.main"],
    },
}

BANNER = r"""
╔══════════════════════════════════════════════════════════════╗
║           🎓 粤教留学 · AI 智能助手平台 v2.0               ║
║          Yuejiao Study Abroad AI Platform                   ║
╚══════════════════════════════════════════════════════════════╝
"""


def print_banner():
    print(BANNER)
    print("  服务端口映射:")
    print(f"  {'服务':<20} {'端口':<8} {'地址'}")
    print(f"  {'─'*20} {'─'*8} {'─'*30}")
    for key, svc in SERVICES.items():
        print(f"  {svc['name']:<20} {svc['port']:<8} http://localhost:{svc['port']}")
    print(f"\n  📱 统一前端:  http://localhost:9000/portal")
    print(f"  📖 API文档:    http://localhost:9000/docs")
    print()


def start_service(key, svc):
    """启动单个服务（后台进程，保留输出到日志）"""
    cwd = ROOT / svc["dir"]
    print(f"  🚀 启动 {svc['name']} (:{svc['port']})...", end=" ", flush=True)
    try:
        # 日志输出到文件，便于排查问题
        log_dir = ROOT / "logs"
        log_dir.mkdir(exist_ok=True)
        log_file = (log_dir / f"{key}.log").open("a", encoding="utf-8")
        proc = subprocess.Popen(
            svc["cmd"],
            cwd=str(cwd),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        print(f"✅ (日志: logs/{key}.log)")
        return proc
    except Exception as e:
        print(f"❌ 失败: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="粤教留学 AI 平台启动器")
    parser.add_argument("services", nargs="*", help="要启动的服务名 (customer, student, enterprise, assessment, report)")
    parser.add_argument("--frontend-only", action="store_true", help="仅启动前端")
    args = parser.parse_args()

    print_banner()

    # 确定要启动的服务
    if args.frontend_only:
        to_start = {"customer": SERVICES["customer"]}
    elif args.services:
        to_start = {}
        for s in args.services:
            if s in SERVICES:
                to_start[s] = SERVICES[s]
            else:
                print(f"  ⚠️ 未知服务: {s}，可选: {', '.join(SERVICES.keys())}")
        if not to_start:
            return
    else:
        to_start = dict(SERVICES)

    print(f"\n  准备启动 {len(to_start)} 个服务...\n")

    # Python 路径检查
    sys.path.insert(0, str(ROOT))

    # 逐个启动
    processes = {}
    for key in to_start:
        svc = to_start[key]
        proc = start_service(key, svc)
        if proc:
            processes[key] = proc
        time.sleep(1.5)  # 错开启动避免端口竞争

    print(f"\n  ✅ 已启动 {len(processes)}/{len(to_start)} 个服务")
    print(f"\n  🌐 打开浏览器访问: http://localhost:9000/portal")
    print(f"  🛑 按 Ctrl+C 停止所有服务\n")

    # 等待退出
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n  正在停止所有服务...")
        for key, proc in processes.items():
            print(f"  🛑 停止 {SERVICES[key]['name']}...", end=" ", flush=True)
            try:
                proc.terminate()
                proc.wait(timeout=5)
                print("✅")
            except Exception:
                proc.kill()
                print("💀")
        print("\n  所有服务已停止。再见 👋\n")


if __name__ == "__main__":
    main()
