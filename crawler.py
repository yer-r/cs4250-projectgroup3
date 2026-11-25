#-------------------------------------------------------------------------
# AUTHOR: Eric Kim,
# FILENAME: crawler.py
# SPECIFICATION: Breadth-first crawler for the CPP Biological Sciences
#                department. Follows the project pseudocode: the frontier starts
#                with only the seed URL, pages are fetched and stored, faculty
#                pages are recognized by the default header section, and the
#                crawl stops when num_targets faculty pages have been found.
# FOR: CS 4250 - Course Project (Biology department)
#-------------------------------------------------------------------------

import time
from collections import deque
from urllib.parse import urljoin, urldefrag, urlparse

import requests
from bs4 import BeautifulSoup

import common

# ---------------------------------------------------------
# Settings
# ---------------------------------------------------------
SEED = "https://www.cpp.edu/sci/biological-sciences/index.shtml"
NUM_TARGETS = 13

# Links are followed only if they start with one of these prefixes: the department
# site and the university's faculty-pages area. Without a scope, a breadth-first
# crawl from the department home page would wander across all of cpp.edu.
ALLOWED_PREFIXES = (
    "https://www.cpp.edu/sci/biological-sciences/",
    "https://www.cpp.edu/faculty/",
)

CRAWL_DELAY = 0.5      # seconds between requests (be polite to the server)
TIMEOUT = 10           # seconds
INDEX_NAMES = ("index.shtml", "index.html", "index.htm")
SKIP_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".zip",
                   ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".mp3",
                   ".mp4", ".css", ".js", ".ico")


# ---------------------------------------------------------
# URL handling
# ---------------------------------------------------------
def normalize_url(url):
    """Returns a canonical absolute URL, or None if it should not be followed.
    Drops #fragments and maps .../alas, .../alas/ and .../alas/index.shtml to one URL."""
    url, _ = urldefrag(url.strip())
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None

    host = parts.netloc.lower()
    scheme = parts.scheme
    if host == "cpp.edu":
        host = "www.cpp.edu"
    if host.endswith("cpp.edu"):
        scheme = "https"

    path = parts.path or "/"
    last = path.rsplit("/", 1)[-1]
    if last in INDEX_NAMES:
        path = path[:-len(last)]
    elif "." not in last and not path.endswith("/"):
        path += "/"

    if path.lower().endswith(SKIP_EXTENSIONS):
        return None

    query = "?" + parts.query if parts.query else ""
    return f"{scheme}://{host}{path}{query}"


def in_scope(url):
    return url.startswith(ALLOWED_PREFIXES)


# ---------------------------------------------------------
# Pseudocode helpers
# ---------------------------------------------------------
def fetch_html(session, url):
    """Returns the HTML of a page, or None for broken links / non-HTML responses."""
    try:
        response = session.get(url, timeout=TIMEOUT)
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    content_type = response.headers.get("Content-Type", "").lower()
    if "html" not in content_type:
        return None
    if "charset" not in content_type:
        response.encoding = response.apparent_encoding
    return response.text


def extract_links(soup, base_url):
    """Absolute, canonical, in-scope links found in the page (relative links are resolved)."""
    links = []
    for a in soup.find_all("a", href=True):
        link = normalize_url(urljoin(base_url, a["href"]))
        if link is not None and in_scope(link) and link not in links:
            links.append(link)
    return links


def store_page(db, url, faculty_name, html):
    db["pages"].insert_one({"url": url, "facultyName": faculty_name, "html": html})


# ---------------------------------------------------------
# Crawler (follows the project pseudocode)
# ---------------------------------------------------------
def crawler(seed, num_targets):
    db = common.get_db()
    db["pages"].drop()

    targets_found = 0
    frontier = deque([seed])
    seen = {normalize_url(seed)}
    found_names = set()
    session = requests.Session()
    session.headers["User-Agent"] = "CS4250-ProjectCrawler/1.0 (course project)"

    while frontier:
        url = frontier.popleft()                      # frontier.removeFirst()
        html = fetch_html(session, url)
        time.sleep(CRAWL_DELAY)

        if html is None:                              # broken link: nothing to store or follow
            print(f"  [broken]  {url}")
            continue

        soup = BeautifulSoup(html, "html.parser")

        faculty_name = None
        if common.target_page(soup):
            name = common.extract_faculty_name(soup)
            # A professor's other pages (courses, research, ...) share the same header;
            # only the first page found for each professor counts as a target.
            if name not in found_names:
                found_names.add(name)
                faculty_name = name
                targets_found += 1
                print(f"  [target {targets_found}/{num_targets}]  {name}  {url}")

        store_page(db, url, faculty_name, html)

        if targets_found == num_targets:
            frontier.clear()
        else:
            for link in extract_links(soup, url):
                if link not in seen:
                    seen.add(link)
                    frontier.append(link)

    return targets_found


if __name__ == "__main__":
    print(f"Crawling from {SEED}")
    found = crawler(SEED, NUM_TARGETS)
    pages = common.get_db()["pages"].count_documents({})
    print(f"\nDone: {pages} pages stored, {found} faculty pages found.")
    if found < NUM_TARGETS:
        print(f"WARNING: expected {NUM_TARGETS} faculty pages. The header pattern in "
              "common.py (find_header) probably needs adjusting.")
