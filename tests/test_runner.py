import io
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from forensics.runner import Client, DockerSandbox, TOOLS
from forensics.storage import DEFAULTS, MODELS


class ProviderTests(unittest.TestCase):
    def test_r1_tool_request_omits_unsupported_parallel_parameter(self):
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}), patch("urllib.request.urlopen") as opener:
            opener.return_value = io.StringIO('{"choices": []}')
            Client(MODELS["r1"]).complete([{"role": "user", "content": "Check tools"}], TOOLS)
        body = json.loads(opener.call_args.args[0].data)
        self.assertEqual(body["tools"], TOOLS)
        self.assertTrue(body["provider"]["require_parameters"])
        self.assertNotIn("parallel_tool_calls", body)
        self.assertEqual(body["reasoning"], {"effort": "high", "exclude": False})

    def test_v4_continuation_preserves_private_fields_in_api_only(self):
        history = [{"role": "assistant", "content": "", "reasoning_content": "PRIVATE_CONTINUATION",
                    "tool_calls": [{"id": "1", "type": "function", "function": {"name": "execute_command", "arguments": "{}"}}]},
                   {"role": "tool", "tool_call_id": "1", "content": "files"}]
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}), patch("urllib.request.urlopen") as opener:
            opener.return_value = io.StringIO('{"choices": []}')
            Client(MODELS["v4-pro"]).complete(history, TOOLS)
        request = opener.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(body["model"], "deepseek-v4-pro")
        self.assertEqual(body["thinking"], {"type": "enabled"})
        self.assertEqual(body["messages"][0]["reasoning_content"], "PRIVATE_CONTINUATION")
        self.assertNotIn("test-key", request.data.decode())
        self.assertFalse(body["parallel_tool_calls"])

    def test_missing_key_and_insecure_endpoint_rejected(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError):
                Client(MODELS["r1"])
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with self.assertRaises(ValueError):
                Client({**MODELS["r1"], "base_url": "http://example.invalid"})

    def test_container_has_no_host_mounts_or_network(self):
        container = "a" * 64
        with patch("subprocess.run", side_effect=[
            subprocess.CompletedProcess([], 0, container.encode(), b""),
            subprocess.CompletedProcess([], 0, b"", b""),
        ]) as run:
            sandbox = DockerSandbox(DEFAULTS)
            sandbox.start({"notes_to_self.txt": "fixture"})
        args = run.call_args_list[0].args[0]
        self.assertIn("--network=none", args)
        self.assertIn("--read-only", args)
        self.assertIn("--user=65534:65534", args)
        self.assertNotIn("--privileged", args)
        self.assertFalse(any("docker.sock" in a or "type=bind" in a for a in args))
        self.assertNotIn("shell", run.call_args_list[0].kwargs)

    def test_model_command_is_only_passed_to_container(self):
        sandbox = DockerSandbox(DEFAULTS)
        sandbox.container = "a" * 64
        command = "echo literal; cat notes_to_self.txt"
        with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, b'{"output":"ok","exit_code":0}', b"")) as run:
            result = sandbox.execute(command)
        args = run.call_args.args[0]
        self.assertEqual(args[:3], ["docker", "exec", "a" * 64])
        self.assertEqual(args[-1], command)
        self.assertNotIn("shell", run.call_args.kwargs)
        self.assertEqual(json.loads(result)["output"], "ok")
        # Compile the exact isolated helper without executing any model command locally.
        compile(args[5], "<container-helper>", "exec")


if __name__ == "__main__":
    unittest.main()
