#!/usr/bin/env python3
"""
Auto Blog Generator for gibberney.github.io
--------------------------------------------
Runs as a Render.com cron job every Monday.

What it does:
  1. Reads prompts.json from your GitHub repo
  2. Picks the next unused prompt
  3. Calls OpenAI API to write a full article in your voice
  4. Commits the new article HTML to the blog/ folder
  5. Updates index.html to list the new article
  6. Marks the prompt as used in prompts.json

Required environment variables (set in Render dashboard):
  OPENAI_API_KEY      - Your OpenAI API key
  GITHUB_TOKEN        - GitHub Personal Access Token (repo write access)
  GITHUB_REPO         - e.g. "Gibberney/gibberney.github.io"
  GITHUB_BRANCH       - default: "main"
  PROMPTS_FILE_PATH   - default: "auto_blog/prompts.json"
"""

import os
import json
import base64
import re
from datetime import date

from openai import OpenAI
import requests

# ─── CONFIG ────────────────────────────────────────────────────────────────────────────────────

OPENAI_API_KEY    = os.environ["OPENAI_API_KEY"]
GITHUB_TOKEN      = os.environ["GITHUB_TOKEN"]
GITHUB_REPO       = os.environ.get("GITHUB_REPO", "Gibberney/gibberney.github.io")
GITHUB_BRANCH     = os.environ.get("GITHUB_BRANCH", "main")
PROMPTS_FILE_PATH = os.environ.get("PROMPTS_FILE_PATH", "auto_blog/prompts.json")

GITHUB_API = "https://api.github.com"
GH_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

openai_client = OpenAI(api_key=OPENAI_API_KEY)


# ─── GITHUB HELPERS ────────────────────────────────────────────────────────────────────────────────────────

def github_get_file(path):
    """Fetch a file from the repo. Returns (content_str, sha)."""
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}?ref={GITHUB_BRANCH}"
    r = requests.get(url, headers=GH_HEADERS)
    r.raise_for_status()
    data = r.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    return content, data["sha"]


def github_put_file(path, content, commit_message, sha=None):
    """Create or update a file in the repo."""
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}"
    payload = {
        "message": commit_message,
        "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    r = requests.put(url, headers=GH_HEADERS, json=payload)
    r.raise_for_status()
    return r.json()


# ─── UTILITIES ────────────────────────────────────────────────────────────────────────────────────────────

def slugify(text):
    """Convert a title to a URL-safe slug."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")[:60]


# ─── ARTICLE GENERATION ────────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are ghostwriting a blog article for Mike Gibney's personal website.

About Mike: He's a non-technical guy who has spent nearly a decade in SaaS —
pre-sales, onboarding, analytics, and operations. He's self-aware, candid, and
a bit self-deprecating. He writes the way he talks: conversational, direct,
occasionally funny, always grounded in real experience. He's not trying to be
a thought leader — he's just someone navigating tech, work, and life honestly.

Your output must be a single valid JSON object with exactly these fields:
  "title"      : A catchy, personal-sounding article title (no quotes around it in JSON)
  "description": A one-sentence teaser for the homepage, max 15 words
  "html_body"  : The article as HTML. Start with <h1>title</h1>, then use <p>
                 and <h2> tags only. No <html>, <head>, <body>, or wrapper tags.
                 Write 650–900 words. Sound like Mike — not a blogger or marketer Never use Em-dashes when writing.

Output ONLY the raw JSON object. No markdown. No code fences. No explanation. DO NOT USE EM-DASHES EVER"""


def generate_article(prompt_text):
    """Call OpenAI to generate an article. Returns a dict with title/description/html_body."""
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        max_tokens=2500,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Write an article about: {prompt_text}"},
        ],
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown code fences if the model wraps the output anyway
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)

    return json.loads(raw)


# ─── HTML BUILDING ────────────────────────────────────────────────────────────────────────────────────────

