from database import db

from services.profile_service import ProfileService


class RecommendService:


    """
    留学课程推荐引擎
    """


    # =========================
    # 专业关键词库
    # =========================

    MAJOR_MAP = {


        "计算机":[

            "计算机",

            "computer",

            "cs",

            "computer science",

            "人工智能",

            "ai",

            "软件工程",

            "software",

            "数据科学",

            "data"

        ],


        "商科":[

            "商科",

            "business",

            "金融",

            "finance",

            "管理",

            "management",

            "marketing"

        ],


        "工程":[

            "工程",

            "engineering",

            "机械",

            "电子",

            "土木"

        ],


        "医学":[

            "医学",

            "medical",

            "medicine",

            "health"

        ]

    }



    # =========================
    # 总入口
    # =========================


    @staticmethod
    def recommend(conversation_id):


        profile = ProfileService.get_profile(
            conversation_id
        )


        if not profile:

            return {

                "success":False,

                "message":"用户不存在"

            }



        courses = RecommendService.get_courses()



        result=[]



        for course in courses:


            score,reason = RecommendService.score(

                profile,

                course

            )


            course_result={

                "course_id":course["id"],

                "course_name":course["course_name"],

                "university":course["university"],

                "country":course["country"],

                "score":score,

                "reason":reason

            }


            result.append(course_result)



        result.sort(

            key=lambda x:x["score"],

            reverse=True

        )



        return {


            "success":True,


            "recommendations":result[:5]

        }




    # =========================
    # 获取课程
    # =========================


    @staticmethod
    def get_courses():


        sql="""

        SELECT *

        FROM courses

        WHERE enabled=1

        """


        return db.query(sql)



    # =========================
    # 核心评分
    # =========================


    @staticmethod
    def score(profile,course):


        score=0


        reasons=[]



        # 学历
        s,r = RecommendService.score_education(

            profile,

            course

        )


        score+=s


        if r:

            reasons.append(r)




        # 专业

        s,r = RecommendService.score_major(

            profile,

            course

        )


        score+=s


        if r:

            reasons.append(r)




        # 语言

        s,r = RecommendService.score_language(

            profile,

            course

        )


        score+=s


        if r:

            reasons.append(r)




        # 国家

        s,r = RecommendService.score_country(

            profile,

            course

        )


        score+=s


        if r:

            reasons.append(r)



        # GPA

        s,r = RecommendService.score_gpa(

            profile,

            course

        )


        score+=s


        if r:

            reasons.append(r)



        return score,reasons


    @staticmethod
    def score_education(profile,course):


        user_edu = profile.get(
            "education"
        )


        course_edu = course.get(
            "degree_level"
        )


        if not user_edu:

            return 0,None



        if user_edu in course_edu:


            return 30,"学历符合"



        return 0,None

    @staticmethod
    def score_major(profile,course):


        user_major = profile.get(
            "target_major"
        )


        course_major = course.get(
            "major"
        )



        if not user_major:

            return 0,None



        user_major=user_major.lower()

        course_major=course_major.lower()



        for category,keywords in RecommendService.MAJOR_MAP.items():


            hit_user=False


            for k in keywords:


                if k.lower() in user_major:

                    hit_user=True



            if hit_user:


                for k in keywords:


                    if k.lower() in course_major:


                        return 35,"专业高度匹配"



        return 10,"专业方向相关"

    @staticmethod
    def parse_language(value):


        if not value:

            return 0



        value=str(value).lower()



        import re


        number=re.findall(

            r"\d+\.?\d*",

            value

        )


        if not number:

            return 0



        score=float(number[0])



        if "ielts" in value or "雅思" in value:


            return score



        if "toefl" in value or "托福" in value:


            return score/15



        return score

    @staticmethod
    def score_language(profile,course):


        user_score=RecommendService.parse_language(

            profile.get("language_score")

        )


        requirement=RecommendService.parse_language(

            course.get("language_requirement")

        )


        if user_score>=requirement:


            return 20,"语言成绩满足"



        return 5,"语言成绩接近"


    @staticmethod
    def score_country(profile,course):


        country=profile.get(
            "target_country"
        )


        if not country:

            return 0,None



        if country in course.get(
            "country",
            ""
        ):


            return 10,"国家匹配"



        return 0,None


    @staticmethod
    def score_gpa(profile,course):


        gpa=profile.get(
            "gpa"
        )


        min_gpa=course.get(
            "min_gpa"
        )


        if not gpa or not min_gpa:

            return 0,None



        if float(gpa)>=float(min_gpa):

            return 5,"GPA符合"



        return 0,"GPA不足"