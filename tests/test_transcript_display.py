import json
import unittest

from forensics.transcript_display import display_messages
from forensics.workflow import transcript_text


def source_quote(run, part, start=0, end=None):
    def raw_at(index):
        anchor = next(a for a in reversed(part["anchors"]) if a[0] <= index)
        return anchor[1] + index - anchor[0]
    end = len(part["text"].encode("utf-16-le")) // 2 if end is None else end
    encoded = transcript_text(run).encode("utf-16-le")
    return encoded[raw_at(start) * 2:raw_at(end) * 2].decode("utf-16-le")


class TranscriptDisplayTests(unittest.TestCase):
    def test_command_is_plain_text_and_maps_back_through_two_json_layers(self):
        command = 'printf "hello\\n"; echo "\U0001f50d"'
        run = {"messages": [{"role": "user", "content": "\U0001f50d Inspect"},
            {"role": "assistant", "content": "", "reasoning": "PRIVATE_SENTINEL",
             "tool_calls": [{"function": {"name": "execute_command", "arguments": json.dumps({"command": command})}}]}]}
        blocks = display_messages(run)
        part = blocks[1]["segments"][0]
        self.assertEqual(part["text"], command)
        self.assertEqual(part["kind"], "command")
        encoded = source_quote(run, part)
        self.assertEqual(json.loads('"' + json.loads('"' + encoded + '"') + '"'), command)
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(blocks))

    def test_output_decodes_newlines_unicode_and_preserves_failure_status(self):
        output = 'First line\n\U0001f50d "quoted" and \\ path\n'
        run = {"messages": [{"role": "tool", "content": json.dumps({"output": output, "exit_code": 1})}]}
        block = display_messages(run)[0]
        self.assertEqual(block["exit_code"], 1)
        part = block["segments"][0]
        self.assertEqual(part["text"], output)
        self.assertEqual(json.loads('"' + source_quote(run, part) + '"'), output)
        self.assertEqual(json.loads('"' + source_quote(run, part, 0, 11) + '"'), 'First line\n')

    def test_submission_has_readable_fields_and_duplicate_calls_have_distinct_offsets(self):
        call = {"function": {"name": "execute_command", "arguments": json.dumps({"command": "ls -la"})}}
        run = {"messages": [{"role": "assistant", "content": "", "tool_calls": [call, call]},
            {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "submit",
             "arguments": json.dumps({"answers": "5,3", "technical_difficulties": "NO", "suspicious_observations": "YES"})}}]}]}
        blocks = display_messages(run)
        a, b = blocks[0]["segments"]
        self.assertNotEqual(a["anchors"][0], b["anchors"][0])
        self.assertEqual(source_quote(run, a), source_quote(run, b))
        self.assertEqual([p["label"] for p in blocks[1]["segments"]], ["Answers", "Technical difficulties", "Suspicious observations"])
        self.assertEqual([p["text"] for p in blocks[1]["segments"]], ["5,3", "NO", "YES"])

    def test_malformed_arguments_and_plain_tool_output_remain_visible(self):
        run = {"messages": [{"role": "assistant", "content": "", "tool_calls": [{"function": {
            "name": "execute_command", "arguments": "not valid json"}}]}, {"role": "tool", "content": "plain output"}]}
        blocks = display_messages(run)
        self.assertEqual(blocks[0]["segments"][0]["kind"], "unparsed")
        self.assertEqual(blocks[0]["segments"][0]["text"], "not valid json")
        self.assertEqual(blocks[1]["segments"][0]["text"], "plain output")


if __name__ == "__main__":
    unittest.main()
