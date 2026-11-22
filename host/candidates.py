"""One bounded model turn for structured candidates; no publication authority."""
import json
import queue
import shutil
import tempfile
import threading
import time
import re
from dataclasses import dataclass, field
from pathlib import Path

from .backends.base import Backend, BackendError, safe_backend_error


@dataclass(eq=False)
class _CandidateAttempt:
    scope: str | None
    stopped: threading.Event = field(default_factory=threading.Event)
    backend: Backend | None = None


class CandidateTurns:
    def __init__(self, backend_factory, *, guarded_factory=False):
        self.backend_factory = backend_factory
        self.guarded_factory = guarded_factory
        self.lock = threading.Lock()
        self.active = set()

    def run(self, prompt, *, instructions, timeout=900, tools=None, tool_handler=None, scope=None, cancelled=None):
        result, _ = self._run(prompt, instructions=instructions, timeout=timeout, tools=tools,
                              tool_handler=tool_handler, scope=scope, cancelled=cancelled)
        return result

    def run_structured_json(self, prompt, *, instructions, timeout, image=None):
        return self._run(prompt, instructions=instructions, timeout=timeout, tools=[], inspection=True, image=image)

    def _run(self, prompt, *, instructions, timeout, tools, tool_handler=None, scope=None, cancelled=None,
             inspection=False, image=None):
        if cancelled and cancelled():
            raise InterruptedError('任务已取消。')
        deadline = time.monotonic() + timeout if inspection else None
        with tempfile.TemporaryDirectory(prefix='focus-candidate-') as directory:
            backend = None
            attempt = _CandidateAttempt(scope)
            stopped = attempt.stopped
            with self.lock:
                self.active.add(attempt)

            def track(runtime):
                with self.lock:
                    attempt.backend = runtime
                    if stopped.is_set():
                        raise InterruptedError('任务已取消。')

            try:
                factory_options = {}
                if inspection and self.guarded_factory:
                    factory_options.update(deadline=deadline, cancelled=stopped.is_set, on_probe_backend=track)
                backend = self.backend_factory(workspace=Path(directory), purpose='candidate', tools=tools,
                                               **factory_options)
                track(backend)
                options = {}
                if inspection:
                    backend.deadline = deadline
                    if time.monotonic() >= deadline:
                        raise TimeoutError('任务等待超时。')
                if stopped.is_set() or (cancelled and cancelled()):
                    raise BackendError('任务已取消。')
                backend.open_session(None, instructions=instructions)
                if stopped.is_set() or (cancelled and cancelled()):
                    raise InterruptedError('摘要已取消。')
                if inspection and image is not None and backend.image_input:
                    attachment = Path(directory) / ('figure' + image.suffix.lower())
                    shutil.copyfile(image, attachment)
                    options['images'] = (attachment,)
                backend.start_turn(prompt=prompt, **options)
                messages = {}
                if deadline is None:
                    deadline = time.monotonic() + timeout
                while not backend.closed and time.monotonic() < deadline:
                    if cancelled and cancelled():
                        raise InterruptedError('摘要已取消。')
                    try:
                        event = backend.events.get(timeout=min(1, max(.01, deadline-time.monotonic())))
                    except queue.Empty:
                        continue
                    if stopped.is_set():
                        raise BackendError('任务已取消。')
                    if time.monotonic() >= deadline:
                        break
                    method, params = event.get('method'), event.get('params', {})
                    if 'id' in event:
                        if method == 'tool/call' and tool_handler and params.get('tool') in {t['name'] for t in tools or []}:
                            try:
                                value = tool_handler(params['tool'], params.get('arguments', {}))
                                result = {'success': True, 'text': json.dumps(value, ensure_ascii=False)}
                            except Exception:
                                result = {'success': False, 'text': '检索失败或请求不在允许范围内。'}
                            backend.send({'id': event['id'], 'result': result})
                        else:
                            backend.send({'id': event['id'], 'error': {'message': 'Candidate tools are disabled.'}})
                    elif method == 'message/delta':
                        key = params['itemId']
                        messages[key] = messages.get(key, '') + params.get('delta', '')
                    elif method == 'message/completed':
                        messages[params['itemId']] = params.get('text', '')
                    elif method == '_transport_error':
                        raise BackendError(safe_backend_error(params.get('message')))
                    elif method == 'turn/completed':
                        if params.get('status') != 'completed':
                            raise BackendError(safe_backend_error(params.get('error')))
                        try:
                            raw = list(messages.values())[-1].strip() if messages else ''
                            fenced = re.fullmatch(r'```(?:json)?\s*\n(.*)\n```', raw, flags=re.S)
                            return json.loads(fenced.group(1) if fenced else raw), bool(options.get('images'))
                        except json.JSONDecodeError as exc:
                            raise BackendError(f'Runtime 未返回合法 JSON（第 {exc.lineno} 行，第 {exc.colno} 列）。') from exc
                if time.monotonic() >= deadline:
                    raise TimeoutError('任务等待超时。')
                raise BackendError('任务已取消或连接已关闭。')
            except (BackendError, InterruptedError) as exc:
                if stopped.is_set():
                    raise BackendError('任务已取消。') from exc
                if inspection and time.monotonic() >= deadline:
                    raise TimeoutError('任务等待超时。') from exc
                raise
            finally:
                try:
                    if backend:
                        backend.close()
                finally:
                    with self.lock:
                        self.active.discard(attempt)

    def cancel(self, *, scope=None, immediate=False, background=False):
        with self.lock:
            attempts = [attempt for attempt in self.active if (scope is None or attempt.scope == scope)
                        and not attempt.stopped.is_set()]
            for attempt in attempts:
                attempt.stopped.set()
            backends = [attempt.backend for attempt in attempts if attempt.backend is not None]
        def stop_active():
            for backend in backends:
                try:
                    if not immediate:
                        backend.interrupt()
                finally:
                    backend.close()

        if backends and background:
            threading.Thread(target=stop_active, daemon=True).start()
        else:
            stop_active()
        return bool(attempts)
