from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from urllib.error import URLError
from urllib.request import urlopen
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_WORKSPACES_DIR = REPO_ROOT / "data" / "test_workspaces"


class WorkerProcess:
    def __init__(
        self,
        transport: str,
        project_root: Path | None = None,
        workspace_root: Path | None = None,
    ) -> None:
        self.transport = transport
        TEST_WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
        self.session_root: Path | None = None
        if project_root is None and workspace_root is None:
            self.session_root = Path(tempfile.mkdtemp(dir=TEST_WORKSPACES_DIR))
            self.project_root = self.session_root / "worker_project"
            self.workspace_root = self.session_root / "workspace"
            self.project_root.mkdir(parents=True, exist_ok=True)
            self.workspace_root.mkdir(parents=True, exist_ok=True)
        else:
            self.project_root = (project_root or REPO_ROOT).resolve()
            self.workspace_root = (workspace_root or self.project_root).resolve()
            self.project_root.mkdir(parents=True, exist_ok=True)
            self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "src.app",
                "--transport",
                transport,
                "--project-root",
                str(self.project_root),
                "--workspace-root",
                str(self.workspace_root),
            ],
            cwd=REPO_ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self._next_id = 1

    def close(self) -> None:
        if self.process.stdin is not None:
            self.process.stdin.close()
        if self.process.stdout is not None:
            self.process.stdout.close()
        self.process.wait(timeout=10)
        if self.session_root is not None:
            shutil.rmtree(self.session_root, ignore_errors=True)

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": method,
            "params": params or {},
        }
        self._next_id += 1

        if self.transport == "ndjson":
            return self._request_ndjson(payload)
        return self._request_content_length(payload)

    def _request_ndjson(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        encoded = json.dumps(payload).encode("utf-8") + b"\n"
        self.process.stdin.write(encoded)
        self.process.stdin.flush()
        response_line = self.process.stdout.readline()
        return json.loads(response_line.decode("utf-8"))

    def _request_content_length(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        encoded = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(encoded)}\r\n\r\n".encode("utf-8")
        self.process.stdin.write(header)
        self.process.stdin.write(encoded)
        self.process.stdin.flush()

        headers: dict[str, str] = {}
        while True:
            line = self.process.stdout.readline()
            if line in (b"\r\n", b"\n"):
                break
            name, value = line.decode("utf-8").strip().split(":", 1)
            headers[name.strip().lower()] = value.strip()
        body = self.process.stdout.read(int(headers["content-length"]))
        return json.loads(body.decode("utf-8"))


def request_ndjson_process(process: subprocess.Popen[bytes], payload: dict[str, Any]) -> dict[str, Any]:
    assert process.stdin is not None
    assert process.stdout is not None
    process.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
    process.stdin.flush()
    return json.loads(process.stdout.readline().decode("utf-8"))


def ollama_api_available() -> bool:
    try:
        with urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return bool(payload.get("models"))
    except (OSError, URLError, json.JSONDecodeError):
        return False


class WorkerRoundTripTests(unittest.TestCase):
    def test_ndjson_round_trip_supports_self_extension_scaffold(self) -> None:
        worker = WorkerProcess("ndjson")
        try:
            initialize = worker.request("initialize")
            self.assertEqual(initialize["result"]["serverInfo"]["name"], "usefulhelper-worker")

            tools = worker.request("tools/list")
            tool_names = {tool["name"] for tool in tools["result"]["tools"]}
            self.assertIn("worker.create_tool_scaffold", tool_names)
            self.assertIn("fs.patch_text", tool_names)
            self.assertIn("fs.search_text", tool_names)
            self.assertIn("python.run_unittest", tool_names)
            self.assertIn("python.run_compileall", tool_names)
            self.assertIn("inference.describe_loops", tool_names)
            self.assertIn("ollama.chat_text", tool_names)
            self.assertIn("ollama.list_models", tool_names)

            scaffold = worker.request(
                "tools/call",
                {
                    "name": "worker.create_tool_scaffold",
                    "arguments": {
                        "tool_name": "ollama.chat_json",
                        "description": "Draft stub for an Ollama-backed JSON chat tool.",
                        "manager": "workspace",
                        "action": "ollama.chat_json",
                    },
                },
            )
            generated_files = scaffold["result"]["structuredContent"]["generated_files"]
            self.assertIn(
                "src/core/components/extensions/ollama_chat_json_component.py",
                generated_files,
            )

            ast_scan = worker.request(
                "tools/call",
                {
                    "name": "ast.scan_python",
                    "arguments": {"paths": ["src"], "max_files": 20},
                },
            )
            self.assertGreaterEqual(ast_scan["result"]["structuredContent"]["files_scanned"], 1)

            read_back = worker.request(
                "tools/call",
                {
                    "name": "fs.read_files",
                    "arguments": {
                        "paths": ["src/core/components/extensions/ollama_chat_json_component.py"]
                    },
                },
            )
            content = read_back["result"]["structuredContent"]["files"][0]["content"]
            self.assertIn("class OllamaChatJsonComponent", content)
        finally:
            worker.close()

    def test_ndjson_round_trip_supports_extension_refresh_and_hot_reload(self) -> None:
        tool_name = "demo.echo_runtime_probe"
        safe_name = "demo_echo_runtime_probe"
        module_path = REPO_ROOT / "src" / "core" / "components" / "extensions" / f"{safe_name}_component.py"
        test_path = REPO_ROOT / "tests" / "generated" / f"test_{safe_name}.py"
        blueprint_json_path = REPO_ROOT / "_docs" / "tool_blueprints" / f"{safe_name}.json"
        blueprint_md_path = REPO_ROOT / "_docs" / "tool_blueprints" / f"{safe_name}.md"

        created_paths = [module_path, test_path, blueprint_json_path, blueprint_md_path]
        for path in created_paths:
            if path.exists():
                path.unlink()

        worker = WorkerProcess("ndjson", project_root=REPO_ROOT, workspace_root=REPO_ROOT)
        try:
            worker.request("initialize")

            scaffold_response = worker.request(
                "tools/call",
                {
                    "name": "worker.create_tool_scaffold",
                    "arguments": {
                        "tool_name": tool_name,
                        "description": "Runtime refresh probe tool.",
                        "manager": "workspace",
                        "action": "demo.echo_runtime_probe",
                    },
                },
            )
            generated_files = scaffold_response["result"]["structuredContent"]["generated_files"]
            self.assertIn(
                "src/core/components/extensions/demo_echo_runtime_probe_component.py",
                generated_files,
            )

            first_component = (
                "from __future__ import annotations\n\n\n"
                "class DemoEchoRuntimeProbeComponent:\n"
                "    \"\"\"Runtime refresh probe tool.\"\"\"\n\n"
                "    def demo_echo_runtime_probe(self, arguments: dict[str, object]) -> dict[str, object]:\n"
                "        return {\n"
                '            "phase": "first",\n'
                '            "arguments": arguments,\n'
                "        }\n"
            )
            worker.request(
                "tools/call",
                {
                    "name": "fs.write_files",
                    "arguments": {
                        "files": [
                            {
                                "path": "src/core/components/extensions/demo_echo_runtime_probe_component.py",
                                "content": first_component,
                            }
                        ],
                        "mode": "overwrite",
                    },
                },
            )

            refresh_response = worker.request(
                "tools/call",
                {
                    "name": "worker.refresh_extension_tools",
                    "arguments": {},
                },
            )
            refresh_result = refresh_response["result"]["structuredContent"]
            self.assertIn(tool_name, refresh_result["active_extension_tool_names"])

            tools_response = worker.request("tools/list")
            tool_names = {tool["name"] for tool in tools_response["result"]["tools"]}
            self.assertIn(tool_name, tool_names)

            first_call = worker.request(
                "tools/call",
                {
                    "name": tool_name,
                    "arguments": {"message": "hello"},
                },
            )
            self.assertEqual(
                first_call["result"]["structuredContent"]["phase"],
                "first",
            )

            second_component = first_component.replace('"phase": "first"', '"phase": "second"')
            worker.request(
                "tools/call",
                {
                    "name": "fs.write_files",
                    "arguments": {
                        "files": [
                            {
                                "path": "src/core/components/extensions/demo_echo_runtime_probe_component.py",
                                "content": second_component,
                            }
                        ],
                        "mode": "overwrite",
                    },
                },
            )

            second_refresh = worker.request(
                "tools/call",
                {
                    "name": "worker.refresh_extension_tools",
                    "arguments": {},
                },
            )
            self.assertIn(
                tool_name,
                second_refresh["result"]["structuredContent"]["active_extension_tool_names"],
            )

            second_call = worker.request(
                "tools/call",
                {
                    "name": tool_name,
                    "arguments": {"message": "hello again"},
                },
            )
            self.assertEqual(
                second_call["result"]["structuredContent"]["phase"],
                "second",
            )
        finally:
            worker.close()
            for path in created_paths:
                path.unlink(missing_ok=True)

    def test_inference_tools_expose_loop_slot_and_text_mode(self) -> None:
        worker = WorkerProcess("ndjson")
        try:
            worker.request("initialize")

            describe_response = worker.request(
                "tools/call",
                {
                    "name": "inference.describe_loops",
                    "arguments": {},
                },
            )
            describe_result = describe_response["result"]["structuredContent"]
            self.assertEqual(describe_result["default_loop_name"], "ollama.single_turn")
            self.assertGreaterEqual(describe_result["loop_count"], 1)
            self.assertEqual(describe_result["loops"][0]["loop_name"], "ollama.single_turn")

            if not ollama_api_available():
                return

            text_response = worker.request(
                "tools/call",
                {
                    "name": "ollama.chat_text",
                    "arguments": {
                        "loop_name": "ollama.single_turn",
                        "model": "qwen2.5:0.5b",
                        "system": "Answer briefly.",
                        "user": "Reply with exactly: useful helper ready",
                        "temperature": 0,
                        "max_tokens": 40,
                        "timeout_seconds": 60,
                    },
                },
            )

            result = text_response["result"]["structuredContent"]
            self.assertEqual(result["loop_name"], "ollama.single_turn")
            self.assertEqual(result["response_format"], "text")
            self.assertTrue(result["content"].strip())
            self.assertEqual(result["model"], "qwen2.5:0.5b")
        finally:
            worker.close()

    def test_ndjson_round_trip_supports_search_and_python_helpers(self) -> None:
        worker = WorkerProcess("ndjson")
        try:
            worker.request("initialize")

            write_response = worker.request(
                "tools/call",
                {
                    "name": "fs.write_files",
                    "arguments": {
                        "files": [
                            {
                                "path": "pkg/__init__.py",
                                "content": "",
                            },
                            {
                                "path": "pkg/sample_math.py",
                                "content": "def add(a: int, b: int) -> int:\n    return a + b\n",
                            },
                            {
                                "path": "tests/test_sample_math.py",
                                "content": (
                                    "import unittest\n\n"
                                    "from pkg.sample_math import add\n\n\n"
                                    "class SampleMathTests(unittest.TestCase):\n"
                                    "    def test_add(self) -> None:\n"
                                    "        self.assertEqual(add(2, 5), 7)\n\n\n"
                                    "if __name__ == '__main__':\n"
                                    "    unittest.main()\n"
                                ),
                            },
                            {
                                "path": "notes/search_target.txt",
                                "content": "Alpha line\nNeedle phrase lives here\nOmega line\n",
                            },
                        ]
                    },
                },
            )
            self.assertIn("pkg/sample_math.py", write_response["result"]["structuredContent"]["created_files"])

            search_response = worker.request(
                "tools/call",
                {
                    "name": "fs.search_text",
                    "arguments": {
                        "pattern": "needle phrase",
                        "paths": ["notes", "tests"],
                        "max_results": 10,
                    },
                },
            )
            search_result = search_response["result"]["structuredContent"]
            self.assertEqual(search_result["match_count"], 1)
            self.assertEqual(search_result["matches"][0]["path"], "notes/search_target.txt")
            self.assertEqual(search_result["matches"][0]["lineno"], 2)

            unittest_response = worker.request(
                "tools/call",
                {
                    "name": "python.run_unittest",
                    "arguments": {
                        "start_dir": "tests",
                        "timeout_seconds": 60,
                    },
                },
            )
            unittest_result = unittest_response["result"]["structuredContent"]
            self.assertTrue(unittest_result["succeeded"])
            self.assertEqual(unittest_result["exit_code"], 0)

            compileall_response = worker.request(
                "tools/call",
                {
                    "name": "python.run_compileall",
                    "arguments": {
                        "paths": ["pkg", "tests"],
                        "timeout_seconds": 60,
                    },
                },
            )
            compileall_result = compileall_response["result"]["structuredContent"]
            self.assertTrue(compileall_result["succeeded"])
            self.assertEqual(compileall_result["exit_code"], 0)
        finally:
            worker.close()

    def test_ndjson_round_trip_supports_allowlisted_git_sysops(self) -> None:
        worker = WorkerProcess("ndjson")
        try:
            worker.request("initialize")
            worker.request(
                "tools/call",
                {
                    "name": "fs.write_files",
                    "arguments": {
                        "files": [
                            {
                                "path": "repo_notes/notes.txt",
                                "content": "tracked change\n",
                            }
                        ],
                        "mode": "overwrite",
                    },
                },
            )

            git_available = shutil.which("git") is not None
            if git_available:
                subprocess.run(
                    ["git", "init"],
                    cwd=worker.workspace_root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                subprocess.run(
                    ["git", "config", "user.name", "Useful Helper Tests"],
                    cwd=worker.workspace_root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                subprocess.run(
                    ["git", "config", "user.email", "tests@example.invalid"],
                    cwd=worker.workspace_root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                subprocess.run(
                    ["git", "add", "repo_notes/notes.txt"],
                    cwd=worker.workspace_root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                subprocess.run(
                    ["git", "commit", "-m", "Initial notes"],
                    cwd=worker.workspace_root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                worker.request(
                    "tools/call",
                    {
                        "name": "fs.write_files",
                        "arguments": {
                            "files": [
                                {
                                    "path": "repo_notes/notes.txt",
                                    "content": "tracked change\nsecond line\n",
                                }
                            ],
                            "mode": "overwrite",
                        },
                    },
                )
                subprocess.run(
                    ["git", "add", "repo_notes/notes.txt"],
                    cwd=worker.workspace_root,
                    capture_output=True,
                    text=True,
                    check=False,
                )

            status_response = worker.request(
                "tools/call",
                {
                    "name": "sysops.git_status",
                    "arguments": {
                        "path": ".",
                        "timeout_seconds": 30,
                    },
                },
            )
            status_result = status_response["result"]["structuredContent"]
            self.assertEqual(status_result["git_available"], git_available)

            diff_response = worker.request(
                "tools/call",
                {
                    "name": "sysops.git_diff_summary",
                    "arguments": {
                        "path": ".",
                        "cached": True,
                        "timeout_seconds": 30,
                    },
                },
            )
            diff_result = diff_response["result"]["structuredContent"]
            self.assertEqual(diff_result["git_available"], git_available)

            repo_summary_response = worker.request(
                "tools/call",
                {
                    "name": "sysops.git_repo_summary",
                    "arguments": {
                        "path": ".",
                        "timeout_seconds": 30,
                    },
                },
            )
            repo_summary_result = repo_summary_response["result"]["structuredContent"]
            self.assertEqual(repo_summary_result["git_available"], git_available)

            recent_commits_response = worker.request(
                "tools/call",
                {
                    "name": "sysops.git_recent_commits",
                    "arguments": {
                        "path": ".",
                        "limit": 5,
                        "timeout_seconds": 30,
                    },
                },
            )
            recent_commits_result = recent_commits_response["result"]["structuredContent"]
            self.assertEqual(recent_commits_result["git_available"], git_available)

            if git_available:
                self.assertTrue(status_result["repo_detected"])
                self.assertIn("repo_notes/notes.txt", status_result["stdout"])
                self.assertTrue(diff_result["repo_detected"])
                self.assertIn("repo_notes/notes.txt", diff_result["changed_files"])
                self.assertTrue(repo_summary_result["repo_detected"])
                self.assertIsNotNone(repo_summary_result["branch"])
                self.assertEqual(repo_summary_result["head_subject"], "Initial notes")
                self.assertGreaterEqual(repo_summary_result["dirty_file_count"], 1)
                self.assertTrue(recent_commits_result["repo_detected"])
                self.assertGreaterEqual(recent_commits_result["commit_count"], 1)
                self.assertEqual(recent_commits_result["commits"][0]["subject"], "Initial notes")
            else:
                self.assertFalse(status_result["repo_detected"])
                self.assertFalse(diff_result["repo_detected"])
                self.assertFalse(repo_summary_result["repo_detected"])
                self.assertFalse(recent_commits_result["repo_detected"])
        finally:
            worker.close()

    def test_ndjson_round_trip_supports_archive_inspect_and_extract(self) -> None:
        worker = WorkerProcess("ndjson")
        try:
            worker.request("initialize")

            safe_archive = worker.workspace_root / "archives" / "sample_bundle.zip"
            safe_archive.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(safe_archive, "w") as archive:
                archive.writestr("bundle/README.md", "# Bundle\n")
                archive.writestr("bundle/src/app.py", "print('hello bundle')\n")

            inspect_response = worker.request(
                "tools/call",
                {
                    "name": "archive.inspect_zip",
                    "arguments": {
                        "archive_path": "archives/sample_bundle.zip",
                        "max_entries": 20,
                    },
                },
            )
            inspect_result = inspect_response["result"]["structuredContent"]
            self.assertEqual(inspect_result["unsafe_entry_count"], 0)
            self.assertEqual(inspect_result["entry_count"], 2)

            extract_response = worker.request(
                "tools/call",
                {
                    "name": "archive.extract_zip",
                    "arguments": {
                        "archive_path": "archives/sample_bundle.zip",
                        "target_dir": "extracted/sample_bundle",
                        "mode": "overwrite",
                    },
                },
            )
            extract_result = extract_response["result"]["structuredContent"]
            self.assertIn(
                "extracted/sample_bundle/bundle/README.md",
                extract_result["created_files"],
            )
            self.assertIn(
                "extracted/sample_bundle/bundle/src/app.py",
                extract_result["created_files"],
            )
            self.assertEqual(
                (
                    worker.workspace_root
                    / "extracted"
                    / "sample_bundle"
                    / "bundle"
                    / "README.md"
                ).read_text(encoding="utf-8"),
                "# Bundle\n",
            )

            unsafe_archive = worker.workspace_root / "archives" / "unsafe_bundle.zip"
            with zipfile.ZipFile(unsafe_archive, "w") as archive:
                archive.writestr("../escape.txt", "should never extract\n")

            unsafe_response = worker.request(
                "tools/call",
                {
                    "name": "archive.extract_zip",
                    "arguments": {
                        "archive_path": "archives/unsafe_bundle.zip",
                        "target_dir": "extracted/unsafe_bundle",
                    },
                },
            )
            self.assertIn("error", unsafe_response)
            self.assertIn("unsafe member paths", unsafe_response["error"]["message"])
        finally:
            worker.close()

    def test_ndjson_round_trip_supports_one_call_archive_to_sandbox_intake(self) -> None:
        worker = WorkerProcess("ndjson")
        try:
            worker.request("initialize")

            bundle_archive = worker.workspace_root / "archives" / "intake_bundle.zip"
            bundle_archive.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(bundle_archive, "w") as archive:
                archive.writestr("bundle_pkg/README.md", "# Intake Bundle\n")
                archive.writestr(
                    "bundle_pkg/app_manifest.json",
                    json.dumps(
                        {
                            "name": "IntakeBundle",
                            "description": "Sample intake bundle.",
                            "mcp_entrypoint": "bundle_pkg/mcp_server.py",
                            "self_test_entrypoint": "bundle_pkg/smoke_test.py",
                            "human_guide": "bundle_pkg/README.md",
                        }
                    ),
                )
                archive.writestr("bundle_pkg/mcp_server.py", "def run() -> None:\n    pass\n")
                archive.writestr("bundle_pkg/smoke_test.py", "print('smoke')\n")
                archive.writestr(
                    "bundle_pkg/src/intake_demo.py",
                    (
                        "class IntakeDemo:\n"
                        "    def render(self) -> str:\n"
                        "        return 'intake demo'\n"
                    ),
                )

            intake_response = worker.request(
                "tools/call",
                {
                    "name": "intake.zip_to_sandbox",
                    "arguments": {
                        "archive_path": "archives/intake_bundle.zip",
                        "target_dir": "intake/bundles/intake_bundle",
                        "mode": "overwrite",
                        "reset_sandbox": True,
                        "max_files": 20,
                    },
                },
            )
            intake_result = intake_response["result"]["structuredContent"]
            self.assertEqual(intake_result["unsafe_entry_count"], 0)
            self.assertEqual(
                intake_result["inspection"]["archive_path"],
                "archives/intake_bundle.zip",
            )
            self.assertIn(
                "intake/bundles/intake_bundle/bundle_pkg/README.md",
                intake_result["extraction"]["created_files"],
            )
            self.assertIn(
                "intake/bundles/intake_bundle/bundle_pkg/src/intake_demo.py",
                intake_result["ingestion"]["created_files"],
            )
            self.assertGreaterEqual(intake_result["sandbox_head_file_count"], 5)
            summary_files = intake_result["bundle_summary"]["summary_files"]
            self.assertIn("bundle_pkg/app_manifest.json", summary_files)
            manifest_details = intake_result["bundle_summary"]["manifest_details"]
            app_manifest_detail = next(
                item
                for item in manifest_details
                if item["path"] == "bundle_pkg/app_manifest.json"
            )
            self.assertEqual(app_manifest_detail["name"], "IntakeBundle")
            self.assertEqual(
                app_manifest_detail["mcp_entrypoint"],
                "bundle_pkg/mcp_server.py",
            )
            entrypoint_paths = {
                item["path"] for item in intake_result["likely_entrypoints"]
            }
            self.assertIn("bundle_pkg/mcp_server.py", entrypoint_paths)
            self.assertIn("bundle_pkg/smoke_test.py", entrypoint_paths)

            sandbox_read = worker.request(
                "tools/call",
                {
                    "name": "sandbox.read_head",
                    "arguments": {
                        "paths": [
                            "intake/bundles/intake_bundle/bundle_pkg/README.md",
                            "intake/bundles/intake_bundle/bundle_pkg/src/intake_demo.py",
                        ]
                    },
                },
            )
            read_files = {
                item["path"]: item["content"]
                for item in sandbox_read["result"]["structuredContent"]["files"]
            }
            self.assertEqual(
                read_files["intake/bundles/intake_bundle/bundle_pkg/README.md"],
                "# Intake Bundle\n",
            )
            self.assertIn(
                "class IntakeDemo",
                read_files["intake/bundles/intake_bundle/bundle_pkg/src/intake_demo.py"],
            )
        finally:
            worker.close()

    def test_ndjson_round_trip_supports_parts_catalog_build_search_get_and_export(self) -> None:
        worker = WorkerProcess("ndjson")
        try:
            worker.request("initialize")

            worker.request(
                "tools/call",
                {
                    "name": "fs.write_files",
                    "arguments": {
                        "files": [
                            {
                                "path": "src/core/components/sample_component.py",
                                "content": (
                                    "class SampleComponent:\n"
                                    "    def render(self) -> str:\n"
                                    "        return 'sample component'\n"
                                ),
                            },
                            {
                                "path": "src/core/services/sample_service.py",
                                "content": (
                                    "def provide_value() -> int:\n"
                                    "    return 7\n"
                                ),
                            },
                            {
                                "path": "_docs/COMPONENT_NOTES.md",
                                "content": (
                                    "# Sample Component Notes\n\n"
                                    "This sample component supports sample rendering.\n"
                                    "It is a component export bundle note for docs-focused retrieval.\n"
                                ),
                            },
                            {
                                "path": "_docs/_AppJOURNAL/entries/2026-04-08_sample.md",
                                "content": (
                                    "# Journal Entry\n\n"
                                    "This journal records a sample component export bundle experiment.\n"
                                ),
                            },
                            {
                                "path": "tests/test_sample_component.py",
                                "content": (
                                    "import unittest\n\n"
                                    "from src.core.components.sample_component import SampleComponent\n\n"
                                    "class SampleComponentTests(unittest.TestCase):\n"
                                    "    def test_render(self) -> None:\n"
                                    "        self.assertEqual(SampleComponent().render(), 'sample component')\n"
                                ),
                            },
                        ]
                    },
                },
            )

            build_response = worker.request(
                "tools/call",
                {
                    "name": "parts.catalog_build",
                    "arguments": {
                        "paths": ["src", "_docs", "tests"],
                        "reset": True,
                        "max_files": 50,
                    },
                },
            )
            build_result = build_response["result"]["structuredContent"]
            self.assertGreaterEqual(build_result["part_count"], 4)
            self.assertIn(
                "src/core/components/sample_component.py",
                build_result["created_parts"],
            )

            search_response = worker.request(
                "tools/call",
                {
                    "name": "parts.catalog_search",
                    "arguments": {
                        "query": "render sample component",
                        "kinds": ["component"],
                        "layers": ["core"],
                        "limit": 10,
                    },
                },
            )
            search_result = search_response["result"]["structuredContent"]
            self.assertGreaterEqual(search_result["result_count"], 1)
            self.assertGreaterEqual(search_result["item_count"], 1)
            self.assertIn("evidence shelf", search_result["shelf_summary"].lower())
            self.assertEqual(
                search_result["location_index"][0],
                "src/core/components/sample_component.py",
            )
            self.assertEqual(
                search_result["location_records"][0]["location"],
                "src/core/components/sample_component.py",
            )
            first_part_id = search_result["results"][0]["part_id"]
            self.assertEqual(first_part_id, "src/core/components/sample_component.py")
            self.assertGreaterEqual(search_result["results"][0]["matched_token_count"], 3)
            self.assertIsNotNone(search_result["results"][0]["fts_rank"])
            self.assertEqual(
                search_result["items"][0]["location"],
                "src/core/components/sample_component.py",
            )
            self.assertIn("component", search_result["items"][0]["item_summary"].lower())
            self.assertIn("samplecomponent", search_result["items"][0]["item_summary"].lower())
            self.assertGreaterEqual(len(search_result["items"][0]["why_matched"]), 1)

            prefer_docs_response = worker.request(
                "tools/call",
                {
                    "name": "parts.catalog_search",
                    "arguments": {
                        "query": "component export bundle",
                        "prefer_docs": True,
                        "limit": 5,
                    },
                },
            )
            prefer_docs_result = prefer_docs_response["result"]["structuredContent"]
            self.assertEqual(prefer_docs_result["intent_target"], "auto")
            self.assertEqual(prefer_docs_result["items"][0]["kind"], "doc")
            self.assertEqual(
                prefer_docs_result["items"][0]["location"],
                "_docs/COMPONENT_NOTES.md",
            )
            self.assertEqual(
                prefer_docs_result["items"][0]["document_role"],
                "doc",
            )
            self.assertEqual(
                prefer_docs_result["location_records"][0]["document_role"],
                "doc",
            )

            prefer_code_response = worker.request(
                "tools/call",
                {
                    "name": "parts.catalog_search",
                    "arguments": {
                        "query": "component export bundle",
                        "prefer_code": True,
                        "intent_target": "structural",
                        "limit": 5,
                    },
                },
            )
            prefer_code_result = prefer_code_response["result"]["structuredContent"]
            self.assertEqual(prefer_code_result["intent_target"], "structural")
            self.assertEqual(prefer_code_result["items"][0]["kind"], "component")

            history_docs_response = worker.request(
                "tools/call",
                {
                    "name": "parts.catalog_search",
                    "arguments": {
                        "query": "journal history sample component export bundle",
                        "prefer_docs": True,
                        "intent_target": "semantic",
                        "limit": 5,
                    },
                },
            )
            history_docs_result = history_docs_response["result"]["structuredContent"]
            self.assertEqual(
                history_docs_result["items"][0]["document_role"],
                "journal_entry",
            )

            get_response = worker.request(
                "tools/call",
                {
                    "name": "parts.catalog_get",
                    "arguments": {
                        "part_ids": [first_part_id],
                        "max_chars_per_part": 5000,
                    },
                },
            )
            get_result = get_response["result"]["structuredContent"]
            self.assertEqual(get_result["count"], 1)
            self.assertIn("class SampleComponent", get_result["parts"][0]["content"])
            symbol_names = {
                item["symbol_name"] for item in get_result["parts"][0]["symbols"]
            }
            self.assertIn("SampleComponent", symbol_names)

            export_response = worker.request(
                "tools/call",
                {
                    "name": "parts.export_selection",
                    "arguments": {
                        "part_ids": [first_part_id, "src/core/services/sample_service.py"],
                        "target_dir": "parts_exports/selection_v1",
                        "mode": "overwrite",
                    },
                },
            )
            export_result = export_response["result"]["structuredContent"]
            self.assertIn(
                "parts_exports/selection_v1/src/core/components/sample_component.py",
                export_result["created_files"],
            )
            exported_component = (
                worker.workspace_root
                / "parts_exports"
                / "selection_v1"
                / "src"
                / "core"
                / "components"
                / "sample_component.py"
            )
            self.assertTrue(exported_component.exists())
            self.assertIn("SampleComponent", exported_component.read_text(encoding="utf-8"))
        finally:
            worker.close()

    def test_ndjson_round_trip_supports_sandbox_head_and_revision_flow(self) -> None:
        worker = WorkerProcess("ndjson")
        try:
            worker.request("initialize")

            worker.request(
                "tools/call",
                {
                    "name": "fs.write_files",
                    "arguments": {
                        "files": [
                            {
                                "path": "src/sample.py",
                                "content": (
                                    "import os\n\n"
                                    "class Demo:\n"
                                    "    def run(self) -> str:\n"
                                    "        return os.getcwd()\n\n"
                                    "def helper(value: int) -> int:\n"
                                    "    return value + 1\n"
                                ),
                            },
                            {
                                "path": "docs/notes.txt",
                                "content": "Alpha line\nNeedle lives here\nOmega line\n",
                            },
                        ]
                    },
                },
            )

            sandbox_init = worker.request(
                "tools/call",
                {
                    "name": "sandbox.init",
                    "arguments": {"reset": True},
                },
            )
            self.assertTrue(
                sandbox_init["result"]["structuredContent"]["db_path"].endswith(
                    "project_sandbox.sqlite3"
                )
            )

            sandbox_ingest = worker.request(
                "tools/call",
                {
                    "name": "sandbox.ingest_workspace",
                    "arguments": {"paths": ["src", "docs"], "max_files": 20},
                },
            )
            ingest_result = sandbox_ingest["result"]["structuredContent"]
            self.assertIn("src/sample.py", ingest_result["created_files"])
            self.assertIn("docs/notes.txt", ingest_result["created_files"])

            sandbox_search = worker.request(
                "tools/call",
                {
                    "name": "sandbox.search_head",
                    "arguments": {"pattern": "needle", "paths": ["docs"]},
                },
            )
            self.assertEqual(sandbox_search["result"]["structuredContent"]["match_count"], 1)

            sandbox_symbols = worker.request(
                "tools/call",
                {
                    "name": "sandbox.query_symbols",
                    "arguments": {"paths": ["src"], "limit": 20},
                },
            )
            symbol_names = {
                item["name"] for item in sandbox_symbols["result"]["structuredContent"]["symbols"]
            }
            self.assertIn("Demo", symbol_names)
            self.assertIn("helper", symbol_names)

            sandbox_stage = worker.request(
                "tools/call",
                {
                    "name": "sandbox.stage_diff",
                    "arguments": {
                        "changes": [
                            {
                                "path": "docs/notes.txt",
                                "operation": "replace_text",
                                "old_text": "Needle lives here",
                                "new_text": "Needle now lives in sandbox HEAD",
                                "count": 1,
                            },
                            {
                                "path": "generated/from_sandbox.txt",
                                "operation": "set_text",
                                "text": "Created only in sandbox before export.\n",
                            },
                        ]
                    },
                },
            )
            stage_result = sandbox_stage["result"]["structuredContent"]
            self.assertIn("docs/notes.txt", stage_result["updated_files"])
            self.assertIn("generated/from_sandbox.txt", stage_result["created_files"])

            sandbox_read = worker.request(
                "tools/call",
                {
                    "name": "sandbox.read_head",
                    "arguments": {"paths": ["docs/notes.txt", "generated/from_sandbox.txt"]},
                },
            )
            files = {
                item["path"]: item["content"]
                for item in sandbox_read["result"]["structuredContent"]["files"]
            }
            self.assertIn("sandbox HEAD", files["docs/notes.txt"])
            self.assertEqual(files["generated/from_sandbox.txt"], "Created only in sandbox before export.\n")

            sandbox_history = worker.request(
                "tools/call",
                {
                    "name": "sandbox.history_for_file",
                    "arguments": {"path": "docs/notes.txt", "limit": 5},
                },
            )
            history_result = sandbox_history["result"]["structuredContent"]
            self.assertGreaterEqual(history_result["revision_count"], 2)
            self.assertEqual(history_result["path"], "docs/notes.txt")

            sandbox_export = worker.request(
                "tools/call",
                {
                    "name": "sandbox.export_head",
                    "arguments": {
                        "target_dir": "sandbox_exports/head_v1",
                        "mode": "overwrite",
                    },
                },
            )
            export_result = sandbox_export["result"]["structuredContent"]
            self.assertIn(
                "sandbox_exports/head_v1/docs/notes.txt",
                export_result["created_files"],
            )
            exported_notes = (
                worker.workspace_root / "sandbox_exports" / "head_v1" / "docs" / "notes.txt"
            )
            exported_generated = (
                worker.workspace_root
                / "sandbox_exports"
                / "head_v1"
                / "generated"
                / "from_sandbox.txt"
            )
            self.assertTrue(exported_notes.exists())
            self.assertTrue(exported_generated.exists())
            self.assertIn("sandbox HEAD", exported_notes.read_text(encoding="utf-8"))
            self.assertEqual(
                exported_generated.read_text(encoding="utf-8"),
                "Created only in sandbox before export.\n",
            )
        finally:
            worker.close()

    def test_content_length_round_trip_enforces_guardrails_and_memory_tools(self) -> None:
        worker = WorkerProcess("content-length")
        try:
            worker.request("initialize")

            write_response = worker.request(
                "tools/call",
                {
                    "name": "fs.write_files",
                    "arguments": {
                        "files": [
                            {"path": "demo/example.txt", "content": "hello worker\n"}
                        ],
                        "mode": "overwrite",
                    },
                },
            )
            self.assertIn(
                "demo/example.txt",
                write_response["result"]["structuredContent"]["created_files"],
            )

            patch_response = worker.request(
                "tools/call",
                {
                    "name": "fs.patch_text",
                    "arguments": {
                        "changes": [
                            {
                                "path": "demo/example.txt",
                                "operation": "replace_text",
                                "old_text": "hello",
                                "new_text": "guarded",
                                "count": 1,
                            }
                        ]
                    },
                },
            )
            self.assertEqual(patch_response["result"]["structuredContent"]["count"], 1)

            read_response = worker.request(
                "tools/call",
                {
                    "name": "fs.read_files",
                    "arguments": {"paths": ["demo/example.txt"]},
                },
            )
            file_content = read_response["result"]["structuredContent"]["files"][0]["content"]
            self.assertEqual(file_content, "guarded worker\n")

            tasklist_replace = worker.request(
                "tools/call",
                {
                    "name": "tasklist.replace",
                    "arguments": {
                        "items": [
                            {"text": "Verify guardrails", "status": "in_progress"},
                            {"text": "Document transport tests", "status": "pending"},
                        ]
                    },
                },
            )
            self.assertEqual(tasklist_replace["result"]["structuredContent"]["item_count"], 2)

            tasklist_view = worker.request(
                "tools/call",
                {
                    "name": "tasklist.view",
                    "arguments": {},
                },
            )
            self.assertEqual(tasklist_view["result"]["structuredContent"]["item_count"], 2)

            journal_append = worker.request(
                "tools/call",
                {
                    "name": "journal.append",
                    "arguments": {
                        "title": "Round-trip verification",
                        "summary": "Verified guardrails and memory tools through content-length framing.",
                        "files_changed": ["demo/example.txt"],
                        "testing": ["content-length end-to-end subprocess round trip"],
                    },
                },
            )
            mirror_path = Path(journal_append["result"]["structuredContent"]["mirror_path"])
            self.assertTrue(mirror_path.exists())

            absolute_path_error = worker.request(
                "tools/call",
                {
                    "name": "fs.write_files",
                    "arguments": {
                        "files": [
                            {
                                "path": str(worker.workspace_root / "outside.txt"),
                                "content": "should fail",
                            }
                        ]
                    },
                },
            )
            self.assertIn("error", absolute_path_error)
            self.assertIn("Absolute paths are not accepted", absolute_path_error["error"]["message"])
        finally:
            worker.close()

    def test_sidecar_export_bundle_can_run_as_vendored_worker(self) -> None:
        worker = WorkerProcess("ndjson")
        try:
            worker.request("initialize")

            export_response = worker.request(
                "tools/call",
                {
                    "name": "sidecar.export_bundle",
                    "arguments": {
                        "target_dir": "_sidecar/usefulhelper",
                        "include_tests": True,
                    },
                },
            )
            structured = export_response["result"]["structuredContent"]
            self.assertIn(
                "_sidecar/usefulhelper/src/app.py",
                structured["created_files"],
            )
            self.assertIn(
                "_sidecar/usefulhelper/run_for_app.bat",
                structured["created_files"],
            )
            self.assertIn(
                "_sidecar/usefulhelper/_docs/builder_constraint_contract.md",
                structured["created_files"],
            )
            self.assertIn(
                "_sidecar/usefulhelper/_docs/ONBOARDING.md",
                structured["created_files"],
            )
            self.assertIn(
                "_sidecar/usefulhelper/_docs/TODO.md",
                structured["created_files"],
            )
            self.assertIn(
                "_sidecar/usefulhelper/_docs/dev_log.md",
                structured["created_files"],
            )
            self.assertIn(
                "_sidecar/usefulhelper/tests/test_worker_roundtrip.py",
                structured["created_files"],
            )

            exported_root = worker.workspace_root / "_sidecar" / "usefulhelper"
            manifest_path = exported_root / "sidecar_manifest.json"
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["relative_app_root_from_sidecar"], "..\\..")
            self.assertTrue(manifest["include_tests"])
            self.assertIn("run_for_app.bat", manifest["managed_files"])

            exported_readme = exported_root / "README.md"
            exported_readme.write_text("# locally changed\n", encoding="utf-8")
            unmanaged_notes = exported_root / "local_notes.txt"
            unmanaged_notes.write_text("keep me\n", encoding="utf-8")

            dry_run_response = worker.request(
                "tools/call",
                {
                    "name": "sidecar.export_bundle",
                    "arguments": {
                        "target_dir": "_sidecar/usefulhelper",
                        "include_tests": True,
                        "dry_run": True,
                    },
                },
            )
            dry_run_result = dry_run_response["result"]["structuredContent"]
            self.assertFalse(dry_run_result["applied"])
            self.assertEqual(dry_run_result["install_state"], "existing_sidecar")
            self.assertTrue(dry_run_result["recognized_existing_sidecar"])
            self.assertIn("README.md", dry_run_result["planned_updated_files"])
            self.assertIn("local_notes.txt", dry_run_result["unmanaged_existing_files"])

            blocked_reinstall = worker.request(
                "tools/call",
                {
                    "name": "sidecar.export_bundle",
                    "arguments": {
                        "target_dir": "_sidecar/usefulhelper",
                        "include_tests": True,
                    },
                },
            )
            self.assertIn("error", blocked_reinstall)
            self.assertIn("overwrite=true and reinstall=true", blocked_reinstall["error"]["message"])

            reinstall_response = worker.request(
                "tools/call",
                {
                    "name": "sidecar.export_bundle",
                    "arguments": {
                        "target_dir": "_sidecar/usefulhelper",
                        "include_tests": True,
                        "overwrite": True,
                        "reinstall": True,
                    },
                },
            )
            reinstall_result = reinstall_response["result"]["structuredContent"]
            self.assertTrue(reinstall_result["applied"])
            self.assertIn("_sidecar/usefulhelper/README.md", reinstall_result["overwritten_files"])
            self.assertIn("local_notes.txt", reinstall_result["unmanaged_existing_files"])
            self.assertEqual(
                exported_readme.read_text(encoding="utf-8"),
                (REPO_ROOT / "README.md").read_text(encoding="utf-8"),
            )
            self.assertEqual(unmanaged_notes.read_text(encoding="utf-8"), "keep me\n")

            vendored_process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "src.app",
                    "--transport",
                    "ndjson",
                    "--project-root",
                    str(exported_root),
                    "--workspace-root",
                    str(worker.workspace_root),
                ],
                cwd=exported_root,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            try:
                initialize = request_ndjson_process(
                    vendored_process,
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {},
                    },
                )
                self.assertEqual(
                    initialize["result"]["serverInfo"]["name"],
                    "usefulhelper-worker",
                )

                write_response = request_ndjson_process(
                    vendored_process,
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {
                            "name": "fs.write_files",
                            "arguments": {
                                "files": [
                                    {
                                        "path": "notes/from_vendored_sidecar.txt",
                                        "content": "vendored worker is live\n",
                                    }
                                ]
                            },
                        },
                    },
                )
                self.assertIn("result", write_response)
                written_path = worker.workspace_root / "notes" / "from_vendored_sidecar.txt"
                self.assertTrue(written_path.exists())
                self.assertEqual(
                    written_path.read_text(encoding="utf-8"),
                    "vendored worker is live\n",
                )
            finally:
                if vendored_process.stdin is not None:
                    vendored_process.stdin.close()
                if vendored_process.stdout is not None:
                    vendored_process.stdout.close()
                vendored_process.wait(timeout=10)
        finally:
            worker.close()

    def test_sidecar_export_bundle_rejects_non_sidecar_overwrite_targets(self) -> None:
        worker = WorkerProcess("ndjson")
        try:
            worker.request("initialize")
            occupied_dir = worker.workspace_root / "_sidecar" / "occupied_target"
            occupied_dir.mkdir(parents=True, exist_ok=True)
            (occupied_dir / "notes.txt").write_text("not a sidecar\n", encoding="utf-8")

            dry_run_response = worker.request(
                "tools/call",
                {
                    "name": "sidecar.export_bundle",
                    "arguments": {
                        "target_dir": "_sidecar/occupied_target",
                        "dry_run": True,
                    },
                },
            )
            dry_run_result = dry_run_response["result"]["structuredContent"]
            self.assertEqual(dry_run_result["install_state"], "occupied_non_sidecar")
            self.assertIn("notes.txt", dry_run_result["unmanaged_existing_files"])

            blocked_response = worker.request(
                "tools/call",
                {
                    "name": "sidecar.export_bundle",
                    "arguments": {
                        "target_dir": "_sidecar/occupied_target",
                        "overwrite": True,
                    },
                },
            )
            self.assertIn("error", blocked_response)
            self.assertIn("not a recognized UsefulHELPER sidecar", blocked_response["error"]["message"])
        finally:
            worker.close()

    @unittest.skipUnless(ollama_api_available(), "Local Ollama API is unavailable.")
    def test_ollama_chat_json_returns_structured_json(self) -> None:
        worker = WorkerProcess("ndjson")
        try:
            worker.request("initialize")

            response = worker.request(
                "tools/call",
                {
                    "name": "ollama.chat_json",
                    "arguments": {
                        "model": "qwen2.5:0.5b",
                        "system": "Return JSON only. Do not include markdown fences.",
                        "user": (
                            "Return a JSON object with keys status and value. "
                            "Set status to ok and value to 7."
                        ),
                        "temperature": 0,
                        "max_tokens": 80,
                        "timeout_seconds": 60,
                    },
                },
            )

            result = response["result"]["structuredContent"]
            self.assertEqual(result["parsed_json"]["status"], "ok")
            self.assertEqual(int(result["parsed_json"]["value"]), 7)
            self.assertEqual(result["model"], "qwen2.5:0.5b")
        finally:
            worker.close()

    @unittest.skipUnless(ollama_api_available(), "Local Ollama API is unavailable.")
    def test_ollama_list_models_returns_local_model_inventory(self) -> None:
        worker = WorkerProcess("ndjson")
        try:
            worker.request("initialize")

            response = worker.request(
                "tools/call",
                {
                    "name": "ollama.list_models",
                    "arguments": {"timeout_seconds": 10},
                },
            )

            result = response["result"]["structuredContent"]
            self.assertGreaterEqual(result["model_count"], 1)
            self.assertTrue(any(model.startswith("qwen") for model in result["models"]))
        finally:
            worker.close()
