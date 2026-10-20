"""Run after building: .venv/bin/python -m unittest discover -s tests -v"""
import json
from pathlib import Path
import re
import sys
import tempfile
import shutil
import subprocess
import unittest
from urllib.parse import urlsplit
from unittest.mock import patch
import io
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from i18n import Catalog, annotate_note, freeze, thaw, valid_translation
from update_translations import google_translate


class TranslationTests(unittest.TestCase):
    def test_precedence_and_stale_source(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog = Catalog(Path(folder), "zh-Hans")
            node = BeautifulSoup("<p>Latency is 10 microseconds.</p>", "html.parser").p
            self.assertEqual(catalog.resolve("intro", node, "test")[1], "fallback")
            record = catalog.sources["intro"]
            catalog.cache["intro"] = {"text": "延迟为 ⟦0⟧ 微秒。", "source_hash": record["source_hash"]}
            self.assertEqual(catalog.resolve("intro", node, "test"), ("延迟为 10 微秒。", "machine"))
            catalog.manual["intro"] = {"text": "手工译文：10 微秒。", "source_hash": record["source_hash"]}
            self.assertEqual(catalog.resolve("intro", node, "test")[1], "manual")
            catalog.sources.clear()
            edited = BeautifulSoup("<p>Latency is 20 microseconds.</p>", "html.parser").p
            self.assertEqual(catalog.resolve("intro", edited, "test")[0], "手工译文：10 微秒。")
            self.assertIn("intro", catalog.report["stale_manual"])
            del catalog.manual["intro"]
            self.assertEqual(catalog.resolve("intro", edited, "test")[1], "fallback")

    def test_protected_content(self):
        node = BeautifulSoup('<p>Use <a href="/x?a=1&amp;b=2">QLeaf</a> and <code>x &lt; 10</code> at 2.5 μs.</p>', "html.parser").p
        source, slots, _ = freeze(node, {"QLeaf": "QLeaf"})
        self.assertNotIn("2.5", source)
        self.assertNotIn("x &lt;", source)
        self.assertTrue(valid_translation(source, source))
        self.assertFalse(valid_translation(source, source.replace("⟦0⟧", "")))
        restored = BeautifulSoup(thaw(source, slots), "html.parser")
        self.assertEqual(restored.a["href"], "/x?a=1&b=2")
        self.assertEqual(restored.code.get_text(), "x < 10")
        self.assertIn("2.5", restored.get_text())

    def test_note_ids_survive_reordering(self):
        first = "<!-- i18n: first --><p>One</p>"
        second = "<!-- i18n: second --><p>Two</p>"
        for content in (first + second, second + first):
            soup = BeautifulSoup(annotate_note(content, "note"), "html.parser")
            self.assertEqual(soup.find(attrs={"data-i18n": "note.note.first"}).text, "One")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            annotate_note(first + first, "note")

    def test_api_request_with_mock(self):
        response = io.BytesIO(json.dumps({"data": {"translations": [{"translatedText": "测试 ⟦0⟧"}]}}).encode())
        with patch("urllib.request.urlopen", return_value=response) as call:
            self.assertEqual(google_translate(["Test ⟦0⟧"], "zh-Hans", "fake"), ["测试 ⟦0⟧"])
            payload = json.loads(call.call_args.args[0].data)
            self.assertEqual(payload["target"], "zh-CN")
            self.assertEqual(payload["format"], "text")


class GeneratedSiteTests(unittest.TestCase):
    def test_complete_authored_note(self):
        with tempfile.TemporaryDirectory() as folder:
            checkout = Path(folder) / "site"
            shutil.copytree(ROOT, checkout, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
            target = checkout / "content/translations/zh-Hans/posts/qleaf-inference-latency.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('---\ntitle: 手写标题\nsummary: 手写摘要\nsource_hash: outdated\n---\n\n## 手写正文\n\n我的中文笔记。\n')
            subprocess.run([sys.executable, str(checkout / "scripts/build_site.py")], check=True, capture_output=True)
            for name in ("zh/blog.html", "zh/blog/qleaf-inference-latency/index.html", "zh/feed.xml"):
                text = (checkout / name).read_text()
                self.assertIn("手写标题", text)
                self.assertIn("手写摘要", text)
            note = BeautifulSoup((checkout / "zh/blog/qleaf-inference-latency/index.html").read_text(), "html.parser")
            self.assertIn("我的中文笔记。", note.select_one(".note-content").get_text())
            report = json.loads((checkout / "translations/reports/zh-Hans.json").read_text())
            self.assertIn("post.qleaf-inference-latency", report["stale_manual"])

    def test_catalog_complete(self):
        report = json.loads((ROOT / "translations/reports/zh-Hans.json").read_text())
        self.assertFalse(report["missing"])
        self.assertFalse(report["invalid_cache"])

    def test_navigation_and_assets(self):
        names = ["index.html", "about.html", "projects.html", "publications.html",
                 "contact.html", "blog.html", "404.html", "blog/qleaf-inference-latency/index.html"]
        for prefix in ("", "zh/"):
            for name in names:
                soup = BeautifulSoup((ROOT / prefix / name).read_text(), "html.parser")
                self.assertEqual(soup.html["lang"], "zh-Hans" if prefix else "en")
                self.assertEqual(len(soup.select(".language-switch a")), 2)
                if name != "404.html":
                    self.assertEqual(len(soup.select('link[hreflang]')), 3)
                for tag in soup.select("[href], [src]"):
                    url = urlsplit(tag.get("href", tag.get("src")))
                    if url.scheme or url.netloc or not url.path:
                        continue
                    target = ROOT / url.path.lstrip("/") if url.path.startswith("/") else ROOT / prefix / Path(name).parent / url.path
                    if target.is_dir():
                        target /= "index.html"
                    self.assertTrue(target.exists(), f"{prefix}{name}: {url.path}")
        xml = ET.parse(ROOT / "sitemap.xml")
        urls = [element.text for element in xml.iter() if element.tag.endswith("}loc")]
        self.assertEqual(len(urls), 14)
        self.assertNotIn("https://jjli.info/404.html", urls)

    def test_benchmark_numbers_and_code_preserved(self):
        pages = [BeautifulSoup((ROOT / prefix / "blog/qleaf-inference-latency/index.html").read_text(), "html.parser")
                 for prefix in ("", "zh")]
        self.assertEqual([c.get_text() for c in pages[0].select(".note-content code")],
                         [c.get_text() for c in pages[1].select(".note-content code")])
        numbers = lambda soup: re.findall(r"\d+(?:\.\d+)?", " ".join(t.get_text() for t in soup.select(".note-content table")))
        self.assertEqual(numbers(pages[0]), numbers(pages[1]))


if __name__ == "__main__":
    unittest.main()
