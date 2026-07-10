from study_abroad_agent.database import  db

class ProfileService:

    """
    用户画像服务
    """

    REQUIRED_FIELDS = [
        "education",
        "target_major",
        "language_score"
    ]

    @staticmethod
    def get_profile(conversation_id):

        sql = """
        SELECT *
        FROM user_profiles
        WHERE conversation_id=%s
        """

        return db.query_one(sql, (conversation_id,))

    @staticmethod
    def create_profile(conversation_id):

        sql = """
        INSERT INTO user_profiles
        (
            conversation_id
        )
        VALUES
        (
            %s
        )
        """

        db.execute(sql, (conversation_id,))

        return ProfileService.get_profile(conversation_id)

    @staticmethod
    def save_profile(conversation_id, data):

        profile = ProfileService.get_profile(conversation_id)

        if not profile:

            ProfileService.create_profile(conversation_id)

        allow_fields = [

            "name",

            "education",

            "target_major",

            "language_score",

            "target_country",

            "gpa",

            "budget",

            "phone",

            "wechat",

            "email"

        ]

        update_fields = []

        values = []

        for field in allow_fields:

            if field in data:

                update_fields.append(f"{field}=%s")

                values.append(data[field])

        if not update_fields:

            return ProfileService.get_profile(conversation_id)

        sql = f"""

        UPDATE user_profiles

        SET

        {",".join(update_fields)}

        WHERE conversation_id=%s

        """

        values.append(conversation_id)

        db.execute(sql, tuple(values))

        return ProfileService.get_profile(conversation_id)

    @staticmethod
    def check_profile(conversation_id):

        profile = ProfileService.get_profile(conversation_id)

        if not profile:

            return {

                "complete": False,

                "missing": ProfileService.REQUIRED_FIELDS

            }

        missing = []

        for field in ProfileService.REQUIRED_FIELDS:

            value = profile.get(field)

            if value is None:

                missing.append(field)

                continue

            if isinstance(value, str):

                if value.strip() == "":

                    missing.append(field)

        return {

            "complete": len(missing) == 0,

            "missing": missing

        }

    @staticmethod
    def get_profile_detail(conversation_id):

        profile = ProfileService.get_profile(conversation_id)

        if not profile:

            return None

        return profile

    @staticmethod
    def delete_profile(conversation_id):

        sql = """

        DELETE

        FROM user_profiles

        WHERE conversation_id=%s

        """

        db.execute(sql, (conversation_id,))

    @staticmethod
    def get_missing_question(conversation_id):

        check = ProfileService.check_profile(conversation_id)

        if check["complete"]:
            return None

        mapping = {

            "education": "请问您目前的最高学历是什么？",

            "target_major": "您计划申请什么专业？",

            "language_score": "目前有雅思、托福或者其他语言成绩吗？"

        }

        field = check["missing"][0]

        return {

            "field": field,

            "question": mapping[field]

        }