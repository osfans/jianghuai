#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import List

prefix = ""

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


def parse_posts_from_sql(sql_path: Path) -> List[List]:
    posts: List[List] = []
    collecting = False
    stmt_lines: List[str] = []

    with sql_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            stripped = line.lstrip()

            if not collecting and stripped.startswith(f"INSERT INTO `{prefix}_posts`"):
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
                if line.endswith(";"):
                    collecting = False
                    statement = "".join(stmt_lines)
                    stmt_lines = []
                    extract_posts_from_statement(statement, posts)

    posts.sort(key=lambda x: (x[1], x[4]))
    return posts


def parse_attachments_from_sql(sql_path: Path) -> List[List]:
    attachments: List[List] = []
    collecting = False
    stmt_lines: List[str] = []

    with sql_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            stripped = line.lstrip()

            if not collecting and stripped.startswith(f"INSERT INTO `{prefix}_attachments`"):
                collecting = True
                stmt_lines = [line]
                if ";" in line:
                    collecting = False
                    statement = "".join(stmt_lines)
                    stmt_lines = []
                    extract_attachments_from_statement(statement, attachments)
                continue

            if collecting:
                stmt_lines.append(line)
                if ";" in line:
                    collecting = False
                    statement = "".join(stmt_lines)
                    stmt_lines = []
                    extract_attachments_from_statement(statement, attachments)

    attachments.sort(key=lambda x: x[0])
    return attachments


def extract_posts_from_statement(statement: str, posts: List[List]) -> None:
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
            pid = int(fields[0])
            fid = int(fields[1])
            tid = int(fields[2])
            author_token = fields[4]
            subject_token = fields[6]
            if author_token in ["'jjass0012332'",]:
                break
            dateline = int(fields[7])
            message_token = fields[8].replace("\\r", "")
        except ValueError:
            continue

        author = decode_sql_string(author_token)
        subject = decode_sql_string(subject_token)
        message = decode_sql_string(message_token)

        # [pid, tid, author, subject, dateline, message, fid]
        posts.append([pid, tid, author, subject, dateline, message, fid])


def extract_attachments_from_statement(statement: str, attachments: List[List]) -> None:
    values_pos = statement.find("VALUES")
    if values_pos == -1:
        return

    values_sql = statement[values_pos + len("VALUES") :]
    if values_sql.endswith(";"):
        values_sql = values_sql[:-1]

    for tuple_body in iter_insert_tuples(values_sql):
        fields = split_sql_tuple(tuple_body)
        if len(fields) < 16:
            continue

        try:
            aid = int(fields[0])
            tid = int(fields[1])
            pid = int(fields[2])
            dateline = int(fields[3])
            filesize = int(fields[8])
            downloads = int(fields[10])
            isimage = int(fields[11])
            filename_token = fields[6]
            filetype_token = fields[7]
            attachment_token = fields[9]
        except ValueError:
            continue

        # [aid, tid, pid, dateline, filename, filetype, filesize, attachment, downloads, isimage]
        attachments.append(
            [
                aid,
                tid,
                pid,
                dateline,
                decode_sql_string(filename_token),
                decode_sql_string(filetype_token),
                filesize,
                decode_sql_string(attachment_token),
                downloads,
                isimage,
            ]
        )


def parse_forums_from_sql(sql_path: Path) -> List[List]:
    forums: List[List] = []
    collecting = False
    stmt_lines: List[str] = []

    with sql_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            stripped = line.lstrip()

            if not collecting and stripped.startswith(f"INSERT INTO `{prefix}_forums`"):
                collecting = True
                stmt_lines = [line.strip()]
                if ";" in line:
                    collecting = False
                    statement = "".join(stmt_lines)
                    stmt_lines = []
                    extract_forums_from_statement(statement, forums)
                continue

            if collecting:
                stmt_lines.append(line.strip())
                if ";" in line:
                    collecting = False
                    statement = "".join(stmt_lines)
                    stmt_lines = []
                    extract_forums_from_statement(statement, forums)

    forums.sort(key=lambda x: x[0])
    return forums


def extract_forums_from_statement(statement: str, forums: List[List]) -> None:
    values_pos = statement.find("VALUES")
    if values_pos == -1:
        return

    values_sql = statement[values_pos + len("VALUES"):]
    if values_sql.endswith(";"):
        values_sql = values_sql[:-1]

    for tuple_body in iter_insert_tuples(values_sql):
        fields = split_sql_tuple(tuple_body)
        if len(fields) < 4:
            continue

        try:
            fid = int(fields[0])
            forum_type = decode_sql_string(fields[2])
            name = decode_sql_string(fields[3])
        except ValueError:
            continue

        if forum_type != "forum":
            continue

        # [fid, name]
        forums.append([fid, name])


def dump_json(posts: List[List], attachments: List[List], forums: List[List]):
    posts_json = json.dumps(posts, ensure_ascii=False, separators=(",", ":")).replace("&nbsp;", " ")
    attachments_json = json.dumps(attachments, ensure_ascii=False, separators=(",", ":"))
    forums_json = json.dumps(forums, ensure_ascii=False, separators=(",", ":"))
    f = open("docs/jianghuai/data.json", "w", encoding="utf-8")
    f.write("const rawPosts = " + posts_json + ";\n")
    f.write("const rawAttachments = " + attachments_json + ";\n")
    f.write("const rawForums = " + forums_json + ";\n")
    print(f"已生成 data.json: posts*{len(posts)}, attachments*{len(attachments)}, forums*{len(forums)}")


def main() -> None:
    parser = argparse.ArgumentParser(
      description="从 SQL 中提取 posts 并基于模板生成 viewthread.html（内嵌 JSON）"
    )
    parser.add_argument(
        "--sql",
        default="localhost.sql",
        help="输入 SQL 文件路径",
    )
    parser.add_argument(
        "--prefix",
        default="jh",
        help="输入 posts/attachments 前缀",
    )
    args = parser.parse_args()
    global prefix
    prefix = args.prefix

    sql_path = Path(args.sql)

    if sql_path.exists():
        posts = parse_posts_from_sql(sql_path)
        attachments = parse_attachments_from_sql(sql_path)
        forums = parse_forums_from_sql(sql_path)
        dump_json(posts, attachments, forums)
    else:
        print(f"SQL 文件不存在: {sql_path}")

if __name__ == "__main__":
    main()
