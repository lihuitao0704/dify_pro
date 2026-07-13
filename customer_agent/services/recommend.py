"""
留学课程推荐引擎

合并自 study_abroad_agent/services/recommend_service.py
根据用户画像，从 courses 表中匹配并打分排序，返回 Top5 推荐。
"""
from customer_agent.db import get_db
from customer_agent.services.profiles import ProfileService


class RecommendService:
    """基于画像的课程推荐。"""

    # 专业关键词库
    MAJOR_MAP = {
        "计算机": [
            "计算机", "computer", "cs", "computer science",
            "人工智能", "ai", "软件工程", "software",
            "数据科学", "data",
        ],
        "商科": [
            "商科", "business", "金融", "finance",
            "管理", "management", "marketing",
        ],
        "工程": ["工程", "engineering", "机械", "电子", "土木"],
        "医学": ["医学", "medical", "medicine", "health"],
    }

    # 用于匹配课程名+描述+亮点
    MATCH_FIELDS = ["course_name", "description", "highlights", "sub_category"]

    # =========================
    # 总入口
    # =========================
    @staticmethod
    def recommend(conversation_id) -> dict:
        """对给定 conversation_id 进行课程推荐。

        返回:
          {"success": True,  "recommendations": [ {course fields + score + reasons} ]}
          {"success": False, "message": "..."}
        """
        profiles = ProfileService.get_by_conversation_id(conversation_id)

        if not profiles:
            return {"success": False, "message": "用户不存在"}

        profile = profiles[0]
        courses = RecommendService.get_courses()

        result = []
        for course in courses:
            score, reasons = RecommendService.score(profile, course)
            course_result = {
                "course_id": course["id"],
                "course_name": course["course_name"],
                "country": course["country"],
                "category": course["category"],
                "sub_category": course["sub_category"],
                "target_education": course["target_education"],
                "score": score,
                "reasons": reasons,
            }
            result.append(course_result)

        result.sort(key=lambda x: x["score"], reverse=True)
        return {"success": True, "recommendations": result[:5]}

    # =========================
    # 获取课程
    # =========================
    @staticmethod
    def get_courses():
        sql = """
            SELECT id, course_name, category, sub_category, country,
                   target_education, min_gpa, min_budget, max_budget,
                   language_requirement, duration, price, description,
                   highlights
            FROM courses
            WHERE is_active = 1
        """
        return get_db().query(sql)

    # =========================
    # 核心评分
    # =========================
    @staticmethod
    def score(profile, course):
        score = 0
        reasons = []

        s, r = RecommendService.score_education(profile, course)
        score += s
        if r:
            reasons.append(r)

        s, r = RecommendService.score_major(profile, course)
        score += s
        if r:
            reasons.append(r)

        s, r = RecommendService.score_language(profile, course)
        score += s
        if r:
            reasons.append(r)

        s, r = RecommendService.score_country(profile, course)
        score += s
        if r:
            reasons.append(r)

        s, r = RecommendService.score_gpa(profile, course)
        score += s
        if r:
            reasons.append(r)

        return score, reasons

    # =========================
    # 学历匹配
    # =========================
    @staticmethod
    def score_education(profile, course):
        user_edu = profile.get("education")
        course_edu = course.get("target_education") or ""
        if not user_edu:
            return 0, None
        if user_edu in course_edu:
            return 30, "学历符合"
        return 0, None

    # =========================
    # 专业匹配（关键词）
    # =========================
    @staticmethod
    def score_major(profile, course):
        user_major = profile.get("target_major")
        if not user_major:
            return 0, None
        user_major = user_major.lower()
        course_text = " ".join(
            str(course.get(f, "") or "") for f in RecommendService.MATCH_FIELDS
        ).lower()
        for category, keywords in RecommendService.MAJOR_MAP.items():
            hit_user = any(k.lower() in user_major for k in keywords)
            if not hit_user:
                continue
            if any(k.lower() in course_text for k in keywords):
                return 35, f"专业匹配（{category}）"
        return 5, "专业方向相关"

    # =========================
    # 语言成绩解析 / 评分
    # =========================
    @staticmethod
    def parse_language(value):
        if not value:
            return 0
        import re
        value = str(value).lower()
        number = re.findall(r"\d+\.?\d*", value)
        if not number:
            return 0
        score = float(number[0])
        if "ielts" in value or "雅思" in value:
            return score
        if "toefl" in value or "托福" in value:
            return score / 15
        return score

    @staticmethod
    def score_language(profile, course):
        user_score = RecommendService.parse_language(profile.get("language_score"))
        requirement = RecommendService.parse_language(
            course.get("language_requirement")
        )
        if not requirement:
            return 20, "无语言门槛"
        if user_score >= requirement:
            return 20, "语言成绩满足"
        return 5, "语言成绩接近"

    # =========================
    # 国家匹配
    # =========================
    @staticmethod
    def score_country(profile, course):
        country = profile.get("target_country")
        if not country:
            return 0, None
        if country in (course.get("country") or ""):
            return 10, "国家匹配"
        return 0, None

    # =========================
    # GPA 匹配
    # =========================
    @staticmethod
    def score_gpa(profile, course):
        gpa = profile.get("gpa")
        min_gpa = course.get("min_gpa")
        if not gpa or not min_gpa:
            return 0, None
        if float(gpa) >= float(min_gpa):
            return 5, "GPA符合"
        return 0, "GPA不足"
