"""
知识库问答路由（重构版）
POST /api/agent/knowledge/query - 知识库问答

功能：
1. 加载 Knowledge/ 目录下的所有教育文档（留学政策、公司业务等）
2. 加载 enterprise_agent/knowledge_base.json 中的规章制度
3. 使用 jieba 分词 + TF-IDF 评分做问答匹配
"""
from fastapi import APIRouter, Depends, HTTPException
import logging
import json
import os
import re
from collections import Counter
from math import log

import jieba

from enterprise_agent.schemas import ApiResponse, KnowledgeQueryRequest

logger = logging.getLogger("enterprise_agent.knowledge")
router = APIRouter()

# ============================================================
# 知识库文档加载器
# ============================================================

# 知识库根目录
_KNOWLEDGE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "Knowledge")
)
_JSON_KB_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "knowledge_base.json")
)

# 知识类别映射（目录名 → 显示用分类名）
CATEGORY_MAP = {
    "公司业务": "公司业务",
    "公司信息": "公司信息",
    "新人指南": "新人指南",
    "留学政策": "留学政策",
    "高频问题FAQ": "常见问题",
}


class KnowledgeDoc:
    """单篇知识文档"""
    def __init__(self, doc_id: str, title: str, content: str,
                 category: str = "通用", source: str = ""):
        self.doc_id = doc_id
        self.title = title
        self.content = content
        self.category = category
        self.source = source or category
        # jieba分词结果（去停用词）
        self.words = self._tokenize(content)
        # 词频统计
        self.word_freq = Counter(self.words)
        self.total_words = len(self.words)

    @staticmethod
    def _tokenize(text: str) -> list:
        """分词并过滤短词和停用词"""
        # 简单停用词表
        stop_words = {
            "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
            "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
            "会", "着", "没有", "看", "好", "自己", "这", "他", "她", "它",
            "们", "那", "些", "什么", "怎么", "如何", "为", "能", "及", "与",
            "等", "或", "但", "被", "把", "对", "从", "向", "在", "而",
            "且", "如果", "虽然", "因为", "所以", "但是", "可以", "可能",
            "已经", "这个", "那个", "之", "将", "所", "其", "中",
        }
        # 使用jieba精确模式分词
        words = jieba.lcut(text.lower())
        # 过滤：停用词、单字词、纯数字、空白
        return [
            w for w in words
            if w not in stop_words
            and len(w) > 1
            and not w.isdigit()
            and w.strip()
        ]


