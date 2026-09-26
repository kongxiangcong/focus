"""Bounded Codex candidate inspection; an independent Runtime capability.

Not part of default single-document ingestion, which declares and calls only the
Parser it uses. It is verified on this boundary alone: read-only, ephemeral,
bounded excerpt, and never a Core writer.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from .proxy import backend_environment


class CodexIngestionRuntime:
    def __init__(self, codex_bin: Path, *, model: str, timeout: float = 180.0):
        self.codex_bin = Path(codex_bin).resolve()
        self.model = model
        self.timeout = timeout
        if not self.codex_bin.is_file():
            raise ValueError("Codex executable does not exist")
        self._lock = threading.Lock()
        self._process = None

    def inspect(self, candidate: Path) -> dict:
        candidate = Path(candidate).resolve()
        content_path = candidate / "content.md"
        metadata_path = candidate / "metadata.json"
        if not content_path.is_file() or not metadata_path.is_file():
            raise RuntimeError("Candidate is missing required inspection inputs")
        content = content_path.read_text(encoding="utf-8", errors="replace")
        title = next((line[2:].strip() for line in content.splitlines() if line.startswith("# ")), "")
        # Figures are optional: an image-less candidate is inspected without one.
        image = next((path for path in sorted((candidate / "images").glob("*")) if path.is_file()), None)
        if not title:
            raise RuntimeError("Candidate has no inspectable title")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("source_kind") != "paper_pdf" or metadata.get("parser") != "article-parser":
            raise RuntimeError("Candidate provenance is invalid")

        schema = {
            "type": "object",
            "properties": {
                "title_matches": {"type": "boolean"},
                "image_observed": {"type": "boolean"},
                "notes": {"type": "string", "maxLength": 500},
            },
            "required": ["title_matches", "image_observed", "notes"],
            "additionalProperties": False,
        }
        excerpt = content[:4000]
        prompt = (
            "Inspect only the supplied bounded paper excerpt"
            + (" and attached extracted figure. " if image is not None else ". ")
            + "Do not call tools or modify files. Return the required JSON. "
            "title_matches is true only if the first Markdown heading equals the declared title. "
            "image_observed is true only if an attached image is a legible paper figure, "
            "and false when no figure is attached.\n\n"
            f"Declared title: {title}\n\nMarkdown excerpt:\n{excerpt}"
        )
        with tempfile.TemporaryDirectory(prefix="focus-codex-ingestion-") as temporary:
            root = Path(temporary)
            schema_path = root / "schema.json"
            output_path = root / "result.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            command = [
                str(self.codex_bin),
                "exec",
                "--ephemeral",
                "-c", 'forced_login_method="chatgpt"',
                "--ignore-user-config",
                "--ignore-rules",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "-C",
                str(root),
                "-m",
                self.model,
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
            ]
            if image is not None:
                image_path = root / ("figure" + image.suffix.lower())
                shutil.copy2(image, image_path)
                command += ["--image", str(image_path)]
            command.append("-")
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                env=backend_environment('codex'),
            )
            with self._lock:
                self._process = process
            try:
                process.communicate(prompt, timeout=self.timeout)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                process.communicate()
                raise RuntimeError("Codex inspection timed out") from exc
            finally:
                with self._lock:
                    self._process = None
            if process.returncode != 0:
                raise RuntimeError(f"Codex inspection failed with exit code {process.returncode}")
            try:
                result = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError("Codex inspection returned invalid JSON") from exc
        if set(result) != {"title_matches", "image_observed", "notes"}:
            raise RuntimeError("Codex inspection result shape is invalid")
        return result

    def cancel(self) -> bool:
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None:
                return False
            process.terminate()
            return True
