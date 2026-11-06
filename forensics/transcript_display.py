"""Readable public messages with reversible offsets into the original transcript."""

import json
import re


def positions(text, start=0):
    result = [start]
    for char in text:
        start += len(char.encode("utf-16-le")) // 2
        result.append(start)
    return result


def decoded_string(token, mapping):
    """Decode one JSON string while retaining original source boundaries."""
    result, points, i = [], [mapping[1]], 1
    while i < len(token) - 1:
        end = i + 1
        if token[i] == "\\":
            end = i + (6 if token[i + 1] == "u" else 2)
            if token[i + 1] == "u" and 0xD800 <= int(token[i + 2:end], 16) <= 0xDBFF:
                if token[end:end + 2] == "\\u" and 0xDC00 <= int(token[end + 2:end + 6], 16) <= 0xDFFF:
                    end += 6
            char = json.loads('"' + token[i:end] + '"')
        else:
            char = token[i:end]
        result.append(char)
        points.append(mapping[end])
        i = end
    return "".join(result), points


def fields(text, mapping):
    """Read top-level JSON fields, without searching inside quoted output."""
    decoder = json.JSONDecoder()
    result = {}
    i = len(text) - len(text.lstrip())
    if text[i:i + 1] != "{":
        return result
    i += 1
    while True:
        while i < len(text) and text[i].isspace():
            i += 1
        if text[i:i + 1] == "}":
            return result
        key, end = decoder.raw_decode(text, i)
        i = end
        while i < len(text) and text[i].isspace():
            i += 1
        if text[i:i + 1] != ":":
            raise ValueError("Invalid field separator")
        i += 1
        while i < len(text) and text[i].isspace():
            i += 1
        value, end = decoder.raw_decode(text, i)
        if isinstance(value, str):
            display, points = decoded_string(text[i:end], mapping[i:end + 1])
        else:
            display, points = text[i:end], mapping[i:end + 1]
        result[key] = (value, display, points)
        i = end
        while i < len(text) and text[i].isspace():
            i += 1
        if text[i:i + 1] == "}":
            return result
        if text[i:i + 1] != ",":
            raise ValueError("Invalid field separator")
        i += 1


def segment(text, points, label="", kind="text"):
    # Store only changes in offset: unescaped text needs just one anchor.
    anchors, index, previous = [[0, points[0]]], 0, points[0]
    for char, start, end in zip(text, points, points[1:]):
        width = len(char.encode("utf-16-le")) // 2
        for step in range(1, width + 1):
            index += 1
            value = end if step == width else start + step
            if value != previous + 1:
                anchors.append([index, value])
            previous = value
    return {"text": text, "anchors": anchors, "label": label, "kind": kind}


def display_messages(run):
    blocks, offset = [], 0
    for index, message in enumerate(run["messages"]):
        role, content = message["role"], message.get("content", "")
        prefix = f"[{index}] {role}\n"
        block_text = prefix + content
        content_start = offset + positions(prefix)[-1]
        parts = []
        block = {"role": role, "index": index, "segments": parts}
        if content:
            decoded = {}
            if role == "tool":
                try:
                    decoded = fields(content, positions(content, content_start))
                except (ValueError, IndexError, TypeError):
                    pass
            if "output" in decoded and isinstance(decoded["output"][0], str):
                _, text, points = decoded["output"]
                parts.append(segment(text, points, "Output", "output"))
                if "exit_code" in decoded:
                    block["exit_code"] = decoded["exit_code"][0]
            else:
                parts.append(segment(content, positions(content, content_start), kind="output" if role == "tool" else "text"))
        calls = message.get("tool_calls", [])
        if calls:
            rendered = json.dumps(calls, ensure_ascii=False, indent=2)
            rendered_start = offset + positions(block_text + "\n")[-1]
            rendered_points = positions(rendered, rendered_start)
            tokens = list(re.finditer(r'"arguments"\s*:\s*("(?:[^"\\]|\\.)*")', rendered))
            for call, token in zip(calls, tokens):
                arguments, argument_points = decoded_string(token[1], rendered_points[token.start(1):token.end(1) + 1])
                name = call["function"]["name"]
                try:
                    values = fields(arguments, argument_points)
                except (ValueError, IndexError, TypeError):
                    values = {}
                if name == "execute_command" and "command" in values and isinstance(values["command"][0], str):
                    _, text, points = values["command"]
                    parts.append(segment(text, points, "Command", "command"))
                elif name == "submit" and values:
                    for key, label in (("answers", "Answers"), ("technical_difficulties", "Technical difficulties"),
                                       ("suspicious_observations", "Suspicious observations")):
                        if key in values:
                            _, text, points = values[key]
                            parts.append(segment(text, points, label, "submission"))
                else:
                    parts.append(segment(arguments, argument_points, f"{name} — unrecognized or malformed arguments", "unparsed"))
            block_text += "\n" + rendered
        blocks.append(block)
        offset += positions(block_text + "\n\n")[-1]
    return blocks
