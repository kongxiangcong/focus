"""Synthetic source assets for real Chromium/HTTP figure acceptance."""
import json
import shutil
from PIL import Image, ImageDraw


def configure(workspace, source, plan):
    translations = {}
    bodies = {
        1: ['![Figure](images/image-001.png)', 'Figure 1. Full architecture caption with compute, memory and data movement.', '',
            *[f'Paragraph {i}: independent text scrolling keeps the architecture image visible.' for i in range(1, 46)]],
        2: ['![Figure](images/image-002.png)', 'Figure 2. First image in this chunk.', '',
            '![Figure](images/image-003.png)', 'Figure 3. Second tall image in this chunk.', '',
            *[f'Paragraph {i}: the two figures have an independent gallery scroll.' for i in range(1, 30)]],
        3: ['No images in this chunk.', '', *['Plain reading text remains centered.'] * 12],
        4: ['![Figure](images/image-004.png)', 'Figure 4. An unread chunk figure.', '',
            '<figure><img src="images/image-005.png"><figcaption>Figure 5. Full HTML image caption.</figcaption></figure>', '',
            '$$y = Ax$$', '', '<table><tr><td>Required table <img src="images/image-006.png"></td></tr></table>', '',
            '<img class="equation" src="images/image-007.png" alt="Equation 1">', '',
            '<!-- Canonical Bundle bindings: ![bound](images/image-005.png) ![bound](images/image-006.png) ![bound](images/image-007.png) -->'],
    }
    lines, chunks = [], []
    for index in range(1, 10):
        body = bodies.get(index, ['Ordinary subsequent reading content.'])
        start = len(lines) + 1
        lines.extend([f'## Section {index}', '', *body, ''])
        import re
        images = re.findall(r'!\[[^]]*\]\(([^)]+)\)', '\n'.join(body))
        chunks.append({'chunk_id':f'chunk-{index:03}', 'index':index, 'section_path':[f'Section {index}'], 'source_lines':[start,len(lines)], 'images':images})
        translations[index] = '\n'.join(body).replace('Figure 1. Full architecture caption with compute, memory and data movement.', '图 1：完整架构图注，包含计算、存储与数据搬运。')\
            .replace('Figure 2. First image in this chunk.', '图 2：本段第一张图片。').replace('Figure 3. Second tall image in this chunk.', '图 3：本段第二张纵向图片。')\
            .replace('Figure 4. An unread chunk figure.', '图 4：尚未阅读段落中的图片。').replace('Figure 5. Full HTML image caption.', '图 5：完整 HTML 图片图注。')
    (source/'parser-bundle/content.md').write_text('\n'.join(lines)+'\n')
    (plan/'chunks.jsonl').write_text(''.join(json.dumps(c)+'\n' for c in chunks))
    images = source/'parser-bundle/images'
    for i in range(1, 8):
        size = (900, 1800) if i == 3 else (2400, 1600) if i <= 5 else (680, 110) if i == 6 else (250, 50)
        image = Image.new('RGB',size,'white'); draw=ImageDraw.Draw(image)
        for j in range(4):
            x=40+j*(size[0]//4); draw.rectangle((x,40,min(x+size[0]//5,size[0]-1),min(size[1]-1,400)), outline='#527285', width=4)
            draw.text((x+15,55),f'Figure {i}: block {j+1}',fill='black')
        image.save(images/f'image-{i:03}.png')
    second = workspace/'sources/second-paper'
    shutil.copytree(source,second)
    metadata=json.loads((second/'source.yaml').read_text());metadata.update(source_id='second-paper',title='Second source for figure isolation',short_name='second',identity='fixture:second')
    (second/'source.yaml').write_text(json.dumps(metadata))
    state=json.loads((workspace/'state.json').read_text());state['sources']['second-paper']={'current_plan_id':'plan-001','current_chunk_id':'chunk-001'}
    (workspace/'state.json').write_text(json.dumps(state))
    return translations
