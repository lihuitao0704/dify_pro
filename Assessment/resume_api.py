"""
学生信息录入 - FastAPI 接口 + 前端页面
路由前缀：/api/agent

流程：表单提交 / 简历上传 → 写入 user_profiles → 触发研判 → 返回研判结论
"""
import os
import sys
import json
import traceback
import pymysql
from pymysql.cursors import DictCursor
from fastapi import APIRouter, FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse

# 兼容两种运行方式：
#   python resume_api.py          → 相对导入
#   python -m Assessment.resume_api → 绝对导入
try:
    from resume import ResumeRequest
    from Assessment.assessment import run_targeted_assessment
except ImportError:
    from Assessment.resume import ResumeRequest
    from Assessment.assessment import run_targeted_assessment

router = APIRouter()
app = FastAPI(title="学生信息录入 API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api/agent")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "192.168.48.121"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "offer"),
    "password": os.getenv("DB_PASSWORD", "123456"),
    "database": os.getenv("DB_NAME", "dify_pro"),
    "charset": "utf8mb4",
}


# ============================================
# 后端接口：接收表单数据 → 入库 → 研判 → 返回结论
# ============================================
@router.post("/resume/add")
def add_resume(req: ResumeRequest):
    """
    接收学生信息表格数据：
    1. 写入 user_profiles 表
    2. 触发画像研判评估
    3. 返回自然语言研判结论
    """
    d = req.dict()
    conn = pymysql.connect(**DB_CONFIG, cursorclass=DictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_profiles
                (name, age, major, education, target_major, language_score,
                 target_country, gpa, budget, phone, development, abilities,
                 `is_Closed_loop`, wechat, email, assess)
                VALUES
                (%(name)s, %(age)s, %(major)s, %(education)s, %(target_major)s,
                 %(language_score)s, %(target_country)s, %(gpa)s, %(budget)s,
                 %(phone)s, %(development)s, %(abilities)s, %(is_Closed_loop)s,
                 %(wechat)s, %(email)s, '待研判')
            """, d)
            conn.commit()
            new_user_id = cur.lastrowid
    finally:
        conn.close()

    # 按 ID 精准触发研判（只研判这一个新用户）
    sql_filter = "`id` = %s" % int(new_user_id)
    try:
        assessment_result = run_targeted_assessment(sql_filter=sql_filter, student_view=True)
    except Exception as e:
        return JSONResponse(status_code=200, content={
            "code": 500,
            "msg": "研判失败: %s" % str(e),
            "data": {"user_id": new_user_id, "assessment_result": None}
        })

    return {
        "code": 0,
        "msg": "success",
        "data": {
            "user_id": new_user_id,
            "assessment_result": assessment_result,
        }
    }


# ============================================
# 简历上传接口：文件 → LLM 提取 → 入库 → 研判
# ============================================
import importlib.util as _ilu
# 动态引用 LLM 客户端配置（与 assessment.py 共享同一个 API Key 和 base_url）
_openai_client = None


def _get_openai_client():
    """获取 OpenAI 兼容客户端（通义千问）"""
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    # 优先从 assessment 模块取已初始化的配置
    try:
        from Assessment import assessment as _assess_mod
        _openai_client = _assess_mod._get_client()
        return _openai_client
    except Exception:
        pass
    # 备用：自行初始化
    from openai import OpenAI
    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    base_url = os.getenv(
        "LLM_BASE_URL",
        "https://ws-80gz91pjbhgouudd.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    )
    _openai_client = OpenAI(api_key=api_key, base_url=base_url)
    return _openai_client


def _extract_text_from_file(filename: str, content: bytes) -> str:
    """
    从上传的文件中提取纯文本。
    支持：.txt / .pdf / .docx
    """
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if suffix == "txt":
        # 多种编码尝试
        for enc in ("utf-8", "gbk", "gb2312", "utf-16", "latin-1"):
            try:
                return content.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return content.decode("utf-8", errors="replace")

    elif suffix == "pdf":
        import io
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(content))
        parts = []
        for page in pages if (pages := reader.pages) else []:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(parts)

    elif suffix == "docx":
        import io
        import docx
        doc = docx.Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    else:
        raise ValueError(f"不支持的文件格式: .{suffix}，仅支持 txt / pdf / .docx")


def _extract_fields_from_resume(resume_text: str) -> dict:
    """
    调用 LLM 从简历文本中提取结构化字段。
    """
    client = _get_openai_client()
    model = os.getenv("LLM_MODEL", "qwen-plus")

    prompt = f"""你是一名资深的留学顾问。请仔细阅读以下中国学生的简历内容，提取并整理出留学申请所需的关键信息。

【简历内容】
{resume_text}

【需要提取的字段】
请从简历中识别以下信息。如果简历中没有明确提到，请根据上下文合理推断；完全无法推断的字段请留 null：
- name: 姓名（字符串）
- age: 年龄（整数，若只有出生年份请推算为 2026 年时的年龄）
- major: 当前专业 / 所学专业（字符串）
- education: 当前学历（只能从以下选项中选择：高中 / 本科 / 硕士 / 博士 / 其他）
- target_major: 目标申请专业 / 意向专业（字符串，简历中未提及则沿用当前专业）
- language_score: 语言成绩（字符串，如"雅思 7.0"、"托福 100"、"CET-6 550"；未提及则留 null）
- target_country: 目标留学国家 / 意向国家（字符串，简历中未提及则留 null）
- gpa: GPA 成绩（浮点数，如 3.5；4 分制；未提及则留 null）
- budget: 留学预算 / 可承担的留学费用（整数，单位：元人民币；未提及则留 null）
- phone: 联系电话 / 手机（字符串；未提及则留 null）
- is_Closed_loop: 是否接受封闭式实训（"是" 或 "否"，简历中无法判断则默认"否"）
- wechat: 微信号（字符串；未提及则留 null）
- email: 电子邮箱（字符串；未提及则留 null）
- development: 发展需求 / 职业规划（总结客户的职业发展需求和规划，100 字以内）
- abilities: 综合能力（根据客户的工作经历 / 实习经历 / 项目经历 / 学习经历 / 获奖证书 / 技能证书 / 兴趣爱好等方面的描述，综合总结客户的综合能力，150 字以内。重点关注：专业技能、实践能力、沟通协作、学习创新能力等）

【返回格式】
严格输出 JSON 对象，不要 markdown 代码块，不要其他文字：
{{"name":"张三","age":22,"major":"车辆工程","education":"本科","target_major":"人工智能","language_score":"雅思 7.0","target_country":"新加坡","gpa":3.5,"budget":200000,"phone":"138xxxx","is_Closed_loop":"否","wechat":null,"email":"<EMAIL>":"希望从事 AI 行业的技术研发工作，在硕士阶段深入学习机器学习方向","abilities":"具备扎实的编程基础，熟练掌握 Python 和 C++，曾在互联网公司实习，具有良好的团队协作能力和自主学习能力"}}
"""
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是一名资深留学顾问，擅长从中国学生的简历中提取结构化信息。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
    )
    raw = (resp.choices[0].message.content or "").strip()
    # 清理 markdown 代码块
    raw = raw.strip("`").removeprefix("json").removeprefix("JSON").strip()
    return json.loads(raw)


@router.post("/resume/upload")
async def upload_resume(file: UploadFile = File(...)):
    """
    上传简历文件（txt/pdf/docx）→ LLM 提取字段 → 入库 → 研判 → 返回结论
    """
    # 1. 检查文件格式
    filename = file.filename or ""
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in ("txt", "pdf", "docx"):
        return JSONResponse(status_code=400, content={
            "code": 400, "msg": f"不支持的文件格式 .{suffix}，仅支持 txt / pdf / docx", "data": None
        })

    try:
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:  # 10 MB 限制
            return JSONResponse(status_code=400, content={
                "code": 400, "msg": "文件过大，请上传 10MB 以内的文件", "data": None
            })

        # 2. 提取文本
        resume_text = _extract_text_from_file(filename, content)
        if not resume_text.strip():
            return JSONResponse(status_code=400, content={
                "code": 400, "msg": "未能从文件中提取到有效文本，请检查文件内容", "data": None
            })

        # 3. LLM 提取字段
        fields = _extract_fields_from_resume(resume_text)

        # 验证必填字段
        if not fields.get("name"):
            return JSONResponse(status_code=400, content={
                "code": 400, "msg": "未能从简历中识别出姓名，请检查简历内容", "data": None
            })

        # 4. 写入 user_profiles 表
        conn = pymysql.connect(**DB_CONFIG, cursorclass=DictCursor)
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO user_profiles
                    (name, age, major, education, target_major, language_score,
                     target_country, gpa, budget, phone, development, abilities,
                     `is_Closed_loop`, wechat, email, assess)
                    VALUES
                    (%(name)s, %(age)s, %(major)s, %(education)s, %(target_major)s,
                     %(language_score)s, %(target_country)s, %(gpa)s, %(budget)s,
                     %(phone)s, %(development)s, %(abilities)s, %(is_Closed_loop)s,
                     %(wechat)s, %(email)s, '待研判')
                """, fields)
                conn.commit()
                new_user_id = cur.lastrowid
        finally:
            conn.close()

        # 5. 触发研判
        sql_filter = "`id` = %s" % int(new_user_id)
        try:
            assessment_result = run_targeted_assessment(sql_filter=sql_filter, student_view=True)
        except Exception as e:
            return JSONResponse(status_code=200, content={
                "code": 500,
                "msg": "研判失败: %s" % str(e),
                "data": {"user_id": new_user_id, "assessment_result": None}
            })

        return {
            "code": 0,
            "msg": "success",
            "data": {
                "user_id": new_user_id,
                "assessment_result": assessment_result,
            }
        }

    except json.JSONDecodeError:
        return JSONResponse(status_code=500, content={
            "code": 500, "msg": "大模型解析简历失败，请检查简历内容是否完整", "data": None
        })
    except ValueError as ve:
        return JSONResponse(status_code=400, content={
            "code": 400, "msg": str(ve), "data": None
        })
    except Exception as e:
        logger.error("简历上传处理失败: %s", e, exc_info=True) if 'logger' in dir() else None
        return JSONResponse(status_code=500, content={
            "code": 500, "msg": "处理失败: %s" % str(e), "data": None
        })


