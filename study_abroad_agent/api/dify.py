from flask import Blueprint
from flask import request
from study_abroad_agent.services.profile_service import ProfileService
from study_abroad_agent.services.recommend_service import RecommendService
from study_abroad_agent.services.consultation_service import ConsultationService
from study_abroad_agent.utils.response import success, fail
from study_abroad_agent.database import db


dify = Blueprint(
    "dify",
    __name__,
    url_prefix="/api/dify"
)


@dify.route("/profile", methods=["POST"])
def save_profile():

    body = request.get_json(silent=True)
    if not body:
        return fail("Body不能为空")

    conversation_id = body.get("conversation_id")
    if not conversation_id:
        return fail("conversation_id不能为空")

    profile = ProfileService.save_profile(
        conversation_id,
        body
    )

    check = ProfileService.check_profile(
        conversation_id
    )

    return success(
        {
            "profile": profile,
            "complete": check["complete"],
            "missing": check["missing"]
        }
    )


# 推荐课程
@dify.route("/recommend", methods=["POST"])
def recommend():

    body = request.get_json(silent=True)
    if not body:
        return fail("Body不能为空")

    conversation_id = body.get("conversation_id")
    if not conversation_id:
        return fail("conversation_id不能为空")

    result = RecommendService.recommend(
        conversation_id
    )
    if not result["success"]:
        return fail(result["message"])

    return success(result)


# 保存咨询记录
@dify.route("/consultation", methods=["POST"])
def save_consultation():

    body = request.get_json(silent=True)
    if not body:
        return fail("Body不能为空")

    conversation_id = body.get("conversation_id")
    if not conversation_id:
        return fail("conversation_id不能为空")

    summary = body.get("summary", "")
    recommend_ids = body.get("recommend_ids", [])

    ConsultationService.save(
        conversation_id,
        summary,
        recommend_ids
    )

    return success()


# 获取profile
@dify.route("/profile/<conversation_id>")
def get_profile(conversation_id):

    profile = ProfileService.get_profile_detail(
        conversation_id
    )
    if not profile:
        return fail("用户不存在")

    return success(profile)


# 删除profile
@dify.route("/profile/<conversation_id>", methods=["DELETE"])
def delete_profile(conversation_id):

    ProfileService.delete_profile(
        conversation_id
    )
    return success()


# health
@dify.route("/health")
def health():

    result = db.query("SELECT 1")
    return success(result)
