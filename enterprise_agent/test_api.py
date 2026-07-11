"""
企业智能助手 - API 测试脚本
运行：python -m enterprise_agent.test_api
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json, logging
from enterprise_agent.database import test_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-5s | %(message)s")
logger = logging.getLogger("test")

PASS = 0
FAIL = 0

def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        logger.info("  PASS | %s", name)
    else:
        FAIL += 1
        logger.warning("  FAIL | %s | %s", name, detail)


def test_db():
    logger.info("[1/5] Database connection")
    ok = test_connection()
    check("test_connection", ok)


def test_imports():
    logger.info("[2/5] Module imports")
    try:
        from enterprise_agent.routers.customer import router as r1
        from enterprise_agent.routers.leave import router as r2
        from enterprise_agent.routers.report import router as r3
        from enterprise_agent.routers.organization import router as r4
        from enterprise_agent.routers.todo import router as r5
        from enterprise_agent.routers.complaint import router as r6
        from enterprise_agent.routers.score import router as r7
        from enterprise_agent.routers.knowledge import router as r8
        from enterprise_agent.routers.nl2sql import router as r9
        from enterprise_agent.models import (
            Account, Employee, IntentionCustomer, LeaveApplication,
            StudentComplaint, StudentScore, Department)
        count = sum(len(r.routes) for r in [r1,r2,r3,r4,r5,r6,r7,r8,r9])
        check("all routers import OK, total routes=%d" % count, count == 19)
    except Exception as e:
        check("module imports", False, str(e))


def test_api():
    logger.info("[3/5] API endpoints (via http)")
    import urllib.request

    base = "http://localhost:8001"
    uid = "current_user_id=1&current_user_type=%E7%AE%A1%E7%90%86%E8%80%85"

    # Health
    try:
        r = urllib.request.urlopen(base + "/health")
        d = json.loads(r.read())
        check("GET /health", d.get("status") == "ok")
    except Exception as e:
        check("GET /health", False, str(e))

    # Todo
    try:
        r = urllib.request.urlopen(base + "/api/agent/todo/all?" + uid)
        d = json.loads(r.read())
        check("GET /todo/all", d.get("code") == 0)
    except Exception as e:
        check("GET /todo/all", False, str(e))

    # Customer list
    try:
        r = urllib.request.urlopen(base + "/api/agent/customer/list?" + uid + "&page=1&page_size=5")
        d = json.loads(r.read())
        check("GET /customer/list", d.get("code") == 0 and d.get("data",{}).get("total",0) > 0)
    except Exception as e:
        check("GET /customer/list", False, str(e))

    # Org tree
    try:
        r = urllib.request.urlopen(base + "/api/agent/organization/tree?" + uid)
        d = json.loads(r.read())
        check("GET /organization/tree", d.get("code") == 0)
    except Exception as e:
        check("GET /organization/tree", False, str(e))

    # Knowledge
    try:
        body = json.dumps({"question":"请假","current_user_id":1,"current_user_type":"管理者"}).encode()
        req = urllib.request.Request(base + "/api/agent/knowledge/query", data=body,
                                     headers={"Content-Type":"application/json"})
        r = urllib.request.urlopen(req)
        d = json.loads(r.read())
        check("POST /knowledge/query", d.get("code") == 0 and d.get("data",{}).get("answer"))
    except Exception as e:
        check("POST /knowledge/query", False, str(e))

    # Permission check (学生 -> 403)
    try:
        u2 = "current_user_id=4&current_user_type=%E5%AD%A6%E5%91%98"
        r = urllib.request.urlopen(base + "/api/agent/customer/list?" + u2)
        check("Permission (学生 should 403)", False, "expected 403")
    except urllib.error.HTTPError as e:
        check("Permission (学生 -> 403)", e.code == 403)


def test_seed():
    logger.info("[4/5] Seed idempotency")
    try:
        from enterprise_agent.seed_data import seed_all
        seed_all()
        check("seed_all() ran without error", True)
    except Exception as e:
        check("seed_all()", False, str(e))


def test_models():
    logger.info("[5/5] Model attributes")
    try:
        from enterprise_agent.models import IntentionCustomer
        cols = [c.name for c in IntentionCustomer.__table__.columns]
        for required in ["customer_id","customer_name","current_status","sales_user_id","create_time"]:
            check("IntentionCustomer has %s" % required, required in cols)
    except Exception as e:
        check("Model introspection", False, str(e))


if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("Enterprise Agent - Test Suite")
    logger.info("=" * 50)

    test_imports()
    test_models()
    test_db()
    test_api()
    test_seed()

    logger.info("=" * 50)
    logger.info("Results: %d passed, %d failed out of %d",
                PASS, FAIL, PASS + FAIL)
    logger.info("=" * 50)

    sys.exit(0 if FAIL == 0 else 1)
