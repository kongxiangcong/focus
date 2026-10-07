import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readerSuccess, type ReaderChunk, type ReaderHost, type ReadingWindow } from "@focus/reader-contracts";
import { chunkFigures, imageIdentity } from "./figures";
import { FocusReader } from "./FocusReader";

const chunk: ReaderChunk = { sourceId: "demo-paper", planId: "plan-001", chunkId: "chunk-001", index: 1, total: 3, sectionPath: ["Method"], sourceLines: [1, 20],
  sourceMarkdown: '![Figure](./images/fig%20A.png)\n\nFigure 3. Full architecture caption.\n\n<figure><img src="images/figB.png"><figcaption>Figure 4. Second image.</figcaption></figure>\n\n$$y=Ax$$\n\n<table><tr><td><img src="images/table.png"></td></tr></table>\n\n<img class="equation" src="images/equation.png">',
  translation: '![Figure](<images/fig A.png>)\n\n图 3：完整架构图注。\n\n<figure><img src="images/figB.png"><figcaption>图 4：第二张图。</figcaption></figure>\n\n$$y=Ax$$\n\n<table><tr><td><img src="images/table.png"></td></tr></table>\n\n<img class="equation" src="images/equation.png">',
  images: [{ src: '/reader/assets/demo-paper/images/fig%20A.png', caption: 'Figure 3. Full architecture caption.' }, { src: 'images/table.png', caption: 'Table 1' }, { src: 'images/equation.png', caption: '' }],
  relevantGlossary: [], presentationStatus: 'presented' };
const future = { src: '/reader/assets/demo-paper/images/future.png', caption: 'Figure 9. Unread figure.' };
const window: ReadingWindow = { status: 'reading', source: { sourceId: chunk.sourceId, title: 'Demo', topicId: null }, sessionId: 's1', current: chunk, history: [], conversation: [], figures: [...chunk.images, future] };
beforeEach(() => {
  sessionStorage.clear(); localStorage.clear();
  HTMLElement.prototype.scrollTo = vi.fn();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
});
afterEach(cleanup);
it('normalizes local URLs, preserves source order, localizes full captions, and excludes tables/equations', () => {
  expect(imageIdentity('./images/fig%20A.png#fragment', chunk.sourceId)).toBe(imageIdentity('/reader/assets/demo-paper/images/fig A.png', chunk.sourceId));
  const figures = chunkFigures(chunk);
  expect(figures.map(f => f.label)).toEqual(['图 3', '图 4']);
  expect(figures[0].caption).toBe('图 3：完整架构图注。');
  expect(chunkFigures(chunk, true)[0].caption).toBe('Figure 3. Full architecture caption.');
});
it('extracts linked Markdown, reference images and HTML captions without mistaking code or inline prose for standalone figures', () => {
  const input = { ...chunk, translation: null, images: [], sourceMarkdown: '[![link](images/linked.png)](https://example.org)\n\n![ref][image]\n\n[image]: images/ref.png\n\ninline ![badge](images/badge.png) prose\n\n```md\n![code](images/code.png)\n```' };
  expect(chunkFigures(input).map(f => f.src.split('/').at(-1))).toEqual(['linked.png', 'ref.png']);
});
it('uses stable fallback labels and does not collapse different paths sharing a filename', () => {
  const input = { ...chunk, translation: null, sourceMarkdown: '', images: [{src:'images/a.png',caption:''},{src:'other/a.png',caption:''},{src:'images/%E5%9B%BE.png',caption:''}] };
  const figures = chunkFigures(input);
  expect(figures).toHaveLength(3);
  expect(figures[0].label).toBe(chunkFigures({...input, images:[input.images[0]]})[0].label);
  expect(figures[2].label).toBe('插图 图.png');
});
it('uses available original captions when a translation omits images and never requests more translation', () => {
  expect(chunkFigures({...chunk, translation:'译文无图片。'})[0].caption).toBe('Figure 3. Full architecture caption.');
});
it('extracts MinerU image and caption joined by a single newline as one standalone figure', () => {
  const input = {...chunk, translation:null, images:[], sourceMarkdown:'![Architecture](images/a.png)\nFigure 2. Complete caption\ncontinuation.'};
  expect(chunkFigures(input)).toHaveLength(1);
  expect(chunkFigures(input)[0].caption).toBe('Figure 2. Complete caption\ncontinuation.');
});
it('moves an image on its own source line even when Markdown joins the following prose into its paragraph', () => {
  const input = {...chunk, translation:null, images:[], sourceMarkdown:'![Illustration](images/a.png)\nExplanatory prose stays in the text.'};
  expect(chunkFigures(input)).toHaveLength(1);
  expect(chunkFigures(input)[0].caption).toBe('Illustration');
});
it('keeps rasterized tables and equations in the body, including supplementary bindings', () => {
  const input = {...chunk, translation:null, sourceMarkdown:'![data](images/table.png)\nTable 2. Raster table.\n\n![Equation 1](images/equation.png)', images:[{src:'images/table.png',caption:'Table 2. Raster table.'},{src:'images/equation.png',caption:'Equation 1'}]};
  expect(chunkFigures(input)).toEqual([]);
});
it('opens unread figures without navigation or rebinding the question, and shares the side space with notes', async () => {
  let emit!: Parameters<NonNullable<ReaderHost['subscribe']>>[0];
  const host: ReaderHost = { getReadingWindow: vi.fn(async()=>readerSuccess(window)), continueReading:vi.fn(), sendMessage:vi.fn(async()=>readerSuccess(window)), subscribe: callback=>{emit=callback;return()=>{};} };
  render(<FocusReader host={host} appearance="mist" />);
  await screen.findByRole('heading', {name:'Method'});
  const pane = screen.getByRole('main', {name:'阅读与对话'});
  expect(pane.querySelector('.katex')).toBeTruthy();
  expect(pane.querySelector('table img')).toBeTruthy();
  expect(pane.querySelector('img[src*="equation"]')).toBeTruthy();
  expect(pane.querySelectorAll('img')).toHaveLength(2);
  fireEvent.change(screen.getByRole('textbox'),{target:{value:'original draft'}});
  const toolbar = screen.getByRole('navigation',{name:'阅读侧栏'});
  expect(within(toolbar).getAllByRole('button')).toHaveLength(2);
  expect(screen.queryByText(/本段图片/)).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'全文图片'})).not.toBeInTheDocument();
  const navigation = screen.getByRole('navigation',{name:'图片目录'});
  expect(within(navigation).getAllByRole('button').map(b => b.textContent)).toEqual(['图 3', '图 4', '图 9']);
  expect(navigation.querySelector('img')).toBeNull();
  const disclosure = navigation.closest('details')!;
  expect(disclosure.open).toBe(true);
  act(() => { disclosure.open = false; });
  expect(screen.getByRole('button',{name:'隐藏图片区'})).toBeInTheDocument();
  act(() => { disclosure.open = true; });
  fireEvent.click(within(screen.getByRole('navigation',{name:'图片目录'})).getByRole('button',{name:/图 9/}));
  expect(screen.getByRole('navigation',{name:'图片目录'}).querySelector('[aria-current=true]')).toHaveTextContent('图 9');
  expect(host.continueReading).not.toHaveBeenCalled();
  expect(screen.getByRole('textbox')).toHaveValue('original draft');
  fireEvent.click(screen.getByRole('button',{name:'笔记与记录'}));
  expect(screen.queryByRole('img',{name:future.caption})).not.toBeInTheDocument();
  expect(screen.getByRole('complementary',{name:'笔记与阅读记录'})).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'发送 ↑'}));
  expect(host.sendMessage).toHaveBeenCalledWith(expect.objectContaining({receipt:expect.objectContaining({chunkId:chunk.chunkId})}));
  act(()=>emit(readerSuccess({...window, revision:2, source:{...window.source, sourceId:'another-paper'},current:{...chunk,sourceId:'another-paper',sourceMarkdown:'no figure',translation:null,images:[]},figures:[]})));
  expect(screen.queryByRole('region',{name:'阅读资料侧栏'})).not.toBeInTheDocument();
});
it('selects the viewed chunk in the full gallery and exposes it from no-image chunks and history', async()=> {
  let emit!: Parameters<NonNullable<ReaderHost['subscribe']>>[0];
  const noImages = {...chunk,chunkId:'chunk-002',index:2,sourceMarkdown:'no images',translation:null,images:[]};
  const host: ReaderHost={getReadingWindow:vi.fn(async()=>readerSuccess(window)),continueReading:vi.fn(),sendMessage:vi.fn(),subscribe:callback=>{emit=callback;return()=>{};}};
  render(<FocusReader host={host} appearance="mist" />);
  await screen.findByRole('button',{name:'隐藏图片区'});
  act(()=>emit(readerSuccess({...window,revision:2,current:noImages,history:[chunk]})));
  expect(screen.queryByRole('region',{name:'阅读资料侧栏'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'展开图片区'}));
  expect(within(screen.getByRole('navigation',{name:'图片目录'})).getByRole('button',{name:'图 9'})).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'隐藏图片区'}));
  expect(screen.queryByRole('navigation',{name:'图片目录'})).not.toBeInTheDocument();
  fireEvent.click(within(screen.getByRole('navigation',{name:'段落目录'})).getByRole('button',{name:/01/}));
  expect(screen.getByRole('button',{name:'隐藏图片区'})).toBeInTheDocument();
});

