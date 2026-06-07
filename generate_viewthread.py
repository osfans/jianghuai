#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Dict, List


def decode_sql_string(token: str) -> str:
    if len(token) >= 2 and token[0] == "'" and token[-1] == "'":
        token = token[1:-1]

    out: List[str] = []
    i = 0
    while i < len(token):
        ch = token[i]
        if ch == "\\" and i + 1 < len(token):
            nxt = token[i + 1]
            mapping = {
                "n": "\n",
                "r": "\r",
                "t": "\t",
                "0": "\0",
                "\\": "\\",
                "'": "'",
                '"': '"',
            }
            out.append(mapping.get(nxt, nxt))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def split_sql_tuple(tuple_body: str) -> List[str]:
    fields: List[str] = []
    current: List[str] = []
    in_string = False
    i = 0

    while i < len(tuple_body):
        ch = tuple_body[i]

        if in_string:
            current.append(ch)
            if ch == "\\" and i + 1 < len(tuple_body):
                current.append(tuple_body[i + 1])
                i += 2
                continue
            if ch == "'":
                if i + 1 < len(tuple_body) and tuple_body[i + 1] == "'":
                    current.append("'")
                    i += 2
                    continue
                in_string = False
            i += 1
            continue

        if ch == "'":
            in_string = True
            current.append(ch)
            i += 1
            continue

        if ch == ",":
            fields.append("".join(current).strip())
            current = []
            i += 1
            continue

        current.append(ch)
        i += 1

    fields.append("".join(current).strip())
    return fields


def iter_insert_tuples(values_sql: str):
    in_string = False
    depth = 0
    start_idx = -1
    i = 0

    while i < len(values_sql):
        ch = values_sql[i]

        if in_string:
            if ch == "\\" and i + 1 < len(values_sql):
                i += 2
                continue
            if ch == "'":
                if i + 1 < len(values_sql) and values_sql[i + 1] == "'":
                    i += 2
                    continue
                in_string = False
            i += 1
            continue

        if ch == "'":
            in_string = True
            i += 1
            continue

        if ch == "(":
            if depth == 0:
                start_idx = i + 1
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and start_idx >= 0:
                yield values_sql[start_idx:i]
                start_idx = -1

        i += 1


def parse_posts_from_sql(sql_path: Path) -> List[Dict]:
    posts: List[Dict] = []
    collecting = False
    stmt_lines: List[str] = []

    with sql_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            stripped = line.lstrip()

            if not collecting and stripped.startswith("INSERT INTO `jh_posts`"):
                collecting = True
                stmt_lines = [line]
                if ";" in line:
                    collecting = False
                    statement = "".join(stmt_lines)
                    stmt_lines = []
                    extract_posts_from_statement(statement, posts)
                continue

            if collecting:
                stmt_lines.append(line)
                if ";" in line:
                    collecting = False
                    statement = "".join(stmt_lines)
                    stmt_lines = []
                    extract_posts_from_statement(statement, posts)

    posts.sort(key=lambda x: x["dateline"])
    return posts


def extract_posts_from_statement(statement: str, posts: List[Dict]) -> None:
    values_pos = statement.find("VALUES")
    if values_pos == -1:
        return

    values_sql = statement[values_pos + len("VALUES") :]
    if values_sql.endswith(";"):
        values_sql = values_sql[:-1]

    for tuple_body in iter_insert_tuples(values_sql):
        fields = split_sql_tuple(tuple_body)
        if len(fields) < 9:
            continue

        try:
            tid = int(fields[2])
            author_token = fields[4]
            subject_token = fields[6]
            dateline = int(fields[7])
            message_token = fields[8]
        except ValueError:
            continue

        author = decode_sql_string(author_token)
        subject = decode_sql_string(subject_token)
        message = decode_sql_string(message_token)

        posts.append(
            {
                "tid": tid,
                "author": author,
                "subject": subject,
                "dateline": dateline,
                "message": message,
            }
        )


def build_html(template_path: Path, posts: List[Dict]) -> str:
    template = template_path.read_text(encoding="utf-8")
    embedded = json.dumps(posts, ensure_ascii=False)
    return template.replace("__EMBEDDED_POSTS_JSON__", embedded)


def main() -> None:
    parser = argparse.ArgumentParser(
      description="从 SQL 中提取 jh_posts 并基于模板生成 viewthread.html（内嵌 JSON）"
    )
    parser.add_argument(
        "--sql",
        default="tbhmsruls20190215.sql",
        help="输入 SQL 文件路径",
    )
    parser.add_argument(
      "--template",
      default="docs/jianghuai/viewthread.template.html",
      help="HTML 模板文件路径",
    )
    parser.add_argument(
        "--html-out",
        default="docs/jianghuai/viewthread.html",
        help="输出 HTML 文件路径",
    )
    args = parser.parse_args()

    sql_path = Path(args.sql)
    template_path = Path(args.template)
    html_out = Path(args.html_out)

    if not sql_path.exists():
        raise SystemExit(f"SQL 文件不存在: {sql_path}")
    if not template_path.exists():
      raise SystemExit(f"模板文件不存在: {template_path}")

    posts = parse_posts_from_sql(sql_path)

    html_out.parent.mkdir(parents=True, exist_ok=True)

    html = build_html(template_path, posts)
    with html_out.open("w", encoding="utf-8") as f:
        f.write(html)

    print(f"解析帖子数: {len(posts)}")
    print(f"模板已读取: {template_path}")
    print(f"HTML 已生成: {html_out}")


if __name__ == "__main__":
    main()
