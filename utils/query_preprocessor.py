"""
中文 / 英文 / 马来语 查询预处理模块
-------------------------------------
功能：
  1. 繁体中文 -> 简体中文（OpenCC）
  2. 三语同义词扩展（中文 / English / Bahasa Melayu）
     将用户口语、缩写、马来语输入映射到知识库中使用的标准词汇，
     扩展后的多个查询全部传入检索，取并集，提升召回率

用法：
    preprocessor = QueryPreprocessor()
    queries = preprocessor.process("签证怎么续签")
    # -> ["签证怎么续签", "student pass renewal", "permit pelajar"]
"""

import re
import unicodedata

try:
    import opencc
    _converter = opencc.OpenCC("t2s")  # 繁体 -> 简体
    _OPENCC_AVAILABLE = True
except Exception:
    _OPENCC_AVAILABLE = False

# ---------------------------------------------------------------------------
# 三语同义词扩展词典
# key   = 用户可能输入的词（中文简体 / 英文 / 马来语 均可作 key）
# value = 额外补充检索的多语言标准词组，列表中可混用三种语言
# ---------------------------------------------------------------------------
SYNONYM_MAP: dict[str, list[str]] = {

    # ── 签证 / 学生准证 ──────────────────────────────────────────────────────
    "签证":             ["student pass", "visa", "permit pelajar", "EMGS", "eVisa"],
    "续签":             ["renew student pass", "visa renewal", "pembaharuan permit pelajar"],
    "准证":             ["student pass", "permit pelajar", "visa renewal"],
    "student pass":     ["permit pelajar", "visa renewal", "EMGS", "续签 签证"],
    "permit pelajar":   ["student pass", "visa renewal", "EMGS", "续签"],
    "visa":             ["student pass", "permit pelajar", "eVisa", "签证"],
    "EMGS":             ["student pass", "visa", "permit pelajar", "EMGS approval"],

    # ── 注册 / 选课 ──────────────────────────────────────────────────────────
    "注册":             ["registration", "pendaftaran", "enrolment UKM"],
    "选课":             ["course registration", "pendaftaran kursus", "timetable add drop"],
    "退课":             ["drop course", "withdrawal", "tangguh pengajian"],
    "registration":     ["pendaftaran", "注册", "enrolment", "course registration"],
    "pendaftaran":      ["registration", "注册", "enrolment UKM"],

    # ── 学位 / 毕业 ──────────────────────────────────────────────────────────
    "毕业":             ["graduation", "konvokesyen", "convocation", "tamat pengajian"],
    "毕业证书":         ["degree certificate", "sijil ijazah", "transcript"],
    "成绩单":           ["transcript", "rekod akademik", "result slip", "keputusan"],
    "留服认证":         ["CSCSE", "credential evaluation", "pengesahan sijil China"],
    "convocation":      ["konvokesyen", "graduation", "毕业", "graduation ceremony"],
    "konvokesyen":      ["convocation", "graduation", "毕业典礼"],

    # ── 导师 / 教职人员 ──────────────────────────────────────────────────────
    "导师":             ["supervisor", "penyelia", "advisor", "academic staff FTSM"],
    "教授":             ["professor", "profesor", "Dr.", "academic staff"],
    "老师":             ["lecturer", "pensyarah", "tutor", "academic staff FTSM"],
    "supervisor":       ["penyelia", "导师", "advisor", "academic staff"],
    "pensyarah":        ["lecturer", "老师", "tutor", "academic staff FTSM"],
    "penyelia":         ["supervisor", "导师", "advisor FTSM"],
    "staf akademik":    ["academic staff", "lecturer", "老师 导师"],

    # ── 课程 / 项目 ──────────────────────────────────────────────────────────
    "硕士":             ["master", "sarjana", "postgraduate", "MSc FTSM"],
    "博士":             ["PhD", "doktor falsafah", "doctoral", "doctorate FTSM"],
    "本科":             ["undergraduate", "sarjana muda", "bachelor", "degree FTSM"],
    "人工智能":         ["artificial intelligence", "kecerdasan buatan", "AI program MSc"],
    "网络安全":         ["cyber security", "keselamatan siber", "MSc cyber FTSM"],
    "数据科学":         ["data science", "sains data", "MSc data science FTSM"],
    "软件工程":         ["software engineering", "kejuruteraan perisian", "MSc SE FTSM"],
    "信息技术":         ["information technology", "teknologi maklumat", "IT program FTSM"],
    "信息系统":         ["information systems", "sistem maklumat", "MSc IS FTSM"],
    "计算机科学":       ["computer science", "sains komputer", "CS program FTSM"],
    "创意媒体":         ["creative media technology", "teknologi media kreatif", "MSc CMT"],
    "sarjana":          ["master", "硕士", "postgraduate", "MSc"],
    "sarjana muda":     ["bachelor", "undergraduate", "本科", "degree program"],
    "doktor falsafah":  ["PhD", "博士", "doctoral program FTSM"],
    "kecerdasan buatan":["artificial intelligence", "AI", "人工智能 FTSM"],
    "keselamatan siber":["cyber security", "网络安全", "MSc cyber"],
    "sains data":       ["data science", "数据科学", "MSc data"],
    "sains komputer":   ["computer science", "计算机科学", "CS FTSM"],

    # ── 设施 / 校园 ──────────────────────────────────────────────────────────
    "图书馆":           ["library", "perpustakaan", "UKM library"],
    "宿舍":             ["hostel", "kolej kediaman", "residential college UKM"],
    "食堂":             ["cafeteria", "kafeteria", "kantin", "DTC"],
    "公交":             ["bus", "bas kampus", "campus bus UKM route"],
    "巴士":             ["bus", "bas", "campus bus UKM route"],
    "实验室":           ["lab", "makmal", "laboratory FTSM"],
    "停车场":           ["parking", "tempat letak kereta", "car park UKM"],
    "perpustakaan":     ["library", "图书馆", "UKM library"],
    "kolej kediaman":   ["residential college", "hostel", "宿舍 UKM"],
    "bas kampus":       ["campus bus", "公交 巴士", "UKM bus route"],
    "makmal":           ["lab", "laboratory", "实验室 FTSM"],

    # ── 假期 / 日历 ──────────────────────────────────────────────────────────
    "假期":             ["public holiday", "cuti umum", "holiday Malaysia"],
    "放假":             ["public holiday", "cuti semester", "semester break"],
    "开斋节":           ["Hari Raya Aidilfitri", "Eid", "cuti Hari Raya"],
    "春节":             ["Chinese New Year", "Tahun Baru Cina", "CNY cuti"],
    "屠妖节":           ["Deepavali", "Diwali", "cuti Deepavali"],
    "哈芝节":           ["Hari Raya Aidiladha", "Eid al-Adha", "cuti Aidiladha"],
    "国庆日":           ["Hari Merdeka", "National Day", "31 Ogos"],
    "cuti umum":        ["public holiday", "假期", "holiday Malaysia"],
    "hari raya":        ["Eid", "开斋节", "Aidilfitri", "cuti"],
    "deepavali":        ["屠妖节", "Diwali", "Indian festival holiday"],

    # ── 申请 / 入学 ──────────────────────────────────────────────────────────
    "申请":             ["apply", "permohonan", "application admission FTSM"],
    "入学":             ["admission", "kemasukan", "enrollment intake FTSM"],
    "录取":             ["offer letter", "surat tawaran", "acceptance admission"],
    "permohonan":       ["application", "申请", "admission FTSM"],
    "kemasukan":        ["admission", "入学", "enrollment UKM"],
    "surat tawaran":    ["offer letter", "录取通知", "acceptance letter UKM"],

    # ── 系统 / 平台 ──────────────────────────────────────────────────────────
    "系统":             ["system", "sistem", "portal UKM platform"],
    "学生系统":         ["student portal", "portal pelajar", "SMP system UKM"],
    "成绩":             ["result", "keputusan", "grade CGPA GPA"],
    "学费":             ["tuition fee", "yuran pengajian", "fees bayaran"],
    "portal pelajar":   ["student portal", "学生系统", "UKM student system"],
    "sistem":           ["system", "系统", "portal UKM"],
    "yuran":            ["fees", "学费", "tuition fee UKM"],
    "keputusan":        ["result", "成绩", "grade CGPA"],

    # ── 实习 ────────────────────────────────────────────────────────────────
    "实习":             ["industrial training", "latihan industri", "internship FTSM"],
    "工业培训":         ["industrial training", "latihan industri FTSM"],
    "latihan industri": ["industrial training", "实习", "internship FTSM"],
    "internship":       ["latihan industri", "实习", "industrial training FTSM"],

    # ── 联系方式 ────────────────────────────────────────────────────────────
    "联系":             ["contact", "hubungi", "email phone FTSM"],
    "电话":             ["phone", "nombor telefon", "contact number FTSM"],
    "邮箱":             ["email", "e-mel", "contact FTSM"],
    "办公室":           ["office", "pejabat", "FTSM office"],
    "hubungi":          ["contact", "联系", "phone email FTSM"],
    "pejabat":          ["office", "办公室", "FTSM office"],

    # ── 奖学金 / 经济援助 ────────────────────────────────────────────────────
    "奖学金":           ["scholarship", "biasiswa", "financial aid UKM"],
    "助学金":           ["bursary", "bantuan kewangan", "financial assistance"],
    "biasiswa":         ["scholarship", "奖学金", "financial aid UKM"],
    "bantuan kewangan": ["financial aid", "助学金 奖学金", "bursary UKM"],

    # ── 论文 / 研究 ──────────────────────────────────────────────────────────
    "论文":             ["thesis", "tesis", "dissertation research FTSM"],
    "毕业论文":         ["final year project", "FYP", "tesis sarjana muda"],
    "研究":             ["research", "penyelidikan", "research FTSM"],
    "tesis":            ["thesis", "论文", "dissertation FTSM"],
    "penyelidikan":     ["research", "研究", "research center FTSM"],
    "FYP":              ["final year project", "毕业论文", "tesis sarjana muda FTSM"],

    # ── 学生事务 ─────────────────────────────────────────────────────────────
    "学生事务":         ["student affairs", "hal ehwal pelajar", "HEP FTSM"],
    "hal ehwal pelajar":["student affairs", "学生事务", "HEP FTSM"],
    "HEJIM":            ["hal ehwal jaringan industri masyarakat", "industry engagement"],

    # ── 国际交流 ─────────────────────────────────────────────────────────────
    "交流":             ["mobility", "exchange", "program pertukaran pelajar"],
    "交换生":           ["exchange student", "pelajar pertukaran", "mobility program UKM"],
    "mobility":         ["pertukaran pelajar", "交流 交换", "exchange program UKM"],
}


