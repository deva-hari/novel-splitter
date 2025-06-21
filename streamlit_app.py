import os
import re
import zipfile
import chardet
import streamlit as st
from io import BytesIO
import googletrans
from googletrans import Translator


# --- Utility ---
def sanitize_filename(name):
    return re.sub(r'[\\/:*?"<>|]+', "", name)


def split_novel(text):
    title_match = re.search(r"『(.*?)/作者:(.*?)』", text)
    status_match = re.search(r"『状态:更新到:(.*?)』", text)
    summary_match = re.search(r"『内容简介:\s*(.*?)』", text, re.S)

    book_name = title_match.group(1).strip() if title_match else "UnknownBook"
    author = title_match.group(2).strip() if title_match else "UnknownAuthor"
    latest_chapter = status_match.group(1).strip() if status_match else "Unknown"
    summary = (
        summary_match.group(1).strip() if summary_match else "No summary available."
    )

    content_start = re.split(r"章节内容开始|章节開始|------章节内容开始-------", text)
    if len(content_start) < 2:
        raise Exception("未找到章节内容起始标记 (chapter start marker not found)")
    chapter_text = content_start[1]

    chapter_regex = re.compile(
        r"(第[\s\u3000]*[\d０-９一二三四五六七八九十百千万零〇]+[\s\u3000]*(章|回)[^\n\r]*)"
    )
    parts = chapter_regex.split(chapter_text)

    chapters = []
    for i in range(1, len(parts), 3):
        title = parts[i].strip()
        body = (parts[i + 2] if i + 2 < len(parts) else "").strip()
        if body.startswith(title):
            body = body[len(title) :].strip()
        if title:
            chapters.append({"title": title, "body": body})

    return {
        "meta": {
            "bookName": book_name,
            "author": author,
            "latestChapter": latest_chapter,
            "summary": summary,
        },
        "chapters": chapters,
    }


def try_decode(raw, encodings):
    for enc in encodings:
        try:
            return raw.decode(enc), enc
        except Exception:
            continue
    return None, None


def main():
    st.set_page_config(page_title="Chinese Novel Splitter (Python)", page_icon="📖")
    st.title("📖 Chinese Novel Splitter (Python)")
    st.markdown(
        """
    - Upload a Chinese novel `.txt` file (any encoding).
    - If not UTF-8, it will be re-encoded automatically.
    - The app will split chapters and provide a ZIP for download.
    """
    )
    translate_titles = st.checkbox(
        "Translate chapter titles to English for filenames?", value=False
    )
    uploaded_file = st.file_uploader("Upload your novel .txt file", type=["txt"])
    text, encoding, encoding_confirmed = None, None, False
    if uploaded_file:
        raw = uploaded_file.read()
        result = chardet.detect(raw)
        encoding = result["encoding"] or "utf-8"
        st.info(f"Detected encoding: {encoding}")
        # Try detected encoding, then utf-8, then common Chinese encodings
        text, used_encoding = try_decode(
            raw, [encoding, "utf-8", "gbk", "gb2312", "big5"]
        )
        if text is not None:
            encoding = used_encoding
            encoding_confirmed = True
        else:
            is_utf8 = st.radio(
                "Automatic encoding failed. Is your file UTF-8 encoded?",
                ("Yes", "No"),
                horizontal=True,
            )
            if is_utf8 == "Yes":
                text, used_encoding = try_decode(raw, ["utf-8"])
            else:
                text, used_encoding = try_decode(raw, ["gbk", "gb2312", "big5"])
            if text is not None:
                encoding = used_encoding
                encoding_confirmed = True
            else:
                st.error("Failed to decode file with all attempted encodings.")
        if encoding_confirmed:
            if encoding.lower() != "utf-8":
                utf8_bytes = text.encode("utf-8")
                st.download_button(
                    "Download UTF-8 Re-encoded File",
                    data=utf8_bytes,
                    file_name=uploaded_file.name.replace(".txt", "_utf8.txt"),
                    mime="text/plain",
                )
            if st.button("Split Book"):
                try:
                    result = split_novel(text)
                    meta = result["meta"]
                    chapters = result["chapters"]
                    zip_buffer = BytesIO()
                    translator = Translator() if translate_titles else None
                    if translate_titles:
                        try:
                            translated_book_name = sanitize_filename(
                                translator.translate(
                                    meta["bookName"], src="zh-cn", dest="en"
                                ).text
                            )
                        except Exception:
                            translated_book_name = sanitize_filename(meta["bookName"])
                    else:
                        translated_book_name = sanitize_filename(meta["bookName"])
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                        info = f"书名: {meta['bookName']}\n作者: {meta['author']}\n更新至: {meta['latestChapter']}\n简介:\n{meta['summary']}\n"
                        zipf.writestr("info.txt", info)
                        for ch in chapters:
                            if translate_titles:
                                try:
                                    translated = translator.translate(
                                        ch["title"], src="zh-cn", dest="en"
                                    ).text
                                    fname = sanitize_filename(translated) + ".txt"
                                except Exception:
                                    fname = sanitize_filename(ch["title"]) + ".txt"
                            else:
                                fname = sanitize_filename(ch["title"]) + ".txt"
                            content = f"{ch['title']}\n{ch['body']}\n"
                            zipf.writestr(fname, content)
                    st.success(f"Split {len(chapters)} chapters! Download your zip below.")
                    st.download_button(
                        label="Download Chapters ZIP",
                        data=zip_buffer.getvalue(),
                        file_name=f"{translated_book_name}_split.zip",
                        mime="application/zip",
                    )
                except Exception as e:
                    st.error(f"Error: {e}")


if __name__ == "__main__":
    main()
