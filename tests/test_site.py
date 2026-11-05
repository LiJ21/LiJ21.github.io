import json
import re
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
PAGES = ["index.html", "about.html", "projects.html", "publications.html",
         "contact.html", "blog.html", "404.html", "blog/qleaf-inference-latency/index.html"]


def page(name):
    return BeautifulSoup((ROOT / name).read_text(), "html.parser")


class PublicationTests(unittest.TestCase):
    def test_authors_use_given_name_first(self):
        for record in json.loads((ROOT / "data/publications.json").read_text()):
            for author in record["authors"]:
                self.assertNotIn(",", author, record["id"])

    def test_every_record_highlights_the_site_owner(self):
        records = page("publications.html").select("#publication-list .publication")
        self.assertEqual(len(records), 43)
        for record in records:
            self.assertIsNotNone(record.select_one(".authors strong"), record["id"])


class ShellTests(unittest.TestCase):
    def test_header_names_the_site_and_links_home(self):
        for prefix in ("", "zh/"):
            for name in PAGES:
                soup = page(prefix + name)
                site_name = soup.select_one(".site-header .site-name")
                self.assertEqual(site_name.get_text(), "Jiajun Li", prefix + name)
                target = (ROOT / prefix / Path(name).parent / site_name["href"]).resolve()
                self.assertEqual(target, (ROOT / prefix / "index.html").resolve(), prefix + name)

    def test_one_location_is_marked_current(self):
        for prefix in ("", "zh/"):
            for name in ("index.html", "about.html", "publications.html", "blog/qleaf-inference-latency/index.html"):
                current = page(prefix + name).select(".site-header [aria-current='page']")
                self.assertEqual(len(current), 1, prefix + name)

    def test_chinese_navigation_is_translated(self):
        soup = page("zh/index.html")
        self.assertEqual(soup.select("nav a")[0].get_text(), "关于")
        self.assertEqual(soup.select(".translation-notice [data-translation]"), [])
        self.assertFalse(soup.select(".site-header [data-translation='fallback']"))


class HomepageTests(unittest.TestCase):
    def test_latest_note_links_to_the_newest_post(self):
        for prefix in ("", "zh/"):
            card = page(prefix + "index.html").select_one(".home-note .note-preview h3 a")
            self.assertEqual(card["href"], "blog/qleaf-inference-latency/index.html")
            self.assertTrue((ROOT / prefix / card["href"]).exists())

    def test_latest_note_precedes_experience(self):
        sections = [s.get("class") for s in page("index.html").select("main > section")]
        self.assertLess(sections.index(["home-section", "home-note"]),
                        sections.index(["home-section", "home-experience"]))


class CareerTimelineTests(unittest.TestCase):
    def test_every_record_has_one_mark_linking_to_it(self):
        for prefix in ("", "zh/"):
            soup = page(prefix + "publications.html")
            marks = soup.select(".record-years .mark")
            self.assertEqual(len(marks), 43)
            ids = {mark["href"].removeprefix("#") for mark in marks}
            self.assertEqual(ids, {r["id"] for r in json.loads((ROOT / "data/publications.json").read_text())})
            for mark in marks:
                self.assertIsNotNone(soup.find(id=mark["href"].removeprefix("#")))

    def test_marks_stay_out_of_keyboard_order_and_off_the_homepage(self):
        self.assertFalse(page("index.html").select(".mark"))
        chart = page("publications.html").select_one(".record-years")
        self.assertEqual(chart["aria-hidden"], "true")
        self.assertTrue(all(mark["tabindex"] == "-1" for mark in chart.select(".mark")))

    def test_positions_read_in_time_order(self):
        starts = [float(re.search(r"--from: ([\d.]+)%", li["style"])[1])
                  for li in page("index.html").select(".career-path li")]
        self.assertEqual(starts, sorted(starts))
        self.assertEqual(len(starts), 5)