# ============================================
# 前端页面：信息录入表格
# ============================================
@app.get("/", response_class=HTMLResponse)
def index():
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>学生信息录入</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f5f7fa;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: flex-start;
            padding: 40px 20px;
        }
        .container {
            background: #fff;
            border-radius: 12px;
            box-shadow: 0 4px 24px rgba(0,0,0,0.08);
            padding: 40px;
            width: 100%;
            max-width: 720px;
        }
        h1 {
            text-align: center;
            color: #1a1a2e;
            margin-bottom: 8px;
            font-size: 24px;
        }
        .subtitle {
            text-align: center;
            color: #888;
            font-size: 13px;
            margin-bottom: 32px;
        }
        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            margin-bottom: 4px;
        }
        .form-group {
            margin-bottom: 16px;
        }
        .form-group.full {
            grid-column: 1 / -1;
        }
        label {
            display: block;
            font-size: 14px;
            color: #333;
            margin-bottom: 6px;
            font-weight: 500;
        }
        label .required { color: #e74c3c; }
        label .optional { color: #aaa; font-weight: 400; font-size: 12px; }
        input, select, textarea {
            width: 100%;
            padding: 10px 14px;
            border: 1.5px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
            color: #333;
            transition: border-color 0.2s;
            outline: none;
        }
        input:focus, select:focus, textarea:focus {
            border-color: #4a90d9;
        }
        textarea { resize: vertical; min-height: 70px; }
        .divider {
            height: 1px;
            background: #eee;
            margin: 24px 0 16px;
        }
        .section-title {
            font-size: 13px;
            color: #999;
            margin-bottom: 16px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .btn-submit {
            width: 100%;
            padding: 14px;
            background: #4a90d9;
            color: #fff;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
            margin-top: 8px;
        }
        .btn-submit:hover { background: #357abd; }
        .btn-submit:disabled { background: #b0c4de; cursor: not-allowed; }
        .result-box {
            margin-top: 24px;
            padding: 16px;
            background: #f8f9fa;
            border: 1px solid #e8e8e8;
            border-radius: 8px;
            display: none;
        }
        .result-box.show { display: block; }
        .result-box h3 { font-size: 14px; color: #555; margin-bottom: 8px; }
        .result-box pre {
            white-space: pre-wrap;
            word-break: break-all;
            font-size: 13px;
            color: #333;
            line-height: 1.7;
        }
        .result-box.success {
            background: #f0f9eb;
            border-color: #e1f3d8;
        }
        .result-box.success h3 { color: #67c23a; }
        .result-box.fail {
            background: #fef0f0;
            border-color: #fde2e2;
        }
        .result-box.fail h3 { color: #f56c6c; }
        .error-msg {
            color: #e74c3c;
            font-size: 13px;
            margin-top: 12px;
            display: none;
        }
        .loading {
            text-align: center;
            color: #4a90d9;
            margin-top: 12px;
            display: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>学生信息录入</h1>
        <p class="subtitle">请填写以下信息，提交后将自动进行画像研判评估</p>

        <form id="resumeForm">
            <!-- 基本信息 -->
            <div class="form-row">
                <div class="form-group">
                    <label>姓名 <span class="required">*</span></label>
                    <input type="text" id="name" placeholder="请输入姓名" required>
                </div>
                <div class="form-group">
                    <label>年龄 <span class="required">*</span></label>
                    <input type="number" id="age" placeholder="请输入年龄" min="1" max="100" required>
                </div>
            </div>

            <div class="form-row">
                <div class="form-group">
                    <label>当前专业 <span class="required">*</span></label>
                    <input type="text" id="major" placeholder="如：车辆工程" required>
                </div>
                <div class="form-group">
                    <label>当前学历 <span class="required">*</span></label>
                    <select id="education" required>
                        <option value="">请选择</option>
                        <option value="高中">高中</option>
                        <option value="本科">本科</option>
                        <option value="硕士">硕士</option>
                        <option value="博士">博士</option>
                        <option value="其他">其他</option>
                    </select>
                </div>
            </div>

            <div class="form-row">
                <div class="form-group">
                    <label>目标申请专业 <span class="required">*</span></label>
                    <input type="text" id="target_major" placeholder="如：人工智能" required>
                </div>
                <div class="form-group">
                    <label>语言成绩 <span class="required">*</span></label>
                    <input type="text" id="language_score" placeholder="如：雅思 7.0 / 托福 100" required>
                </div>
            </div>

            <div class="form-row">
                <div class="form-group">
                    <label>目标留学国家 <span class="required">*</span></label>
                    <input type="text" id="target_country" placeholder="如：德国" required>
                </div>
                <div class="form-group">
                    <label>GPA <span class="required">*</span></label>
                    <input type="number" id="gpa" placeholder="如：3.5" step="0.01" min="0" max="4" required>
                </div>
            </div>

            <div class="form-row">
                <div class="form-group">
                    <label>留学预算（元）<span class="required">*</span></label>
                    <input type="number" id="budget" placeholder="如：200000" min="0" required>
                </div>
                <div class="form-group">
                    <label>手机号码 <span class="required">*</span></label>
                    <input type="text" id="phone" placeholder="请输入手机号" pattern="\\d{11}" required>
                </div>
            </div>

            <div class="form-group full">
                <label>发展需求 <span class="required">*</span></label>
                <textarea id="development" placeholder="请描述学生的职业发展需求和规划..." required></textarea>
            </div>

            <div class="form-group full">
                <label>综合能力 <span class="required">*</span></label>
                <textarea id="abilities" placeholder="请描述学生的综合能力，如专业技能、项目经验等..." required></textarea>
            </div>

            <div class="form-row">
                <div class="form-group">
                    <label>是否接受封闭式实训 <span class="required">*</span></label>
                    <select id="is_Closed_loop" required>
                        <option value="">请选择</option>
                        <option value="是">是</option>
                        <option value="否">否</option>
                    </select>
                </div>
            </div>

            <!-- 分割线 -->
            <div class="divider"></div>
            <div class="section-title">选填信息（Optional）</div>

            <div class="form-row">
                <div class="form-group">
                    <label>微信号 <span class="optional">选填</span></label>
                    <input type="text" id="wechat" placeholder="请输入微信号">
                </div>
                <div class="form-group">
                    <label>电子邮箱 <span class="optional">选填</span></label>
                    <input type="email" id="email" placeholder="请输入邮箱">
                </div>
            </div>

            <div class="form-row">
                <div class="form-group">
                    <label>会话 ID <span class="optional">选填</span></label>
                    <input type="text" id="conversation_id" placeholder="留空将自动生成">
                </div>
            </div>

            <button type="submit" class="btn-submit" id="submitBtn">提交信息</button>
        </form>

        <div class="loading" id="loading">正在提交，请稍候...</div>
        <div class="error-msg" id="errorMsg"></div>

        <div class="result-box" id="resultBox">
            <h3 id="resultTitle">研判结论</h3>
            <pre id="resultContent"></pre>
        </div>
    </div>

    <script>
        document.getElementById('resumeForm').addEventListener('submit', async function(e) {
            e.preventDefault();

            const submitBtn = document.getElementById('submitBtn');
            const loading = document.getElementById('loading');
            const errorMsg = document.getElementById('errorMsg');
            const resultBox = document.getElementById('resultBox');
            const resultTitle = document.getElementById('resultTitle');
            const resultContent = document.getElementById('resultContent');

            // 隐藏之前的结果
            errorMsg.style.display = 'none';
            resultBox.classList.remove('show', 'success', 'fail');
            submitBtn.disabled = true;
            loading.style.display = 'block';

            // 收集表单数据
            const formData = {
                name: document.getElementById('name').value,
                age: parseInt(document.getElementById('age').value),
                major: document.getElementById('major').value,
                education: document.getElementById('education').value,
                target_major: document.getElementById('target_major').value,
                language_score: document.getElementById('language_score').value,
                target_country: document.getElementById('target_country').value,
                gpa: parseFloat(document.getElementById('gpa').value),
                budget: parseFloat(document.getElementById('budget').value),
                phone: document.getElementById('phone').value,
                development: document.getElementById('development').value,
                abilities: document.getElementById('abilities').value,
                is_Closed_loop: document.getElementById('is_Closed_loop').value,
                wechat: document.getElementById('wechat').value || null,
                email: document.getElementById('email').value || null,
                conversation_id: document.getElementById('conversation_id').value || null
            };

            try {
                // 只调一次后端：入库 + 研判
                const res = await fetch('/api/agent/resume/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(formData)
                });
                const data = await res.json();

                if (data.code !== 0) {
                    throw new Error(data.msg || '提交失败');
                }

                // 直接展示研判结论
                const result = data.data.assessment_result || '研判完成，无详细结论。';
                resultContent.textContent = result;

                // 根据结论判断是"通过"还是"未通过"
                if (result.includes('已通过') && !result.includes('已通过 0 人')) {
                    resultBox.classList.add('success');
                    resultTitle.textContent = '研判结论 - 已通过（已转为意向客户）';
                } else {
                    resultBox.classList.add('fail');
                    resultTitle.textContent = '研判结论 - 未通过';
                }

                resultBox.classList.add('show');

            } catch (err) {
                errorMsg.textContent = '错误：' + err.message;
                errorMsg.style.display = 'block';
            } finally {
                submitBtn.disabled = false;
                loading.style.display = 'none';
            }
        });
    </script>
</body>
</html>
    """


# ============================================
# 独立运行入口（直接 python resume_api.py 即可启动）
# ============================================
if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("resume_api:app", host=host, port=port, reload=True)
