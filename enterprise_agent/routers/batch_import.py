"""
企业智能助手 - 批量导入用户信息（user_profiles 表）
支持：
  1. 粘贴文本（自动识别多个人）
  2. 上传简历文件（txt / pdf / docx）
缺失字段时返回追问提示
"""

import os
import re
import json
import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import JSONResponse

from enterprise_agent.database import get_db
from enterprise_agent.schemas import ApiResponse

logger = logging.getLogger("enterprise_agent.batch_import")
router = APIRouter()

# ──────────────────────────────────────────────────────────────
# 配置（复用 Assessment 模块的 LLM 客户端）
# ──────────────────────────────────────────────────────────────
_openai_client = None


def _get_openai_client():
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    # 优先复用 Assessment 模块的客户端
    try:
        from Assessment import assessment as _assess_mod
        _openai_client = _assess_mod._get_client()
        return _openai_client
    except Exception:
        pass
    from openai import OpenAI
    _openai_client = OpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY", ""),
        base_url=os.getenv(
            "LLM_BASE_URL",
            "https://ws-80gz91pjbhgouudd.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
        ),
    )
    return _openai_client


def _get_model():
    return os.getenv("LLM_MODEL", "qwen-plus")


# ──────────────────────────────────────────────────────────────
# 文件文本提取（复用 Assessment 模块逻辑）
# ──────────────────────────────────────────────────────────────
def _extract_text_from_file(filename: str, content: bytes) -> str:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if suffix == "txt":
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
        for page in (reader.pages or []):
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(parts)

    elif suffix == "docx":
        import io
        import docx
        document = docx.Document(io.BytesIO(content))
        return "\n".join(p.text for p in document.paragraphs if p.text.strip())

    else:
        raise ValueError(f"不支持的文件格式: .{suffix}")