class QueryPreprocessor:
    """三语查询预处理器：繁转简 + 中/英/马来语同义词扩展"""

    def __init__(self, max_expansions: int = 2):
        """
        Args:
            max_expansions: 最多额外生成几条扩展查询（避免检索太分散）
        """
        self.max_expansions = max_expansions

    def traditional_to_simplified(self, text: str) -> str:
        """繁体 -> 简体（仅对中文有效，英文和马来语不受影响）"""
        if not _OPENCC_AVAILABLE:
            return text
        return _converter.convert(text)

    def normalize(self, text: str) -> str:
        """基础归一化：全角->半角、去除多余空白"""
        text = unicodedata.normalize("NFKC", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def expand_synonyms(self, text: str) -> list[str]:
        """
        同义词扩展：扫描文本，匹配词典中的 key（大小写不敏感），
        返回扩展查询列表（不含原始查询）。
        """
        expansions: list[str] = []
        text_lower = text.lower()

        for keyword, synonyms in SYNONYM_MAP.items():
            if keyword.lower() in text_lower:
                for syn in synonyms[:self.max_expansions]:
                    candidate = f"{text} {syn}".strip()
                    if candidate not in expansions and candidate != text:
                        expansions.append(candidate)
                if len(expansions) >= self.max_expansions:
                    break
        return expansions

    def process(self, query: str) -> list[str]:
        """
        完整预处理流程，返回查询列表（第一个为主查询，其余为扩展）。

        支持输入语言：简体中文、繁体中文、English、Bahasa Melayu（混合均可）

        Args:
            query: 用户原始输入
        Returns:
            [主查询, 扩展查询1, 扩展查询2, ...]  至多 1 + max_expansions 条
        """
        simplified = self.traditional_to_simplified(query)
        normalized = self.normalize(simplified)
        expansions = self.expand_synonyms(normalized)
        return [normalized] + expansions[:self.max_expansions]


# 全局单例
preprocessor = QueryPreprocessor()


if __name__ == "__main__":
    tests = [
        # 繁体中文
        "籤證怎麼續簽",
        # 简体中文
        "硕士人工智能怎么申请",
        "图书馆在哪里",
        "导师联系方式",
        "有什么奖学金",
        # 马来语
        "bagaimana nak renew permit pelajar",
        "sarjana kecerdasan buatan FTSM",
        "bas kampus UKM",
        "biasiswa untuk pelajar antarabangsa",
        "latihan industri FTSM",
        "konvokesyen bila",
        # 英文
        "What is the master program?",
        "How to apply for scholarship?",
    ]
    for q in tests:
        result = preprocessor.process(q)
        print(f"\nInput : {q}")
        for i, r in enumerate(result):
            tag = "main " if i == 0 else f"exp{i} "
            print(f"  [{tag}] {r}")
