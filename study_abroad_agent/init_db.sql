-- ============================================
-- 智能留学顾问系统 - 数据库初始化脚本
-- 数据库：dify_pro
-- ============================================

# CREATE DATABASE IF NOT EXISTS dify_pro DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE dify_pro;

-- ============================================
-- 1. 用户信息表
-- ============================================
DROP TABLE IF EXISTS `user_profiles`;
CREATE TABLE user_profiles (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    conversation_id VARCHAR(100) NOT NULL DEFAULT '0' COMMENT 'Dify会话ID',
    name VARCHAR(50) DEFAULT NULL COMMENT '姓名',
    `age` INT DEFAULT NULL COMMENT '年龄',
    major VARCHAR(100) DEFAULT NULL COMMENT '专业',
    education VARCHAR(50) DEFAULT NULL COMMENT '学历（必填）',
    target_major VARCHAR(100) DEFAULT NULL COMMENT '意向专业（必填）',
    language_score VARCHAR(50) DEFAULT NULL COMMENT '语言成绩（必填）',
    target_country VARCHAR(50) DEFAULT NULL COMMENT '目标国家',
    gpa DECIMAL(3,2) DEFAULT NULL COMMENT 'GPA',
    budget INT DEFAULT NULL COMMENT '预算（人民币）',
    phone VARCHAR(30) DEFAULT NULL COMMENT '手机号',
    wechat VARCHAR(50) DEFAULT NULL COMMENT '微信',
    email VARCHAR(100) DEFAULT NULL COMMENT '邮箱',
    consultation_status ENUM(
        'collecting',
        'recommended',
        'finished'
    ) DEFAULT 'collecting',
    assess VARCHAR(100) DEFAULT NULL COMMENT '是否研判',
    development VARCHAR(100) DEFAULT NULL COMMENT '发展需求',
    abilities VARCHAR(100) DEFAULT NULL COMMENT '综合能力',
    `is_Closed-loop` VARCHAR(100) DEFAULT NULL COMMENT '是否接受封闭式实训',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='潜在用户信息表';


-- ============================================
-- 2. 课程表
-- ============================================
DROP TABLE IF EXISTS `courses`;
CREATE TABLE `courses` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `course_name` VARCHAR(200) NOT NULL COMMENT '课程名称',
    `category` VARCHAR(50) NOT NULL COMMENT '课程类别：留学方案/语言课程/背景提升',
    `sub_category` VARCHAR(50) DEFAULT '' COMMENT '子类别',
    `country` VARCHAR(100) DEFAULT '' COMMENT '目标国家',
    `target_education` VARCHAR(50) DEFAULT '' COMMENT '适用学历',
    `min_gpa` DECIMAL(3,2) DEFAULT 0.00 COMMENT '最低GPA要求',
    `max_budget` DECIMAL(12,2) DEFAULT NULL COMMENT '最高预算',
    `min_budget` DECIMAL(12,2) DEFAULT NULL COMMENT '最低预算',
    `language_requirement` VARCHAR(50) DEFAULT '' COMMENT '语言要求',
    `duration` VARCHAR(50) DEFAULT '' COMMENT '课程时长',
    `tuition_fee` DECIMAL(12,2) DEFAULT 0.00 COMMENT '课程价格(元)',
    `description` TEXT COMMENT '课程描述',
    `highlights` TEXT COMMENT '课程亮点',
    `is_active` TINYINT(1) DEFAULT 1 COMMENT '是否上架',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='课程表';

-- ============================================
-- 3. 咨询记录表
-- ============================================
DROP TABLE IF EXISTS `consultations`;
CREATE TABLE `consultations` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` BIGINT DEFAULT NULL COMMENT '用户ID',
    `course_id` INT DEFAULT NULL COMMENT '推荐课程ID',
    `conversation_summary` TEXT COMMENT '对话摘要',
    `recommended_courses` TEXT COMMENT '推荐的课程列表(JSON)',
    `user_feedback` VARCHAR(255) DEFAULT '' COMMENT '用户反馈',
    `status` VARCHAR(20) DEFAULT 'new' COMMENT '状态：new/recommended/interested/not_interested/consulting',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='咨询记录表';



DROP TABLE IF EXISTS `lecture_registrations`;
CREATE TABLE `lecture_registrations` (
  `registration_id` int NOT NULL AUTO_INCREMENT,
  `lecture_id` int DEFAULT NULL COMMENT '关联讲座ID',
  `name` varchar(50) NOT NULL COMMENT '报名人姓名',
  `phone` varchar(20) NOT NULL COMMENT '手机号码',
  PRIMARY KEY (`registration_id`),
  UNIQUE KEY `uk_lecture_reg` (`lecture_id`,`name`,`phone`)
) ENGINE=InnoDB AUTO_INCREMENT=23 DEFAULT CHARSET=utf8mb4 COMMENT='讲座报名表';
;



DROP TABLE IF EXISTS `lectures`;
CREATE TABLE `lectures` (
  `lecture_id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL COMMENT '讲座主题',
  `event_time` datetime DEFAULT NULL COMMENT '讲座时间',
  `location` varchar(255) DEFAULT NULL COMMENT '地点',
  `registration_method` varchar(100) DEFAULT NULL COMMENT '报名方式',
  `speaker` varchar(100) DEFAULT NULL COMMENT '主讲人',
  PRIMARY KEY (`lecture_id`),
  UNIQUE KEY `uk_lectures` (`title`,`event_time`)
) ENGINE=InnoDB AUTO_INCREMENT=20 DEFAULT CHARSET=utf8mb4 COMMENT='讲座计划表';