class KnowledgeBase:
    """知识库引擎（TF-IDF检索）"""

    def __init__(self):
        self.docs: list[KnowledgeDoc] = []
        self.idf: dict[str, float] = {}  # word -> IDF
        self.doc_count = 0
        self._loaded = False

    def _source_files(self) -> list:
        """返回所有源文件路径列表（用于检测变更）"""
        files = []
        if os.path.isdir(_KNOWLEDGE_ROOT):
            for dirname in os.listdir(_KNOWLEDGE_ROOT):
                dirpath = os.path.join(_KNOWLEDGE_ROOT, dirname)
                if not os.path.isdir(dirpath):
                    continue
                for fname in os.listdir(dirpath):
                    if fname.endswith(".txt"):
                        files.append(os.path.join(dirpath, fname))
        if os.path.exists(_JSON_KB_FILE):
            files.append(_JSON_KB_FILE)
        return files

    def _cache_valid(self, cache_path: str, source_files: list) -> bool:
        """检查缓存是否仍有效（所有源文件mtime未变）"""
        if not os.path.exists(cache_path):
            return False
        cache_mtime = os.path.getmtime(cache_path)
        for f in source_files:
            if os.path.getmtime(f) > cache_mtime:
                return False
        return True

    def load(self):
        """加载所有知识源（使用pickle缓存加速）"""
        import pickle

        cache_dir = os.path.join(os.path.dirname(__file__), "..", "__pycache__")
        cache_file = os.path.join(cache_dir, "knowledge_index.pkl")
        source_files = self._source_files()

        # 尝试从缓存加载
        if self._cache_valid(cache_file, source_files):
            try:
                with open(cache_file, "rb") as f:
                    cached = pickle.load(f)
                self.docs = cached["docs"]
                self.idf = cached["idf"]
                self.doc_count = cached["doc_count"]
                self._loaded = True
                logger.info(
                    "知识库从缓存加载: %d 篇文档, %d 个关键词",
                    self.doc_count, len(self.idf),
                )
                return
            except Exception as e:
                logger.warning("知识库缓存加载失败，将重建: %s", e)

        # 缓存无效 → 从源文件重建
        self.docs = []
        self._load_knowledge_root()
        self._load_json_kb()
        self._build_idf()
        self._loaded = True
        logger.info(
            "知识库重建完成: %d 篇文档, %d 个关键词",
            len(self.docs), len(self.idf),
        )

        # 写缓存
        try:
            os.makedirs(cache_dir, exist_ok=True)
            with open(cache_file, "wb") as f:
                pickle.dump({
                    "docs": self.docs,
                    "idf": self.idf,
                    "doc_count": self.doc_count,
                }, f)
            logger.info("知识库索引已缓存: %s", cache_file)
        except Exception as e:
            logger.warning("知识库缓存写入失败: %s", e)

    def _load_knowledge_root(self):
        """从 Knowledge/ 目录加载所有 .txt 文件"""
        if not os.path.isdir(_KNOWLEDGE_ROOT):
            logger.warning("知识库目录不存在: %s", _KNOWLEDGE_ROOT)
            return

        for dirname in os.listdir(_KNOWLEDGE_ROOT):
            dirpath = os.path.join(_KNOWLEDGE_ROOT, dirname)
            if not os.path.isdir(dirpath):
                continue

            category = CATEGORY_MAP.get(dirname, dirname)
            for fname in os.listdir(dirpath):
                if not fname.endswith(".txt"):
                    continue
                fpath = os.path.join(dirpath, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                    if not content:
                        continue
                    # 用文件名作为标题（去掉.txt和后缀编码）
                    title = fname.replace(".txt", "")
                    doc_id = f"knowledge/{dirname}/{fname}"
                    source = f"公司知识库/{category}"

                    # 如果是问答对格式（有 Q：和 A：），按问答对拆分
                    if "Q：" in content and "A：" in content:
                        self._parse_qa_pairs(doc_id, title, content, category, source)
                    else:
                        self.docs.append(KnowledgeDoc(
                            doc_id, title, content, category, source,
                        ))
                except Exception as e:
                    logger.error("加载知识文件失败 %s: %s", fpath, e)

    def _parse_qa_pairs(self, doc_id: str, title: str, content: str,
                        category: str, source: str):
        """将问答对格式拆分成多条知识条目"""
        # 按 Q：分割
        blocks = re.split(r'\n(?=Q：)', content)
        for i, block in enumerate(blocks):
            block = block.strip()
            if not block:
                continue
            q_match = re.search(r'Q[：:]\s*(.*?)(?:\n|$)', block)
            a_match = re.search(r'A[：:]\s*([\s\S]*)', block)
            question = q_match.group(1).strip() if q_match else ""
            answer = a_match.group(1).strip() if a_match else block

            # 问题和答案拼接作为索引内容
            full_content = f"{question} {answer}"
            self.docs.append(KnowledgeDoc(
                f"{doc_id}/q{i}",
                question or f"{title}#{i}",
                full_content,
                category,
                source,
            ))

    def _load_json_kb(self):
        """从 knowledge_base.json 加载规章制度"""
        if not os.path.exists(_JSON_KB_FILE):
            logger.warning("JSON知识库不存在: %s", _JSON_KB_FILE)
            return

        try:
            with open(_JSON_KB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key, entry in data.items():
                content = f"{key}：{entry.get('answer', '')}"
                source = entry.get("source", "企业规章制度")
                self.docs.append(KnowledgeDoc(
                    f"rules/{key}",
                    key,
                    content,
                    "企业规章制度",
                    source,
                ))
                # 关键词作为额外索引
                keywords_text = " ".join(entry.get("keywords", []))
                if keywords_text:
                    self.docs.append(KnowledgeDoc(
                        f"rules/{key}/kw",
                        key,
                        keywords_text,
                        "企业规章制度",
                        source,
                    ))
        except Exception as e:
            logger.error("加载JSON知识库失败: %s", e)

    def _build_idf(self):
        """构建IDF倒排索引"""
        self.doc_count = len(self.docs)
        if self.doc_count == 0:
            self.idf = {}
            return

        # 统计每个词出现在几篇文档中
        word_doc_count: Counter = Counter()
        for doc in self.docs:
            seen = set(doc.words)
            for w in seen:
                word_doc_count[w] += 1

        # 计算IDF
        n = self.doc_count
        self.idf = {
            w: log((n + 1) / (count + 1)) + 1
            for w, count in word_doc_count.items()
        }

    def search(self, question: str, top_k: int = 5) -> list[dict]:
        """TF-IDF检索，返回匹配结果列表"""
        if not self._loaded:
            self.load()
        if not self.docs:
            return self._fallback_answer(question)

        query_words = KnowledgeDoc._tokenize(question)
        if not query_words:
            return self._fallback_answer(question)

        # 计算每个文档的TF-IDF余弦相似度
        query_tf = Counter(query_words)

        scores = []
        for doc in self.docs:
            if doc.total_words == 0:
                continue

            score = 0.0
            for word, q_tf in query_tf.items():
                if word in doc.word_freq and word in self.idf:
                    tf = doc.word_freq[word] / doc.total_words
                    score += tf * self.idf[word] * q_tf

            if score > 0:
                scores.append((score, doc))

        # 按分数降序排列
        scores.sort(key=lambda x: -x[0])

        results = []
        for score, doc in scores[:top_k]:
            # 截取答案片段（优先返回完整内容，过长则截断）
            answer = doc.content
            if len(answer) > 500:
                # 尝试找到匹配问题相关段落
                answer = self._extract_relevant_section(
                    answer, query_words, max_len=500,
                )

            results.append({
                "doc_id": doc.doc_id,
                "title": doc.title,
                "category": doc.category,
                "source": doc.source,
                "answer": answer,
                "score": round(float(score), 4),
            })

        return results

    def _extract_relevant_section(self, text: str, query_words: list,
                                  max_len: int = 500) -> str:
        """从长文本中提取与查询最相关的段落"""
        # 按段落拆分
        paragraphs = re.split(r'\n+', text)
        best_para = ""
        best_count = 0

        for para in paragraphs:
            para_lower = para.lower()
            count = sum(1 for w in query_words if w in para_lower)
            if count > best_count:
                best_count = count
                best_para = para

        if best_para:
            return best_para[:max_len]
        return text[:max_len]

    def _fallback_answer(self, question: str) -> list:
        """兜底回复"""
        return [{
            "doc_id": "fallback",
            "title": "默认回复",
            "category": "通用",
            "source": "企业智能助手知识库",
            "answer": (
                f"您好！您问的是「{question}」相关的信息。\n\n"
                "当前知识库覆盖以下内容：\n"
                "📌 公司信息（简介、地址、联系方式等）\n"
                "📌 规章制度（上班时间、请假制度、薪资福利等）\n"
                "📌 留学政策（德国、新加坡等国家）\n"
                "📌 公司业务（中德精英人才共建、新加坡国际本硕升学计划等）\n\n"
                "请尝试换个说法提问，或选择左侧的快捷功能。"
            ),
            "score": 0,
        }]


# ==================== 全局单例 ====================
_KB = KnowledgeBase()


def _ensure_loaded():
    """确保知识库已加载"""
    if not _KB._loaded:
        _KB.load()


# ==================== POST /api/agent/knowledge/query ====================
@router.post("/knowledge/query", response_model=ApiResponse, summary="知识库问答")
def query_knowledge(req: KnowledgeQueryRequest):
    """
    知识库问答
    覆盖公司业务、规章制度、留学政策、常见问题等
    使用 jieba 分词 + TF-IDF 检索
    """
    try:
        question = req.question.strip()
        logger.info(
            "知识库问答: question='%s', user_id=%s, type=%s",
            question, req.current_user_id, req.current_user_type,
        )

        if not question:
            return ApiResponse(code=400, msg="问题不能为空")

        # 确保知识库已加载
        _ensure_loaded()

        # 检索
        results = _KB.search(question, top_k=3)

        # 取最佳结果
        best = results[0]

        # 如果有多个结果，显示来源
        answer = best["answer"]
        source = best["source"]

        if len(results) > 1:
            related = [
                f"- {r['title']}（{r['category']}）"
                for r in results[1:3]
                if r["score"] > 0.01
            ]
            if related:
                answer += "\n\n💡 你可能还想了解：\n" + "\n".join(related)

        return ApiResponse(data={
            "question": question,
            "answer": answer,
            "source": source,
            "category": best["category"],
            "score": best["score"],
            "total_matches": len([r for r in results if r["score"] > 0]),
        })

    except Exception as e:
        logger.error("知识库问答失败: %s", e, exc_info=True)
        return ApiResponse(code=500, msg=f"查询失败: {str(e)}")


# ==================== 管理接口 ====================
@router.get("/knowledge/reload", response_model=ApiResponse, summary="重新加载知识库")
def reload_knowledge():
    """手动触发知识库重新加载"""
    try:
        _KB.load()
        return ApiResponse(data={
            "doc_count": len(_KB.docs),
            "word_count": len(_KB.idf),
        })
    except Exception as e:
        logger.error("重新加载知识库失败: %s", e, exc_info=True)
        return ApiResponse(code=500, msg=f"重新加载失败: {str(e)}")


@router.get("/knowledge/stats", response_model=ApiResponse, summary="知识库统计")
def knowledge_stats():
    """查看知识库统计信息"""
    _ensure_loaded()
    categories = Counter(d.category for d in _KB.docs)
    return ApiResponse(data={
        "total_docs": len(_KB.docs),
        "total_keywords": len(_KB.idf),
        "categories": dict(categories),
    })
