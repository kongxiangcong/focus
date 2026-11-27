import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from core.local_mineru import LocalMinerUParser, LocalProbe
from core.mineru import ParserError
from core.mineru import _normalize
from core.mineru_selector import AutoMinerUParser
from core.reading_workspace import _validate_parser_bundle


class FakeLocal:
    base_url = "http://127.0.0.1:18765"
    timeout = 2
    interval = 0
    def __init__(self, state):
        self.state = state
        self.started = self.resumed = 0
    def probe(self):
        return LocalProbe(self.state, "probe " + self.state, "4.2.3")
    def parse(self, source, candidate, *, checkpoint):
        self.started += 1
        checkpoint({"backend": "local-mineru", "reference_kind": "local_mineru_job", "reference_id": "job1"})
        raise ParserError("job failed", recoverable=False)
    def resume(self, *args, **kwargs):
        self.resumed += 1


class FakeRemote:
    hosted = None
    timeout = 2
    interval = 0
    def __init__(self):
        self.started = 0
    def parse(self, source, candidate, *, checkpoint):
        self.started += 1
        checkpoint({"reference_kind": "batch_id", "reference_id": "batch1"})
        Path(candidate).mkdir(parents=True, exist_ok=True)
        (Path(candidate) / "metadata.json").write_text("{}", encoding="utf-8")
        return {"batch_id": "batch1"}