DROP TABLE IF EXISTS `activities`;
CREATE TABLE `activities` (
  `activity_id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL COMMENT '活动主题',
  `event_time` datetime DEFAULT NULL COMMENT '活动时间',
  `location` varchar(255) DEFAULT NULL COMMENT '活动地点',
  `registration_method` varchar(100) DEFAULT NULL COMMENT '报名方式',
  PRIMARY KEY (`activity_id`),
  UNIQUE KEY `uk_activities` (`title`,`event_time`)
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COMMENT='活动计划表';

DROP TABLE IF EXISTS `activity_registrations`;
CREATE TABLE `activity_registrations` (
  `registration_id` int NOT NULL AUTO_INCREMENT,
  `activity_id` int DEFAULT NULL COMMENT '关联活动ID',
  `name` varchar(50) NOT NULL COMMENT '报名人姓名',
  `phone` varchar(20) NOT NULL COMMENT '手机号码',
  PRIMARY KEY (`registration_id`),
  UNIQUE KEY `uk_activity_reg` (`activity_id`,`name`,`phone`),
) ENGINE=InnoDB AUTO_INCREMENT=17 DEFAULT CHARSET=utf8mb4 COMMENT='活动报名表';

DROP TABLE IF EXISTS `intention_diagnosis`;
CREATE TABLE `intention_diagnosis` (
  `diag_id` int NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `project_id` int NOT NULL,
  `score` int NOT NULL DEFAULT '0',
  `rule_details` text,
  `diag_time` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`diag_id`),
  UNIQUE KEY `uk_user_project` (`user_id`,`project_id`),
  KEY `idx_user` (`user_id`),
  KEY `idx_project` (`project_id`)
) ENGINE=InnoDB AUTO_INCREMENT=16 DEFAULT CHARSET=utf8mb4  COMMENT='意向诊断结果表'
;

DROP TABLE IF EXISTS `portrait_rule`;
CREATE TABLE `portrait_rule` (
  `rule_id` int NOT NULL AUTO_INCREMENT COMMENT '规则ID',
  `project_id` int NOT NULL COMMENT '关联项目ID',
  `rule_category` varchar(50) NOT NULL COMMENT '规则大类',
  `rule_subcategory` varchar(50) NOT NULL COMMENT '规则子类',
  `rule_key` varchar(100) NOT NULL COMMENT '规则维度',
  `rule_value` text NOT NULL COMMENT '规则说明',
  `score_max` int NOT NULL DEFAULT '0' COMMENT '该项满分',
  `score_desc` text COMMENT '打分标准',
  `match_condition` varchar(200) DEFAULT NULL COMMENT '匹配条件',
  `sort_order` int DEFAULT '10' COMMENT '排序',
  `is_active` tinyint DEFAULT '1' COMMENT '是否启用',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`rule_id`),
  KEY `idx_project_id` (`project_id`)
) ENGINE=InnoDB AUTO_INCREMENT=17 DEFAULT CHARSET=utf8mb4 COMMENT='用户画像研判+打分规则表'


DROP TABLE IF EXISTS `study_project`;
CREATE TABLE `study_project` (
  `project_id` int NOT NULL AUTO_INCREMENT COMMENT '项目ID',
  `project_code` varchar(50) NOT NULL COMMENT '项目编码',
  `project_name` varchar(100) NOT NULL COMMENT '项目名称',
  `country` varchar(50) NOT NULL COMMENT '目标国家',
  `project_type` varchar(50) NOT NULL COMMENT '项目类型',
  `description` text COMMENT '项目说明',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`project_id`),
  UNIQUE KEY `uk_project_code` (`project_code`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COMMENT='留学项目基础表'


-- ============================================
-- 插入示例课程数据（仅德国和新加坡）
-- ============================================

---- 语言课程（德国和新加坡相关）
--INSERT INTO `courses` (`course_name`, `category`, `sub_category`, `country`, `target_education`, `min_gpa`, `min_budget`, `max_budget`, `language_requirement`, `duration`, `price`, `description`, `highlights`) VALUES
--('德语零基础到A2班', '语言课程', '德语', '德国', '高中/本科/硕士', 0.00, 5000, 50000, '无', '3个月', 6800.00, '从零基础系统学习德语，达到A2水平，掌握日常交流能力', '德籍外教,小班教学,文化体验,免费试听'),
--('德语B1进阶班', '语言课程', '德语', '德国', '本科/硕士', 0.00, 10000, 80000, '德语A2基础', '3个月', 8800.00, '在A2基础上提升至B1，强化听说读写，开始接触专业德语', '外教口语,德国文化,真题训练,学习督导'),
--('德语B2强化班', '语言课程', '德语', '德国', '本科/硕士', 0.00, 10000, 80000, '德语B1基础', '4个月', 12800.00, '零基础到B2一站式，满足德国大学语言入学要求', '德籍外教,TestDaF备考,留学语言衔接,小班授课'),
--('TestDaF备考冲刺班', '语言课程', 'TestDaF', '德国', '本科/硕士', 0.00, 15000, 100000, '德语B2基础', '2个月', 9800.00, '针对TestDaF考试专项训练，目标4x4，满足德国大学入学要求', '真题精讲,全真模考,写作批改,口语对练'),
--('DSH考试辅导班', '语言课程', 'DSH', '德国', '本科/硕士', 0.00, 15000, 100000, '德语B2基础', '2个月', 8800.00, 'DSH考试专项辅导，涵盖听力阅读写作口语，目标DSH-2', 'DSH真题,模拟考试,一对一辅导,考点预测'),
--('英语授课德语入门班', '语言课程', '德语', '德国', '本科/硕士', 0.00, 5000, 30000, '无', '2个月', 4800.00, '针对选择英语授课项目的学生，学习基础德语方便日常生活', '生活德语,场景教学,文化融入,灵活课时'),
--('IELTS 6.5分直达班', '语言课程', 'IELTS', '德国/新加坡', '高中/本科/硕士', 0.00, 8000, 60000, '无', '3个月', 8800.00, '系统备考雅思，听说读写全面提升，目标6.5分', '小班教学,全真模考,口语陪练,写作批改'),
--('IELTS 7.0分冲刺班', '语言课程', 'IELTS', '德国/新加坡', '本科/硕士', 0.00, 20000, 150000, 'IELTS 6.0+', '2个月', 12800.00, '针对冲刺高分学员，精讲技巧与高频考点，目标7.0+', '名师授课,一对一辅导,考前预测,保分承诺'),
--('TOEFL 90分突破班', '语言课程', 'TOEFL', '德国/新加坡', '本科/硕士', 0.00, 10000, 80000, '无', '3个月', 9800.00, '从基础到突破，覆盖托福听说读写，目标90+', 'TPO真题,口语对练,写作精批,模考评估'),
--('新加坡英语学术写作班', '语言课程', '学术英语', '新加坡', '本科/硕士', 0.00, 8000, 50000, 'IELTS 6.0+/TOEFL 80+', '2个月', 6800.00, '针对新加坡大学学术写作要求，提升论文写作与学术表达能力', '学术写作规范,论文结构,引用格式,答辩技巧');
--
---- 背景提升课程（德国和新加坡相关）
--INSERT INTO `courses` (`course_name`, `category`, `sub_category`, `country`, `target_education`, `min_gpa`, `min_budget`, `max_budget`, `language_requirement`, `duration`, `price`, `description`, `highlights`) VALUES
--('德国TU9科研实习项目', '背景提升', '科研项目', '德国', '本科', 3.00, 50000, 300000, '德语B1+/英语良好', '4-8周', 48000.00, '进入德国TU9理工联盟高校实验室参与科研项目，获得教授推荐信', 'TU9名校,教授推荐信,科研经历,实验室实习'),
--('德国名企实习计划', '背景提升', '实习', '德国', '本科/硕士', 2.80, 30000, 200000, '德语B1+/英语良好', '4-12周', 35000.00, '进入西门子、大众、宝马等德国名企远程或实地实习', '德企实习证明,导师推荐信,行业人脉,德语实战'),
--('新加坡国立科研项目', '背景提升', '科研项目', '新加坡', '本科', 3.00, 50000, 300000, 'IELTS 6.5+/TOEFL 90+', '4-8周', 52000.00, '与NUS/NTU教授合作科研课题，产出论文并获推荐信', 'NUS/NTU教授,论文发表,科研经历,推荐信'),
--('新加坡金融科技实习', '背景提升', '实习', '新加坡', '本科/硕士', 2.80, 30000, 250000, 'IELTS 6.0+/TOEFL 80+', '4-12周', 38000.00, '进入新加坡金融机构或科技公司实习，积累国际工作经验', '名企实习,行业导师,真实项目,留新机会'),
--('学术论文辅导发表', '背景提升', '论文', '德国/新加坡', '本科/硕士', 3.00, 20000, 150000, '无硬性要求', '3-6个月', 25000.00, '一对一学术导师辅导，完成高质量论文并投稿国际期刊', '一对一导师,选题指导,投稿支持,SCI/EI/核心期刊'),
--('国际竞赛辅导', '背景提升', '竞赛', '德国/新加坡', '高中/本科', 3.00, 20000, 100000, '无硬性要求', '2-4个月', 15000.00, '针对数学建模、工程竞赛、商赛等国际竞赛的系统辅导', '金牌导师,历年真题,模拟训练,获奖保障'),
--('德国大学预科桥梁项目', '背景提升', '预科', '德国', '高中', 2.50, 50000, 200000, '德语A2+', '6-12个月', 38000.00, '德国公立预科准备课程，衔接德国本科申请，含APS辅导', 'APS辅导,预科衔接,大学申请,签证指导');
--
---- 留学方案（德国和新加坡）
--INSERT INTO `courses` (`course_name`, `category`, `sub_category`, `country`, `target_education`, `min_gpa`, `min_budget`, `max_budget`, `language_requirement`, `duration`, `price`, `description`, `highlights`) VALUES
--('德国TU9名校申请', '留学方案', '德国', '德国', '本科/硕士', 2.80, 80000, 250000, '德语B2+/TestDaF 4/英语可替代', '12-18个月', 35000.00, '德国顶尖理工科大学（TU9）申请全流程服务，含APS审核辅导', 'APS辅导,德语培训,院校匹配,签证办理'),
--('德国精英大学申请方案', '留学方案', '德国', '德国', '本科/硕士', 3.00, 100000, 300000, '德语C1/TestDaF 4+/IELTS 6.5+', '12-18个月', 45000.00, '针对海德堡、慕尼黑工大等德国精英大学的全套高端申请服务', '精英大学资源,个性化文书,面试辅导,奖学金申请'),
--('德国公立大学免学费方案', '留学方案', '德国', '德国', '本科/硕士', 2.50, 50000, 150000, '德语B2+/TestDaF 4', '8-12个月', 25000.00, '聚焦德国公立大学（免学费）申请，高性价比留学方案', '公立大学,免学费,低成本,APS一站式'),
--('德国艺术音乐学院申请', '留学方案', '德国', '德国', '本科/硕士', 0.00, 80000, 250000, '德语B1+', '12-18个月', 42000.00, '德国公立艺术/音乐学院申请，含作品集辅导与面试培训', '作品集指导,面试培训, audition准备,院校推荐'),
--('德国博士申请全程辅导', '留学方案', '德国', '德国', '硕士', 3.30, 100000, 400000, '英语良好/德语加分', '12-24个月', 48000.00, '德国博士/博后申请全程辅导，含导师套磁与研究计划书', '导师套磁,RP辅导,职位制博士,奖学金申请'),
--('新加坡国立大学申请', '留学方案', '新加坡', '新加坡', '本科/硕士', 3.30, 150000, 400000, 'IELTS 6.5+/TOEFL 90+', '12-18个月', 42000.00, 'NUS新加坡国立大学全套申请服务，含文书、面试辅导', 'NUS名校资源,文书精修,面试模拟,奖学金申请'),
--('新加坡南洋理工申请', '留学方案', '新加坡', '新加坡', '本科/硕士', 3.20, 150000, 400000, 'IELTS 6.5+/TOEFL 90+', '12-18个月', 38000.00, 'NTU南洋理工大学申请全流程服务，理工科优势明显', 'NTU资源,专业选校,科研匹配,签证服务'),
--('新加坡名校双申方案', '留学方案', '新加坡', '新加坡', '本科/硕士', 3.00, 120000, 350000, 'IELTS 6.0+/TOEFL 85+', '8-12个月', 32000.00, 'NUS+NTU+SMU联合申请方案，提高录取概率', '多校联申,高录取率,费用优化,落地服务'),
--('新加坡低龄留学方案', '留学方案', '新加坡', '新加坡', '高中', 2.50, 80000, 300000, '无硬性要求', '6-12个月', 28000.00, '新加坡中小学/国际学校申请，含陪读签证办理', '学校匹配,AEIS备考,陪读签证,寄宿安排'),
--('德国新加坡双国联申', '留学方案', '德国/新加坡', '德国/新加坡', '本科/硕士', 3.00, 150000, 500000, 'IELTS 6.5+/德语加分', '12-18个月', 48000.00, '德国+新加坡双国联合申请，最大化留学选择，降低风险', '双国联申,方案对比,灵活选择,一站式服务');
--
---- ============================================
---- 插入测试用户数据
---- ============================================
--INSERT INTO `user_profiles` (conversation_id,`name`, `age`, major,education,target_major,language_score ,target_country,`gpa`, `budget`,phone, wechat, email, `consultation_status`) VALUES
--(1,'测试用户A', 22, '车辆工程','本科','车辆工程','TestDaF 4','德国', 3.50, 200000.00, 13060642199 ,13060642199 ,null, 'collecting'),
--(2,'测试用户B', 20, '车辆工程','本科', '人工智能', 'IELTS 5.5','新加坡',2.80,   300000.00,  13060642198, 13060642198,null,  'collecting'),
--(3,'测试用户C', 18, '车辆工程','高中','电气工程','德语B1', '德国',3.80,  250000.00,  13060642197 , 13060642197 ,null, 'finished');


-- 示例1：德国留学，已完成信息收集
INSERT INTO user_profiles (conversation_id, name, age, major, education, target_major, language_score, target_country, gpa, budget, phone, wechat, email, consultation_status, assess, development, abilities, `is_Closed-loop`)
VALUES ('conv_001', '张三', 22, '车辆工程', '本科', '机械工程', 'TestDaF 4', '德国', 3.50, 200000, '13800138001', 'zhangsan_wx', 'zhangsan@qq.com', 'collecting', '已研判', '科研能力提升', '逻辑思维强', '是');

-- 示例2：新加坡留学，已推荐课程
INSERT INTO user_profiles (conversation_id, name, age, major, education, target_major, language_score, target_country, gpa, budget, phone, wechat, email, consultation_status, assess, development, abilities, `is_Closed-loop`)
VALUES ('conv_002', '李四', 20, '计算机科学', '本科', '人工智能', 'IELTS 5.5', '新加坡', 2.80, 300000, '13800138002', 'lisi_wx', 'lisi@gmail.com', 'recommended', NULL, '语言能力提升', '编程能力强', '否');

-- 示例3：已完成咨询
INSERT INTO user_profiles (conversation_id, name, age, major, education, target_major, language_score, target_country, gpa, budget, phone, wechat, email, consultation_status, assess, development, abilities, `is_Closed-loop`)
VALUES ('conv_003', '王五', 18, '理科', '高中', '电气工程', '德语B1', '德国', 3.80, 250000, '13800138003', 'wangwu_wx', 'wangwu@163.com', 'finished', '已研判', '预科衔接', '数学优秀', '是');

--##courses
-- 示例1：语言课程 - 德语
INSERT INTO courses (course_name, category, sub_category, country, target_education, min_gpa, max_budget, min_budget, language_requirement, duration, price, description, highlights, is_active)
VALUES ('德语零基础到A2班', '语言课程', '德语', '德国', '高中/本科/硕士', 0.00, 50000, 5000, '无', '3个月', 6800.00, '从零基础系统学习德语，达到A2水平', '德籍外教,小班教学', 1);

-- 示例2：背景提升 - 科研项目
INSERT INTO courses (course_name, category, sub_category, country, target_education, min_gpa, max_budget, min_budget, language_requirement, duration, price, description, highlights, is_active)
VALUES ('德国TU9科研实习项目', '背景提升', '科研项目', '德国', '本科', 3.00, 300000, 50000, '德语B1+/英语良好', '4-8周', 48000.00, '进入德国TU9理工联盟高校实验室参与科研项目', 'TU9名校,教授推荐信', 1);

-- 示例3：留学方案
INSERT INTO courses (course_name, category, sub_category, country, target_education, min_gpa, max_budget, min_budget, language_requirement, duration, price, description, highlights, is_active)
VALUES ('新加坡国立大学申请', '留学方案', '新加坡', '新加坡', '本科/硕士', 3.30, 400000, 150000, 'IELTS 6.5+/TOEFL 90+', '12-18个月', 42000.00, 'NUS新加坡国立大学全套申请服务', 'NUS名校资源,文书精修', 1);


-- consultations
-- 示例1：新咨询，尚未推荐
INSERT INTO consultations (user_id, course_id, conversation_summary, recommended_courses, user_feedback, status)
VALUES (1, NULL, '{"rounds":[{"role":"user","msg":"想去德国读机械"},{"role":"assistant","msg":"推荐TU9方案"}]}', NULL, '', 'new');

-- 示例2：已推荐课程
INSERT INTO consultations (user_id, course_id, conversation_summary, recommended_courses, user_feedback, status)
VALUES (2, 4, '{"rounds":[{"role":"user","msg":"想去新加坡学AI"}]}', '[4, 15, 17]', '对科研项目很感兴趣', 'recommended');

-- 示例3：用户表示感兴趣
INSERT INTO consultations (user_id, course_id, conversation_summary, recommended_courses, user_feedback, status)
VALUES (3, 1, '{"rounds":[{"role":"user","msg":"高中生想去德国读电气"}]}', '[1, 19]', '想先学德语', 'interested');

--lectures
INSERT INTO lectures (title, event_time, location, registration_method, speaker)
VALUES
('德国TU9名校申请攻略', '2026-08-15 14:00:00', '线上腾讯会议', '扫码报名', 'Dr. Müller'),
('新加坡留学新政解读', '2026-08-20 19:00:00', '上海浦东校区', '微信预约', '陈老师'),
('TestDaF备考经验分享', '2026-09-01 15:00:00', '线上Zoom', '扫码报名', '王学长');


INSERT INTO lecture_registrations (lecture_id, name, phone)
VALUES
(1, '张三', '13800138001'),
(1, '李四', '13800138002'),
(2, '王五', '13800138003');


INSERT INTO activities (title, event_time, location, registration_method)
VALUES
('留学德国线下答疑会', '2026-08-25 10:00:00', '北京朝阳校区', '电话预约'),
('新加坡名校招生官见面会', '2026-09-10 14:00:00', '线上直播', '微信报名');


INSERT INTO intention_diagnosis (user_id, project_id, score, rule_details)
VALUES
(1, 1, 85, '{"gpa_score":25,"language_score":20,"budget_match":15,"background":25}'),
(2, 2, 62, '{"gpa_score":15,"language_score":12,"budget_match":20,"background":15}');


INSERT INTO portrait_rule (project_id, rule_category, rule_subcategory, rule_key, rule_value, score_max, score_desc, match_condition, sort_order, is_active)
VALUES
(1, '学术能力', 'GPA', 'gpa_3.5_plus', 'GPA ≥ 3.5/4.0', 30, 'GPA越高分数越高，3.5以上满分', 'user.gpa >= 3.5', 1, 1),
(1, '语言能力', '德语', 'testdaf_4', 'TestDaF 4x4', 25, 'TestDaF达到4x4得满分', 'user.language_score LIKE "%TestDaF 4%"', 2, 1),
(1, '经济能力', '预算', 'budget_200k', '预算 ≥ 20万', 20, '预算满足最低要求得满分', 'user.budget >= 200000', 3, 1);


INSERT INTO study_project (project_code, project_name, country, project_type, description)
VALUES
('DE-TU9-001', '德国TU9精英硕士项目', '德国', '硕士申请', '面向德国TU9理工联盟的硕士申请项目'),
('SG-NUS-001', '新加坡国立大学本科项目', '新加坡', '本科申请', '面向NUS的本科申请全流程服务');
