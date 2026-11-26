"""Skill names: one spelling per skill, in English and Traditional Chinese, and which skills are related but NOT equal.

Matching compares canonical names, so "UI設計", "ui design" and "UI Design" are one skill. An alias is added only when
the two words name the same skill. Related skills ("figma" and "ui design", "python" and "machine learning") are listed
separately: they are mentioned in explanations ("related: you have figma") but never counted as covering each other.
Keep this list short and reviewed by hand; a wrong alias silently merges different skills (java is not javascript).
"""
import re
import unicodedata

# canonical name -> other spellings of exactly the same skill
ALIASES = {
    "python": ["py", "python3", "python 3"],
    "javascript": ["js", "es6", "ecmascript"],
    "typescript": ["ts"],
    "react": ["react.js", "reactjs"],
    "node.js": ["nodejs", "node"],
    "c++": ["cpp"],
    "c#": ["csharp", "c sharp"],
    "go": ["golang"],
    "sql": ["sql database"],
    "html/css": ["html", "css", "html css", "html and css"],
    "machine learning": ["ml", "機器學習"],
    "deep learning": ["dl", "深度學習"],
    "data analysis": ["資料分析", "數據分析", "data analytics"],
    "data visualization": ["資料視覺化", "數據視覺化", "data viz", "dataviz"],
    "statistics": ["統計", "統計學"],
    "ui design": ["ui", "ui設計", "使用者介面設計", "介面設計"],
    "ux design": ["ux", "ux設計", "使用者經驗設計", "使用者體驗設計"],
    "user research": ["使用者研究", "ux research"],
    "interviews": ["訪談", "user interviews", "interviewing"],
    "graphic design": ["平面設計", "視覺設計"],
    "illustration": ["插畫"],
    "3d modeling": ["3d建模", "3d 建模", "3d modelling"],
    "video editing": ["影片剪輯", "剪輯"],
    "photography": ["攝影"],
    "copywriting": ["文案", "文案撰寫"],
    "translation": ["翻譯"],
    "public speaking": ["演講", "公開演講"],
    "pitching": ["pitch", "簡報提案"],
    "marketing": ["行銷"],
    "social media": ["社群媒體", "社群經營", "social media marketing"],
    "branding": ["品牌", "品牌設計"],
    "financial modeling": ["financial modelling", "財務模型", "財務建模"],
    "excel": ["microsoft excel", "ms excel"],
    "project management": ["專案管理"],
    "event planning": ["活動企劃", "活動規劃"],
    "research": ["研究"],
    "web development": ["網頁開發", "web dev"],
    "frontend": ["前端", "front-end", "front end"],
    "backend": ["後端", "back-end", "back end"],
    "embedded systems": ["嵌入式系統"],
    "chinese": ["中文", "mandarin", "華語"],
    "english": ["英文", "英語"],
    "japanese": ["日文", "日語"],
}

# related but different: shown as a hint, never counted as coverage (both directions)
RELATED = [
    ("figma", "ui design"), ("ui design", "ux design"), ("ux design", "user research"), ("user research", "interviews"),
    ("python", "machine learning"), ("machine learning", "deep learning"), ("python", "data analysis"),
    ("data analysis", "data visualization"), ("data analysis", "statistics"), ("javascript", "typescript"),
    ("javascript", "react"), ("react", "frontend"), ("html/css", "frontend"), ("node.js", "backend"),
    ("graphic design", "illustration"), ("graphic design", "branding"), ("marketing", "social media"),
    ("marketing", "copywriting"), ("financial modeling", "excel"), ("pitching", "public speaking"),
    ("photography", "video editing"), ("arduino", "embedded systems"), ("c", "embedded systems"),
]

SPLIT = re.compile(r"[,，、;；\n]+")


def _clean(t):
    t = unicodedata.normalize("NFKC", t or "").lower().strip(" .\t")   # full-width letters and spaces become normal ones
    return re.sub(r"\s+", " ", t)


_INDEX = {}
for _canon, _alts in ALIASES.items():
    _INDEX[_clean(_canon)] = _canon
    for _a in _alts: _INDEX[_clean(_a)] = _canon
_REL = {}
for _a, _b in RELATED:
    _REL.setdefault(_a, set()).add(_b); _REL.setdefault(_b, set()).add(_a)


def normalize(tag):
    """One canonical spelling for a skill; unknown skills keep their cleaned spelling."""
    t = _clean(tag)
    return _INDEX.get(t, t)


def tags(text):
    """Canonical skills from a comma list (English or Chinese commas), duplicates removed, order kept."""
    out = []
    for part in SPLIT.split(text or ""):
        t = normalize(part)
        if t and t not in out: out.append(t)
    return out


def related(a, b):
    """True when two canonical skills are related but different."""
    return b in _REL.get(a, set())


def related_to(skill, have):
    """Skills in `have` that are related to `skill` (never equal to it)."""
    return sorted(h for h in have if related(skill, h))
