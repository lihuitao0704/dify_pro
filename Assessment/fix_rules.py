"""
修复 portrait_rule：1) 统一 rule_key 为中文（P1 德双元 P2 德国精英）2) 防 LLM 把 2+2 算成数学表达式 — 后端已兜底，本脚本重新清缓存
运行:   python Assessment\fix_rules.py
"""
import hashlib, json, logging, os, re, sys

import pymysql
from pymysql.cursors import DictCursor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DB = dict(
    host=os.getenv("DB_HOST", "192.168.48.121"),
    port=int(os.getenv("DB_PORT", 3306)),
    user=os.getenv("DB_USER", "offer"),
    password=os.getenv("DB_PASSWORD", "123456"),
    database=os.getenv("DB_NAME", "dify_pro"),
    charset="utf8mb4",
)

# 中文名 PROJECT_KEY_FIXES[project_id][old_key] = (new_key, new_sub, new_cat)
PROJECT_KEY_FIXES = {
    1: {  # 德国双元制 / 创新创业
        "age_match": ("年龄匹配", "年龄", "基本条件"),
    },
    2: {  # 德国精英
        "年龄匹配": ("年龄匹配", "年龄", "基本条件"),  # 确保一致
        "学历匹配": ("学历匹配", "学历", "基本条件"),
    },
}


def main() -> None:
    conn = pymysql.connect(**DB, cursorclass=DictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) n FROM portrait_rule")  # 连通性探测
            logging.info("portrait_rule 共 %d 条", cur.fetchone()["n"])

        # 0. 强制清掉全部缓存
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE project_expression_cache")
            logging.info("清空 project_expression_cache")
        conn.commit()

        # 1. 逐 project / 逐规则检查 + 可选更新 rule_key
        with conn.cursor() as cur:
            cur.execute("SELECT project_id, rule_id, rule_key FROM portrait_rule WHERE is_active=1 ORDER BY project_id, sort_order")
            rows = cur.fetchall()

        changes = 0
        for r in rows:
            fixes = PROJECT_KEY_FIXES.get(r["project_id"], {})
            if r["rule_key"] in fixes:
                new_key, new_sub, new_cat = fixes[r["rule_key"]]
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE portrait_rule SET rule_key=%s, rule_subcategory=%s, rule_category=%s WHERE rule_id=%s",
                        (new_key, new_sub, new_cat, r["rule_id"]),
                    )
                conn.commit()
                changes += 1
                logging.info("P%d R%-2d key %-12s → %s", r["project_id"], r["rule_id"], r["rule_key"], new_key)

        if changes == 0:
            logging.info("rule_key 已经是中文，无需改动")

        # 2. 校验：每 project 满分=100
        with conn.cursor() as cur:
            cur.execute("SELECT project_id, SUM(score_max) s FROM portrait_rule WHERE is_active=1 GROUP BY project_id")
            for r in cur.fetchall():
                flag = "✅" if r["s"] == 100 else "⚠ 非 100"
                logging.info("Project %d 满分=%d %s", r["project_id"], r["s"], flag)

        # 3. 校验：修完后 hash 会变 → 缓存已空，确认
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) n FROM project_expression_cache")
            n = cur.fetchone()["n"]
            assert n == 0, f"缓存未清空: {n}"
            logging.info("缓存已清空，下次评估自动按新 key 走 LLM")

    finally:
        conn.close()

    logging.info("全部完成")


if __name__ == "__main__":
    main()
