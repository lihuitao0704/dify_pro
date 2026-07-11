"""
知识库问答路由
POST /api/agent/knowledge/query - 新人入职指引（Mock实现）
"""
from fastapi import APIRouter, Depends, HTTPException
import logging
import re

from enterprise_agent.schemas import ApiResponse, KnowledgeQueryRequest

logger = logging.getLogger("enterprise_agent.knowledge")
router = APIRouter()


# ==================== Mock 规章制度知识库 ====================
# TODO: 正式环境请将 KNOWLEDGE_BASE 移到数据库或 JSON 配置文件
# 新增问答条目只需在此 dict 中加一个 key: { keywords, answer, source }
KNOWLEDGE_BASE = {
    "上班时间": {
        "keywords": ["上班时间", "工作时间", "几点上班", "几点下班", "作息", "考勤时间"],
        "answer": "公司实行五天工作制，周一至周五。上班时间：上午 9:00 - 12:00，下午 13:30 - 18:00（午休 12:00-13:30）。",
        "source": "《员工考勤管理制度》第2章第3条",
    },
    "请假制度": {
        "keywords": ["请假", "休假", "事假", "病假", "年假", "婚假", "产假"],
        "answer": "员工请假需提前提交申请：\n1. 事假需提前1天申请，最长连续7天\n2. 病假可凭医院证明补办，3天以内部门主管审批，3天以上需总监审批\n3. 年假：入职满1年享有5天，满10年10天，满20年15天\n4. 婚假：13天（需提供结婚证）\n5. 产假：98天基础+30天奖励",
        "source": "《员工考勤管理制度》第3章 请假管理",
    },
    "薪资福利": {
        "keywords": ["工资", "薪资", "薪酬", "发薪", "工资条", "福利", "补贴", "奖金", "五险一金"],
        "answer": "薪资福利说明：\n1. 每月10日发放上月薪资（遇节假日提前）\n2. 五险一金：入职即缴纳，基数按实际工资\n3. 年终奖：根据年度绩效评定，通常为1-3个月工资\n4. 餐补：工作日每天20元\n5. 交通补贴：每月200元\n6. 节日福利：春节、中秋、端午等传统节日发放礼品或礼金",
        "source": "《薪酬福利管理制度》第1-4章",
    },
    "加班调休": {
        "keywords": ["加班", "调休", "加班费", "加班工资"],
        "answer": "加班管理规定：\n1. 工作日加班：按基本工资1.5倍计算\n2. 休息日加班：可选择2倍加班费或同等时间调休\n3. 法定节假日加班：按基本工资3倍计算\n4. 加班需提前填写《加班申请单》，经部门主管审批",
        "source": "《员工考勤管理制度》第4章 加班管理",
    },
    "出差报销": {
        "keywords": ["出差", "报销", "差旅", "报销流程", "发票"],
        "answer": "出差及报销流程：\n1. 出差需提前填写《出差申请单》，注明事由、地点、天数\n2. 交通：长途可乘坐高铁二等座/飞机经济舱\n3. 住宿：一线城市≤500元/晚，其他城市≤350元/晚\n4. 餐补：100元/天\n5. 报销需在出差回来后5个工作日内提交，附上发票和行程单",
        "source": "《财务报销管理制度》第3章 差旅费报销",
    },
    "培训发展": {
        "keywords": ["培训", "学习", "发展", "晋升", "职业发展", "技能培训"],
        "answer": "员工培训与发展：\n1. 新员工入职培训：入职第一周集中培训\n2. 在职培训：每年至少40小时专业技能培训\n3. 学历提升补贴：在职攻读相关专业学位，可申请50%学费补贴\n4. 晋升通道：每年两次晋升评估（6月和12月）\n5. 内部竞聘：空缺岗位优先内部招聘",
        "source": "《员工培训与发展制度》全章",
    },
    "保密制度": {
        "keywords": ["保密", "机密", "信息安全", "数据安全", "保密协议"],
        "answer": "公司保密制度：\n1. 员工需签署《保密协议》\n2. 禁止将公司客户信息、技术资料、财务数据带出办公场所\n3. 办公电脑需设置密码，离开工位需锁定屏幕\n4. 禁止在公共网络传输公司敏感数据\n5. 违反保密制度视情节轻重给予警告、罚款或解雇处理",
        "source": "《信息安全与保密管理制度》全章",
    },
    "办公规范": {
        "keywords": ["着装", "仪容仪表", "办公规范", "行为规范", "工位", "办公环境"],
        "answer": "办公规范要求：\n1. 着装：周一至周四正装或商务休闲，周五可穿便装\n2. 工位保持整洁，下班前整理桌面\n3. 办公区域禁止吸烟\n4. 会议提前5分钟到场，手机调至静音\n5. 节约用纸、用水、用电",
        "source": "《员工行为规范手册》第2章 办公规范",
    },
    "默认": {
        "keywords": [],
        "answer": "您好！我是企业智能助手。当前可提供以下方面的入职指引信息：\n• 上班时间与考勤\n• 请假制度\n• 薪资福利\n• 加班调休\n• 出差报销\n• 培训发展\n• 保密制度\n• 办公规范\n\n请直接提出您的问题，我将为您详细解答。",
        "source": "企业智能助手知识库",
    },
}


def match_question(question: str) -> dict:
    """匹配问题并返回答案，使用关键词匹配"""
    if not question or not question.strip():
        return KNOWLEDGE_BASE["默认"]

    # 遍历所有知识条目
    best_match = None
    best_score = 0

    for key, entry in KNOWLEDGE_BASE.items():
        if key == "默认":
            continue
        for kw in entry["keywords"]:
            if kw in question:
                score = len(kw)  # 关键词越长越精确
                if score > best_score:
                    best_score = score
                    best_match = entry

    if best_match:
        return best_match

    # 如果没有精准匹配，尝试单个字匹配
    return KNOWLEDGE_BASE["默认"]


# ==================== POST /api/agent/knowledge/query ====================
@router.post("/knowledge/query", response_model=ApiResponse, summary="知识库问答")
def query_knowledge(req: KnowledgeQueryRequest):
    """
    新人入职指引知识库问答
    根据用户问题从规章制度文档中检索答案（当前为Mock实现）
    """
    try:
        question = req.question.strip()
        logger.info(f"知识库问答: question='{question}', user_id={req.current_user_id}, type={req.current_user_type}")

        if not question:
            return ApiResponse(code=400, msg="问题不能为空")

        result = match_question(question)

        return ApiResponse(data={
            "question": question,
            "answer": result["answer"],
            "source": result["source"],
        })

    except Exception as e:
        logger.error(f"知识库问答失败: {e}", exc_info=True)
        return ApiResponse(code=500, msg=f"查询失败: {str(e)}")