it('lists all ten source figures in numeric order and preserves selection when toggling the panel', async () => {
  const figures = Array.from({length:10}, (_, i) => ({src:`images/figure-${10-i}.png`,caption:`Figure ${10-i}. Caption`}));
  const current = {...chunk, sourceMarkdown:'Text without images.', translation:null, images:[]};
  const host: ReaderHost = {getReadingWindow:vi.fn(async()=>readerSuccess({...window,current,figures})),continueReading:vi.fn(),sendMessage:vi.fn()};
  render(<FocusReader host={host} appearance="mist" />);
  await screen.findByRole('heading',{name:'Method'});
  fireEvent.click(screen.getByRole('button',{name:'展开图片区'}));
  const directory = screen.getByRole('navigation',{name:'图片目录'});
  expect(within(directory).getAllByRole('button').map(b=>b.textContent)).toEqual(Array.from({length:10},(_,i)=>`图 ${i+1}`));
  fireEvent.click(within(directory).getByRole('button',{name:'图 10'}));
  expect(screen.getByLabelText('图片浏览').querySelector('figure[data-selected=true] img')).toHaveAttribute('src','/reader/assets/demo-paper/images/figure-10.png');
  fireEvent.click(screen.getByRole('button',{name:'隐藏图片区'}));
  fireEvent.click(screen.getByRole('button',{name:'展开图片区'}));
  expect(within(screen.getByRole('navigation',{name:'图片目录'})).getByRole('button',{name:'图 10'})).toHaveAttribute('aria-current','true');
  expect(host.continueReading).not.toHaveBeenCalled();
});
