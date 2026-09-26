"""Official Harness SDK adapter. Business tool capabilities await ticket 02.

Connectivity runs use an isolated profile and no FOCUS tools. A successful text
request does not enable this adapter for business tasks.
"""
import threading
import uuid
from pathlib import Path

from .base import Backend, BackendError, MESSAGE_COMPLETED, SESSION_OPENED, TURN_COMPLETED, TURN_STARTED, safe_backend_error
from ..proxy import backend_environment


class DeepSeekBackend(Backend):
    name = 'deepseek'
    unavailable_reason = '实验接入：完整业务能力尚未验收。'
    option_keys = Backend.option_keys | {'runtime_path', 'api_key', 'purpose'}

    def __init__(self, workspace, *, model=None, runtime_path=None, api_key=None,
                 purpose='business', **options):
        super().__init__(workspace, model=model, **options)
        self.runtime_path, self.api_key, self.purpose = runtime_path, api_key, purpose
        self.harness = None
        self.session_id = None
        self.thread = None

    def open_session(self, resume_key, *, instructions, skills=()):
        if self.purpose != 'connectivity':
            raise BackendError(self.unavailable_reason)
        if resume_key or skills:
            raise BackendError('连通检查不接受来源会话或技能。')
        from deepseek_harness import DeepSeekHarness
        root = Path(self.workspace)
        patch = root / 'connectivity.patch.yml'
        patch.write_text('- id: persistent-bash\n  disabled: true\n- id: persistent-pwsh\n  disabled: true\n', encoding='utf-8')
        env = backend_environment(self.name)
        env['DSH_SYSTEM_PROMPT'] = instructions
        self.harness = DeepSeekHarness(
            cwd=str(root), dsh_home=str(root / 'runtime-home'), dsh_bin=self.runtime_path,
            profile='sdk-minimal', patches=(str(patch),), api_key=self.api_key or '',
            env=env, model=self.model or 'deepseek-v4-flash', max_tokens=64,
            initialize_timeout_seconds=15, request_timeout_seconds=15,
        )
        self.harness.start()
        self.session_id = 'focus-check-' + uuid.uuid4().hex
        self.emit(SESSION_OPENED, {'key': self.session_id})
        return self.session_id

    def start_turn(self, *, prompt, skills=()):
        if self.closed or self.harness is None:
            raise BackendError('Runtime 尚未启动。')
        self.emit(TURN_STARTED, {'turnId': self.session_id})

        def run():
            try:
                result = self.harness.run(prompt, session_id=self.session_id)
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
        raise BackendError('连通检查不开放业务工具。')

    def interrupt(self):
        self.close()

    def close(self):
        if self.closed:
            return
        super().close()
        if self.harness:
            self.harness.close()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=5)
