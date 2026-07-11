"""
简历信息录入 - FastAPI 接口 + 前端页面
路由前缀：/api/agent
"""
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from resume import ResumeRequest, generate_insert_instruction

router = APIRouter()
app = FastAPI(title="学生信息录入 API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api/agent")

# Dify 接口地址
DIFY_API_URL = "http://192.168.48.121/v1/chat-messages"


# ============================================
# 后端接口：接收表单数据 → 生成文本 → 调用 Dify
# ============================================
@router.post("/resume/add")
def add_resume(req: ResumeRequest):
    """
    接收学生信息表格数据，生成自然语言指令文本。
    """
    try:
        generated_text = generate_insert_instruction(req)
        return {"code": 0, "msg": "success", "data": {"generated_text": generated_text}}
    except Exception as e:
        return {"code": 500, "msg": str(e), "data": None}


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
        <p class="subtitle">请填写以下信息，提交后将通过 AI 助手进行分析</p>

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
                    <label>封闭式实训 <span class="required">*</span></label>
                    <select id="closed_loop" required>
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
            <h3>AI 回复结果</h3>
            <pre id="resultContent"></pre>
        </div>
    </div>

    <script>
        const DIFY_API_URL = "http://192.168.48.121/v1/chat-messages";
        const DIFY_API_KEY = "app-qRMvQywnR0juwptiOwIDilKc";

        document.getElementById('resumeForm').addEventListener('submit', async function(e) {
            e.preventDefault();

            const submitBtn = document.getElementById('submitBtn');
            const loading = document.getElementById('loading');
            const errorMsg = document.getElementById('errorMsg');
            const resultBox = document.getElementById('resultBox');
            const resultContent = document.getElementById('resultContent');

            // 隐藏之前的结果
            errorMsg.style.display = 'none';
            resultBox.classList.remove('show');
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
                closed_loop: document.getElementById('closed_loop').value,
                wechat: document.getElementById('wechat').value || null,
                email: document.getElementById('email').value || null,
                conversation_id: document.getElementById('conversation_id').value || null
            };

            try {
                // 先生成本地文本
                const localRes = await fetch('/api/agent/resume/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(formData)
                });
                const localData = await localRes.json();

                if (localData.code !== 0) {
                    throw new Error(localData.msg || '生成文本失败');
                }

                const generatedText = localData.data.generated_text;

                // 调用 Dify API
                const difyRes = await fetch(DIFY_API_URL, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + DIFY_API_KEY
                    },
                    body: JSON.stringify({
                        inputs: { profile_text: generatedText },
                        query: generatedText,
                        response_mode: "blocking",
                        conversation_id: formData.conversation_id || "",
                        user: "student-form"
                    })
                });

                const difyData = await difyRes.json();

                // 显示结果
                resultContent.textContent = JSON.stringify(difyData, null, 2);
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
    import os
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("resume_api:app", host=host, port=port, reload=True)
