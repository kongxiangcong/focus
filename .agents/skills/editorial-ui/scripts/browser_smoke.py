#!/usr/bin/env python3
"""Exercise bundled native starters with file:// + blocked network. Requires Playwright."""
from __future__ import annotations
import argparse
import csv
import json
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT/'validation-local')
    parser.add_argument('--browser', type=str, default=None, help='Optional Chromium executable path.')
    parser.add_argument('--transport', choices=['file','inline'], default='file', help='file tests direct opening; inline validates content when managed browser policy blocks file URLs.')
    args = parser.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('NOT_RUN: Playwright is absent. Install it only with user authorization. See README.')
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    checks: list[dict] = []
    screenshots: list[str] = []
    attempted: list[str] = []
    exceptions: list[str] = []
    browser_version = ''

    def verify(name: str, condition: bool, detail: str = '') -> None:
        record = {'name': name, 'status': 'PASS' if condition else 'FAIL', 'detail': detail}
        checks.append(record)
        print(f"{record['status']}: {name}", flush=True)
        if not condition:
            raise AssertionError(f'{name}: {detail}')

    def screenshot(page, filename: str) -> None:
        page.screenshot(path=str(args.out/filename), full_page=True, animations='disabled')
        screenshots.append(filename)

    try:
        with sync_playwright() as p:
            executable = args.browser or shutil.which('chromium') or shutil.which('chromium-browser')
            options = {'headless': True, 'args': ['--no-sandbox', '--disable-dev-shm-usage']}
            if executable:
                options['executable_path'] = executable
            browser = p.chromium.launch(**options)
            browser_version = browser.version

            def fresh(slug: str, width: int = 1440, height: int = 1000, reduced: bool = False):
                ctx = browser.new_context(viewport={'width': width, 'height': height}, color_scheme='light',
                                          reduced_motion='reduce' if reduced else 'no-preference',
                                          offline=True, accept_downloads=True)
                ctx.route('**/*', lambda route: route.abort() if route.request.url.startswith(('http://','https://')) else route.continue_())
                page = ctx.new_page()
                page.set_default_timeout(5000)
                page.on('request', lambda req: attempted.append(req.url) if req.url.startswith(('http://','https://','ws://','wss://')) else None)
                page.on('pageerror', lambda err: exceptions.append(str(err)))
                if args.transport == 'file':
                    page.goto((ROOT/f'assets/starters/{slug}.html').as_uri(), wait_until='load')
                else:
                    page.set_content((ROOT/f'assets/starters/{slug}.html').read_text(encoding='utf-8'), wait_until='load')
                page.wait_for_timeout(50)
                return ctx, page

            # Layout/theme/motion matrix across independent layouts.
            for slug in ['reader','flow-explorer','report']:
                for width,height in [(1440,1000),(1024,768),(390,844),(320,740)]:
                    ctx,page=fresh(slug,width,height)
                    verify(f'{slug} {width}: primary heading', page.locator('h1').count()==1)
                    overflow=page.evaluate('document.documentElement.scrollWidth-window.innerWidth')
                    verify(f'{slug} {width}: no page overflow', overflow<=1, f'overflow={overflow}px')
                    verify(f'{slug} {width}: visible main', page.locator('main').is_visible())
                    if width in [1440,390]:
                        screenshot(page,f'{slug}-{width}-light.png')
                    page.locator('[data-theme-toggle]').click()
                    verify(f'{slug} {width}: theme switch', page.locator('html').get_attribute('data-theme')=='dark')
                    if width==1440:
                        screenshot(page,f'{slug}-{width}-dark.png')
                    ctx.close()
                ctx,page=fresh(slug,reduced=True)
                verify(f'{slug}: reduced-motion CSS', page.locator('.btn').first.evaluate('(el)=>getComputedStyle(el).transitionDuration')=='0s')
                if slug=='reader': page.locator('#explain').click()
                elif slug=='flow-explorer': page.locator('[data-stage="2"]').click()
                else: page.locator('.row-link').first.click()
                verify(f'{slug}: reduced-motion JS', page.evaluate('document.getAnimations().filter(a=>a.playState==="running").length')==0)
                ctx.close()

            ctx,page=fresh('reader')
            page.locator('#explain').click()
            verify('reader: dialog opens with question focus',page.locator('#explanation').evaluate('(el)=>el.open') and page.evaluate('document.activeElement.id')=='question')
            for _ in range(15):
                page.keyboard.press('Tab')
                verify('reader: focus contained in dialog',page.evaluate('document.getElementById("explanation").contains(document.activeElement)'))
            page.keyboard.press('Escape')
            verify('reader: close restores opener focus',page.evaluate('document.activeElement.id')=='explain')
            verify('reader: explanation does not advance progress','1 / 3' in page.locator('#progress').inner_text())
            page.locator('#continue').click()
            verify('reader: continue appends not replaces',page.locator('[data-section="1"]').is_visible() and page.locator('[data-section="2"]').is_visible() and not page.locator('[data-section="3"]').is_visible())
            page.locator('#explain').click()
            question=page.locator('#question')
            question.fill('中文输入测试')
            question.evaluate('(el)=>el.dispatchEvent(new CompositionEvent("compositionstart",{bubbles:true,data:"中"}))')
            page.keyboard.press('Enter')
            verify('reader: synthetic composing Enter does not submit',page.locator('#stop').is_disabled())
            question.evaluate('(el)=>el.dispatchEvent(new CompositionEvent("compositionend",{bubbles:true,data:"中文"}))')
            question.evaluate('(el)=>el.dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",keyCode:229,bubbles:true,cancelable:true}))')
            verify('reader: legacy 229 guard',page.locator('#stop').is_disabled())
            question.fill('换行测试'); question.press('End');question.press('Shift+Enter')
            verify('reader: Shift Enter newline', '\n' in question.input_value() and page.locator('#stop').is_disabled())
            question.fill('');page.locator('#send').click()
            verify('reader: empty question validation','请先输入' in page.locator('#answer-status').inner_text())
            question.fill('为什么要保留阅读位置？');page.locator('#send').click()
            page.wait_for_function('document.getElementById("stream-content").textContent.length>450')
            verify('reader: stream has real overflow',page.locator('#stream').evaluate('(el)=>el.scrollHeight>el.clientHeight'))
            page.locator('#stream').evaluate('(el)=>{el.scrollTop=0;el.dispatchEvent(new Event("scroll"));}')
            initial=page.locator('#stream').evaluate('(el)=>el.scrollTop')
            page.wait_for_timeout(220)
            after=page.locator('#stream').evaluate('(el)=>el.scrollTop')
            verify('reader: appended text does not steal history scroll',abs(after-initial)<=2,f'{initial} -> {after}')
            verify('reader: jump control appears',page.locator('#jump-latest').is_visible())
            page.locator('#jump-latest').click();page.wait_for_timeout(60)
            verify('reader: explicit jump resumes following',page.locator('#stream').evaluate('(el)=>el.scrollHeight-el.clientHeight-el.scrollTop<35'))
            page.locator('#stop').click()
            count=len(page.locator('#stream-content').inner_text());page.wait_for_timeout(120)
            verify('reader: stop halts stream',len(page.locator('#stream-content').inner_text())==count)
            verify('reader: cancelled draft preserved',question.input_value()=='为什么要保留阅读位置？')
            page.locator('#simulate-error').check();page.locator('#retry').click()
            page.wait_for_function('document.getElementById("answer-status").dataset.kind==="error"')
            verify('reader: failure preserves draft',question.input_value()=='为什么要保留阅读位置？')
            page.locator('#simulate-error').uncheck();page.locator('#retry').click()
            page.wait_for_function('document.getElementById("answer-status").dataset.kind==="success"',timeout=12000)
            verify('reader: success clears consumed draft',question.input_value()=='')
            question.fill('第二次问题');page.locator('#send').click();question.fill('生成过程中写下的新草稿')
            page.wait_for_function('document.getElementById("answer-status").dataset.kind==="success"',timeout=12000)
            verify('reader: newer draft survives completion',question.input_value()=='生成过程中写下的新草稿')
            page.locator('#send').click();page.keyboard.press('Escape')
            # Native close cleanup is queued after the Escape key action.
            # Wait for the same observable final state; do not weaken the assertion.
            page.wait_for_function('!document.getElementById("explanation").open && document.getElementById("stop").disabled',timeout=2000)
            verify('reader: closing running dialog cancels work',page.locator('#stop').is_disabled())
            verify('reader: questions preserve current reading state','2 / 3' in page.locator('#progress').inner_text())
            screenshot(page,'reader-after-interactions.png');ctx.close()

            ctx,page=fresh('flow-explorer')
            page.locator('[data-stage="2"]').focus();page.keyboard.press('Enter')
            verify('flow: keyboard node selection','执行与资源竞争'==page.locator('#stage-title').inner_text())
            verify('flow: selected state coherent',page.locator('[data-stage="2"]').get_attribute('aria-pressed')=='true')
            h=page.locator('#splitter')
            h.focus();before=float(h.get_attribute('aria-valuenow'));page.keyboard.press('ArrowRight')
            verify('flow: keyboard separator increases ratio',float(h.get_attribute('aria-valuenow'))>before)
            container_width=page.locator('#explorer').bounding_box()['width']-14
            left_width=page.locator('#graph-pane').bounding_box()['width']
            expected=float(h.get_attribute('aria-valuenow'))/100
            verify('flow: reported ratio matches actual geometry',abs(left_width/container_width-expected)<.015)
            page.keyboard.press('Home')
            verify('flow: Home uses lower limit',abs(float(h.get_attribute('aria-valuenow'))-float(h.get_attribute('aria-valuemin')))<=1)
            page.keyboard.press('End')
            verify('flow: End uses upper limit',abs(float(h.get_attribute('aria-valuenow'))-float(h.get_attribute('aria-valuemax')))<=1)
            page.locator('#equalize').click();verify('flow: reset split to 50',h.get_attribute('aria-valuenow')=='50')
            def begin_drag(delta: float):
                rect=h.bounding_box();x=rect['x']+rect['width']/2;y=rect['y']+80
                page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+delta,y)
            begin_drag(2)
            verify('flow: sub-threshold pointer movement does not resize',h.get_attribute('aria-valuenow')=='50')
            page.mouse.up()
            begin_drag(85)
            verify('flow: real drag changes geometry',h.get_attribute('aria-valuenow')!='50')
            page.keyboard.press('Escape');page.mouse.up()
            verify('flow: Escape restores initial ratio',h.get_attribute('aria-valuenow')=='50')
            verify('flow: Escape removes dragging state',page.locator('#explorer').get_attribute('data-dragging') is None)
            begin_drag(70);h.dispatch_event('pointercancel');page.mouse.up()
            verify('flow: pointercancel rolls back',h.get_attribute('aria-valuenow')=='50')
            begin_drag(70);h.dispatch_event('lostpointercapture');page.mouse.up()
            verify('flow: lost capture rolls back',h.get_attribute('aria-valuenow')=='50')
            begin_drag(60);page.set_viewport_size({'width':390,'height':844});page.mouse.up();page.wait_for_timeout(50)
            verify('flow: resize during drag cleans state',page.locator('#explorer').get_attribute('data-dragging') is None)
            verify('flow: mobile splitter removed from layout',not h.is_visible())
            verify('flow: selection survives responsive layout',page.locator('#stage-title').inner_text()=='执行与资源竞争')
            page.set_viewport_size({'width':1440,'height':1000})
            page.locator('#reset-explorer').click()
            verify('flow: confirmation starts on safe action',page.evaluate('document.activeElement.id')=='cancel-reset')
            page.locator('#cancel-reset').click()
            verify('flow: cancelling reset preserves selection',page.locator('#stage-title').inner_text()=='执行与资源竞争')
            page.locator('#reset-explorer').click();page.locator('#confirm-reset').click()
            verify('flow: reset confirms real state change',page.locator('#stage-title').inner_text()=='候选架构' and h.get_attribute('aria-valuenow')=='54')
            verify('flow: reset restores focus',page.evaluate('document.activeElement.id')=='reset-explorer')
            ctx.close()

            ctx,page=fresh('report')
            verify('report: starts with six fixture rows',page.locator('#rows tr').count()==6)
            values=[float(v) for v in page.locator('#rows tr td:nth-child(5)').all_text_contents()]
            verify('report: numeric sorting',values==sorted(values))
            page.locator('#filter-query').fill('plan b')
            verify('report: search filters data',page.locator('#rows tr').count()==1 and page.locator('.row-link').inner_text()=='Plan B')
            verify('report: derived summary tracks filtered data','12.8 ms' in page.locator('#result-status').inner_text())
            page.locator('#filter-status').select_option('review')
            verify('report: empty state visible',page.locator('#empty-state').is_visible() and page.locator('#rows tr').count()==0)
            verify('report: empty export disabled',page.locator('#export-csv').is_disabled())
            page.locator('#empty-reset').click();page.wait_for_function('document.querySelectorAll("#rows tr").length===6')
            verify('report: reset restores all rows',page.locator('#rows tr').count()==6)
            page.locator('#filter-status').select_option('checked')
            page.locator('#sort-order').select_option('sram')
            verify('report: status filter',page.locator('#rows tr').count()==3)
            values=[int(v) for v in page.locator('#rows tr td:nth-child(4)').all_text_contents()]
            verify('report: numeric SRAM sort',values==[2,4,6])
            link=page.get_by_role('button',name='Plan B',exact=True);link.click()
            verify('report: detail content matches selection',page.locator('#detail-title').inner_text()=='Plan B' and '12.8' in page.locator('#detail-latency').inner_text())
            page.keyboard.press('Escape')
            verify('report: detail focus restoration',link.evaluate('(el)=>document.activeElement===el'))
            with page.expect_download() as info:
                page.locator('#export-csv').click()
            download=info.value;export_path=args.out/'export-fixture.csv';download.save_as(str(export_path))
            with export_path.open(encoding='utf-8-sig',newline='') as f: csv_rows=list(csv.reader(f))
            verify('report: export uses filtered view',len(csv_rows)==4 and [row[0] for row in csv_rows[1:]]==['Plan A','Plan B','Plan E'])
            verify('report: export retains data caveat',all(row[-1]=='手工构造的示例数据' for row in csv_rows[1:]))
            safe=page.evaluate('EU.csvCell("=1+1")')
            verify('report: CSV formula neutralized',safe=='"\'=1+1"')
            quoted=page.evaluate('EU.csvCell(\'a,"b"\')')
            verify('report: CSV quotes escaped',quoted=='"a,""b"""')
            page.locator('#filter-query').fill('<img src=x onerror=alert(1)>')
            verify('report: search text never becomes HTML',page.locator('#rows img').count()==0 and page.locator('#rows tr').count()==0)
            ctx.close()
            verify('all pages: zero attempted external requests',not attempted,str(attempted))
            verify('all pages: zero uncaught page errors',not exceptions,str(exceptions))
            browser.close()
    except Exception as exc:
        checks.append({'name':'suite execution','status':'FAIL','detail':f'{type(exc).__name__}: {exc}'})
    record={
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'platform': platform.platform(), 'python': platform.python_version(),
        'browser': {'engine':'Chromium','version':browser_version},
        'mode':f'fresh contexts; {args.transport} transport; offline=True; HTTP(S) blocked; no dependency installation',
        'summary': {'passed':sum(c['status']=='PASS' for c in checks),'failed':sum(c['status']=='FAIL' for c in checks)},
        'checks':checks,'attempted_external_requests':attempted,'uncaught_page_errors':exceptions,
        'screenshots':screenshots,
        'not_run':(['direct file:// open (inline transport selected)'] if args.transport != 'file' else []) + ['Codex/Claude Code/Cursor skill loading and generation evals','Safari and Firefox','native OS IME','screen reader audit','real mobile touch/iframe interactions','200% browser zoom']
    }
    (args.out/'browser-results.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(record['summary'],ensure_ascii=False))
    if record['summary']['failed']:
        print(json.dumps([c for c in checks if c['status']=='FAIL'],ensure_ascii=False,indent=2))
    print(f'Evidence: {args.out.resolve()}')
    return 1 if record['summary']['failed'] else 0

if __name__=='__main__':
    raise SystemExit(main())
