import os
import re
import zipfile
import streamlit as st
from io import BytesIO
from googletrans import Translator
import json
import logging

CONFIG_PATH = "novel_splitter_config.json"

# --- Logger Setup ---
LOG_LEVELS = ["NONE", "ERROR", "WARNING", "INFO", "DEBUG"]

def log(msg, level="INFO"):
    level = level.upper()
    if log_level == "NONE":
        return
    allowed_levels = LOG_LEVELS[LOG_LEVELS.index(log_level):]
    if level in allowed_levels:
        getattr(logging, level.lower(), logging.info)(msg)

def setup_logging(selected_level):
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=getattr(logging, selected_level, logging.INFO),
    )


# --- Config I/O ---
def load_config():
    default_config = {
        "chapter_marker": r"^(?P<full>第\s*[\d０-９一二三四五六七八九十百千万零〇]+[章回]\s*[^\n\r]*)",
        "book_title_marker": r"(?:『)?(?P<title>[^\n/／]+)[/／](?:作者[:：])?(?P<author>[^\n』]+)(?:』)?|^(?P<title_alt>.+)[\r\n]+作者[:：](?P<author_alt>.+)",
        "summary_marker": r"(?:内容简介|简介)[:：]?\s*(?P<summary>.+?)(?=\n+第[\d一二三四五六七八九十百千万零〇]+章|\n*$)",
        "log_level": "INFO",
        "translate_titles": False
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_config.update(data)
        except Exception as e:
            logging.warning(f"Failed to load config: {e}")
    return default_config


def save_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    st.sidebar.success("✅ Configuration saved!")


def sanitize_filename(name):
    return re.sub(r'[\\/:*?"<>|]+', "", name)


def try_decode_until_marker(raw, encodings, marker_regex):
    for enc in encodings:
        try:
            text = raw.decode(enc)
            if re.search(marker_regex, text, re.M):
                log(f"Decoded using encoding: {enc}", "INFO")
                return text, enc
        except Exception as e:
            log(f"Failed decoding with {enc}: {e}", "DEBUG")
    return None, None


def split_novel(text, chapter_marker, book_title_marker, summary_marker):
    log("Splitting novel...", "INFO")

    title_match = re.search(book_title_marker, text, re.M)
    if title_match:
        g = title_match.groupdict()
        book_name = g.get("title") or g.get("title_alt") or "UnknownBook"
        author = g.get("author") or g.get("author_alt") or "UnknownAuthor"
        log(f"Book title: {book_name}, Author: {author}", "INFO")
    else:
        log("Book title and author not found.", "WARNING")
        book_name = "UnknownBook"
        author = "UnknownAuthor"

    summary_match = re.search(summary_marker, text, re.S)
    summary = summary_match.groupdict().get("summary", "").strip() if summary_match else ""
    if not summary:
        summary = "No summary available."
        log("Summary not found.", "WARNING")
    else:
        log("Summary extracted.", "INFO")

    chapter_regex = re.compile(chapter_marker, re.M)
    matches = list(chapter_regex.finditer(text))
    if not matches:
        log("No chapters found.", "ERROR")
        raise Exception("未找到章节内容起始标记 (chapter start marker not found)")

    chapters = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        title = match.group("full").strip()
        body = text[start:end].strip()
        log(f"Found chapter {i+1}: {title}", "DEBUG")
        chapters.append({"title": title, "body": body})

    log(f"Total chapters extracted: {len(chapters)}", "INFO")

    return {
        "meta": {
            "bookName": book_name,
            "author": author,
            "latestChapter": chapters[-1]["title"] if chapters else "",
            "summary": summary,
        },
        "chapters": chapters,
    }


def main():
    global log_level
    config = load_config()
    log_level = config.get("log_level", "INFO")
    setup_logging(log_level)

    st.set_page_config(page_title="📖 Chinese Novel Splitter", page_icon="📚")
    st.title("📖 Chinese Novel Splitter")

    # --- Sidebar Configuration ---
    st.sidebar.header("⚙️ Configuration")
    new_log_level = st.sidebar.selectbox("Log Level", LOG_LEVELS, index=LOG_LEVELS.index(config["log_level"]))
    config["translate_titles"] = st.sidebar.checkbox("Translate chapter titles to English?", value=config["translate_titles"])
    config["chapter_marker"] = st.sidebar.text_area("Chapter Marker (Regex)", config["chapter_marker"], height=70)
    config["book_title_marker"] = st.sidebar.text_area("Book Title Marker (Regex)", config["book_title_marker"], height=70)
    config["summary_marker"] = st.sidebar.text_area("Summary Marker (Regex)", config["summary_marker"], height=70)

    if st.sidebar.button("💾 Save Config"):
        config["log_level"] = new_log_level
        save_config(config)
        st.rerun()

    log_level = new_log_level
    setup_logging(log_level)

    uploaded_file = st.file_uploader("📤 Upload a `.txt` Chinese novel", type=["txt"])
    encodings_to_try = ["gb18030", "gbk", "gb2312", "utf-8", "big5", "utf-16", "utf-32"]

    if uploaded_file:
        raw = uploaded_file.read()
        text, encoding = try_decode_until_marker(raw, encodings_to_try, config["chapter_marker"])
        if not text:
            st.error("❌ Failed to decode text. Adjust encoding or markers.")
            return

        st.success(f"✅ Successfully decoded using {encoding}")

        # --- Live Preview ---
        st.subheader("🧪 Regex Match Preview")

        with st.expander("📘 Title & Author Match", expanded=False):
            title_match = re.search(config["book_title_marker"], text, re.M)
            if title_match:
                g = title_match.groupdict()
                st.markdown(f"**Title:** {g.get('title') or g.get('title_alt')}")
                st.markdown(f"**Author:** {g.get('author') or g.get('author_alt')}")
            else:
                st.warning("No match found for title/author.")

        with st.expander("📖 Summary Match", expanded=False):
            summary_match = re.search(config["summary_marker"], text, re.S)
            summary = summary_match.groupdict().get("summary", "").strip() if summary_match else ""
            if summary:
                st.markdown("**Preview:**")
                st.code(summary[:500] + ("..." if len(summary) > 500 else ""), language="markdown")
            else:
                st.warning("No summary matched.")

        with st.expander("📚 Chapter Title Matches", expanded=False):
            chapter_regex = re.compile(config["chapter_marker"], re.M)
            matches = list(chapter_regex.finditer(text))
            if matches:
                for i, match in enumerate(matches[:3]):
                    st.markdown(f"**Match {i+1}:** `{match.group('full')}`")
                if len(matches) > 3:
                    st.info(f"Showing 3 of {len(matches)} matches...")
            else:
                st.warning("No chapter markers matched.")

        if encoding.lower() != "utf-8":
            st.download_button("⬇ Download UTF-8 Re-encoded File", data=text.encode("utf-8"),
                               file_name=uploaded_file.name.replace(".txt", "_utf8.txt"),
                               mime="text/plain")

        if st.button("📚 Split Book"):
            try:
                result = split_novel(text, config["chapter_marker"], config["book_title_marker"], config["summary_marker"])
                meta = result["meta"]
                chapters = result["chapters"]
                translator = Translator() if config["translate_titles"] else None

                book_folder = sanitize_filename(meta["bookName"])
                if translator:
                    try:
                        book_folder = sanitize_filename(translator.translate(meta["bookName"], src="zh-cn", dest="en").text)
                        log(f"Translated book folder: {book_folder}", "INFO")
                    except Exception as e:
                        log(f"Title translation failed: {e}", "WARNING")

                zip_buffer = BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                    zipf.writestr("info.txt", f"书名: {meta['bookName']}\n作者: {meta['author']}\n更新至: {meta['latestChapter']}\n简介:\n{meta['summary']}\n")
                    for ch in chapters:
                        try:
                            fname = ch["title"]
                            if translator:
                                fname = translator.translate(fname, src="zh-cn", dest="en").text
                            fname = sanitize_filename(fname) + ".txt"
                        except Exception as e:
                            log(f"Chapter title translation failed: {e}", "WARNING")
                            fname = sanitize_filename(ch["title"]) + ".txt"
                        content = f"{ch['title']}\n{ch['body']}\n"
                        zipf.writestr(fname, content)
                        log(f"Wrote: {fname}", "DEBUG")

                st.success(f"✅ {len(chapters)} chapters split. Ready for download.")
                st.download_button("⬇ Download Chapters ZIP", data=zip_buffer.getvalue(),
                                   file_name=f"{book_folder}_split.zip", mime="application/zip")

            except Exception as e:
                log(f"Splitting error: {e}", "ERROR")
                st.error(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
