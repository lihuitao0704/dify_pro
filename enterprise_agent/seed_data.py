"""
企业智能助手 - 测试数据初始化脚本
幂等设计：重复运行安全，已有数据自动跳过或覆盖
运行：python -m enterprise_agent.seed_data
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, date, timedelta
import random
import logging

from enterprise_agent.database import SessionLocal
from enterprise_agent.models import (
    Department, Employee, Student, StudentInfo,
    IntentionCustomer, EmployeeDailyReport,
    StudentComplaint, StudentScore, LeaveApplication, Account,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger("seed")

NOW = datetime.now()

def safe_add(db, model, records, key_attr="id"):
    """安全插入：已存在则跳过，不存在则新增"""
    added = 0
    skipped = 0
    for rec in records:
        v = getattr(rec, key_attr)
        exists = db.query(model).filter(getattr(model, key_attr) == v).first()
        if exists:
            skipped += 1
            continue
        db.add(rec)
        added += 1
    db.flush()
    return added, skipped


def seed_all():
    logger.info("=" * 50)
    logger.info("Seeding test data (idempotent)...")
    logger.info("=" * 50)

    db = SessionLocal()
    try:
        # ---- Student Info ----
        students = db.query(Student).all()
        added, skipped = 0, 0
        for stu in students:
            exists = db.query(StudentInfo).filter(StudentInfo.id == stu.id).first()
            if exists:
                skipped += 1
                continue
            db.add(StudentInfo(
                id=stu.id, name=stu.name, phone=stu.phone, email=stu.email,
                education=stu.education, major=stu.major, school=stu.school,
                status="在读", create_time=NOW, update_time=NOW,
            ))
            added += 1
        db.flush()
        logger.info("  student_info: +%d, skip=%d", added, skipped)

        # ---- Department ----
        depts = [
            Department(dept_id=1, dept_name="咨询部", dept_desc="留学咨询与客户跟进", parent_dept_id=0, manager_id=101, status=1),
            Department(dept_id=2, dept_name="市场部", dept_desc="市场推广与品牌运营", parent_dept_id=0, manager_id=104, status=1),
            Department(dept_id=3, dept_name="教务部", dept_desc="教学管理与学生服务", parent_dept_id=0, manager_id=107, status=1),
            Department(dept_id=4, dept_name="行政部", dept_desc="行政与人事管理", parent_dept_id=0, manager_id=None, status=1),
            Department(dept_id=5, dept_name="财务部", dept_desc="财务与结算", parent_dept_id=0, manager_id=None, status=1),
            Department(dept_id=6, dept_name="美国咨询组", dept_desc="美国留学咨询", parent_dept_id=1, manager_id=102, status=1),
            Department(dept_id=7, dept_name="英国咨询组", dept_desc="英国留学咨询", parent_dept_id=1, manager_id=103, status=1),
        ]
        a, s = safe_add(db, Department, depts, "dept_id")
        logger.info("  department: +%d, skip=%d", a, s)

        # ---- Employee ----
        emps = [
            Employee(emp_id=101, emp_name="王建国", dept_id=1, position="咨询总监", phone="13800001001", email="wjg@edu.com", status=1),
            Employee(emp_id=102, emp_name="李明", dept_id=6, position="美国组组长", phone="13800001002", email="lm@edu.com", status=1),
            Employee(emp_id=103, emp_name="赵雪", dept_id=7, position="英国组组长", phone="13800001003", email="zx@edu.com", status=1),
            Employee(emp_id=104, emp_name="孙浩然", dept_id=2, position="市场总监", phone="13800001004", email="shr@edu.com", status=1),
            Employee(emp_id=105, emp_name="周婷", dept_id=2, position="市场专员", phone="13800001005", email="zt@edu.com", status=1),
            Employee(emp_id=106, emp_name="吴迪", dept_id=2, position="新媒体运营", phone="13800001006", email="wd@edu.com", status=1),
            Employee(emp_id=107, emp_name="郑慧", dept_id=3, position="教务总监", phone="13800001007", email="zh@edu.com", status=1),
            Employee(emp_id=108, emp_name="陈晨", dept_id=3, position="教务专员", phone="13800001008", email="cc@edu.com", status=1),
            Employee(emp_id=109, emp_name="林琳", dept_id=3, position="学生辅导员", phone="13800001009", email="ll@edu.com", status=1),
            Employee(emp_id=110, emp_name="黄磊", dept_id=4, position="行政专员", phone="13800001010", email="hl@edu.com", status=1),
            Employee(emp_id=111, emp_name="何欣", dept_id=5, position="财务专员", phone="13800001011", email="hx@edu.com", status=1),
            Employee(emp_id=112, emp_name="张伟", dept_id=1, position="资深咨询师", phone="13800001012", email="zw@edu.com", status=1),
            Employee(emp_id=113, emp_name="刘洋", dept_id=6, position="咨询师", phone="13800001013", email="ly@edu.com", status=1),
            Employee(emp_id=114, emp_name="王芳", dept_id=7, position="咨询师", phone="13800001014", email="wf@edu.com", status=1),
            Employee(emp_id=115, emp_name="杨帆", dept_id=1, position="咨询师", phone="13800001015", email="yf@edu.com", status=1),
        ]
        a, s = safe_add(db, Employee, emps, "emp_id")
        logger.info("  employee: +%d, skip=%d", a, s)

        # ---- Account (sync from employee) ----
        mgr_ids = set()
        for d in db.query(Department).filter(Department.manager_id.isnot(None)).all():
            mgr_ids.add(d.manager_id)
        a = 0
        for emp in db.query(Employee).all():
            exists = db.query(Account).filter(
                (Account.username == emp.emp_name) | (Account.phone == emp.phone)
            ).first()
            if exists:
                continue
            ut = "管理者" if emp.emp_id in mgr_ids else "员工"
            from enterprise_agent.security import hash_password
            db.add(Account(
                username=emp.emp_name, password=hash_password("123456"), real_name=emp.emp_name,
                user_type=ut, dept_id=emp.dept_id, phone=emp.phone, email=emp.email,
                status=1, create_time=NOW, update_time=NOW,
            ))
            a += 1
        db.flush()
        logger.info("  account: +%d", a)

        # ---- Customer ----
        cust_data = [
            ("张明",22,"男","13910001001","网络","咨询美国CS硕士","意向中",112),
            ("李芳",20,"女","13910001002","转介绍","英国G5本科","意向中",113),
            ("王浩",25,"男","13910001003","展会","加拿大移民留学","已签约",112),
            ("陈思",23,"女","13910001004","网络","澳洲八大硕士","意向中",115),
            ("刘阳",21,"男","13910001005","广告","新加坡NUS本科","已流失",113),
            ("赵丽",24,"女","13910001006","转介绍","香港大学商科","意向中",114),
            ("孙鹏",19,"男","13910001007","网络","美国本科转学","已签约",112),
            ("周瑶",26,"女","13910001008","线下活动","日本SGU项目","意向中",115),
            ("吴凯",22,"男","13910001009","合作机构","德国机械硕士","已签约",114),
            ("郑文",20,"女","13910001010","网络","法国高商本科","意向中",113),
            ("冯雪",27,"女","13910001011","转介绍","美国传媒博士","意向中",112),
            ("褚亮",18,"男","13910001012","展会","英国艺术预科","已流失",115),
            ("卫兰",24,"女","13910001013","网络","荷兰UVA硕士","意向中",114),
            ("蒋华",23,"男","13910001014","电话邀约","加拿大转学分","已签约",113),
            ("沈静",21,"女","13910001015","转介绍","美国建筑本科","意向中",112),
            ("韩冰",25,"男","13910001016","广告","英国G5博士","意向中",114),
            ("杨光",20,"男","13910001017","网络","美国EE硕士","已签约",115),
            ("朱云",22,"女","13910001018","转介绍","新加坡SMU硕士","意向中",113),
            ("秦月",19,"女","13910001019","线下活动","美国本科新生","意向中",112),
            ("许峰",26,"男","13910001020","合作机构","澳洲移民","已签约",113),
        ]
        follow_tpl = [
            "初步沟通了留学意向，客户对方案感兴趣",
            "电话详细介绍了服务流程和成功案例",
            "客户来访面谈，对方案表示满意",
            "微信跟进，客户表示需要和家人商量",
            "发送了详细的申请方案和时间规划表",
            "客户决定签约，已安排合同事宜",
            "签约完成，已对接教务团队开始服务",
            "定期回访，客户反馈服务体验良好",
        ]
        existing_names = set(c.customer_name for c in db.query(IntentionCustomer).all())
        a = 0
        for c in cust_data:
            if c[0] in existing_names:
                continue
            days_ago = random.randint(1, 60)
            ct = NOW - timedelta(days=days_ago)
            n_follows = random.randint(1, 4)
            ft = ""
            for j in range(n_follows):
                fd = ct + timedelta(days=j * random.randint(2, 7))
                ft += "\n【%s】%s" % (fd.strftime("%Y-%m-%d %H:%M:%S"), random.choice(follow_tpl))
            db.add(IntentionCustomer(
                customer_name=c[0], customer_age=c[1], customer_gender=c[2],
                customer_phone=c[3], customer_source=c[4], customer_demand=c[5],
                current_status=c[6], follow_record=ft.strip() or None,
                sales_user_id=c[7], create_time=ct, update_time=ct + timedelta(days=random.randint(1, 10)),
            ))
            a += 1
        db.flush()
        logger.info("  intention_customer: +%d", a)

        # ---- Leave ----
        leaves = [
            LeaveApplication(student_name="王浩", leave_type="病假", start_date=TODAY+timedelta(days=3), end_date=TODAY+timedelta(days=4), reason="感冒发烧", status=0, applicant_type="学生", applicant_id=1001),
            LeaveApplication(student_name="陈思", leave_type="事假", start_date=TODAY+timedelta(days=5), end_date=TODAY+timedelta(days=5), reason="家中急事", status=0, applicant_type="学生", applicant_id=1004),
            LeaveApplication(leave_type="年假", start_date=TODAY+timedelta(days=9), end_date=TODAY+timedelta(days=11), reason="个人休假", status=0, applicant_type="员工", applicant_id=105),
            LeaveApplication(leave_type="事假", start_date=TODAY+timedelta(days=7), end_date=TODAY+timedelta(days=7), reason="参加婚礼", status=0, applicant_type="员工", applicant_id=108),
            LeaveApplication(student_name="李芳", leave_type="病假", start_date=TODAY-timedelta(days=6), end_date=TODAY-timedelta(days=5), reason="身体不适", status=1, approval_user="王建国", applicant_type="学生", applicant_id=1002),
            LeaveApplication(leave_type="年假", start_date=TODAY-timedelta(days=3), end_date=TODAY-timedelta(days=2), reason="年假调休", status=1, approval_user="孙浩然", applicant_type="员工", applicant_id=106),
            LeaveApplication(student_name="刘阳", leave_type="事假", start_date=TODAY-timedelta(days=1), end_date=TODAY+timedelta(days=4), reason="请假过长被驳回", status=2, approval_user="李明", applicant_type="学生", applicant_id=1005),
        ]
        # Use student_name as unique key for idempotency
        a = 0
        for lv in leaves:
            q = db.query(LeaveApplication).filter(
                LeaveApplication.student_name == lv.student_name,
                LeaveApplication.leave_type == lv.leave_type,
                LeaveApplication.start_date == lv.start_date,
                LeaveApplication.applicant_id == lv.applicant_id,
            )
            if q.first():
                continue
            lv.create_time = NOW - timedelta(days=random.randint(1, 14))
            lv.update_time = lv.create_time
            db.add(lv)
            a += 1
        db.flush()
        logger.info("  leave_application: +%d", a)

        # ---- Daily Report ----
        _T = date.today()
        reports = [
            (112,1,_T-timedelta(days=1),"今日联系了3位意向客户，张明对CS项目感兴趣，已发方案。\n完成了客户跟进记录更新。"),
            (112,1,_T,"上午陪同张明面谈，介绍了申请流程。客户对哥大、UIUC感兴趣。\n下午整理客户资料，完成周总结。"),
            (113,6,_T-timedelta(days=1),"美国组跟进5组客户，2组有签约意向。\n参加部门周会，讨论下周目标。"),
            (113,6,_T,"统计本周客户转化率35%。\n新分配2组客户，完成初步沟通。"),
            (114,7,_T-timedelta(days=1),"英国组完成3组跟进。\n更新英国院校排名对比表。"),
            (114,7,_T,"跟进王芳G5申请进度，文书初稿已审阅。\n新客户赵丽对LSE感兴趣，已发资料。"),
            (105,2,_T-timedelta(days=1),"发布公众号文章2篇，阅读量1500+。\n策划下周线上讲座。"),
            (105,2,_T,"社群运营数据统计，新增粉丝120人。\n安排下周线下展会物料。"),
            (108,3,_T-timedelta(days=1),"检查学生签到，出勤率95%。\n处理了3位学生的课程调整申请。"),
            (108,3,_T,"协助王浩办理病假手续。\n更新学生成绩数据库。"),
        ]
        a = 0
        for uid, did, rd, content in reports:
            exists = db.query(EmployeeDailyReport).filter(
                EmployeeDailyReport.user_id == uid,
                EmployeeDailyReport.report_date == rd,
            ).first()
            if exists:
                continue
            db.add(EmployeeDailyReport(
                user_id=uid, dept_id=did, report_content=content,
                submit_time=datetime.combine(rd, datetime.min.time()).replace(hour=18),
                report_date=rd, create_time=NOW, update_time=NOW,
            ))
            a += 1
        db.flush()
        logger.info("  employee_daily_report: +%d", a)

        # ---- Complaint ----
        complaints = [
            (1003,"对课程安排不满意，希望调整上课时间","教务","待处理",108),
            (1001,"咨询师承诺的奖学金申请服务未兑现","服务","处理中",112),
            (1004,"缴费后发票迟迟未开具","财务","待处理",111),
            (1002,"对分配的辅导老师不满意，希望更换","教务","已完结",107),
            (1005,"宿舍空调故障，报修3天未处理","后勤","处理中",110),
        ]
        a = 0
        for sid, detail, ctype, hstatus, handler in complaints:
            exists = db.query(StudentComplaint).filter(
                StudentComplaint.student_id == sid,
                StudentComplaint.complaint_detail.like(detail[:20] + "%"),
            ).first()
            if exists:
                continue
            ct = NOW - timedelta(days=random.randint(1, 30))
            db.add(StudentComplaint(
                student_id=sid, complaint_detail=detail, complaint_type=ctype,
                handle_status=hstatus, handler_user_id=handler,
                create_time=ct, update_time=ct,
            ))
            a += 1
        db.flush()
        logger.info("  student_complaint: +%d", a)

        # ---- Score ----
        scores = [
            (1001,"雅思阅读",7.5,"模拟考",_T-timedelta(days=26),107),
            (1001,"雅思写作",6.5,"模拟考",_T-timedelta(days=26),107),
            (1002,"托福阅读",28.0,"阶段测试",_T-timedelta(days=21),108),
            (1002,"托福听力",25.0,"阶段测试",_T-timedelta(days=21),108),
            (1003,"GRE语文",152.0,"模考",_T-timedelta(days=10),107),
            (1003,"GRE数学",168.0,"模考",_T-timedelta(days=10),107),
            (1004,"雅思口语",6.0,"入学测试",_T-timedelta(days=62),108),
            (1004,"雅思听力",7.0,"入学测试",_T-timedelta(days=62),108),
            (1005,"日语N2",142.0,"期末考",_T-timedelta(days=11),109),
            (1005,"EJU数学",185.0,"期末考",_T-timedelta(days=11),109),
        ]
        a = 0
        for sid, subj, sc, etype, edate, admin in scores:
            exists = db.query(StudentScore).filter(
                StudentScore.student_id == sid,
                StudentScore.subject == subj,
            ).first()
            if exists:
                continue
            it = NOW - timedelta(days=random.randint(1, 30))
            db.add(StudentScore(
                student_id=sid, subject=subj, score=sc, exam_type=etype,
                exam_date=edate,
                admin_user_id=admin, input_time=it, create_time=it, update_time=it,
            ))
            a += 1
        db.flush()
        logger.info("  student_score: +%d", a)

        db.commit()
        logger.info("=" * 50)
        logger.info("Seed complete!")
        for name, model in [
            ("Department", Department), ("Employee", Employee),
            ("Account", Account), ("IntentionCustomer", IntentionCustomer),
            ("LeaveApplication", LeaveApplication), ("EmployeeDailyReport", EmployeeDailyReport),
            ("StudentComplaint", StudentComplaint), ("StudentScore", StudentScore),
            ("StudentInfo", StudentInfo),
        ]:
            cnt = db.query(model).count()
            logger.info("  %-25s: %d rows", name, cnt)
        logger.info("=" * 50)

    except Exception as e:
        db.rollback()
        logger.error("Seed failed: %s", e, exc_info=True)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_all()
