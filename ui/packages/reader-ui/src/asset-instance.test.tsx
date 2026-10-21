import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { imageUrl, imageIdentity, mergeFigures } from './figures';
import { MarkdownContent } from './MarkdownContent';
afterEach(cleanup);
it('binds relative and historical assets to the active instance without changing identity', () => {
  expect(imageUrl('images/a.png', 'demo', 'workspace a')).toBe('/reader/assets/demo/images/a.png?instance=workspace%20a');
  expect(imageUrl('/reader/historical-assets/demo/a.png?v=2#image', 'demo', 'new')).toBe('/reader/historical-assets/demo/a.png?v=2&instance=new#image');
  expect(imageUrl('/reader/assets/demo/a.png?instance=old', 'demo', 'new')).toContain('instance=old');
  expect(imageUrl('https://elsewhere.test/a.png', 'demo', 'new')).toBe('https://elsewhere.test/a.png');
  expect(imageUrl('/other/a.png', 'demo', 'new')).toBe('/other/a.png');
  expect(imageIdentity('images/a.png', 'demo')).toBe(imageIdentity('/reader/assets/demo/images/a.png?instance=new', 'demo'));
});
it('retains the Host instance URL when merging a Markdown scan first', () => {
  const figures = mergeFigures('demo', [{src:'images/a.png',caption:'图 1'}], [{src:'/reader/assets/demo/images/a.png?instance=host',caption:'other'}]);
  expect(figures).toHaveLength(1);
  expect(figures[0].src).toContain('instance=host');
  expect(figures[0].caption).toBe('图 1');
});
it('keeps unsafe Markdown image schemes blocked', () => {
  render(<MarkdownContent text="![bad](javascript:alert)" sourceId="demo" />);
  expect(screen.getByAltText('bad')).not.toHaveAttribute('src', expect.stringContaining('javascript:'));
});

import { AssetInstanceContext } from './asset-context';
import { FigurePanel, FigureViewer } from './FigurePanel';
import { vi } from 'vitest';
it('uses the shared instance for Markdown, gallery and enlarged images', () => {
  const f = mergeFigures('demo', [{src:'images/a.png',caption:'图 1'}])[0];
  HTMLDialogElement.prototype.showModal = vi.fn();
  const {container} = render(<AssetInstanceContext.Provider value="host"><MarkdownContent text="![source](images/a.png)" sourceId="demo" />
    <FigurePanel figures={[f]} selected={f.id} selectionVersion={0} onSelect={vi.fn()} onZoom={vi.fn()} />
    <FigureViewer request={{figure:f,origin:null}} figures={[f]} onClose={vi.fn()} />
  </AssetInstanceContext.Provider>);
  expect(container.querySelectorAll('img')).toHaveLength(4);
  for (const img of container.querySelectorAll('img')) expect(img.src).toContain('instance=host');
});
