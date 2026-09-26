"""Official Harness SDK adapter with isolated, Host-owned tool capabilities."""
import threading
import uuid
import tempfile
from pathlib import Path

from .base import Backend, BackendError, MESSAGE_COMPLETED, SESSION_OPENED, TURN_COMPLETED, TURN_STARTED, safe_backend_error
from ..proxy import backend_environment
from .tool_bridge import ToolBridge
from .task_tools import discussion_tools, library_tools


class DeepSeekBackend(Backend):
    name = 'deepseek'
    unavailable_reason = None
    option_keys = Backend.option_keys | {'runtime_path', 'api_key', 'purpose'}

    def __init__(self, workspace, *, model=None, runtime_path=None, api_key=None,
                 purpose='business', **options):
        super().__init__(workspace, model=model, **options)
        self.runtime_path, self.api_key, self.purpose = runtime_path, api_key, purpose
        self.harness = None
        self.session_id = None
        self.thread = None
        self.bridge = None
        self.temporary = None
        self.session = None
        self._close_done = threading.Event()

    def open_session(self, resume_key, *, instructions, skills=()):
        with self._lifecycle_lock:
            if self.closed:
                raise BackendError('任务已关闭。')
            try:
                return self._open_session(resume_key, instructions=instructions, skills=skills)
            except BackendError:
                raise
            except Exception as exc:
                raise BackendError(safe_backend_error(exc)) from exc

    def _open_session(self, resume_key, *, instructions, skills=()):
        if self.purpose not in ('connectivity', 'candidate', 'discussion', 'business'):
            raise BackendError('不支持此任务类型。')
        if resume_key or skills:
            raise BackendError('新任务不接受原生会话续接或本机技能。')
        from deepseek_harness import DeepSeekHarness
        self.temporary = tempfile.TemporaryDirectory(prefix='focus-deepseek-')
        root = Path(self.temporary.name)
        patch = root / 'connectivity.patch.yml'
        patch_text = '- id: persistent-bash\n  disabled: true\n- id: persistent-pwsh\n  disabled: true\n'
        tool_definitions = self.tools
        if self.purpose == 'discussion' and tool_definitions is None:
            tool_definitions = discussion_tools()
        elif self.purpose == 'business' and tool_definitions is None:
            tool_definitions = library_tools()
        if tool_definitions:
            self.bridge = ToolBridge(self, tool_definitions)
            patch_text += ("- insert:\n    - id: focus\n      name: '@deepseek-ai/dsh-mcp-client'\n"
                           "      config:\n        serverName: focus\n        transport: streamable-http\n"
                           f"        url: {self.bridge.url}\n        failOnStartupError: true\n")
        patch.write_text(patch_text, encoding='utf-8')
        env = backend_environment(self.name)
        env['DSH_SYSTEM_PROMPT'] = instructions
        self.harness = DeepSeekHarness(
            cwd=str(root), dsh_home=str(root / 'runtime-home'), dsh_bin=self.runtime_path,
            profile='sdk-minimal', patches=(str(patch),), api_key=self.api_key or '',
            env=env, model=self.model or 'deepseek-v4-flash',
            max_tokens=64 if self.purpose == 'connectivity' else 16000,
            initialize_timeout_seconds=15, request_timeout_seconds=15,
        )
        self.session_id = 'focus-' + self.purpose + '-' + uuid.uuid4().hex
        self.session = self.harness.start_session(self.session_id)
        self.emit(SESSION_OPENED, {'key': self.session_id})
        return self.session_id

    def start_turn(self, *, prompt, skills=()):
        with self._lifecycle_lock:
            return self._start_turn(prompt=prompt, skills=skills)

    def _start_turn(self, *, prompt, skills=()):
        if self.closed or self.harness is None:
            raise BackendError('Runtime 尚未启动。')
        self.emit(TURN_STARTED, {'turnId': self.session_id})

        def run():
            try:
                # Session.run never auto-starts a closed Harness. Harness.run does.
                result = self.session.run(prompt)
                if self.closed:
                    return
                self.emit(MESSAGE_COMPLETED, {'itemId': self.session_id, 'text': result.final_response})
                codes = [safe_backend_error(event['data']['reason'].get('error', {}))
                         for event in result.events if event.get('type') == 'turn/end'
                         and event.get('data', {}).get('reason', {}).get('kind') == 'error']
                self.emit(TURN_COMPLETED, {'status': result.finish_reason, 'error': ','.join(codes) or None})
            except Exception as exc:
                if not self.closed:
                    self.fail(safe_backend_error(exc))

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def send(self, message):
        if self.bridge:
            self.bridge.send(message)
            return
        raise BackendError('连通检查不开放业务工具。')

    def interrupt(self):
        self.close()

    def close(self):
        with self._lifecycle_lock:
            already_closing = self.closed
            if not already_closing:
                super().close()
                self.fail('DeepSeek Runtime 连接已关闭。')
        if already_closing:
            self._close_done.wait()
            return
        try:
            if self.bridge:
                self.bridge.close()
            if self.harness:
                self.harness.close()
            if self.thread and self.thread is not threading.current_thread():
                self.thread.join(timeout=5)
            if self.temporary:
                self.temporary.cleanup()
        finally:
            self._close_done.set()