class SelectionTests(unittest.TestCase):
    def test_local_priority_without_token_and_failure_stays_local(self):
        local, remote = FakeLocal("available"), FakeRemote()
        selector = AutoMinerUParser(local=local, remote=remote)
        marks = []
        with patch("core.mineru_selector._token", side_effect=AssertionError("cloud token used")):
            with self.assertRaises(ParserError):
                selector.parse(Path("input.pdf"), Path("candidate"), checkpoint=marks.append)
        self.assertEqual((1, 0), (local.started, remote.started))
        self.assertEqual("local-mineru", marks[-1]["backend"])

    def test_absent_or_incompatible_uses_remote_only_with_token(self):
        for state in ("absent", "incompatible"):
            with self.subTest(state=state):
                local, remote = FakeLocal(state), FakeRemote()
                selector = AutoMinerUParser(local=local, remote=remote)
                marks = []
                with tempfile.TemporaryDirectory() as directory, patch("core.mineru_selector._token", return_value="secret"):
                    selector.parse(Path("input.pdf"), Path(directory) / "candidate", checkpoint=marks.append)
                self.assertEqual((0, 1), (local.started, remote.started))
                self.assertEqual("cloud", marks[-1]["backend"])
                self.assertEqual({"model": "vlm", "language": "en", "ocr": False}, marks[-1]["config"])

    def test_no_token_and_busy_or_starting_never_submit(self):
        for state in ("absent", "busy", "starting"):
            with self.subTest(state=state):
                local, remote = FakeLocal(state), FakeRemote()
                with patch("core.mineru_selector._token", side_effect=ParserError("no token", recoverable=False)):
                    with self.assertRaises(ParserError) as error:
                        AutoMinerUParser(local=local, remote=remote).parse(Path("a"), Path("b"))
                self.assertEqual((0, 0), (local.started, remote.started))
                if state == "absent":
                    self.assertIn("MINERU_API_TOKEN", str(error.exception))

    def test_restart_resumes_pinned_local_without_probe_or_cloud(self):
        old = {"backend": "local-mineru", "reference_kind": "local_mineru_job", "reference_id": "job1",
               "base_url": "http://127.0.0.1:18765", "version": "4.2.3", "model": "standard",
               "language": "auto", "ocr": False, "file_id": "file1"}
        local, remote = FakeLocal("absent"), FakeRemote()
        selector = AutoMinerUParser(local=local, remote=remote)
        with patch("core.mineru_selector.LocalMinerUParser") as constructor:
            constructor.return_value.resume.return_value = {"task_id": "job1"}
            self.assertEqual({"task_id": "job1"}, selector.resume(Path("a"), Path("b"), checkpoint=old))
            constructor.return_value.resume.assert_called_once()
        self.assertEqual((0, 0), (local.started, remote.started))

    def test_retry_recovers_only_proven_pre_submission_auth_failure(self):
        from core.ingestion import IngestionApplication
        for errors, recovered in [
            (['authentication_failed'], True),
            (['authentication_failed', 'submission_unknown', 'submission_unknown'], True),
            (['submission_unknown'], False),
            (['authentication_failed', 'parser_failed', 'submission_unknown'], False),
        ]:
            with self.subTest(errors=errors):
                step = {'checkpoint': {'backend': 'cloud', 'reference_kind': 'remote_submission_unknown'},
                        'attempts': [{'status': 'failed', 'error_id': e} for e in errors]}
                IngestionApplication._recover_rejected_submission(step)
                self.assertEqual(recovered, step['checkpoint']['reference_kind'] == 'remote_auth_rejected')

    def test_rejected_submission_retries_pinned_cloud_and_checkpoints_before_sending(self):
        selector = AutoMinerUParser(local=FakeLocal("available"), remote=FakeRemote())
        config = {'model': 'vlm', 'language': 'zh', 'ocr': True}
        old = {'backend': 'cloud', 'reference_kind': 'remote_auth_rejected',
               'reference_id': 'submission', 'config': config, 'selection_reason': 'original selection'}
        marks = []
        with tempfile.TemporaryDirectory() as directory, patch('core.mineru_selector.MinerUIngestionParser',
                return_value=selector.remote) as constructor:
            selector.resume(Path('a.pdf'), Path(directory) / 'out', checkpoint=old, on_checkpoint=marks.append)
            constructor.assert_called_once_with(hosted=None, timeout=2, interval=0, **config)
        self.assertEqual(['remote_submission_unknown', 'batch_id'], [m['reference_kind'] for m in marks])
        self.assertEqual(0, selector.local.started)

    def test_submission_unknown_never_reuploads(self):
        local, remote = FakeLocal("available"), FakeRemote()
        selector = AutoMinerUParser(local=local, remote=remote)
        with self.assertRaisesRegex(ParserError, "不会自动重复上传"):
            selector.resume(Path("a"), Path("b"), checkpoint={"backend": "cloud",
                "reference_kind": "remote_submission_unknown", "reference_id": "submission",
                "config": {"model": "vlm", "language": "en", "ocr": False}})
        self.assertEqual((0, 0), (local.started, remote.started))

    def test_local_health_capability_and_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "in.pdf"
            pdf.write_bytes(b"%PDF-1.4\nfixture")
            archive = io.BytesIO()
            evidence = {"pages": [{}], "metadata": {"producer": {"name": "mineru", "version": "4.2.3"}},
                        "extensions": {"mineru": {"tier": "standard"}}}
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("markdown.md", "# Fixture\n\n**strong**\n")
                for name in ("middle_json.json", "structured_content.json"):
                    bundle.writestr(name, json.dumps({**evidence, "is_full_document": True}))
            parser = LocalMinerUParser(interval=0)
            states = []
            def request(path, **kwargs):
                states.append(path)
                if path == "/v1/health": return {"status": "ok", "version": "4.2.3", "features": {"sources": ["upload"], "task_output_formats": ["default"]}}
                if path == "/v1/tiers": return {"data": [{"id": "standard"}]}
                if path == "/v1/tasks":
                    self.assertEqual(["default"], kwargs["json_body"]["output_formats"])
                    self.assertEqual(pdf.stat().st_size, kwargs["json_body"]["files"][0]["bytes"])
                    return {"task_id": "job1", "files": [{"file_id": "file1"}]}
                if path == "/v1/tasks/job1":
                    completed = "/v1/tasks/job1/uploads/file1" in states
                    status = "completed" if completed else "waiting-file"
                    file = {"file_id": "file1", "status": status}
                    if completed:
                        file.update(parse={"parser_version": "4.2.3", "tier": "standard"},
                                    result_url="/v1/files/file1/content")
                    else:
                        file["upload"] = {"url": "/v1/tasks/job1/uploads/file1"}
                    return {"task_id": "job1", "output_formats": ["default"], "status": status, "files": [file]}
                if path == "/v1/tasks/job1/uploads/file1":
                    self.assertEqual("PUT", kwargs["method"])
                    self.assertEqual(pdf.read_bytes(), kwargs["data"].read())
                    self.assertEqual("job1", checkpoints[-1]["reference_id"])
                    return {"task_id": "job1", "file_id": "file1", "status": "pending"}
                if path == "/v1/files/file1/content":
                    kwargs["destination"].write_bytes(archive.getvalue())
                    return None
                raise AssertionError(path)
            parser._request = request
            self.assertEqual("available", parser.probe().state)
            checkpoints = []
            parser.parse(pdf, root / "candidate", checkpoint=checkpoints.append)
            self.assertEqual("local_mineru_job", checkpoints[-1]["reference_kind"])
            metadata = _validate_parser_bundle(root / "candidate")
            self.assertEqual("local-mineru", metadata["provider"])
            self.assertNotIn("batch_id", metadata)
            self.assertEqual(2, len(metadata["model_evidence"]))
            parser.resume(pdf, root / "resumed", checkpoint=checkpoints[-1])
            self.assertEqual(1, states.count("/v1/tasks"))
            self.assertEqual(1, states.count("/v1/tasks/job1/uploads/file1"))

    def test_pre_upgrade_checkpoint_polls_original_jobs_endpoint(self):
        parser = AutoMinerUParser()
        checkpoint = {**parser.local._reference_settings(), "version": "4.0.8",
                      "reference_id": "original", "file_id": "file1"}
        def request(path, **kwargs):
            if path == "/v1/health":
                return {"status": "ok", "version": "4.0.8"}
            self.assertEqual("/v1/parse/jobs/original", path)
            return {"job_id": "original", "tier": "standard", "status": "failed"}
        with patch.object(LocalMinerUParser, "_request", side_effect=request):
            with self.assertRaises(ParserError) as exc:
                parser.resume(Path("source.pdf"), Path("candidate"), checkpoint=checkpoint)
        self.assertEqual("local_mineru_parse_failed", exc.exception.error_id)

    def test_cancel_uses_pinned_protocol(self):
        selector = AutoMinerUParser()
        checkpoint = {**selector.local._reference_settings(), "reference_id": "job1", "file_id": "file1"}
        for version, path, method, id_key in [
            ("4.2.3", "/v1/tasks/job1/cancel", "POST", "task_id"),
            ("4.0.8", "/v1/parse/jobs/job1", "DELETE", "job_id"),
        ]:
            with self.subTest(version=version), patch.object(LocalMinerUParser, "_request",
                    return_value={id_key: "job1", "status": "canceled"}) as request:
                self.assertTrue(selector.cancel({**checkpoint, "version": version}))
                request.assert_called_once_with(path, method=method)

    def test_local_unknown_submission_cannot_create_another_task(self):
        parser = LocalMinerUParser()
        checkpoint = {**parser._reference_settings(), "reference_kind": "local_submission_unknown",
                      "reference_id": "submission"}
        with patch.object(parser, "_request", side_effect=AssertionError("unexpected request")):
            with self.assertRaisesRegex(ParserError, "不会自动重复提交"):
                parser.resume(Path("input.pdf"), Path("candidate"), checkpoint=checkpoint)

    def test_remote_bundle_preserves_structured_evidence_without_local_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "in.pdf"
            source.write_bytes(b"%PDF-1.4\nfixture")
            archive = root / "remote.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("paper/full.md", "# Remote\n\n**result**")
                bundle.writestr("paper/middle_json.json", json.dumps({"pages": [{"blocks": []}]}))
            _normalize(source, archive, root / "candidate", "batch1", "vlm", "en")
            metadata = _validate_parser_bundle(root / "candidate")
            self.assertEqual("mineru.net", metadata["provider"])
            self.assertNotIn("mineru_version", metadata)
            self.assertIn("mineru/middle_json.json", metadata["model_evidence"])


if __name__ == "__main__": unittest.main()
