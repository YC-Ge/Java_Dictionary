#!/usr/bin/env python3
import html
import json
import re
import ssl
import threading
import time
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HOST = "127.0.0.1"
PORT = 4173
STATIC_DIR = Path(__file__).parent / "static"
ORACLE_DOWNLOADS_URL = "https://www.oracle.com/java/technologies/downloads/"
CACHE_TTL_SECONDS = 60 * 60 * 6
NETWORK_CONTEXT = ssl._create_unverified_context()

STATE = {
    "version": None,
    "version_checked_at": 0.0,
    "indices": {},
    "index_checked_at": {},
    "package_modules": {},
    "translations": {},
}
STATE_LOCK = threading.Lock()

LANGUAGE_LABELS = {
    "zh": "Chinese",
    "es": "Spanish",
    "ja": "Japanese",
}

MANUAL_KNOWLEDGE_MAP = [
    {
        "triggers": ["左对齐", "左对齐格式化", "left justify", "left-justify", "%-", "格式化左对齐", "formatter 左对齐"],
        "result": {
            "kind": "type",
            "title": "Formatter",
            "label": "Formatter",
            "package": "java.util",
            "module": "java.base",
            "className": "Formatter",
            "anchor": "",
            "url_path": "java.base/java/util/Formatter.html",
            "subtitle": "Formatting strings, including left-justify patterns like `%-`",
        },
        "extra_terms": ["formatter", "format specifier", "left-justified", "%-", "java.util.Formatter"],
    },
    {
        "triggers": ["方法引用", "::", "lambda", "lambda表达式", "拉姆达", "->"],
        "result": {
            "kind": "package",
            "title": "java.util.function",
            "label": "java.util.function",
            "package": "java.util.function",
            "module": "java.base",
            "className": "",
            "anchor": "",
            "url_path": "java.base/java/util/function/package-summary.html",
            "subtitle": "Functional interfaces used with lambda expressions and method references",
        },
        "extra_terms": ["functional interface", "lambda expression", "method reference", "java.util.function"],
    },
    {
        "triggers": ["日期时间", "日期", "时间", "date time", "local date time"],
        "result": {
            "kind": "package",
            "title": "java.time",
            "label": "java.time",
            "package": "java.time",
            "module": "java.base",
            "className": "",
            "anchor": "",
            "url_path": "java.base/java/time/package-summary.html",
            "subtitle": "Date, time, instant, and duration APIs in the modern Java time package",
        },
        "extra_terms": ["java.time", "localdate", "localdatetime", "instant", "duration"],
    },
]

SYMBOL_QUERY_HINTS = {
    "%-": ["formatter", "left justify", "left-justified", "format specifier"],
    "%s": ["formatter", "string format", "format specifier"],
    "%d": ["formatter", "integer format", "format specifier"],
    "%f": ["formatter", "floating point format", "format specifier"],
    "->": ["lambda expression", "functional interface"],
    "::": ["method reference", "reference to method"],
    "==": ["equals operator", "comparison operator"],
    "!=": ["not equal operator", "comparison operator"],
    "&&": ["logical and operator", "boolean operator"],
    "||": ["logical or operator", "boolean operator"],
}

TERM_GLOSSARY = [
    {"triggers": ["左对齐", "左对齐格式化", "左对齐输出", "left justify", "left-justify"], "english": ["left justify", "left-justified", "formatter", "format specifier"]},
    {"triggers": ["右对齐", "右对齐格式化", "right justify", "right-justify"], "english": ["right justify", "formatter", "format specifier"]},
    {"triggers": ["格式化", "格式化输出", "formatter"], "english": ["formatter", "format", "format specifier"]},
    {"triggers": ["列表", "数组列表", "动态数组", "list"], "english": ["list", "arraylist", "collection"]},
    {"triggers": ["映射", "哈希表", "字典", "map"], "english": ["map", "hashmap", "linkedhashmap"]},
    {"triggers": ["集合", "set"], "english": ["set", "hashset", "linkedhashset"]},
    {"triggers": ["流", "流式处理", "stream"], "english": ["stream", "java.util.stream"]},
    {"triggers": ["可选值", "可选对象", "optional"], "english": ["optional"]},
    {"triggers": ["空指针", "空指针异常", "null"], "english": ["nullpointerexception", "null", "objects"]},
    {"triggers": ["字符串", "文本", "string"], "english": ["string", "stringbuilder", "charsequence"]},
    {"triggers": ["线程", "thread"], "english": ["thread", "runnable"]},
    {"triggers": ["线程池", "执行器", "并发", "executor"], "english": ["executorservice", "threadpoolexecutor", "concurrent"]},
    {"triggers": ["方法引用", "method reference"], "english": ["method reference", "::"]},
    {"triggers": ["lambda", "lambda表达式", "拉姆达"], "english": ["lambda expression", "functional interface"]},
    {"triggers": ["注解", "annotation"], "english": ["annotation"]},
    {"triggers": ["异常", "exception"], "english": ["exception", "runtimeexception"]},
    {"triggers": ["日期", "时间", "日期时间", "date time"], "english": ["localdate", "localdatetime", "instant", "duration"]},
    {"triggers": ["文件", "路径", "path", "file"], "english": ["path", "files", "file"]},
]

