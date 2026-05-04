#!/usr/bin/env python3
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import server


ROOT = Path(__file__).parent


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def compile_java_snippet(code: str, input_text: str = "") -> str:
    javac_path = shutil.which("javac")
    java_path = shutil.which("java")
    assert_true(javac_path is not None, "javac is required for snippet validation.")
    assert_true(java_path is not None, "java is required for snippet validation.")

    with tempfile.TemporaryDirectory() as temp_dir:
        source_path = Path(temp_dir) / "Example.java"
        source_path.write_text(code, encoding="utf-8")

        compile_run = subprocess.run(
            [javac_path, str(source_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert_true(
            compile_run.returncode == 0,
            f"Java snippet failed to compile: {compile_run.stderr.strip() or compile_run.stdout.strip()}",
        )

        execute_run = subprocess.run(
            [java_path, "-cp", temp_dir, "Example"],
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
        )
        assert_true(
            execute_run.returncode == 0,
            f"Java snippet failed to run: {execute_run.stderr.strip() or execute_run.stdout.strip()}",
        )
        return execute_run.stdout.replace("\r\n", "\n").rstrip("\n")


def test_static_files() -> dict:
    required = [
        ROOT / "static" / "index.html",
        ROOT / "static" / "app.js",
        ROOT / "static" / "styles.css",
        ROOT / "static" / "hero-portrait.svg",
    ]
    for file_path in required:
        assert_true(file_path.exists(), f"Missing static file: {file_path}")
        assert_true(file_path.read_text(encoding="utf-8").strip() != "", f"Empty static file: {file_path}")

    html_text = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert_true('Java Docs Lens' in html_text, "Java search page title missing in HTML.")
    assert_true('id="search-form"' in html_text, "Java search form missing in HTML.")
    assert_true('id="search-panel"' in html_text, "Sticky search panel missing in HTML.")
    assert_true('id="official-excerpt"' in html_text, "Official excerpt container missing in HTML.")
    assert_true('Knowledge Summary' in html_text, "Study mode tabs missing in HTML.")
    assert_true('id="chinese-explanation"' in html_text, "Chinese explanation container missing in HTML.")
    assert_true('id="concept-summary"' in html_text, "Concept summary container missing in HTML.")
    assert_true('id="example-code"' in html_text, "Example code container missing in HTML.")

    js_text = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert_true("loadDocument" in js_text, "Document loading logic missing in JS.")
    assert_true("renderError" in js_text, "UI error handling missing in JS.")
    assert_true("copySnippet" in js_text, "Snippet copy behavior missing in JS.")
    assert_true("modeTabs" in js_text, "Mode switching logic missing in JS.")
    assert_true("syncStickySearch" in js_text, "Sticky search sync logic missing in JS.")
    assert_true("chineseExplanation" in js_text, "Chinese explanation rendering missing in JS.")
    assert_true("conceptSummary" in js_text, "Concept summary rendering missing in JS.")
    assert_true("exampleCode" in js_text, "Example code rendering missing in JS.")

    css_text = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
    assert_true(".results-grid {" in css_text, "Results layout styles missing in CSS.")
    assert_true(".card-official" in css_text, "Documentation card styles missing in CSS.")
    assert_true(".search-sticky {" in css_text, "Sticky search styles missing in CSS.")
    assert_true(".search-sticky.is-stuck" in css_text, "Sticky search compact styles missing in CSS.")
    assert_true("@media (max-width: 960px)" in css_text, "Responsive styles missing in CSS.")

    return {"static_files": len(required)}


def test_lookup_flow() -> dict:
    version = server.get_latest_jdk_version()
    expected_titles = {
        "左对齐": {"Formatter"},
        "%-": {"Formatter"},
        "右对齐": {"Formatter"},
        "方法引用": {"java.util.function"},
        "::": {"java.util.function"},
        "lambda表达式": {"java.util.function", "FunctionalInterface", "BiFunction", "Consumer", "Function"},
        "->": {"java.util.function", "FunctionalInterface", "BiFunction", "Consumer", "Function"},
        "线程池": {"ThreadPoolExecutor", "ExecutorService", "Executors"},
        "空指针": {"NullPointerException", "Objects", "Optional"},
        "列表": {"List", "ArrayList"},
        "映射": {"Map", "HashMap"},
        "字符串": {"String", "StringBuilder", "CharSequence"},
        "日期时间": {"java.time", "LocalDateTime", "LocalDate", "Instant", "Duration"},
    }
    terms = ["ArrayList", "Optional", "Stream", "HashMap", *expected_titles.keys()]
    checked = []

    for term in terms:
        results = server.search_docs(term, version)
        assert_true(results, f"No search results returned for {term}.")
        document = server.lookup_document(results[0]["url"], results[0], "zh")
        excerpt = (document.get("officialExcerpt") or "").strip()
        assert_true(excerpt != "", f"Empty official excerpt for {term}.")
        assert_true((document.get("chineseExplanation") or "").strip() != "", f"Missing Chinese explanation for {term}.")
        assert_true(isinstance(document.get("conceptSummary"), list) and len(document["conceptSummary"]) >= 3, f"Missing concept summary items for {term}.")
        assert_true("example" in document and document["example"]["code"].strip() != "", f"Missing example code for {term}.")
        assert_true(document["example"].get("output", "").strip() != "", f"Missing run output for {term}.")
        assert_true("NOTE: Concept (EN):" in document["example"]["code"], f"Missing English concept note inside code for {term}.")
        assert_true("NOTE: Concept (ZH):" in document["example"]["code"], f"Missing Chinese concept note inside code for {term}.")
        assert_true("NOTE: Suggested terminal input after Run:" in document["example"]["code"], f"Missing input guidance inside code for {term}.")
        assert_true("NOTE: Expected output after" in document["example"]["code"], f"Missing expected output note inside code for {term}.")
        assert_true("Read the official docs for" not in document["example"]["code"], f"Placeholder example leaked into {term}.")
        assert_true("Selected topic:" not in document["example"]["code"], f"Snippet for {term} fell back to a topic-print placeholder.")
        assert_true("public class Example" in document["example"]["code"], f"Snippet for {term} is not a runnable Java example.")
        assert_true(len(document["interviewQA"]) == 3, f"Unexpected interview QA count for {term}.")
        actual_output = compile_java_snippet(document["example"]["code"], document["example"].get("input", ""))
        expected_output = document["example"]["output"].replace("\r\n", "\n").rstrip("\n")
        assert_true(actual_output == expected_output, f"Displayed output does not match actual run output for {term}.")
        if term == "ArrayList":
            assert_true("new ArrayList<>()" in document["example"]["code"], "ArrayList example should use ArrayList directly in code.")
        if term == "HashMap":
            assert_true("new HashMap<>()" in document["example"]["code"], "HashMap example should use HashMap directly in code.")
        if term == "Stream":
            assert_true("Stream<String>" in document["example"]["code"], "Stream example should use Stream directly in code.")
        if term in expected_titles:
            assert_true(
                results[0]["title"] in expected_titles[term],
                f"{term} resolved to {results[0]['title']}, expected one of {sorted(expected_titles[term])}.",
            )
        checked.append(
            {
                "term": term,
                "result": results[0]["title"],
                "excerpt": excerpt[:80],
            }
        )

    return {"latest_jdk_version": version, "checked_terms": checked}


def main() -> None:
    summary = {
        "static": test_static_files(),
        "lookup": test_lookup_flow(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
