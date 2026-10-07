"""Explicit real-provider acceptance on synthetic, non-private source material.

Not part of unittest discovery. Requires the machine's existing credentials.
"""
import json
import sys
import uuid
import shutil
import time
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / '.agents'), str(ROOT / 'tests')]
import test_focus_read
from workspace_fixture import HostService
from host.workbench import Workbench
from host.backend_setup import BackendSetup

OUTPUT = ROOT / 'tmp/workspace-portability'
results = {}


def save():
    (OUTPUT / 'real-journey.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')


def wait(worker, timeout=900):
    deadline = time.monotonic() + timeout
    while worker.is_alive() and time.monotonic() < deadline:
        worker.join(1)
    if worker.is_alive():
        raise TimeoutError('business worker did not terminate')


for backend, selected in (('codex', os.getenv('FOCUS_REAL_CODEX_MODEL', 'gpt-5.6-sol')), ('deepseek', 'deepseek-flash')):
    if os.getenv('FOCUS_REAL_BACKENDS') and backend not in os.environ['FOCUS_REAL_BACKENDS'].split(','):
        continue
    fixture = test_focus_read.FocusReadTests(); fixture.setUp()
    host = app = None
    result = results[backend] = {'model': selected, 'stages': {}}
    try:
        workspace = fixture._workspace()[0]
        bundle = workspace / 'sources/fixture-paper/parser-bundle'
        # A substantive synthetic performance-model paper, explicitly neither
        # a measurement nor a claim about real hardware. Preserve plan anchors.
        content = [
            '# Fixture Paper', '', '## Method',
            'We present a synthetic analytical model for a vector NPU array. No physical device was measured. '
            'An operator is described by F floating-point operations and B bytes transferred from external memory. '
            'The machine is described by peak compute P operations per second and bandwidth W bytes per second. '
            'The compute lower bound is t_c = F/P and the memory lower bound is t_m = B/W. '
            'Assuming ideal overlap, predicted operator time is max(t_c, t_m). Arithmetic intensity is F/B. '
            'The model deliberately excludes launch overhead, communication, cache misses and quantization effects. '
            'A compiler can use this model to compare candidate tiling choices before implementing them. '
            'Increasing tile reuse can lower B, but P and W must remain fixed when comparing those choices. '
            'All numbers below are declared model inputs, not benchmark measurements. '
            'The diagram shows operator and machine descriptions feeding independent compute and memory bounds.',
            '![Architecture](images/image-001.png)', 'Figure 1: Operator and machine inputs produce two analytical bounds; their maximum predicts time.',
            '', '## Runtime',
            'The runtime accepts a dictionary with F, B, P and W, verifies positive P and W and nonnegative F and B, '
            'then computes the two bounds and returns predicted time and the limiting resource. '
            'For a declared input F=4e9 operations, B=4e8 bytes, P=2e12 operations/s and W=5e10 bytes/s, '
            'compute time is 0.002 s and memory time is 0.008 s, hence predicted time is 0.008 s. '
            'Predicted throughput is 500e9 operations/s. This is arithmetic, not a real-device result. '
            'For repeated operators, summing their predicted times assumes serial execution and no reuse across operators. '
            'A future extension could add launch overhead as a separate measured parameter; it is not implemented here. '
            'The model requires exact byte accounting, with read and write traffic both included in B. '
            'When changing tiling, recompute traffic rather than assuming each element is fetched only once.',
            '', '## Results',
            'The baseline synthetic case is memory limited. Halving bandwidth to 2.5e10 bytes/s raises memory time '
            'to 0.016 s while compute remains 0.002 s. Doubling bandwidth gives 0.004 s predicted time. '
            'Reducing transferred bytes from 4e8 to 1e8 gives memory time 0.002 s, matching the compute bound. '
            'Further reduction of bytes then has no predicted benefit unless peak compute also improves. '
            'These calculations demonstrate a resource bottleneck transition; they do not establish achievable speedup. '
            'The contribution is a reproducible transparent input-output estimate for early design comparisons. '
            'Its limitations include ideal overlap, peak-rate assumptions, no contention, no energy model and no validation '
            'against hardware. A falsification experiment would independently measure operator compute and transferred bytes, '
            'then compare prediction errors over sizes and tilings. That experiment has not been performed. '
            'No official implementation repository or artifact is provided with this synthetic source.'
        ]
        (bundle / 'content.md').write_text('\n'.join(content) + '\n', encoding='utf-8')
        from PIL import Image, ImageDraw
        figure = Image.new('RGB', (600, 120), 'white')
        draw = ImageDraw.Draw(figure)
        for x, label in ((10, 'F,B,P,W'), (210, 'F/P and B/W'), (410, 'max(bounds)')):
            draw.rectangle((x, 30, x+170, 90), outline='black'); draw.text((x+12, 52), label, fill='black')
        figure.save(bundle / 'images/image-001.png')
        # Test-only legacy synthetic layout registration; business operations
        # below all use the production manager and real adapters.
        seed = HostService(workspace, None, settings_path=fixture.root / 'machine/settings.json')
        seed.close()
        app = Workbench(settings_path=fixture.root / 'machine/settings.json')
        binding = app.bind({'mode': 'import', 'path': str(workspace),
                           'configuration': {'backend': backend, 'model': selected}})
        host = app.host
        setup = host.setup
        checked = setup.check({'backend': backend})
        result['stages']['defaultConnection'] = checked
        selected_check = setup.check({'backend': backend, 'model': selected})
        result['stages']['selectedConnection'] = selected_check
        save()
        if selected_check['status'] != 'success':
            raise AssertionError('selected model connection failed')
        host.prepare_reading('fixture-paper', request_id=uuid.uuid4().hex)
        wait(host.reading_workers['fixture-paper'])
        prepared = host.snapshot()['preparations']['fixture-paper']
        attempts = [prepared]
        for retry in range(2):
            if prepared['ready'] or prepared['status'] != 'failed':
                break
            host.resume_preparation('fixture-paper', request_id=uuid.uuid4().hex)
            wait(host.reading_workers['fixture-paper'])
            prepared = host.snapshot()['preparations']['fixture-paper']
            attempts.append(prepared)
        result['stages']['preparationAttempts'] = attempts
        result['stages']['preparation'] = prepared
        save()
        if not prepared['ready']:
            raise AssertionError('reading preparation not ready')
        view = host.open_prepared_reading('fixture-paper', request_id=uuid.uuid4().hex)
        current = host.snapshot()['current']
        result['stages']['opened'] = {'chunkId': current['chunkId'], 'translationPresent': bool(current.get('translation'))}
        host.start({'requestId': uuid.uuid4().hex, 'sourceId': 'fixture-paper',
                    'content': '请依据原文解释为什么示例受到内存带宽限制，并将“该示例预测时间为 0.008 秒，属于模型计算而非硬件测量”保存为一条简短笔记。',
                    'receipt': {'sourceId': 'fixture-paper', 'planId': current['planId'], 'chunkId': current['chunkId']}})
        wait(host.worker)
        snapshot = host.snapshot()
        notes = snapshot.get('sourceNotes', {}).get('notes', []) if isinstance(snapshot.get('sourceNotes'), dict) else snapshot.get('sourceNotes', [])
        result['stages']['discussion'] = {'status': snapshot['agent']['run']['status'], 'discussionId': snapshot['discussionId'],
            'messages': snapshot['conversation'], 'notes': snapshot.get('sourceNotes')}
        save()
        if snapshot['agent']['run']['status'] != 'completed':
            raise AssertionError('discussion failed')
        if not snapshot.get('sourceNotes'):
            raise AssertionError('explicit note was not committed')
        host.blog_generate('fixture-paper', request_id=uuid.uuid4().hex)
        wait(host.blog_workers['fixture-paper'])
        result['stages']['blog'] = host.blog_status('fixture-paper')
        save()
        if result['stages']['blog'].get('runStatus') != 'completed':
            raise AssertionError('blog artifacts not completed')
        before = host.snapshot()
        old_identity = binding['workspace']['workspaceId']
        app.close()
        copied = fixture.root / '真实恢复 copy'
        shutil.copytree(workspace, copied)
        shutil.move(str(workspace), fixture.root / 'hidden-original')
        app = Workbench(settings_path=fixture.root / 'new-machine/settings.json')
        restored_binding = app.bind({'mode': 'import', 'path': str(copied), 'configuration': {'backend': backend, 'model': selected}})
        host = app.host
        after = host.snapshot()
        assert old_identity == restored_binding['workspace']['workspaceId']
        assert before['conversation'] == after['conversation']
        assert before['sourceNotes'] == after['sourceNotes']
        request_id = uuid.uuid4().hex
        cursor = after['navigationCurrent'] or after['current']
        host.continue_cached({'requestId': request_id, 'receipt': {
            'sourceId': cursor['sourceId'], 'planId': cursor['planId'], 'chunkId': cursor['chunkId'],
            'readingRevision': after['readingRevision']}})
        if request_id in host.progress_workers:
            wait(host.progress_workers[request_id])
        advanced = host.snapshot()['navigationCurrent'] or host.snapshot()['current']
        assert advanced['chunkId'] != cursor['chunkId']
        host.start({'requestId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'content': '刚才讨论的公式是什么？简短回答。'})
        wait(host.worker)
        result['stages']['restoredContinue'] = {'status': host.snapshot()['agent']['run']['status'],
            'identityPreserved': True, 'discussionPreserved': before['discussionId'] == host.snapshot()['discussionId'],
            'oldConversationPreserved': True, 'oldNotesPreserved': True}
        result['stages']['restoredContinue']['remainingReadingAdvanced'] = True
        result['status'] = 'passed' if result['stages']['restoredContinue']['status'] == 'completed' else 'failed'
    except Exception as exc:
        # No credential or raw provider diagnostics enter evidence.
        result['status'] = 'failed'
        result['error'] = type(exc).__name__ + ': ' + str(exc)[:250]
    finally:
        save()
        print(backend, result['status'], list(result['stages']), flush=True)
        if app:
            app.close()
        fixture.tearDown()
