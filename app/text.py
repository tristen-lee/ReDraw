import html

from bs4 import BeautifulSoup

BLOCK_TAGS = ("p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr")


def html_to_text(markup, escaped=False):
    if not markup:
        return ""
    if escaped:
        markup = html.unescape(markup)
    soup = BeautifulSoup(markup, "html.parser")
    for tag in soup.find_all(BLOCK_TAGS):
        tag.insert_before("\n")
    for item in soup.find_all("li"):
        item.insert_before("• ")
    lines = [" ".join(line.split()) for line in soup.get_text().splitlines()]
    paragraphs, current = [], []
    for line in lines:
        if line:
            current.append(line)
        elif current:
            paragraphs.append("\n".join(current))
            current = []
    if current:
        paragraphs.append("\n".join(current))
    return "\n\n".join(paragraphs)