# ──────────────────────────────────────────────────────────────
# 主接口
# ──────────────────────────────────────────────────────────────
@router.post("/batch_import", response_model=ApiResponse, summary="批量导入用户信息")
async def batch_import(
    text: Optional[str] = Form(None, description="粘贴的文本内容（可包含多个 [Pasted text #N +M lines]）"),
    files: Optional[list[UploadFile]] = File(None, description="简历文件（txt/pdf/docx）"),
):
    """
    企业员工批量导入用户信息到 user_profiles 表。
    - 文本：自动识别包含多少个独立用户，逐一提取字段
    - 文件：先解析文本，再用 LLM 提取字段
    - 缺失关键字段（姓名）时返回追问
    """
    try:
        # ── 1. 合并所有文本来源 ──
        all_text_blocks = []

        if text and text.strip():
            # 识别多个 [Pasted text #N +M lines] 块
            blocks = re.split(r'\[Pasted text #\d+ \+\d+ lines\]', text)
            for b in blocks:
                b = b.strip()
                if b:
                    all_text_blocks.append(b)
            # 没有任何标记时，把整段文本作为一块
            if not all_text_blocks:
                all_text_blocks.append(text.strip())

        if files:
            for f in files:
                content = await f.read()
                if len(content) > 10 * 1024 * 1024:
                    return JSONResponse(status_code=400, content={
                        "code": 400, "msg": f"文件 {f.filename} 过大（>10MB）", "data": None
                    })
                try:
                    file_text = _extract_text_from_file(f.filename or "", content)
                    if file_text.strip():
                        all_text_blocks.append(file_text.strip())
                except ValueError as ve:
                    return JSONResponse(status_code=400, content={
                        "code": 400, "msg": str(ve), "data": None
                    })

        if not all_text_blocks:
            return JSONResponse(status_code=400, content={
                "code": 400, "msg": "请提供文本或上传文件", "data": None
            })

        combined_text = "\n\n---\n\n".join(all_text_blocks)

        # ── 2. LLM 提取结构化数据 ──
        client = _get_openai_client()
        model = _get_model()

        prompt = f"""你是一名资深的留学顾问助手。请仔细阅读以下企业员工录入的信息（可能包含多个用户/客户的数据），提取出每一个人的完整信息。

【输入信息】
{combined_text}

【任务】
1. 首先判断输入中包含多少个独立的用户/客户信息（可能以空行、分隔线、或不同段落分隔）。
2. 对每一个人，提取以下 15 个字段（找不到的字段请填 null）：
   - name: 姓名（字符串，必填。如果某段信息完全无法识别姓名，请在 questions 中追问）
   - age: 年龄（整数）
   - major: 当前专业 / 所学专业（字符串）
   - education: 当前学历（只能从以下选项中选择：高中 / 本科 / 硕士 / 博士 / 其他）
   - target_major: 目标申请专业 / 意向专业（字符串）
   - language_score: 语言成绩（字符串，如"雅思 7.0"、"托福 100"，未提及填 null）
   - target_country: 目标留学国家（字符串）
   - gpa: GPA 成绩（浮点数，4 分制）
   - budget: 留学预算 / 可承担的留学费用（整数，单位：元人民币）
   - phone: 联系电话 / 手机（字符串）
   - development: 发展需求 / 职业规划（字符串，100 字以内）
   - abilities: 综合能力（字符串，根据工作/实习/项目/学习/技能/爱好等总结，150 字以内）
   - is_Closed_loop: 是否接受封闭式实训（"是" 或 "否"）
   - wechat: 微信号（字符串）
   - email: 电子邮箱（字符串）

3. 对于缺少 name（姓名）的用户，必须在"questions"字段中生成追问提示（告知员工需要补充什么信息）。

【返回格式】
严格输出 JSON，不要 markdown 代码块：
{{"users":[{{"name":"张三","age":22,"major":"计算机科学","education":"本科","target_major":"人工智能","language_score":"雅思 7.0","target_country":"德国","gpa":3.5,"budget":200000,"phone":"138xxxx","development":"AI 研发方向","abilities":"熟练掌握 Python，有项目经验","is_Closed_loop":"是","wechat":null,"email":null}}],"questions":["第 2 条信息缺少姓名，请问该客户的姓名是什么？","第 3 条信息缺少年龄，请问该客户年龄多大？"]}}

如果输入中没有明确的客户信息（比如员工只是说了一句"你好"），返回 {{"users":[],"questions":[]}}。"""

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一名资深留学顾问，擅长从企业员工录入的分散信息中提取结构化客户数据。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        raw = (resp.choices[0].message.content or "").strip()
        raw = raw.strip("`").removeprefix("json").removeprefix("JSON").strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # 尝试提取 JSON 部分
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
            else:
                return JSONResponse(status_code=500, content={
                    "code": 500, "msg": "AI 解析失败，请检查输入内容", "data": None
                })

        users_raw = data.get("users", [])
        questions = data.get("questions", [])

        if not users_raw and not questions:
            return JSONResponse(status_code=200, content={
                "code": 0, "msg": "未识别到有效客户信息",
                "data": {"success": 0, "failed": 0, "user_ids": [], "questions": []}
            })

        # ── 3. 入库（有 name 的才写入；缺 name 的留给追问） ──
        db = next(get_db())
        success_ids = []
        failed_items = []
        skipped_for_questions = []

        for idx, u in enumerate(users_raw):
            name = (u.get("name") or "").strip()
            if not name:
                # 缺少姓名，跳过，加入追问
                skipped_for_questions.append({
                    "index": idx + 1,
                    "partial": {k: v for k, v in u.items() if v is not None and v != ""},
                    "reason": "缺少姓名"
                })
                continue

            # 过滤空字符串 → None
            clean = {}
            # 字段长度上限，超长自动截断
            _max_lens = {
                'name': 50, 'major': 100, 'education': 50, 'target_major': 100,
                'language_score': 50, 'target_country': 50, 'phone': 30,
                'development': 300, 'abilities': 500, 'is_Closed_loop': 100,
                'wechat': 50, 'email': 100,
            }
            for k, v in u.items():
                if v is None or (isinstance(v, str) and not v.strip()):
                    clean[k] = None
                elif isinstance(v, str) and k in _max_lens and len(v) > _max_lens[k]:
                    clean[k] = v[:_max_lens[k]]
                else:
                    clean[k] = v

            # 写入 user_profiles
            from sqlalchemy import text
            result = db.execute(text("""
                INSERT INTO user_profiles
                (name, age, major, education, target_major, language_score,
                 target_country, gpa, budget, phone, development, abilities,
                 `is_Closed_loop`, wechat, email, assess)
                VALUES
                (:name, :age, :major, :education, :target_major, :language_score,
                 :target_country, :gpa, :budget, :phone, :development, :abilities,
                 :is_Closed_loop, :wechat, :email, '待研判')
            """), clean)
            db.flush()
            new_id = result.lastrowid
            if new_id is None:
                # pymysql lastrowid fallback
                new_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()
            success_ids.append(int(new_id))

        db.commit()

        # 合并追问：LLM 生成的 + 缺 name 自动补充
        all_questions = list(questions)
        for skip in skipped_for_questions:
            partial_desc = ", ".join(f"{k}={v}" for k, v in skip["partial"].items())
            all_questions.append(
                f"第 {skip['index']} 条信息（{partial_desc}）缺少姓名，请问该客户的姓名是什么？"
            )

        return ApiResponse(data={
            "success": len(success_ids),
            "failed": len(failed_items),
            "user_ids": success_ids,
            "questions": all_questions,
        })

    except ValueError as ve:
        return JSONResponse(status_code=400, content={
            "code": 400, "msg": str(ve), "data": None
        })
    except Exception as e:
        logger.error("batch_import 失败: %s", e, exc_info=True)
        return JSONResponse(status_code=500, content={
            "code": 500, "msg": f"处理失败: {str(e)}", "data": None
        })