QUERY_REPLACEMENTS = [
    ("左对齐", "left justify"),
    ("右对齐", "right justify"),
    ("格式化输出", "format output"),
    ("格式化", "format"),
    ("数组列表", "array list"),
    ("动态数组", "array list"),
    ("列表", "list"),
    ("哈希表", "hash map"),
    ("映射", "map"),
    ("集合", "set"),
    ("流式处理", "stream"),
    ("流", "stream"),
    ("可选值", "optional"),
    ("可选对象", "optional"),
    ("空指针异常", "null pointer exception"),
    ("空指针", "null pointer"),
    ("线程池", "thread pool"),
    ("执行器", "executor"),
    ("并发", "concurrency"),
    ("线程", "thread"),
    ("方法引用", "method reference"),
    ("lambda表达式", "lambda expression"),
    ("拉姆达", "lambda"),
    ("注解", "annotation"),
    ("异常", "exception"),
    ("字符串", "string"),
    ("日期时间", "date time"),
    ("日期", "date"),
    ("时间", "time"),
    ("文件", "file"),
    ("路径", "path"),
]


def fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "JavaStudyApp/1.0",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, context=NETWORK_CONTEXT, timeout=20) as response:
        return response.read().decode("utf-8", "ignore")


def get_latest_jdk_version() -> int:
    now = time.time()
    with STATE_LOCK:
        if STATE["version"] and now - STATE["version_checked_at"] < CACHE_TTL_SECONDS:
            return STATE["version"]

    downloads_html = fetch_text(ORACLE_DOWNLOADS_URL)
    match = re.search(r"Java SE Development Kit\s+(\d+)", downloads_html)
    version = int(match.group(1)) if match else 26

    with STATE_LOCK:
        STATE["version"] = version
        STATE["version_checked_at"] = now

    return version


def docs_base(version: int) -> str:
    return f"https://docs.oracle.com/en/java/javase/{version}/docs/api/"


def parse_search_index(js_payload: str) -> list[dict]:
    start = js_payload.find("[")
    end = js_payload.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Unable to locate JSON array in Oracle search index payload.")
    return json.loads(js_payload[start:end + 1])


def load_index(index_name: str, version: int) -> list[dict]:
    now = time.time()
    with STATE_LOCK:
        cached = STATE["indices"].get(index_name)
        checked_at = STATE["index_checked_at"].get(index_name, 0.0)
        if cached is not None and now - checked_at < CACHE_TTL_SECONDS:
            return cached

    parsed = parse_search_index(fetch_text(f"{docs_base(version)}{index_name}-search-index.js"))

    with STATE_LOCK:
        STATE["indices"][index_name] = parsed
        STATE["index_checked_at"][index_name] = now
        if index_name == "package":
            STATE["package_modules"] = {item["l"]: item.get("m", "") for item in parsed}

    return parsed


def ensure_indices(version: int) -> dict[str, list[dict]]:
    indices = {
        "module": load_index("module", version),
        "package": load_index("package", version),
        "type": load_index("type", version),
        "member": load_index("member", version),
        "tag": load_index("tag", version),
    }
    if not STATE["package_modules"]:
        STATE["package_modules"] = {item["l"]: item.get("m", "") for item in indices["package"]}
    return indices


def package_to_module(package_name: str) -> str:
    return STATE["package_modules"].get(package_name, "")


def score_match(query: str, *values: str) -> int:
    q = query.casefold().strip()
    best = 0
    for value in values:
        if not value:
            continue
        normalized = value.casefold()
        if normalized == q:
            best = max(best, 140)
        elif normalized.startswith(q):
            best = max(best, 110)
        elif q in normalized:
            best = max(best, 80)
        elif all(part in normalized for part in q.split()):
            best = max(best, 60)
    return best


def normalize_query(query: str) -> str:
    normalized = query.strip().casefold()
    normalized = normalized.translate(str.maketrans({"，": ",", "：": ":", "（": "(", "）": ")", "【": "[", "】": "]", "“": "\"", "”": "\"", "　": " "}))
    return re.sub(r"\s+", " ", normalized)


def contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


def translate_query_to_english(query: str) -> str:
    normalized = normalize_query(query)
    if not normalized:
        return ""

    now = time.time()
    with STATE_LOCK:
        cached = STATE["translations"].get(normalized)
        if cached and now - cached["checked_at"] < CACHE_TTL_SECONDS:
            return cached["value"]

    url = (
        "https://translate.googleapis.com/translate_a/single"
        f"?client=gtx&sl=auto&tl=en&dt=t&q={urllib.parse.quote(query)}"
    )
    translated = ""
    try:
        payload = fetch_text(url)
        data = json.loads(payload)
        translated = compact_text("".join(part[0] for part in data[0] if part and part[0]))
    except Exception:
        translated = ""

    with STATE_LOCK:
        STATE["translations"][normalized] = {"value": translated, "checked_at": now}

    return translated


def expand_search_queries(query: str) -> list[str]:
    normalized = normalize_query(query)
    if not normalized:
        return []

    candidates = [query.strip()]
    seen = {normalized}

    def add_candidate(value: str) -> None:
        compact = compact_text(value)
        if not compact:
            return
        key = normalize_query(compact)
        if key in seen:
            return
        seen.add(key)
        candidates.append(compact)

    for symbol, hints in SYMBOL_QUERY_HINTS.items():
        if symbol in normalized:
            for hint in hints:
                add_candidate(hint)

    replaced = normalized
    for source, target in sorted(QUERY_REPLACEMENTS, key=lambda item: len(item[0]), reverse=True):
        if source in replaced:
            replaced = replaced.replace(source, target)
    if replaced != normalized:
        add_candidate(replaced)

    for entry in TERM_GLOSSARY:
        if any(normalize_query(trigger) in normalized for trigger in entry["triggers"]):
            for english in entry["english"]:
                add_candidate(english)

    if contains_cjk(query):
        translated = translate_query_to_english(query)
        if translated:
            add_candidate(translated)

    return candidates


