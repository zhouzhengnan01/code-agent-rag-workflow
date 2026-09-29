"""Local Codezzn product-help FAQ used by the in-app assistant widget."""

import re

FAQ = [
    {
        "id": "projects-and-files",
        "question": "如何让智能体把代码保存成项目文件？",
        "answer": "在对话页选择或创建一个项目，并确认本次允许保存。编码智能体应调用写文件工具生成真实文件；文件会记录到该项目的 Files 面板，可预览、下载或打包下载。拒绝保存时，智能体只回答，不写项目文件。",
        "keywords": ["项目", "文件", "保存", "写代码", "产物", "project", "file"],
    },
    {
        "id": "tool-approval",
        "question": "工具审批有什么作用？",
        "answer": "写文件、Shell、Git 远端操作以及会改变网页状态的浏览器动作可以设置为需要审批。审批卡片出现时检查工具名和参数，再选择允许或拒绝；拒绝后智能体不会重试同一写操作。",
        "keywords": ["审批", "批准", "工具", "权限", "approval", "shell"],
    },
    {
        "id": "browser-tools",
        "question": "如何使用本地浏览器工具？",
        "answer": "在智能体配置中启用浏览器能力，并使用软件工程师角色。浏览器通过本机部署的 Playwright/Chromium 执行；页面状态、DOM 查找、导航、点击、键盘、截图和 PDF 等工具都受 Codezzn 的工具策略约束，不连接 Browser Use Cloud。上传文件到网站会单独请求审批。",
        "keywords": ["浏览器", "Browser Use", "网页", "截图", "Playwright", "Cloud"],
    },
    {
        "id": "skills",
        "question": "如何导入自己的 Skill？",
        "answer": "进入左侧“技能”页面导入 Skill 包。完整包可以包含 SKILL.md、scripts、references 和 assets；智能体必须在能力装配中启用对应 Skill，脚本执行仍遵守审批和隔离策略。",
        "keywords": ["技能", "Skill", "脚本", "scripts", "导入"],
    },
    {
        "id": "ragflow",
        "question": "如何配置 RAGFlow 知识库？",
        "answer": "进入“知识库”，新建或编辑知识库并选择 RAGFlow 后端，配置服务地址与 API 信息后绑定数据集；再把知识库装配到智能体。工作台中的检索结果会作为上下文提供给智能体。",
        "keywords": ["知识库", "RAGFlow", "RAG", "检索", "数据集"],
    },
    {
        "id": "account-login",
        "question": "支持哪些登录方式？",
        "answer": "登录页提供 GitHub、Google 和邮箱登录入口。第三方登录由部署方的 OAuth 配置决定；邮箱验证码需要部署方配置 SMTP/云邮件服务。",
        "keywords": ["登录", "GitHub", "Google", "邮箱", "SMTP", "验证码"],
    },
    {
        "id": "coding-role",
        "question": "哪里选择软件工程师角色？",
        "answer": "进入左侧“智能体”，新建或编辑智能体，在“身份与模型”区域的“角色模板”选择“软件工程师”。该角色使用 Browser Use 开源编码 Agent 的编码提示约定，并保留 Codezzn 的审批、项目保存和沙箱边界。",
        "keywords": ["软件工程师", "角色", "编码", "prompt", "提示词"],
    },
    {
        "id": "support-contact",
        "question": "如何获取帮助？",
        "answer": "可以搜索此帮助面板中的常见问题，或在登录工作台后向 Codezzn 本地配置的模型询问产品使用问题。此面板不连接外部 Pylon 或 Browser Use Cloud 客服。",
        "keywords": ["帮助", "客服", "支持", "联系", "FAQ"],
    },
]


def search_faq(query: str = "", limit: int = 5):
    query = " ".join(str(query or "").lower().split())
    if not query:
        return [{key: value for key, value in item.items() if key != "keywords"} for item in FAQ[:max(1, min(int(limit), 10))]]
    terms = [term for term in query.replace("?", " ").replace("？", " ").split() if term]
    ranked = []
    for item in FAQ:
        haystack = " ".join([item["question"], item["answer"], *item["keywords"]]).lower()
        # Chinese questions are usually unspaced. Match meaningful FAQ keywords
        # inside the question as well as ordinary word or exact-phrase matches.
        keyword_hits = sum(1 for keyword in item["keywords"] if str(keyword).lower() in query)
        score = (10 if query in haystack else 0) + 3 * keyword_hits + sum(haystack.count(term) for term in terms)
        if score:
            ranked.append((score, item))
    ranked.sort(key=lambda item: (-item[0], item[1]["id"]))
    return [{key: value for key, value in item.items() if key != "keywords"} for _, item in ranked[:max(1, min(int(limit), 10))]]


def asks_for_own_projects(question: str) -> bool:
    """Live account inventory is not a FAQ, and must be read from this tenant."""
    text = re.sub(r"\s+", "", str(question or "").lower())
    if not ("项目" in text or "project" in text):
        return False
    return bool(re.search(r"(?:我|当前|现有|已有|账户|账号).{0,12}(?:哪些|列表|多少|几个|所有|有什么|有哪些|列出)|(?:列出|查看|显示|告诉我).{0,12}(?:我|当前|所有).{0,8}项目|(?:my|current|existing)projects?|list(?:my)?projects?", text))