class ProjectTests(unittest.TestCase):
    def test_gardenpipe_is_listed_in_both_languages(self):
        repository = "https://github.com/LiJ21/GardenPipe"
        for prefix in ("", "zh/"):
            for name in ("index.html", "projects.html"):
                self.assertTrue(page(prefix + name).select_one(f'main a[href="{repository}"]'), prefix + name)

    def test_gardenpipe_line_appears_on_both_pages(self):
        for prefix, words in (("", "arbitrarily large data with bounded batch memory"), ("zh/", "以受限的批次内存处理任意规模的数据")):
            self.assertIn(words, page(prefix + "index.html").select_one(".selected-project-list").get_text())
            subtitles = [p.get_text() for p in page(prefix + "projects.html").select(".project-subtitle")]
            self.assertTrue(any(words in subtitle for subtitle in subtitles), prefix)

    def test_gardenpipe_uses_the_shared_project_structure(self):
        rows = page("projects.html").select(".project-row")
        gardenpipe = next(row for row in rows if "GardenPipe" in row.get_text())
        qudrip = next(row for row in rows if "QuDrip" in row.select_one("h2").get_text())
        shape = lambda row: [child.get("class") for child in row.select_one(".project-summary").find_all(recursive=False)]
        self.assertEqual(shape(gardenpipe), shape(qudrip))

    def test_project_descriptions_have_no_untranslated_text(self):
        self.assertFalse(page("zh/projects.html").select("[data-translation='fallback']"))
        self.assertFalse(page("zh/index.html").select("[data-translation='fallback']"))


class WordingTests(unittest.TestCase):
    def test_title_and_footer_match_the_current_focus(self):
        self.assertEqual(page("index.html").title.get_text(), "Jiajun Li · Quantitative researcher")
        self.assertNotIn("人工智能", page("zh/index.html").title.get_text())
        for name in PAGES:
            self.assertNotIn("AI · Computation", page(name).select_one("footer").get_text())

    def test_footer_offers_email_and_feed_in_both_languages(self):
        for prefix, feed in (("", "feed.xml"), ("zh/", "feed.xml")):
            links = [a["href"] for a in page(prefix + "contact.html").select("footer a")]
            self.assertIn("mailto:jiajunligg@gmail.com", links)
            self.assertIn(feed, links)

    def test_about_opens_with_the_two_paragraphs_and_links_github(self):
        soup = page("about.html")
        self.assertIsNone(soup.select_one(".page-hero .intro"))
        paragraphs = [p.get_text() for p in soup.select(".prose > p")]
        self.assertEqual(len(paragraphs), 2)
        self.assertTrue(paragraphs[0].startswith("Trained as a theoretical physicist"))
        self.assertTrue(any("github.com/LiJ21" in a["href"] for a in soup.select(".prose a")))

    def test_contact_lists_email_before_location(self):
        text = page("contact.html").select_one("main").get_text()
        self.assertLess(text.index("jiajunligg@gmail.com"), text.index("Zürich area"))

    def test_project_pages_do_not_skip_heading_levels(self):
        levels = [int(h.name[1]) for h in page("projects.html").select("main h1, main h2, main h3")]
        self.assertTrue(all(b <= a + 1 for a, b in zip(levels, levels[1:])))

    def test_note_tables_fill_the_column(self):
        self.assertTrue(page("blog/qleaf-inference-latency/index.html").select(".table-scroll > table"))


class StyleTests(unittest.TestCase):
    css = (ROOT / "assets/style.css").read_text()

    def test_no_text_below_the_label_size(self):
        sizes = [int(n) for n in re.findall(r"(?:--text-[a-z]+|font-size):[^;]*?(\d+)px", self.css)]
        self.assertGreaterEqual(min(sizes), 12)
        self.assertEqual(re.findall(r"font:\s*\d", self.css), [])

    def test_self_hosted_fonts_exist(self):
        fonts = re.findall(r"url\('([^']+)'\)", self.css)
        self.assertTrue(fonts)
        for font in fonts:
            self.assertTrue((ROOT / "assets" / font).exists(), font)

    def test_print_keeps_the_site_name(self):
        print_rules = self.css[self.css.index("@media print"):]
        hidden = print_rules[:print_rules.index("display: none !important")]
        self.assertNotIn(".site-header,", hidden)
        self.assertNotIn(".site-name", hidden)

    def test_no_third_party_requests(self):
        for name in ("index.html", "publications.html"):
            for tag in page(name).select("link[rel=stylesheet], script[src]"):
                self.assertNotIn("//", tag.get("href", tag.get("src")))


if __name__ == "__main__":
    unittest.main()
