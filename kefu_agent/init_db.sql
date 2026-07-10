-- ============================================
-- 智能留学顾问系统 - 数据库初始化脚本
-- 数据库：dify_pro
-- ============================================

CREATE DATABASE IF NOT EXISTS dify_pro DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE dify_pro;

-- ============================================
-- 1. 用户信息表
-- ============================================
DROP TABLE IF EXISTS `user_profiles`;
CREATE TABLE `user_profiles` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(50) DEFAULT '' COMMENT '用户姓名',
    `age` INT DEFAULT NULL COMMENT '年龄',
    `education` VARCHAR(50) DEFAULT '' COMMENT '学历背景：高中/本科/硕士/博士',
    `major` VARCHAR(100) DEFAULT '' COMMENT '专业方向',
    `gpa` DECIMAL(3,2) DEFAULT NULL COMMENT 'GPA成绩',
    `target_country` VARCHAR(100) DEFAULT '' COMMENT '意向留学国家',
    `target_major` VARCHAR(100) DEFAULT '' COMMENT '意向专业',
    `budget` DECIMAL(12,2) DEFAULT NULL COMMENT '预算(元)',
    `language_level` VARCHAR(50) DEFAULT '' COMMENT '语言水平',
    `language_score` VARCHAR(50) DEFAULT '' COMMENT '语言成绩(如IELTS 6.5)',
    `phone` VARCHAR(20) DEFAULT '' COMMENT '手机号',
    `wechat` VARCHAR(50) DEFAULT '' COMMENT '微信号',
    `contact_method` VARCHAR(20) DEFAULT '' COMMENT '首选联系方式：phone/wechat',
    `consultation_status` VARCHAR(20) DEFAULT 'pending' COMMENT '咨询状态：pending/contacted/following_up/closed',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户信息表';

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
    `price` DECIMAL(12,2) DEFAULT 0.00 COMMENT '课程价格(元)',
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
    `user_id` INT DEFAULT NULL COMMENT '用户ID',
    `course_id` INT DEFAULT NULL COMMENT '推荐课程ID',
    `conversation_summary` TEXT COMMENT '对话摘要',
    `recommended_courses` TEXT COMMENT '推荐的课程列表(JSON)',
    `user_feedback` VARCHAR(255) DEFAULT '' COMMENT '用户反馈',
    `status` VARCHAR(20) DEFAULT 'new' COMMENT '状态：new/recommended/interested/not_interested/consulting',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='咨询记录表';

-- ============================================
-- 插入示例课程数据（仅德国和新加坡）
-- ============================================

-- 语言课程（德国和新加坡相关）
INSERT INTO `courses` (`course_name`, `category`, `sub_category`, `country`, `target_education`, `min_gpa`, `min_budget`, `max_budget`, `language_requirement`, `duration`, `price`, `description`, `highlights`) VALUES
('德语零基础到A2班', '语言课程', '德语', '德国', '高中/本科/硕士', 0.00, 5000, 50000, '无', '3个月', 6800.00, '从零基础系统学习德语，达到A2水平，掌握日常交流能力', '德籍外教,小班教学,文化体验,免费试听'),
('德语B1进阶班', '语言课程', '德语', '德国', '本科/硕士', 0.00, 10000, 80000, '德语A2基础', '3个月', 8800.00, '在A2基础上提升至B1，强化听说读写，开始接触专业德语', '外教口语,德国文化,真题训练,学习督导'),
('德语B2强化班', '语言课程', '德语', '德国', '本科/硕士', 0.00, 10000, 80000, '德语B1基础', '4个月', 12800.00, '零基础到B2一站式，满足德国大学语言入学要求', '德籍外教,TestDaF备考,留学语言衔接,小班授课'),
('TestDaF备考冲刺班', '语言课程', 'TestDaF', '德国', '本科/硕士', 0.00, 15000, 100000, '德语B2基础', '2个月', 9800.00, '针对TestDaF考试专项训练，目标4x4，满足德国大学入学要求', '真题精讲,全真模考,写作批改,口语对练'),
('DSH考试辅导班', '语言课程', 'DSH', '德国', '本科/硕士', 0.00, 15000, 100000, '德语B2基础', '2个月', 8800.00, 'DSH考试专项辅导，涵盖听力阅读写作口语，目标DSH-2', 'DSH真题,模拟考试,一对一辅导,考点预测'),
('英语授课德语入门班', '语言课程', '德语', '德国', '本科/硕士', 0.00, 5000, 30000, '无', '2个月', 4800.00, '针对选择英语授课项目的学生，学习基础德语方便日常生活', '生活德语,场景教学,文化融入,灵活课时'),
('IELTS 6.5分直达班', '语言课程', 'IELTS', '德国/新加坡', '高中/本科/硕士', 0.00, 8000, 60000, '无', '3个月', 8800.00, '系统备考雅思，听说读写全面提升，目标6.5分', '小班教学,全真模考,口语陪练,写作批改'),
('IELTS 7.0分冲刺班', '语言课程', 'IELTS', '德国/新加坡', '本科/硕士', 0.00, 20000, 150000, 'IELTS 6.0+', '2个月', 12800.00, '针对冲刺高分学员，精讲技巧与高频考点，目标7.0+', '名师授课,一对一辅导,考前预测,保分承诺'),
('TOEFL 90分突破班', '语言课程', 'TOEFL', '德国/新加坡', '本科/硕士', 0.00, 10000, 80000, '无', '3个月', 9800.00, '从基础到突破，覆盖托福听说读写，目标90+', 'TPO真题,口语对练,写作精批,模考评估'),
('新加坡英语学术写作班', '语言课程', '学术英语', '新加坡', '本科/硕士', 0.00, 8000, 50000, 'IELTS 6.0+/TOEFL 80+', '2个月', 6800.00, '针对新加坡大学学术写作要求，提升论文写作与学术表达能力', '学术写作规范,论文结构,引用格式,答辩技巧');

