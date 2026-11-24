#-------------------------------------------------------------------------
# AUTHOR: Eric Kim, 
# FILENAME: common.py
# SPECIFICATION: Pieces shared by the crawler, indexer and search programs:
#                the MongoDB connection, text processing, detection of the
#                faculty-page template (default header section) and
#                extraction of the searchable content.
# FOR: CS4250 Search Engine project (Biology department)
#-------------------------------------------------------------------------

import re
import unicodedata

from bs4 import BeautifulSoup, Comment
from pymongo import MongoClient

# ---------------------------------------------------------
# MongoDB
# ---------------------------------------------------------
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "cpp_faculty_search"

_client = None


def get_db():
    """Returns the project database (collections: pages, documents, inverted_index)."""
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI)
    return _client[DB_NAME]


# ---------------------------------------------------------
# Text processing (used for indexing AND for queries, so both match)
# ---------------------------------------------------------
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "for",
    "from", "has", "have", "he", "her", "his", "i", "in", "is", "it", "its",
    "of", "on", "or", "our", "she", "that", "the", "their", "they", "this",
    "to", "was", "we", "were", "which", "who", "with", "s",
}


def tokenize(text):
    """Lowercases, folds accents (valdés -> valdes), drops punctuation and stopwords."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return [t for t in re.findall(r"[a-z0-9]+", text) if t not in STOPWORDS]


# ---------------------------------------------------------
# Faculty-page template (the "default header section" pattern)
# ---------------------------------------------------------
# A faculty page has an <h1> with the faculty name, and next to it a small block
# with a mailto: link plus contact fields (phone, office location, office hours).
# These constants are the only things to tune if the real pages differ.
HEADER_LABELS = ("phone", "office location", "office hours")   # at least 2 must appear
MIN_LABELS = 2
MAX_HEADER_CHARS = 1500       # the header block is short; a whole page is not
MAX_LEVELS_UP = 5             # how far above the <h1> to look for the header block

# Headings that belong to the header block (not to the searchable content)
CONTACT_HEADINGS = {"email", "e-mail", "phone", "phone number", "office",
                    "office location", "office hours"}

# Page chrome that is never searchable content
CHROME_TAGS = ["script", "style", "noscript", "nav", "footer", "form", "iframe"]


def _contains(ancestor, node):
    return any(p is ancestor for p in node.parents)


def _clean(text):
    return re.sub(r"\s+", " ", text).strip()


def _looks_like_header(node):
    text = node.get_text(" ", strip=True).lower()
    if len(text) > MAX_HEADER_CHARS:
        return False
    if node.find("a", href=re.compile(r"^mailto:", re.I)) is None:
        return False
    return sum(label in text for label in HEADER_LABELS) >= MIN_LABELS


def find_header(soup):
    """Returns (h1 tag, header block) if the page follows the faculty template, else None."""
    for h1 in soup.find_all("h1"):
        node = h1.parent
        for _ in range(MAX_LEVELS_UP):
            if node is None or node.name in ("body", "html", "[document]"):
                break
            if _looks_like_header(node):
                return h1, node
            node = node.parent
    return None


def target_page(soup):
    return find_header(soup) is not None


def extract_faculty_name(soup):
    found = find_header(soup)
    return _clean(found[0].get_text(" ")) if found else None


def extract_content(html):
    """Returns the searchable text of a faculty page: everything after the header
    section (About / research / courses / education areas), without menus or footers."""
    soup = BeautifulSoup(html, "html.parser")
    found = find_header(soup)
    if found is None:
        return ""
    h1, header = found

    # Removing menus, footers, scripts (never the block that holds the name)
    for tag in soup(CHROME_TAGS):
        if not _contains(tag, h1):
            tag.decompose()

    # The content starts at the first heading that is not a contact label and
    # that is outside the header block (e.g., "About Me")
    start = None
    for heading in h1.find_all_next(["h2", "h3", "h4", "h5", "h6"]):
        if _contains(header, heading):
            continue
        if _clean(heading.get_text(" ")).lower() not in CONTACT_HEADINGS:
            start = heading
            break

    # Keeping the text inside the main content area when it can be identified
    anchor = start if start is not None else h1
    root = soup
    for candidate in (soup.find(id="main"), soup.find("main"), soup.body):
        if candidate is not None and _contains(candidate, anchor):
            root = candidate
            break

    parts = []
    for s in anchor.find_all_next(string=True):
        if isinstance(s, Comment) or not s.strip():
            continue
        if root is not soup and not _contains(root, s):
            break
        if _contains(header, s) or s.parent is h1:
            continue
        parts.append(s.strip())
    return _clean(" ".join(parts))
