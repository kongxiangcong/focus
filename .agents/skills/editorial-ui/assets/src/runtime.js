/* Native behavior helpers; no runtime imports, persistence, network or third-party code. */
'use strict';
const EU = (() => {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
  const animations = new Set();
  const activeByElement = new WeakMap();
  const cancelAnimations = () => { if (reduce.matches) for (const a of animations) a.cancel(); };
  if (reduce.addEventListener) reduce.addEventListener('change', cancelAnimations);
  function reveal(element) {
    if (!element || reduce.matches || typeof element.animate !== 'function') return;
    activeByElement.get(element)?.cancel();
    const animation = element.animate(
      [{opacity:0, transform:`translateY(${EU_MOTION.distance_px.reveal}px)`}, {opacity:1, transform:'translateY(0)'}],
      {duration:EU_MOTION.duration_ms.reveal, easing:EU_MOTION.easing.standard}
    );
    animations.add(animation); activeByElement.set(element, animation);
    const remove = () => { animations.delete(animation); if (activeByElement.get(element)===animation) activeByElement.delete(element); };
    animation.addEventListener('finish', remove, {once:true});
    animation.addEventListener('cancel', remove, {once:true});
  }
  function initTheme() {
    const system = matchMedia('(prefers-color-scheme: dark)');
    let userChoice = null;
    const button = document.querySelector('[data-theme-toggle]');
    const apply = () => {
      const dark = userChoice === null ? system.matches : userChoice;
      document.documentElement.dataset.theme = dark ? 'dark' : 'light';
      if (button) { button.textContent = dark ? '浅色' : '深色'; button.setAttribute('aria-label', dark ? '切换到浅色模式' : '切换到深色模式'); }
    };
    button?.addEventListener('click', () => { userChoice = document.documentElement.dataset.theme !== 'dark'; apply(); });
    if (system.addEventListener) system.addEventListener('change', apply);
    apply();
  }
  function dialogController(dialog) {
    let opener = null;
    // Native modality can still let Tab enter browser chrome. Keep this task's
    // in-document cycle deterministic, including controls hidden/disabled at runtime.
    dialog.addEventListener('keydown', event => {
      if (event.key !== 'Tab' || !dialog.open) return;
      const candidates = [...dialog.querySelectorAll('button,a[href],input,select,textarea,summary,[tabindex]')]
        .filter(el => el.tabIndex >= 0 && !el.matches(':disabled') && !el.closest('[hidden],[inert]')
          && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden');
      if (!candidates.length) { event.preventDefault(); dialog.focus(); return; }
      const first = candidates[0], last = candidates[candidates.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
    dialog.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => dialog.close()));
    dialog.addEventListener('close', () => {
      if (opener?.isConnected) opener.focus({preventScroll:true});
      else document.querySelector('main')?.focus({preventScroll:true});
    });
    return {
      open(trigger, focusSelector) {
        opener = trigger || document.activeElement;
        if (!dialog.open) dialog.showModal();
        const focus = focusSelector ? dialog.querySelector(focusSelector) : dialog.querySelector('[data-close],button,input,textarea');
        focus?.focus({preventScroll:true}); reveal(dialog);
      },
      close() { dialog.close(); }
    };
  }
  function status(element, text, kind='normal') { element.textContent=text; element.dataset.kind=kind; }
  function scrollFollower(viewport, content, jumpButton) {
    let following=true, frame=0, lastInput=-Infinity;
    const tolerance=32, cooldown=150;
    const nearBottom = () => viewport.scrollHeight-viewport.clientHeight-viewport.scrollTop <= tolerance;
    const show = () => { jumpButton.hidden=following; viewport.dataset.following=String(following); };
    const markInput = (event) => {
      if (event.type==='keydown' && !['ArrowUp','ArrowDown','PageUp','PageDown','Home','End',' '].includes(event.key)) return;
      lastInput=performance.now();
      if ((event.type==='wheel' && event.deltaY<0) || event.type==='touchstart' || (event.type==='keydown' && ['ArrowUp','PageUp','Home'].includes(event.key))) following=false;
      show();
    };
    ['wheel','touchstart','keydown'].forEach(type => viewport.addEventListener(type,markInput,{passive:true}));
    viewport.addEventListener('scroll',()=>{ following=nearBottom(); show(); },{passive:true});
    const update = () => {
      if (frame) return;
      frame=requestAnimationFrame(()=>{
        frame=0;
        if (following && performance.now()-lastInput>cooldown) viewport.scrollTop=viewport.scrollHeight;
        show();
      });
    };
    const jump = () => { following=true; lastInput=-Infinity; viewport.scrollTop=viewport.scrollHeight; show(); };
    jumpButton.addEventListener('click',jump);
    const resize = typeof ResizeObserver==='function' ? new ResizeObserver(update) : null;
    resize?.observe(content);
    show();
    return { update, reset:jump, isFollowing:()=>following, destroy(){ if(frame)cancelAnimationFrame(frame); resize?.disconnect(); } };
  }
  function csvCell(value) {
    let text=String(value ?? '');
    if (typeof value==='string' && /^[\s]*[=+@-]/.test(text)) text="'"+text;
    return '"'+text.replace(/"/g,'""')+'"';
  }
  function downloadCsv(rows, name) {
    const csv='\uFEFF'+rows.map(row=>row.map(csvCell).join(',')).join('\r\n');
    const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
    const anchor=document.createElement('a'); anchor.href=url; anchor.download=name; anchor.hidden=true;
    document.body.append(anchor); anchor.click(); anchor.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1500);
  }
  initTheme();
  return { reveal, dialogController, status, scrollFollower, downloadCsv, csvCell };
})();