-- 背景提升课程（德国和新加坡相关）
INSERT INTO `courses` (`course_name`, `category`, `sub_category`, `country`, `target_education`, `min_gpa`, `min_budget`, `max_budget`, `language_requirement`, `duration`, `price`, `description`, `highlights`) VALUES
('德国TU9科研实习项目', '背景提升', '科研项目', '德国', '本科', 3.00, 50000, 300000, '德语B1+/英语良好', '4-8周', 48000.00, '进入德国TU9理工联盟高校实验室参与科研项目，获得教授推荐信', 'TU9名校,教授推荐信,科研经历,实验室实习'),
('德国名企实习计划', '背景提升', '实习', '德国', '本科/硕士', 2.80, 30000, 200000, '德语B1+/英语良好', '4-12周', 35000.00, '进入西门子、大众、宝马等德国名企远程或实地实习', '德企实习证明,导师推荐信,行业人脉,德语实战'),
('新加坡国立科研项目', '背景提升', '科研项目', '新加坡', '本科', 3.00, 50000, 300000, 'IELTS 6.5+/TOEFL 90+', '4-8周', 52000.00, '与NUS/NTU教授合作科研课题，产出论文并获推荐信', 'NUS/NTU教授,论文发表,科研经历,推荐信'),
('新加坡金融科技实习', '背景提升', '实习', '新加坡', '本科/硕士', 2.80, 30000, 250000, 'IELTS 6.0+/TOEFL 80+', '4-12周', 38000.00, '进入新加坡金融机构或科技公司实习，积累国际工作经验', '名企实习,行业导师,真实项目,留新机会'),
('学术论文辅导发表', '背景提升', '论文', '德国/新加坡', '本科/硕士', 3.00, 20000, 150000, '无硬性要求', '3-6个月', 25000.00, '一对一学术导师辅导，完成高质量论文并投稿国际期刊', '一对一导师,选题指导,投稿支持,SCI/EI/核心期刊'),
('国际竞赛辅导', '背景提升', '竞赛', '德国/新加坡', '高中/本科', 3.00, 20000, 100000, '无硬性要求', '2-4个月', 15000.00, '针对数学建模、工程竞赛、商赛等国际竞赛的系统辅导', '金牌导师,历年真题,模拟训练,获奖保障'),
('德国大学预科桥梁项目', '背景提升', '预科', '德国', '高中', 2.50, 50000, 200000, '德语A2+', '6-12个月', 38000.00, '德国公立预科准备课程，衔接德国本科申请，含APS辅导', 'APS辅导,预科衔接,大学申请,签证指导');