@router.post("/batch_import/followup", response_model=ApiResponse, summary="追问补充后补录用户")
async def batch_import_followup(
    name: str = Form(..., description="客户姓名"),
    age: Optional[int] = Form(None),
    major: Optional[str] = Form(None),
    education: Optional[str] = Form(None),
    target_major: Optional[str] = Form(None),
    language_score: Optional[str] = Form(None),
    target_country: Optional[str] = Form(None),
    gpa: Optional[float] = Form(None),
    budget: Optional[int] = Form(None),
    phone: Optional[str] = Form(None),
    development: Optional[str] = Form(None),
    abilities: Optional[str] = Form(None),
    is_Closed_loop: Optional[str] = Form(None),
    wechat: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
):
    """追问补充：员工回答追问后，补录到 user_profiles"""
    try:
        db = next(get_db())
        from sqlalchemy import text
        result = db.execute(text("""
            INSERT INTO user_profiles
            (name, age, major, education, target_major, language_score,
             target_country, gpa, budget, phone, development, abilities,
             `is_Closed_loop`, wechat, email, assess)
            VALUES
            (:name, :age, :major, :education, :target_major, :language_score,
             :target_country, :gpa, :budget, :phone, :development, :abilities,
             :is_Closed_loop, :wechat, :email, '待研判')
        """), {
            "name": name, "age": age, "major": major, "education": education,
            "target_major": target_major, "language_score": language_score,
            "target_country": target_country, "gpa": gpa, "budget": budget,
            "phone": phone, "development": development, "abilities": abilities,
            "is_Closed_loop": is_Closed_loop, "wechat": wechat, "email": email,
        })
        db.commit()
        new_id = result.lastrowid
        if new_id is None:
            new_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()
        return ApiResponse(data={"user_id": int(new_id)})
    except Exception as e:
        logger.error("batch_import/followup 失败: %s", e, exc_info=True)
        return JSONResponse(status_code=500, content={
            "code": 500, "msg": f"补录失败: {str(e)}", "data": None
        })
