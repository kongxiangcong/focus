import {expect,it} from 'vitest';
import {readingMeasures,readReadingMeasure,effectiveReadingMeasure,measureWidth} from './typography';
it('uses CJK character counts and font size as the only measure table',()=>{
 expect(readingMeasures.map(m=>m.characters)).toEqual([36,42,50,62]);
 expect(measureWidth('standard',18)).toBe(756);expect(measureWidth('standard',22)).toBe(924);
});
it('migrates legacy pixel widths once using the current font size',()=>{
 localStorage.clear();localStorage.setItem('focus.standardWidth','1040');
 expect(readReadingMeasure(localStorage,18)).toBe('full');
 expect(localStorage.getItem('focus.readingMeasure')).toBe('full');
 expect(localStorage.getItem('focus.standardWidth')).toBeNull();
 localStorage.setItem('focus.readingMeasure','narrow');localStorage.setItem('focus.readingWidth','1440');
 expect(readReadingMeasure(localStorage,18)).toBe('narrow');expect(localStorage.getItem('focus.readingWidth')).toBeNull();
 localStorage.clear();localStorage.setItem('focus.readingWidth','wide');expect(readReadingMeasure(localStorage,18)).toBe('full');
 localStorage.clear();
});
it('falls back only for display and restores a wider preference when space returns',()=>{
 expect(effectiveReadingMeasure('full',18,900)).toBe('standard');
 expect(effectiveReadingMeasure('full',18,1600)).toBe('full');
 expect(effectiveReadingMeasure('standard',18,390)).toBe('narrow');
});
