"""
知识库：FAQ精配 + 海外生活指南 + 留学政策 + 升学项目 + 专业名录
面向已签约学生的智能助手，覆盖场景⑥生活支持 + 场景⑦增值转化
"""

import os
import re
from .loader import load_file, load_folder, split_chunks, extract_keywords

# 数据目录
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
# 外部知识库路径，可通过 .env 的 KNOWLEDGE_PATH 配置
DEFAULT_KNOWLEDGE_PATH = os.path.join(os.path.dirname(__file__), "data")
KNOWLEDGE_PATH = os.getenv("KNOWLEDGE_PATH", DEFAULT_KNOWLEDGE_PATH)


class KnowledgeBase:
    """轻量 RAG 知识库，内存检索"""

    def __init__(self):
        self.chunks: list[dict] = []        # [{title, text, keywords}]
        self.faq_map: dict[str, str] = {}   # {question: answer}
        self.doc_count = 0

    # ================================================================
    #  加载入口
    # ================================================================

    def load_all(self):
        """加载全部学生相关知识"""
        self._load_builtin_life_guide()     # 内置：海外生活
        self._load_faq_from_file()          # FAQ：问答对文本版
        self._load_study_policies()         # 留学政策：新加坡 + 德国
        self._load_programs()               # 升学项目：新加坡 + 德国
        self._load_major_catalog()          # 专业方向名录
        self._load_custom_data_folder()     # data/ 目录下自定义文档

    # ================================================================
    #  内置：海外生活指南（不改）
    # ================================================================

    def _load_builtin_life_guide(self):
        guides = [
            ("新加坡医疗服务", """新加坡医疗服务指南：
就医流程：基础看病去社区诊所（GP/Polyclinic），专科需GP转诊，急诊直接去医院A&E（24小时开放）。
费用：国际学生通常需购买学校指定医疗保险。GP诊所问诊费约SGD 30-60，Polyclinic约SGD 13-20，急诊A&E约SGD 120-150。
常用医院：Singapore General Hospital (SGH)、National University Hospital (NUH)、Tan Tock Seng Hospital (TTSH)。
药店：Guardian / Watsons（全岛连锁）、Unity。
紧急电话：995（救护车）/ 1777（非紧急救护车）。"""),

            ("新加坡租房指南", """新加坡租房指南：
房型：HDB政府组屋（普通房SGD 600-1200/月，主人房SGD 1000-1800/月）、Condo公寓（普通房SGD 1200-2000/月）。
注意事项：签约前实地看房、押金通常1-2个月租金、确认水电费是否包含。印花税需在签约后14天内缴纳。
找房渠道：PropertyGuru / 99.co（主流网站）、Carousell、学校内部租房群。"""),

            ("新加坡交通出行", """新加坡交通出行指南：
MRT地铁：覆盖全岛，运营约5:30-24:00，票价SGD 1.00-2.50。主要线路：东西线(绿)、南北线(红)、环线(黄)、东北线(紫)、滨海市区线(蓝)。
巴士：覆盖MRT不到的角落，Ez-Link卡可换乘优惠。
打车：Grab（东南亚版滴滴）、Gojek、TADA。
交通卡：Ez-Link充值卡，或直接用银行卡/Visa/Mastercard/Apple Pay刷SimplyGo。"""),

            ("新加坡银行卡与通讯", """新加坡银行卡与通讯指南：
银行卡：凭Student Pass+Passport+住址证明即可开户。主流银行：DBS/POSB、OCBC、UOB，DBS开户门槛最低。借记卡3-5个工作日寄到。
手机通讯：三大运营商Singtel/StarHub/M1，虚拟运营商GOMO/giga/Circles.Life/SIMBA。月费SGD 10-30可得20-100GB流量。推荐SIMBA（SGD 10/月起，含国际漫游）。
紧急电话：报警999、救护车995、中国驻新加坡大使馆+65 6471 2117、24小时领事保护+65 6475 0165。"""),
        ]
        for title, content in guides:
            self._add_document(title, content)

    # ================================================================
    #  FAQ：从问答对文本版导入
    # ================================================================

    def _load_faq_from_file(self):
        """从问答对文本版.txt导入FAQ"""
        faq_path = os.path.join(KNOWLEDGE_PATH, "公司信息", "问答对文本版.txt")
        content = None
        if os.path.exists(faq_path):
            content = load_file(faq_path)

        if not content:
            self._load_builtin_faq()
            return

        # 只取学生关心的关键词
        student_keywords = [
            "学历", "认证", "报名流程", "退费", "费用", "学制",
            "专升本", "本升硕", "签证", "回国", "留学生归国",
            "学费", "德国项目", "德国培训", "德语", "流程", "政策",
            "申请", "入学测试", "新加坡", "定向培养", "联合办学",
        ]

        count = 0
        for line in content.strip().split("\n"):
            line = line.strip()
            if "\t" not in line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                q, a = parts[0].strip(), parts[1].strip()
                # 检查是否学生相关
                is_student = any(kw in q or kw in a for kw in student_keywords)
                if is_student and q and a:
                    self.faq_map[q] = a
                    count += 1

        if count == 0:
            self._load_builtin_faq()
        else:
            print(f"[KB] FAQ加载: {count}条（已过滤学生相关）")

    def _load_builtin_faq(self):
        """内置FAQ兜底"""
        self.faq_map.update({
            "申请流程是什么": "留学申请一般流程：选校定校 → 材料准备（成绩单/推荐信/语言成绩）→ 文书撰写（PS/CV）→ 递交申请 → 等待Offer → 签证办理。全程我们的顾问会一步步带你走。",
            "退费政策是什么": "不同服务项目退费政策不同。签约后7天内可无条件取消。具体条款请查看合同或咨询你的专属顾问。",
            "学历回国能认证吗": "新加坡公立大学和多数私立大学的学位回国都可以做中留服认证，享受留学生归国福利。具体以中留服最新名单为准。",
        })

    # ================================================================
    #  留学政策
    # ================================================================

    def _load_study_policies(self):
        for fname in ["新加坡留学政策指南.docx", "德国留学政策指南.docx"]:
            p = os.path.join(KNOWLEDGE_PATH, "留学政策", fname)
            if os.path.exists(p):
                content = load_file(p)
                if content:
                    self._add_document(fname, content)

    def _load_programs(self):
        for fname in ["新加坡国际本硕升学计划.docx", "中德精英人才共建计划.docx"]:
            p = os.path.join(KNOWLEDGE_PATH, "公司业务", fname)
            if os.path.exists(p):
                content = load_file(p)
                if content:
                    self._add_document(fname, content)

    def _load_major_catalog(self):
        p = os.path.join(KNOWLEDGE_PATH, "用户研判规则", "中德精英人才共建计划 —— 全专业方向名录.txt")
        if os.path.exists(p):
            content = load_file(p)
            if content:
                self._add_document("德国专业方向名录", content)

    # ================================================================
    #  自定义文档（data/目录）
    # ================================================================

    def _load_custom_data_folder(self):
        if os.path.isdir(DATA_DIR):
            docs = load_folder(DATA_DIR)
            for doc in docs:
                self._add_document(doc["title"], doc["content"])
            if docs:
                print(f"[KB] 自定义文档: {len(docs)}篇")

    # ================================================================
    #  核心：添加文档
    # ================================================================

    def _add_document(self, title: str, content: str):
        chunks = split_chunks(content)
        for chunk in chunks:
            self.chunks.append({
                "title": title,
                "text": chunk,
                "keywords": extract_keywords(chunk),
            })
        self.doc_count += 1

    # ================================================================
    #  检索
    # ================================================================

    def search(self, query: str, top_k: int = 3) -> list[str]:
        """关键词+子串匹配，返回相关文本片段"""
        query_keywords = extract_keywords(query)
        if not self.chunks:
            return []

        scored = []
        for chunk in self.chunks:
            score = len(query_keywords & chunk["keywords"])
            if any(kw in chunk["title"] for kw in query_keywords):
                score += 3
            for qw in query_keywords:
                if qw in chunk["text"]:
                    score += 2
            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [c["text"] for _, c in scored[:top_k]]

    def faq_match(self, query: str) -> str | None:
        """FAQ匹配：精配→模糊→None"""
        # 精确
        if query.strip() in self.faq_map:
            return self.faq_map[query.strip()]
        # 模糊
        query_kw = extract_keywords(query)
        best_score = 0
        best_answer = None
        for question, answer in self.faq_map.items():
            q_kw = extract_keywords(question)
            overlap = len(query_kw & q_kw)
            if overlap > best_score and overlap >= 2:
                best_score = overlap
                best_answer = answer
        return best_answer

    def is_loaded(self) -> bool:
        return len(self.chunks) > 0 or len(self.faq_map) > 0


# ================================================================
#  全局单例
# ================================================================

_kb: KnowledgeBase | None = None


def get_kb() -> KnowledgeBase:
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
        _kb.load_all()
        print(f"[KB] 知识库就绪: {len(_kb.chunks)}个片段, {len(_kb.faq_map)}条FAQ, {_kb.doc_count}篇文档")
    return _kb


def reload_kb():
    """强制重新加载知识库"""
    global _kb
    _kb = KnowledgeBase()
    _kb.load_all()
    print(f"[KB] 知识库已刷新: {len(_kb.chunks)}个片段, {len(_kb.faq_map)}条FAQ")
    return _kb