def lookup_manual_knowledge(queries: list[str], version: int) -> tuple[list[dict], list[str]]:
    normalized_queries = {normalize_query(query) for query in queries if compact_text(query)}
    manual_results = []
    expanded_terms = []

    for item in MANUAL_KNOWLEDGE_MAP:
        normalized_triggers = {normalize_query(trigger) for trigger in item["triggers"]}
        if normalized_queries.isdisjoint(normalized_triggers):
            continue

        result = dict(item["result"])
        result["url"] = urllib.parse.urljoin(docs_base(version), result.pop("url_path"))
        manual_results.append(result)
        expanded_terms.extend(item.get("extra_terms", []))

    return manual_results, expanded_terms


def join_doc_path(*parts: str) -> str:
    return "/".join(part.strip("/") for part in parts if part)


def build_result(item: dict, kind: str, version: int) -> dict:
    package_name = item.get("p", "")
    module_name = item.get("m") or package_to_module(package_name)
    label = item.get("l", "")
    class_name = item.get("c", "")
    anchor = urllib.parse.quote(item.get("u") or label, safe="(),.$_-")

    if kind == "module":
        path = join_doc_path(label, "module-summary.html")
        title = label
        subtitle = "Java module"
    elif kind == "package":
        path = join_doc_path(module_name, package_name.replace(".", "/"), "package-summary.html")
        title = package_name
        subtitle = f"Package in {module_name or 'latest JDK'}"
    elif kind == "type":
        path = join_doc_path(module_name, package_name.replace(".", "/"), f"{label}.html")
        title = label
        subtitle = f"Type in {package_name}"
    elif kind == "member":
        path = join_doc_path(module_name, package_name.replace(".", "/"), f"{class_name}.html")
        title = f"{class_name}.{label}"
        subtitle = f"Member in {package_name}"
    else:
        holder = item.get("h", "")
        path = join_doc_path(module_name, package_name.replace(".", "/"), f"{holder}.html") if holder else ""
        title = label
        subtitle = f"Search tag in {package_name or module_name}"

    return {
        "kind": kind,
        "title": title,
        "label": label,
        "package": package_name,
        "module": module_name,
        "className": class_name,
        "anchor": item.get("u") or label,
        "url": f"{urllib.parse.urljoin(docs_base(version), path)}#{anchor}" if kind in {"member", "tag"} and anchor else urllib.parse.urljoin(docs_base(version), path),
        "subtitle": subtitle,
    }


