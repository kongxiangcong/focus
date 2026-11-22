"""Verify one Backend can read a Host-owned temporary Source."""
import copy
import json
import os
import queue
import secrets
import tempfile
import threading
import time
from pathlib import Path

from .backends.base import (BackendConfigurationError, MESSAGE_COMPLETED, MESSAGE_DELTA, TOOL_CALL, TRANSPORT_ERROR,
                            TURN_COMPLETED, safe_backend_error)
from .core_bridge import CoreBridge, TOOL, WorkspaceError
from core.library_import import import_markdown


def verify_source_round_trip(backend_factory, *, timeout=45, cancelled=None, deadline=None, on_backend=None):
    """Return a check result without reading or changing the user's workspace."""
    marker = secrets.token_hex(16)
    deadline = min(deadline or float('inf'), time.monotonic() + timeout)
    tool = copy.deepcopy(TOOL)
    tool['description'] = ('Read the temporary FOCUS Source with action "read_range". '
                           'Encode the start and end line numbers as a JSON object in arguments.')
    tool['inputSchema']['properties']['action']['enum'] = ['read_range']

    # Source registration adds nested staging names to the host's temp path.
    with tempfile.TemporaryDirectory(prefix='focus-') as temporary:
        root = Path(temporary)
        workspace = root / 'runtime'
        workspace.mkdir()
        original = root / 'probe.md'
        original.write_text(marker + '\n', encoding='utf-8')
        for attempt in range(3):
            if cancelled and cancelled():
                return 'failed', 'Backend 检测已取消。'
            if time.monotonic() >= deadline:
                return 'failed', '请求超时，请检查网络和 Runtime。'
            source_workspace = root / f'kb{attempt}'
            source_workspace.mkdir()
            try:
                source = import_markdown(source_workspace, original, title='Backend connectivity probe',
                                         short_name='probe', language='en')
                break
            except PermissionError as exc:
                # A Windows scanner can briefly hold the new private staging directory.
                if os.name != 'nt' or getattr(exc, 'winerror', None) not in (5, 32) or attempt == 2:
                    raise
                time.sleep(min(.05 * (attempt + 1), max(0, deadline - time.monotonic())))
        original.unlink()
        bridge = CoreBridge(source_workspace)
        try:
            backend = backend_factory(workspace, purpose='connectivity', tools=[tool])
        except BackendConfigurationError as exc:
            return 'failed', str(exc)
        except Exception as exc:
            return 'failed', safe_backend_error(exc)
        timer = threading.Timer(max(0, deadline - time.monotonic()), backend.close)
        timer.daemon = True
        try:
            backend.deadline = deadline
            if on_backend:
                on_backend(backend)
            timer.start()
            if cancelled and cancelled():
                return 'failed', 'Backend 检测已取消。'
            if time.monotonic() >= deadline:
                raise TimeoutError()
            backend.open_session(None, instructions='This is a FOCUS Source access check.')
            if cancelled and cancelled():
                return 'failed', 'Backend 检测已取消。'
            backend.start_turn(prompt='Call the focus tool with action read_range and arguments '
                                      '{"start":1,"end":1}. Reply with the exact source_text value.')
            read_succeeded = False
            messages = {}
            final_item = None
            while time.monotonic() < deadline:
                if cancelled and cancelled():
                    return 'failed', 'Backend 检测已取消。'
                try:
                    event = backend.events.get(timeout=min(.25, max(.01, deadline - time.monotonic())))
                except queue.Empty:
                    continue
                method, params = event.get('method'), event.get('params', {})
                if 'id' in event:
                    if method == TOOL_CALL:
                        result = _read_probe_source(bridge, source['source_id'], params)
                        backend.send({'id': event['id'], 'result': result})
                        read_succeeded |= result['success']
                    else:
                        backend.send({'id': event['id'], 'error': {
                            'message': 'Only the focus read_range operation is allowed for this check.'}})
                elif method in (MESSAGE_DELTA, MESSAGE_COMPLETED):
                    final_item = params['itemId']
                    if method == MESSAGE_DELTA:
                        messages[final_item] = messages.get(final_item, '') + params.get('delta', '')
                    else:
                        messages[final_item] = params.get('text', '')
                elif method == TURN_COMPLETED:
                    if params.get('status') != 'completed':
                        return 'failed', safe_backend_error(params.get('error'))
                    if not read_succeeded:
                        return 'failed', 'Backend 未能通过 focus 工具读取临时原文。'
                    if marker not in messages.get(final_item, ''):
                        return 'failed', 'Backend 已读取临时原文，但最终回复未带回正确标记。'
                    return 'success', 'Backend 已通过原文读取检测。'
                elif method == TRANSPORT_ERROR:
                    return 'failed', safe_backend_error(params.get('message'))
            raise TimeoutError()
        except (TimeoutError, queue.Empty):
            return 'failed', '请求超时，请检查网络和 Runtime。'
        except BackendConfigurationError as exc:
            return 'failed', str(exc)
        except Exception as exc:
            return 'failed', safe_backend_error(exc)
        finally:
            timer.cancel()
            backend.close()


def _read_probe_source(bridge, source_id, params):
    try:
        call = params.get('arguments')
        if params.get('tool') != 'focus' or not isinstance(call, dict) or call.get('action') != 'read_range':
            raise ValueError()
        arguments = json.loads(call.get('arguments', ''))
        if not isinstance(arguments, dict) or arguments.get('source_id') not in (None, source_id):
            raise ValueError()
        value = bridge.tool('read_range', json.dumps({**arguments, 'source_id': source_id}))
        return {'success': True, 'text': json.dumps(value, ensure_ascii=False)}
    except (KeyError, TypeError, ValueError, WorkspaceError):
        return {'success': False, 'text': 'Only read_range on the temporary Source is allowed.'}
