#!/usr/bin/env python3
"""
dify_pro — 粤教留学 AI 智能助手平台
一键启动/停止所有微服务

启动方式:
  python start_all.py              启动所有服务
  python start_all.py [服务名]      启动指定服务
  python start_all.py --stop       停止所有服务（杀死所有端口进程）
  python start_all.py --restart    重启所有服务
  python start_all.py --frontend-only  仅启动前端(9000)
"""

import os
import sys
import subprocess
import time
import signal
import argparse
from pathlib import Path
from typing import TypedDict


class ServiceConfig(TypedDict):
    name: str
    module: str
    port: int
    dir: str
    cmd: list[str]

ROOT = Path(__file__).resolve().parent

SERVICES: dict[str, ServiceConfig] = {
    "study_abroad": {
        "name": "课程推荐引擎",
        "module": "study_abroad_agent.app",
        "port": 5000,
        "dir": "study_abroad_agent",
        "cmd": ["python", "-m", "study_abroad_agent.app"],
    },
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
    "event": {
        "name": "活动讲座报名",
        "module": "Event & Lecture Registration.Event_Lecture_api",
        "port": 8011,
        "dir": "Event & Lecture Registration",
        "cmd": ["python", "Event_Lecture_api.py"],
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
║           [YueJiao] 粤教留学 · AI 智能助手平台 v2.0               ║
║          Yuejiao Study Abroad AI Platform                   ║
╚══════════════════════════════════════════════════════════════╝
"""

# 存储所有启动的子进程，便于停止
_running_processes: list[subprocess.Popen] = []


def print_banner():
    print(BANNER)
    print("  服务端口映射:")
    print(f"  {'服务':<20} {'端口':<8} {'地址'}")
    print(f"  {'─'*20} {'─'*8} {'─'*30}")
    for key, svc in SERVICES.items():
        print(f"  {svc['name']:<20} {svc['port']:<8} http://localhost:{svc['port']}")
    print(f"\n  [WEB] 统一前端:  http://localhost:9000/portal")
    print(f"  [DOCS] API文档:    http://localhost:9000/docs")
    print()


# ── 端口管理 ──

def kill_ports(ports: set[int] | None = None):
    """杀死占用指定端口的进程。不传 ports 则杀所有服务端口"""
    if ports is None:
        ports = {svc["port"] for svc in SERVICES.values()}

    killed_any = False
    for port in sorted(ports):
        pids = _find_pids_on_port(port)
        for pid in pids:
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "-PID", str(pid), "-F", "-T"],
                                   capture_output=True, timeout=10)
                else:
                    os.kill(pid, signal.SIGKILL)
                killed_any = True
            except Exception:
                pass
        if pids:
            print(f"  [KILL] 端口 {port}: 杀掉 {len(pids)} 个进程 (PIDs: {pids})")
    if not killed_any:
        print("  [OK] 没有需要清理的端口")
    else:
        time.sleep(1)  # 等 OS 释放端口


def _find_pids_on_port(port: int) -> list[int]:
    """查找占用指定端口的 PID 列表"""
    pids = set()
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    try:
                        pids.add(int(parts[-1]))
                    except (ValueError, IndexError):
                        pass
        else:
            result = subprocess.run(
                ["lsof", "-ti", f"TCP:{port}"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    pids.add(int(line.strip()))
    except Exception:
        pass

    # 排除当前进程
    current = os.getpid()
    pids.discard(current)
    return sorted(pids)


# ── 服务启动 ──

def start_service(key, svc):
    """启动单个服务（后台进程，输出到日志）"""
    cwd = ROOT / svc["dir"]
    print(f"  [START] 启动 {svc['name']} (:{svc['port']})...", end=" ", flush=True)
    try:
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
        _running_processes.append(proc)
        print(f"[OK] (PID:{proc.pid} 日志: logs/{key}.log)")
        return proc
    except Exception as e:
        print(f"[FAIL] 失败: {e}")
        return None


# ── 全部停止 ──

def stop_all():
    """停止所有本脚本启动的子进程 + 清理所有服务端口"""
    print("\n  正在停止所有服务...")

    # 先优雅终止子进程
    for proc in _running_processes:
        try:
            proc.terminate()
        except Exception:
            pass
    time.sleep(1)

    for proc in _running_processes:
        try:
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    _running_processes.clear()

    # 杀端口上的残留进程
    all_ports = {svc["port"] for svc in SERVICES.values()}
    kill_ports(all_ports)

    print("  所有服务已停止。\n")


# ── 主逻辑 ──

def main():
    parser = argparse.ArgumentParser(description="粤教留学 AI 平台启动器")
    parser.add_argument("services", nargs="*",
                        help="要启动的服务名 (customer, student, enterprise, assessment, report, study_abroad, event)")
    parser.add_argument("--frontend-only", action="store_true", help="仅启动前端")
    parser.add_argument("--stop", action="store_true", help="停止所有服务并清理端口")
    parser.add_argument("--restart", action="store_true", help="先停止再启动所有服务")
    args = parser.parse_args()

    # ── 停止模式 ──
    if args.stop or args.restart:
        stop_all()
        if args.stop:
            return
        print("  等待端口释放...")
        time.sleep(2)

    print_banner()

    # ── 确定要启动的服务 ──
    if args.frontend_only:
        to_start = {"customer": SERVICES["customer"]}
    elif args.services:
        to_start = {}
        for s in args.services:
            if s in SERVICES:
                to_start[s] = SERVICES[s]
            else:
                print(f"  [WARN] 未知服务: {s}，可选: {', '.join(SERVICES.keys())}")
        if not to_start:
            return
    else:
        to_start = dict(SERVICES)

    # ── 启动前先清理端口 ──
    ports_to_clean = {to_start[k]["port"] for k in to_start}
    print(f"\n  [CLEAN] 清理 {len(ports_to_clean)} 个端口...")
    kill_ports(ports_to_clean)

    print(f"\n  准备启动 {len(to_start)} 个服务...\n")
    sys.path.insert(0, str(ROOT))

    processes = {}
    for key in to_start:
        svc = to_start[key]
        proc = start_service(key, svc)
        if proc:
            processes[key] = proc
        time.sleep(1.5)

    print(f"\n  [OK] 已启动 {len(processes)}/{len(to_start)} 个服务")
    print(f"\n  [URL] 打开浏览器访问: http://localhost:9000/portal")
    print(f"  [STOP] 按 Ctrl+C 停止所有服务\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_all()
        print("  再见 [BYE]\n")


if __name__ == "__main__":
    main()