def search_docs(query: str, version: int) -> list[dict]:
    expanded_queries = expand_search_queries(query)
    manual_results, expanded_terms = lookup_manual_knowledge(expanded_queries, version)
    indices = ensure_indices(version)
    ranked = []
    candidate_queries = []
    seen_queries = set()
    for candidate in [query, *expanded_queries, *expanded_terms]:
        normalized = normalize_query(candidate)
        if not normalized or normalized in seen_queries:
            continue
        seen_queries.add(normalized)
        candidate_queries.append(candidate)

    for kind, items in indices.items():
        for item in items:
            score = max(
                score_match(candidate_query, item.get("l", ""), item.get("p", ""), item.get("c", ""))
                for candidate_query in candidate_queries
            )
            if score <= 0:
                continue
            score += {"type": 12, "member": 8, "package": 6, "module": 4, "tag": 2}[kind]
            ranked.append((score, build_result(item, kind, version)))

    for manual_result in manual_results:
        ranked.append((1000, manual_result))

    ranked.sort(key=lambda pair: (-pair[0], pair[1]["title"]))
    unique = []
    seen = set()
    for _, result in ranked:
        key = (result["kind"], result["title"], result["url"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(result)
        if len(unique) >= 12:
            break
    return unique


def strip_html(raw: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", raw, flags=re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S)
    text = re.sub(r"<code>(.*?)</code>", r"`\1`", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def extract_title(page_html: str) -> str:
    for pattern in [
        r"<h1[^>]*class=\"title\"[^>]*>(.*?)</h1>",
        r"<h1[^>]*>(.*?)</h1>",
        r"<title>(.*?)</title>",
    ]:
        match = re.search(pattern, page_html, re.S)
        if match:
            return strip_html(match.group(1))
    return "Java Documentation"


def extract_meta_description(page_html: str) -> str:
    for pattern in [
        r'<meta\s+name="description"\s+content="(.*?)"',
        r'<meta\s+property="og:description"\s+content="(.*?)"',
    ]:
        match = re.search(pattern, page_html, re.I | re.S)
        if match:
            return compact_text(html.unescape(match.group(1)))
    return ""


def extract_signature(page_html: str) -> str:
    for pattern in [
        r"<div class=\"type-signature\"[^>]*>(.*?)</div>",
        r"<div class=\"member-signature\"[^>]*>(.*?)</div>",
        r"<pre[^>]*class=\"[^\">]*signature[^\">]*\"[^>]*>(.*?)</pre>",
    ]:
        match = re.search(pattern, page_html, re.S)
        if match:
            return strip_html(match.group(1))
    return ""


def extract_summary(page_html: str, anchor: str = "") -> str:
    if anchor:
        decoded = urllib.parse.unquote(anchor)
        for pattern in [
            rf'id="{re.escape(decoded)}"',
            rf'id="{re.escape(anchor)}"',
        ]:
            match = re.search(pattern, page_html)
            if not match:
                continue
            window = page_html[match.start():match.start() + 5000]
            block = re.search(r"<div class=\"block\">(.*?)</div>", window, re.S)
            if block:
                summary = strip_html(block.group(1))
                if summary:
                    return summary

    for pattern in [
        r"<section class=\"class-description\".*?<div class=\"block\">(.*?)</div>",
        r"<section class=\"package-description\".*?<div class=\"block\">(.*?)</div>",
        r"<main[^>]*>.*?<div class=\"block\">(.*?)</div>",
        r"<div class=\"block\">(.*?)</div>",
    ]:
        match = re.search(pattern, page_html, re.S)
        if match:
            summary = strip_html(match.group(1))
            if summary:
                return summary

    meta_description = extract_meta_description(page_html)
    if meta_description:
        return meta_description

    title = extract_title(page_html)
    return f"Official Oracle Java documentation page for {title}."


def build_chinese_explanation(result: dict, summary: str, signature: str) -> str:
    title = result["title"]
    package_name = result["package"] or result["module"] or "Java 标准库"
    kind = result["kind"]
    summary_head = summary.split(". ")[0].strip() if summary else ""

    base = {
        "type": f"`{title}` 是 `{package_name}` 中的一个类型。理解它时，先抓住它在官方摘要里的核心职责，再去看构造器、常用方法和使用限制。",
        "member": f"`{result['label']}` 是 `{result['className']}` 里的一个成员。阅读时要先确认它解决什么问题、接收什么参数，以及返回什么结果。",
        "package": f"`{title}` 是一个包级主题，适合先建立整体概念，再继续下钻到里面最常用的类、接口或工具方法。",
        "module": f"`{title}` 是最新 JDK 的模块。可以把它理解为一组相关包和能力的组织边界。",
        "tag": f"`{title}` 是官方文档中的一个重点标签，通常对应某个更聚焦的知识点入口。",
    }.get(kind, f"`{title}` 来自最新 Oracle Java 文档，可以围绕官方概念继续展开学习。")

    extra = f"官方摘要里最先强调的是：{summary_head}。" if summary_head else ""
    signature_note = f"如果签名已给出，接下来重点看它的参数、返回值、异常和适用场景。" if signature else "接下来重点看它在官方页面中的定位、方法说明和适用场景。"
    return f"{base}{extra}{signature_note}"


def build_official_concept_summary(result: dict, summary: str, signature: str) -> list[str]:
    title = result["title"]
    package_name = result["package"] or result["module"] or "Java 标准库"
    first_sentence = summary.split(". ")[0].strip() if summary else f"{title} 是 Oracle 官方文档中的一个 Java 概念。"

    points = [
        f"官方概念定位：{first_sentence}",
        f"所属位置：模块 `{result['module'] or 'latest JDK'}`，包 `{package_name}`。",
        f"学习重点：先确认 `{title}` 在官方定义中负责什么，再区分它适合的输入、输出和边界条件。",
    ]
    if signature:
        points.append(f"签名关注点：{signature}")
    else:
        points.append("签名关注点：优先查看官方页面中的构造器、方法列表或成员定义，确认实际可调用方式。")
    points.append("延伸阅读建议：继续查看官方页面中的方法说明、异常、线程安全说明以及 `Since` 信息。")
    return points


def build_interview_qa(result: dict, lang: str) -> list[dict]:
    title = result["title"]
    package_name = result["package"] or result["module"] or "the JDK"
    qa_en = [
        {
            "question": f"What is `{title}` and when would you choose it?",
            "answer": f"It is an API from `{package_name}`. A strong answer should explain its role from the Oracle summary and when it fits the problem.",
        },
        {
            "question": f"What details should you verify before using `{title}` in production code?",
            "answer": "Check the signature, parameter and return types, exceptions, null-handling, ordering behavior, concurrency expectations, and any `Since` markers.",
        },
        {
            "question": f"How would you explain `{title}` to a junior developer?",
            "answer": "Start from the official summary, then show one small example, then contrast it with a nearby alternative in the same package.",
        },
    ]

    if lang == "zh":
        qa_secondary = [
            {"question": f"`{title}` 是什么，什么场景下适合用它？", "answer": "先说清它在标准库中的定位，再说明适合解决的问题，最后补充限制或代价。"},
            {"question": f"使用 `{title}` 前你会重点确认哪些官方信息？", "answer": "重点看签名、参数、返回值、异常、是否允许空值、是否线程安全，以及版本引入说明。"},
            {"question": f"如果面试官让你举例说明 `{title}`，你会怎么答？", "answer": "先给一个最小可运行示例，再说明为什么它比相近 API 更适合当前场景。"},
        ]
    elif lang == "es":
        qa_secondary = [
            {"question": f"Que es `{title}` y en que escenario conviene usarlo?", "answer": "Explica su funcion dentro del JDK, el problema que resuelve y las restricciones importantes."},
            {"question": f"Que revisarias en la documentacion oficial antes de usar `{title}`?", "answer": "Firma, parametros, retorno, excepciones, null, concurrencia, orden y notas de version."},
            {"question": f"Como lo explicarias en una entrevista tecnica?", "answer": "Primero define el API, luego muestra un ejemplo corto y finalmente compara con una alternativa cercana."},
        ]
    else:
        qa_secondary = [
            {"question": f"`{title}` とは何で、どんな場面で使いますか。", "answer": "JDK 内での役割、解決する問題、使用時の制約やトレードオフを順に説明すると良いです。"},
            {"question": f"`{title}` を使う前に公式ドキュメントのどこを確認しますか。", "answer": "シグネチャ、引数、戻り値、例外、null 許容、並行性、順序、Since 情報を確認します。"},
            {"question": f"面接で `{title}` をどう説明しますか。", "answer": "まず定義、次に短い例、最後に近い API との違いを話すと伝わりやすいです。"},
        ]

    return [{"en": en, "secondary": sec} for en, sec in zip(qa_en, qa_secondary)]


def workspace_java_note() -> str:
    java_files = sorted(path.name for path in Path(__file__).parent.rglob("*.java"))
    if java_files:
        preview = ", ".join(java_files[:3])
        return f"Related local Java source files found in this workspace: {preview}."
    return "Related local Java source files found in this workspace: none."


def build_commented_example(
    *,
    title: str,
    imports: str,
    body: str,
    concept_en: str,
    concept_zh: str,
    usage_en: str,
    usage_zh: str,
    input_guide: str,
    output: str,
    label: str,
    note_zh: str,
    input_text: str = "",
) -> dict:
    code = f"""/*
 * NOTE: Java term = {label}
 * NOTE: Concept (EN): {concept_en}
 * NOTE: Concept (ZH): {concept_zh}
 * NOTE: Practical usage (EN): {usage_en}
 * NOTE: Practical usage (ZH): {usage_zh}
 * NOTE: Workspace context: {workspace_java_note()}
 * NOTE: Suggested terminal input after Run: {input_guide}
 * NOTE: Expected output after using the suggested input:
 * {output.replace(chr(10), chr(10) + ' * ')}
 */
{imports}
public class Example {{
    public static void main(String[] args) throws Exception {{
{body}
    }}
}}"""
    return {
        "title": title,
        "code": code,
        "input": input_text,
        "output": output,
        "notes": {
            "en": "The concept, input guidance, and expected output are embedded directly in the code comments.",
            "zh": note_zh,
        },
    }


def generate_example(result: dict) -> dict:
    title = result["title"]
    class_name = result["className"] or result["label"]
    label = result["label"]
    package_name = result["package"] or "java.base"

    if "ArrayList" in title:
        return build_commented_example(
            title="ArrayList runnable example",
            imports="import java.util.ArrayList;\nimport java.util.List;\nimport java.util.Scanner;\n",
            body="""        Scanner scanner = new Scanner(System.in);
        List<String> names = new ArrayList<>();

        names.add(scanner.nextLine());
        names.add(scanner.nextLine());

        System.out.println("First = " + names.get(0));
        System.out.println("Size = " + names.size());""",
            concept_en="ArrayList is a resizable ordered collection.",
            concept_zh="ArrayList 是一个可动态扩容且保持顺序的集合。",
            usage_en="Use it when records need to be added in order and read back later, such as search results or user-entered items.",
            usage_zh="适合按顺序收集和读取数据，例如搜索结果、表单输入、待处理列表。",
            input_guide="Type: Ada, then Linus",
            output="First = Ada\nSize = 2",
            label=label,
            note_zh="概念、输入指导和正确输出已经直接写在代码注释里；复制到 VS Code 后运行并按注释输入即可。",
            input_text="Ada\nLinus\n",
        )

    if "Stream" in title or "BaseStream" in title:
        return build_commented_example(
            title="Stream runnable example",
            imports="import java.util.Arrays;\nimport java.util.Scanner;\nimport java.util.stream.Stream;\n",
            body="""        Scanner scanner = new Scanner(System.in);
        String line = scanner.nextLine();

        Stream<String> rawItems = Arrays.stream(line.split(","));
        int sumOfSquares = rawItems
                .map(String::trim)
                .mapToInt(Integer::parseInt)
                .map(n -> n * n)
                .filter(n -> n > 10)
                .sum();

        System.out.println("Result = " + sumOfSquares);""",
            concept_en="Stream expresses multi-step data processing as a readable pipeline.",
            concept_zh="Stream 用可读的流水线方式表达多步数据处理。",
            usage_en="Use it for filtering, mapping, and aggregating collections without manual loops everywhere.",
            usage_zh="适合做过滤、转换、聚合等集合处理，减少到处手写循环。",
            input_guide="Type exactly: 1,2,3,4,5",
            output="Result = 41",
            label=label,
            note_zh="这段代码会在 terminal 中等待输入；请按注释里的示例输入，得到与注释一致的输出。",
            input_text="1,2,3,4,5\n",
        )

    if "Optional" in title:
        return build_commented_example(
            title="Optional runnable example",
            imports="import java.util.Optional;\nimport java.util.Scanner;\n",
            body="""        Scanner scanner = new Scanner(System.in);
        String rawNickname = scanner.nextLine();

        Optional<String> nickname = Optional.ofNullable(rawNickname.isBlank() ? null : rawNickname);
        String displayName = nickname.orElse("guest");

        System.out.println("Display name = " + displayName);""",
            concept_en="Optional models a value that may be present or absent.",
            concept_zh="Optional 用来表达一个值可能存在也可能不存在。",
            usage_en="Use it to make fallback behavior explicit when user input or lookup results may be missing.",
            usage_zh="当用户输入或查找结果可能缺失时，用它可以把兜底逻辑写得更清楚。",
            input_guide="Press Enter on an empty line",
            output="Display name = guest",
            label=label,
            note_zh="如果示例需要输入，terminal 会等待你输入；按注释里的建议输入即可复现正确结果。",
            input_text="\n",
        )

    if "Map" in title or "HashMap" in title:
        return build_commented_example(
            title="Map runnable example",
            imports="import java.util.HashMap;\nimport java.util.Map;\nimport java.util.Scanner;\n",
            body="""        Scanner scanner = new Scanner(System.in);
        Map<String, Integer> scores = new HashMap<>();
        scores.put("Alice", 90);
        scores.put("Bob", 85);

        String student = scanner.nextLine();

        System.out.println("Score = " + scores.getOrDefault(student, 0));""",
            concept_en="Map stores values by key and is useful for fast lookup.",
            concept_zh="Map 通过 key 存储和查找 value，适合快速映射。",
            usage_en="Use it for ID lookup, configuration tables, grouped values, and name-to-value mappings.",
            usage_zh="适合做 ID 查找、配置表、分组结果和名称到数值的映射。",
            input_guide="Type exactly: Bob",
            output="Score = 85",
            label=label,
            note_zh="代码注释中已经包含 concept、输入示例和正确输出；页面不再拆成多个板块。",
            input_text="Bob\n",
        )

    if "Formatter" in title:
        return build_commented_example(
            title="Formatter runnable example",
            imports="import java.util.Scanner;\n",
            body="""        Scanner scanner = new Scanner(System.in);
        String word = scanner.nextLine();

        System.out.printf("|%-10s|%n", word);
        System.out.printf("|%10s|%n", word);""",
            concept_en="Formatter controls alignment and formatting in text output.",
            concept_zh="Formatter 用来控制文本输出的对齐和格式。",
            usage_en="Use it for reports, tables, receipts, and any terminal output that must stay aligned.",
            usage_zh="适合报表、表格、清单和任何需要整齐对齐的终端输出。",
            input_guide="Type exactly: Java",
            output="|Java      |\n|      Java|",
            label=label,
            note_zh="如果你搜索的是左对齐、右对齐或 %-，这类说明现在会直接写进代码注释里。",
            input_text="Java\n",
        )

    if title == "java.util.function" or "FunctionalInterface" in title:
        return build_commented_example(
            title="Method reference runnable example",
            imports="import java.util.Scanner;\nimport java.util.function.Function;\n",
            body="""        Scanner scanner = new Scanner(System.in);
        Function<String, Integer> parser = Integer::parseInt;

        String raw = scanner.nextLine();

        int parsed = parser.apply(raw);
        System.out.println("Parsed = " + parsed);
        System.out.println("Doubled = " + (parsed * 2));""",
            concept_en="Method references reuse an existing method as behavior passed into Java code.",
            concept_zh="方法引用把已有方法当作行为传入代码中，常与函数式接口一起使用。",
            usage_en="Use it when converting, parsing, or delegating small behaviors in Streams and callback-style code.",
            usage_zh="适合在 Stream、转换器、回调代码里传入小型行为，代码会更简洁。",
            input_guide="Type exactly: 21",
            output="Parsed = 21\nDoubled = 42",
            label=label,
            note_zh="注释里会直接告诉使用者该输入什么，以及正确输出应该是什么。",
            input_text="21\n",
        )

    if "ExecutorService" in title or "ThreadPoolExecutor" in title or "Executors" in title:
        return build_commented_example(
            title="ExecutorService runnable example",
            imports="import java.util.ArrayList;\nimport java.util.List;\nimport java.util.Scanner;\nimport java.util.concurrent.ExecutorService;\nimport java.util.concurrent.Executors;\nimport java.util.concurrent.Future;\nimport java.util.concurrent.TimeUnit;\n",
            body="""        Scanner scanner = new Scanner(System.in);
        int taskCount = Integer.parseInt(scanner.nextLine());

        ExecutorService pool = Executors.newFixedThreadPool(2);
        List<Future<String>> futures = new ArrayList<>();

        for (int i = 1; i <= taskCount; i++) {
            int taskId = i;
            futures.add(pool.submit(() -> "task " + taskId + " done"));
        }

        for (Future<String> future : futures) {
            System.out.println(future.get());
        }

        pool.shutdown();
        pool.awaitTermination(5, TimeUnit.SECONDS);""",
            concept_en="ExecutorService manages reusable worker threads for concurrent tasks.",
            concept_zh="ExecutorService 管理可复用的工作线程，用于并发任务执行。",
            usage_en="Use it for background jobs, batch work, and asynchronous task handling instead of creating raw threads manually.",
            usage_zh="适合后台任务、批处理、异步任务，不建议大量手写原始 Thread。",
            input_guide="Type exactly: 3",
            output="task 1 done\ntask 2 done\ntask 3 done",
            label=label,
            note_zh="为了保证输出稳定，代码会按 Future 提交顺序打印结果；注释中的 output 与实际运行结果一致。",
            input_text="3\n",
        )

    if "NullPointerException" in title or title == "Objects":
        return build_commented_example(
            title="Null-safety runnable example",
            imports="import java.util.Objects;\nimport java.util.Scanner;\n",
            body="""        Scanner scanner = new Scanner(System.in);
        String raw = scanner.nextLine();

        String normalized = raw.isBlank() ? null : raw;
        String safeName = Objects.requireNonNullElse(normalized, "guest");

        System.out.println("Uppercase = " + safeName.toUpperCase());""",
            concept_en="Null-safety APIs help you avoid deeper bugs by handling missing values explicitly.",
            concept_zh="空值安全相关 API 能帮助你显式处理缺失值，避免更深层的 Bug。",
            usage_en="Use them near input boundaries, constructors, and service methods where null values must be controlled early.",
            usage_zh="适合放在输入边界、构造器和服务入口，尽早控制 null 值带来的风险。",
            input_guide="Press Enter on an empty line",
            output="Uppercase = GUEST",
            label=label,
            note_zh="这里的输入指导和 output 都写在代码注释里，运行时终端会真正等待用户输入。",
            input_text="\n",
        )

    if title == "java.time" or "LocalDate" in title or "LocalDateTime" in title or "Instant" in title or "Duration" in title:
        return build_commented_example(
            title="java.time runnable example",
            imports="import java.time.Duration;\nimport java.time.LocalDateTime;\nimport java.util.Scanner;\n",
            body="""        Scanner scanner = new Scanner(System.in);
        long minutes = Long.parseLong(scanner.nextLine());

        LocalDateTime start = LocalDateTime.of(2026, 1, 1, 9, 0);
        LocalDateTime end = start.plusMinutes(minutes);
        Duration duration = Duration.between(start, end);

        System.out.println("Minutes = " + duration.toMinutes());""",
            concept_en="java.time provides modern immutable classes for time and duration calculations.",
            concept_zh="java.time 提供现代且不可变的时间与时长计算类。",
            usage_en="Use it for scheduling, timestamps, booking logic, and elapsed-time calculations in business systems.",
            usage_zh="适合排期、时间戳、预约系统和业务中的耗时计算。",
            input_guide="Type exactly: 150",
            output="Minutes = 150",
            label=label,
            note_zh="这类时间计算示例非常适合做交互式输入，因为用户能立刻看到输入和输出之间的对应关系。",
            input_text="150\n",
        )

    if "String" in title or "CharSequence" in title or "StringBuilder" in title:
        return build_commented_example(
            title="StringBuilder runnable example",
            imports="import java.util.Scanner;\n",
            body="""        Scanner scanner = new Scanner(System.in);
        String word = scanner.nextLine();

        StringBuilder builder = new StringBuilder();
        builder.append("Hello");
        builder.append(", ");
        builder.append(word);

        String message = builder.toString();
        System.out.println(message);
        System.out.println("Length = " + message.length());""",
            concept_en="StringBuilder is useful when building text in multiple steps.",
            concept_zh="StringBuilder 适合分步骤构建文本内容。",
            usage_en="Use it for log messages, reports, generated text, or loops that append many fragments.",
            usage_zh="适合日志、报表、文本生成，以及循环中多次拼接字符串的场景。",
            input_guide="Type exactly: Java",
            output="Hello, Java\nLength = 11",
            label=label,
            note_zh="concept、输入方式和正确 output 都放进代码注释后，复制体验会更直接。",
            input_text="Java\n",
        )

    if "List" in title:
        return build_commented_example(
            title="List runnable example",
            imports="import java.util.List;\nimport java.util.Scanner;\n",
            body="""        Scanner scanner = new Scanner(System.in);
        String[] parts = scanner.nextLine().split(",");

        List<String> topics = List.of(parts[0].trim(), parts[1].trim(), parts[2].trim());
        for (String topic : topics) {
            System.out.println(topic);
        }""",
            concept_en="List represents an ordered sequence of values.",
            concept_zh="List 表示一组有顺序的值。",
            usage_en="Use it whenever order matters, such as menus, task lists, and returned records.",
            usage_zh="适合菜单、任务列表、接口返回记录等顺序有意义的场景。",
            input_guide="Type exactly: ArrayList, Stream, Optional",
            output="ArrayList\nStream\nOptional",
            label=label,
            note_zh="我保留了单一代码板块的形式，相关讲解都集中在注释里。",
            input_text="ArrayList, Stream, Optional\n",
        )

    if result["kind"] == "type" and result["package"] and label:
        full_name = f"{result['package']}.{label}"
        code = f"""/*
 * NOTE: Java term = {label}
 * NOTE: Concept (EN): `{label}` is used directly through Java reflection so the snippet still performs a real operation on the searched type.
 * NOTE: Concept (ZH): 这里直接通过 Java 反射操作 `{label}`，确保搜索到的类型真的参与代码执行。
 * NOTE: Workspace context: {workspace_java_note()}
 * NOTE: Suggested terminal input after Run: no input required for this starter.
 * NOTE: Expected output after Run:
 * Type = {full_name}
 * Simple name = {label}
 */
public class Example {{
    public static void main(String[] args) throws Exception {{
        Class<?> apiType = Class.forName("{full_name}");
        System.out.println("Type = " + apiType.getName());
        System.out.println("Simple name = " + apiType.getSimpleName());
    }}
}}"""
        return {
            "title": f"{class_name.split('.')[-1] if class_name else 'TargetType'} reflection example",
            "code": code,
            "input": "",
            "output": f"Type = {full_name}\nSimple name = {label}",
            "notes": {
                "en": "The searched Java type is used directly in reflection-based code.",
                "zh": "搜索到的 Java 类型会直接参与反射代码执行，而不是只被打印成说明文字。",
            },
        }

    if result["kind"] == "member" and result["package"] and result["className"] and label:
        owner_type = f"{result['package']}.{result['className']}"
        member_name = label.split("(")[0]
        code = f"""/*
 * NOTE: Java term = {label}
 * NOTE: Concept (EN): This snippet inspects the searched member on its owning Java type.
 * NOTE: Concept (ZH): 这个示例会在所属类型上检查搜索到的成员，保证成员本体参与实际代码。
 * NOTE: Workspace context: {workspace_java_note()}
 * NOTE: Suggested terminal input after Run: no input required for this starter.
 * NOTE: Expected output after Run:
 * Owner type = {owner_type}
 * Matching methods = shown below as a count
 */
public class Example {{
    public static void main(String[] args) throws Exception {{
        Class<?> owner = Class.forName("{owner_type}");
        long count = java.util.Arrays.stream(owner.getDeclaredMethods())
                .filter(method -> method.getName().equals("{member_name}"))
                .count();
        System.out.println("Owner type = " + owner.getName());
        System.out.println("Matching methods = " + count);
    }}
}}"""
        return {
            "title": f"{class_name.split('.')[-1] if class_name else 'Member'} reflection example",
            "code": code,
            "input": "",
            "output": f"Owner type = {owner_type}\nMatching methods = 1" if member_name else f"Owner type = {owner_type}\nMatching methods = 0",
            "notes": {
                "en": "The searched member is inspected directly on its declaring class.",
                "zh": "搜索到的成员会在其声明类上被直接检查，而不是只出现在输出说明里。",
            },
        }

    if result["kind"] == "package" and result["package"]:
        package_literal = result["package"]
        code = f"""/*
 * NOTE: Java term = {label}
 * NOTE: Concept (EN): This snippet searches the runtime package list for the selected Java package.
 * NOTE: Concept (ZH): 这个示例会在运行时包列表里查找当前搜索到的 Java 包。
 * NOTE: Workspace context: {workspace_java_note()}
 * NOTE: Suggested terminal input after Run: no input required for this starter.
 * NOTE: Expected output after Run:
 * Package = {package_literal}
 * Package present = true
 */
import java.util.Arrays;

public class Example {{
    public static void main(String[] args) {{
        boolean present = Arrays.stream(Package.getPackages())
                .map(Package::getName)
                .anyMatch(name -> name.equals("{package_literal}"));
        System.out.println("Package = {package_literal}");
        System.out.println("Package present = " + present);
    }}
}}"""
        return {
            "title": f"{class_name.split('.')[-1] if class_name else 'Package'} package example",
            "code": code,
            "input": "",
            "output": f"Package = {package_literal}\nPackage present = true",
            "notes": {
                "en": "The searched Java package is checked directly in runtime metadata.",
                "zh": "搜索到的 Java 包会直接参与运行时元数据检查。",
            },
        }

    code = f"""/*
 * NOTE: Java term = {label}
 * NOTE: Concept (EN): `{label}` is the selected Java topic.
 * NOTE: Concept (ZH): `{label}` 是当前选中的 Java 知识点。
 * NOTE: Workspace context: {workspace_java_note()}
 * NOTE: Suggested terminal input after Run: no input required for this starter.
 * NOTE: Expected output after Run:
 * Package = {package_name}
 * Kind = {result['kind']}
 */
public class Example {{
    public static void main(String[] args) {{
        String packageName = "{package_name}";
        String kind = "{result['kind']}";
        System.out.println("Package = " + packageName);
        System.out.println("Kind = " + kind);
    }}
}}"""
    return {
        "title": f"{class_name.split('.')[-1] if class_name else 'TargetType'} runnable starter example",
        "code": code,
        "input": "",
        "output": f"Package = {package_name}\nKind = {result['kind']}",
        "notes": {
            "en": "Concept notes and the expected output are embedded directly in the code comments.",
            "zh": "讲解、输入指导和正确输出都已经直接写进代码注释中。",
        },
    }


def lookup_document(url: str, result: dict, lang: str) -> dict:
    page_html = fetch_text(url)
    title = extract_title(page_html)
    signature = extract_signature(page_html)
    summary = extract_summary(page_html, result.get("anchor", ""))
    if not compact_text(summary):
        summary = f"Official Oracle Java documentation page for {title or result['title']}."
    return {
        "pageTitle": title,
        "officialExcerpt": summary,
        "signature": signature,
        "chineseExplanation": build_chinese_explanation(result, summary, signature),
        "conceptSummary": build_official_concept_summary(result, summary, signature),
        "interviewQA": build_interview_qa(result, lang),
        "example": generate_example(result),
    }


def json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)
        try:
            if path == "/api/health":
                json_response(self, {"ok": True, "service": "java-study-app"})
                return
            if path == "/api/config":
                version = get_latest_jdk_version()
                json_response(self, {"ok": True, "latestJdkVersion": version, "docsBaseUrl": docs_base(version), "defaultLanguages": ["en", "zh"], "supportedSecondLanguages": ["zh", "es", "ja"]})
                return
            if path == "/api/search":
                query = (params.get("q") or [""])[0].strip()
                lang = (params.get("lang") or ["zh"])[0]
                if not query:
                    json_response(self, {"ok": False, "error": "Missing q parameter."}, status=400)
                    return
                version = get_latest_jdk_version()
                results = search_docs(query, version)
                doc = lookup_document(results[0]["url"], results[0], lang) if results else None
                json_response(self, {"ok": True, "query": query, "latestJdkVersion": version, "results": results, "selected": results[0] if results else None, "document": doc})
                return
            if path == "/api/doc":
                url = (params.get("url") or [""])[0]
                lang = (params.get("lang") or ["zh"])[0]
                if not url:
                    json_response(self, {"ok": False, "error": "Missing url parameter."}, status=400)
                    return
                result = {
                    "kind": (params.get("kind") or ["type"])[0],
                    "title": (params.get("title") or ["Java API"])[0],
                    "label": (params.get("label") or ["Java API"])[0],
                    "package": (params.get("package") or [""])[0],
                    "module": (params.get("module") or [""])[0],
                    "className": (params.get("className") or [""])[0],
                    "anchor": (params.get("anchor") or [""])[0],
                    "url": url,
                }
                json_response(self, {"ok": True, "document": lookup_document(url, result, lang)})
                return
            self.serve_static(path)
        except Exception as exc:
            json_response(self, {"ok": False, "error": str(exc)}, status=500)

    def serve_static(self, request_path: str) -> None:
        route = "index.html" if request_path in {"/", ""} else request_path.lstrip("/")
        file_path = (STATIC_DIR / route).resolve()
        if not str(file_path).startswith(str(STATIC_DIR.resolve())) or not file_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return
        content_type = "text/plain; charset=utf-8"
        if file_path.suffix == ".html":
            content_type = "text/html; charset=utf-8"
        elif file_path.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif file_path.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        elif file_path.suffix == ".svg":
            content_type = "image/svg+xml; charset=utf-8"
        data = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), AppHandler)
    print(f"Serving on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