def build_html_page(article, pub_date_str):
    """Wrap the article HTML body in the site's full page shell."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{article['title']}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background-color: #fdfdfd;
      color: #222;
      max-width: 750px;
      margin: 60px auto;
      padding: 0 20px;
      line-height: 1.6;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid #ccc;
      padding-bottom: 10px;
      margin-bottom: 40px;
    }}
    header a {{
      color: #41414a;
      text-decoration: none;
      font-weight: bold;
    }}
    header a:hover {{ text-decoration: underline; }}
    h1 {{ font-size: 2em; margin-bottom: 0.3em; }}
    h2 {{ font-size: 1.4em; margin-top: 2em; color: #333; }}
    p  {{ margin-bottom: 1.2em; }}
    .pub-date {{ color: #999; font-size: 0.85em; margin-bottom: 2.5em; display: block; }}
    .ai-note  {{ margin-top: 60px; padding-top: 20px; border-top: 1px solid #eee;
                 font-size: 0.82em; color: #aaa; font-style: italic; }}
    a {{ color: #0070f3; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    footer {{ margin-top: 80px; font-size: 0.85em; color: #999; text-align: center; }}
  </style>
</head>
<body>
  <header>
    <a href="../index.html">Mike Gibney</a>
    <a href="https://linkedin.com/in/michaeldgibney" target="_blank">LinkedIn</a>
  </header>

  <span class="pub-date">{pub_date_str}</span>

  {article['html_body']}

  <p class="ai-note">This article was written by AI based on a topic I chose. The voice is meant to be mine. Make of that what you will.</p>

  <footer>&copy; 2025 Mike Gibney</footer>
</body>
</html>
"""


# ─── INDEX.HTML UPDATE ──────────────────────────────────────────────────────────────────────────────────────

def update_index_html(index_html, title, description, filename, pub_date_str):
    """
    Insert a new article link into the AI Blog section of index.html.
    Looks for the <!-- AUTO_BLOG_INSERT --> marker placed in that section.
    """
    new_entry = (
        f"    <li>\n"
        f"      <a href=\"blog/{filename}\">{title}</a>\n"
        f"      <small>{description}</small>\n"
        f"    </li>\n"
        f"    <!-- AUTO_BLOG_INSERT -->"
    )
    if "<!-- AUTO_BLOG_INSERT -->" not in index_html:
        raise ValueError(
            "index.html is missing the <!-- AUTO_BLOG_INSERT --> marker. "
            "Add it inside the AI Blog <ul> block."
        )
    return index_html.replace("    <!-- AUTO_BLOG_INSERT -->", new_entry)


# ─── MAIN ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────

def main():
    today = date.today()
    pub_date_str = today.strftime("%B %d, %Y")
    print(f"Auto Blog Generator — {pub_date_str}")

    # 1. Load prompts
    print("Loading prompts.json from GitHub...")
    prompts_content, prompts_sha = github_get_file(PROMPTS_FILE_PATH)
    prompts_data = json.loads(prompts_content)

    # 2. Find next unused prompt
    prompt_entry = next(
        (a for a in prompts_data["articles"] if not a.get("used", False)),
        None
    )
    if not prompt_entry:
        print("⚠️  No unused prompts remaining. Add more to prompts.json!")
        return

    print(f"Prompt selected: {prompt_entry['prompt']}")

    # 3. Generate article with OpenAI
    print("Calling OpenAI API...")
    article = generate_article(prompt_entry["prompt"])
    print(f"Article generated: \"{article['title']}\"")

    # 4. Build HTML file
    slug     = slugify(article["title"])
    filename = f"{today.strftime('%Y-%m-%d')}-{slug}.html"
    file_path = f"blog/{filename}"
    html_content = build_html_page(article, pub_date_str)

    # 5. Commit article HTML to GitHub
    print(f"Committing article to {file_path}...")
    github_put_file(file_path, html_content, f"Auto-post: {article['title']}")

    # 6. Update index.html
    print("Updating index.html...")
    index_content, index_sha = github_get_file("index.html")
    updated_index = update_index_html(
        index_content, article["title"], article["description"], filename, pub_date_str
    )
    github_put_file(
        "index.html", updated_index,
        f"Add blog link: {article['title']}",
        sha=index_sha
    )

    # 7. Mark prompt as used
    prompt_entry["used"]           = True
    prompt_entry["published_date"] = today.isoformat()
    prompt_entry["article_file"]   = file_path
    github_put_file(
        PROMPTS_FILE_PATH,
        json.dumps(prompts_data, indent=2),
        "Mark prompt as used",
        sha=prompts_sha
    )

    print(f"\n✅ Done! Published: https://gibberney.github.io/{file_path}")


if __name__ == "__main__":
    main()