-- 留学方案（德国和新加坡）
INSERT INTO `courses` (`course_name`, `category`, `sub_category`, `country`, `target_education`, `min_gpa`, `min_budget`, `max_budget`, `language_requirement`, `duration`, `price`, `description`, `highlights`) VALUES
('德国TU9名校申请', '留学方案', '德国', '德国', '本科/硕士', 2.80, 80000, 250000, '德语B2+/TestDaF 4/英语可替代', '12-18个月', 35000.00, '德国顶尖理工科大学（TU9）申请全流程服务，含APS审核辅导', 'APS辅导,德语培训,院校匹配,签证办理'),
('德国精英大学申请方案', '留学方案', '德国', '德国', '本科/硕士', 3.00, 100000, 300000, '德语C1/TestDaF 4+/IELTS 6.5+', '12-18个月', 45000.00, '针对海德堡、慕尼黑工大等德国精英大学的全套高端申请服务', '精英大学资源,个性化文书,面试辅导,奖学金申请'),
('德国公立大学免学费方案', '留学方案', '德国', '德国', '本科/硕士', 2.50, 50000, 150000, '德语B2+/TestDaF 4', '8-12个月', 25000.00, '聚焦德国公立大学（免学费）申请，高性价比留学方案', '公立大学,免学费,低成本,APS一站式'),
('德国艺术音乐学院申请', '留学方案', '德国', '德国', '本科/硕士', 0.00, 80000, 250000, '德语B1+', '12-18个月', 42000.00, '德国公立艺术/音乐学院申请，含作品集辅导与面试培训', '作品集指导,面试培训, audition准备,院校推荐'),
('德国博士申请全程辅导', '留学方案', '德国', '德国', '硕士', 3.30, 100000, 400000, '英语良好/德语加分', '12-24个月', 48000.00, '德国博士/博后申请全程辅导，含导师套磁与研究计划书', '导师套磁,RP辅导,职位制博士,奖学金申请'),
('新加坡国立大学申请', '留学方案', '新加坡', '新加坡', '本科/硕士', 3.30, 150000, 400000, 'IELTS 6.5+/TOEFL 90+', '12-18个月', 42000.00, 'NUS新加坡国立大学全套申请服务，含文书、面试辅导', 'NUS名校资源,文书精修,面试模拟,奖学金申请'),
('新加坡南洋理工申请', '留学方案', '新加坡', '新加坡', '本科/硕士', 3.20, 150000, 400000, 'IELTS 6.5+/TOEFL 90+', '12-18个月', 38000.00, 'NTU南洋理工大学申请全流程服务，理工科优势明显', 'NTU资源,专业选校,科研匹配,签证服务'),
('新加坡名校双申方案', '留学方案', '新加坡', '新加坡', '本科/硕士', 3.00, 120000, 350000, 'IELTS 6.0+/TOEFL 85+', '8-12个月', 32000.00, 'NUS+NTU+SMU联合申请方案，提高录取概率', '多校联申,高录取率,费用优化,落地服务'),
('新加坡低龄留学方案', '留学方案', '新加坡', '新加坡', '高中', 2.50, 80000, 300000, '无硬性要求', '6-12个月', 28000.00, '新加坡中小学/国际学校申请，含陪读签证办理', '学校匹配,AEIS备考,陪读签证,寄宿安排'),
('德国新加坡双国联申', '留学方案', '德国/新加坡', '德国/新加坡', '本科/硕士', 3.00, 150000, 500000, 'IELTS 6.5+/德语加分', '12-18个月', 48000.00, '德国+新加坡双国联合申请，最大化留学选择，降低风险', '双国联申,方案对比,灵活选择,一站式服务');

-- ============================================
-- 插入测试用户数据
-- ============================================
INSERT INTO `user_profiles` (`name`, `age`, `education`, `major`, `gpa`, `target_country`, `target_major`, `budget`, `language_level`, `language_score`, `consultation_status`) VALUES
('测试用户A', 22, '本科', '机械工程', 3.50, '德国', '车辆工程', 200000.00, '良好', 'TestDaF 4', 'pending'),
('测试用户B', 20, '本科', '计算机科学', 2.80, '新加坡', '人工智能', 300000.00, '一般', 'IELTS 5.5', 'contacted'),
('测试用户C', 18, '高中', '理科', 3.80, '德国', '电气工程', 250000.00, '良好', '德语B1', 'following_up');
