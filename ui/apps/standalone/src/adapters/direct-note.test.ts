import {expect,it,vi} from 'vitest';
import {HttpReaderHost} from './http-reader-host';
import {FixtureReaderHost} from './fixture-reader-host';
it('direct HTTP notes carry instance and stable request identity and retain bundle-change errors',async()=>{
 const fetch=vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response(JSON.stringify({ok:false,error:{code:'note_bundle_changed',message:'这段原文已更新，可改存为整篇笔记',retryable:false}}),{status:409}));
 const host=new HttpReaderHost({baseUrl:'http://localhost',instanceId:'active',fetch});
 const result=await host.createSourceNote({sourceId:'demo',requestId:'request-1234',content:'理解',kind:'thought',origin:'user'});
 expect(result).toMatchObject({ok:false,error:{code:'note_bundle_changed'}});
 const [url,init]=fetch.mock.calls[0];expect(url).toBe('http://localhost/library/sources/demo/notes');expect(init?.method).toBe('POST');
 expect(new Headers(init?.headers).get('X-FOCUS-Instance')).toBe('active');
 expect(JSON.parse(init?.body as string)).toEqual({requestId:'request-1234',content:'理解',kind:'thought',origin:'user'});
});
it('fixture notes are idempotent, Source-owned and independent from conversation and cursor',async()=>{
 const host=new FixtureReaderHost(),before=await host.getReadingWindow();if(!before.ok)throw Error();
 const c=before.value.current!;const input={sourceId:c.sourceId,requestId:'request-1234',content:'理解',kind:'thought' as const,origin:'user' as const,chunk:{planId:c.planId,chunkId:c.chunkId}};
 const first=await host.createSourceNote(input);expect(first.ok).toBe(true);if(!first.ok)throw Error();
 const again=await host.createSourceNote(input);if(!again.ok)throw Error();
 expect(again.value.sourceNotes).toHaveLength(1);expect(again.value.current).toEqual(before.value.current);expect(again.value.conversation).toEqual(before.value.conversation);
 expect(first.value.noteOperation?.note?.anchor?.bundle).toBe(c.bundleVersion);
 expect(await host.createSourceNote({...input,content:'changed'})).toMatchObject({ok:false});
 for(const outcome of ['failed','note_bundle_changed'] as const){host.noteCreateOutcome=outcome;expect(await host.createSourceNote({...input,requestId:'other-request'})).toMatchObject({ok:false,error:{code:outcome==='failed'?'unavailable':outcome}});}
 host.noteCreateOutcome='success';expect(await host.createSourceNote({...input,requestId:'other-request',chunk:undefined})).toMatchObject({ok:true,value:{noteOperation:{note:{anchor:null}}}});
});
