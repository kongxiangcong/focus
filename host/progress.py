"""Public activity labels derived from observed events, never model estimates."""

CORE_LABELS = {
    'catalog': '查看知识库', 'state': '读取阅读位置', 'current': '读取当前段落',
    'map': '规划阅读', 'switch': '切换材料', 'topic': '选择专题',
    'search': '检索原文', 'topic_search': '检索专题',
    'read_range': '读取原文', 'topic_range': '读取原文',
    'translate': '保存译文', 'append_note': '保存笔记', 'list_notes': '读取笔记',
    'topic_notes': '读取专题笔记', 'continue': '推进阅读', 'synthesize_topic': '整理专题',
}


def activity_label(activity):
    title = activity.get('title', '')
    detail = activity.get('detail', '').lower()
    if title == 'commandExecution':
        # Only classify the command itself; output is untrusted and may quote other commands.
        command = detail.split('\n', 1)[0]
        if any(name in command for name in ('mineru_precision.py', 'article_parser.py')):
            return '解析材料'
        if 'core.library_import' in command:
            return '整理入库材料'
        if 'focus_map.py' in command:
            return '规划阅读'
        if 'focus_read.py' in command:
            return '处理阅读内容'
        return '执行操作'
    return {'reasoning': '思考中', 'fileChange': '保存文件',
            'mcpToolCall': '调用工具', 'dynamicToolCall': '调用工具',
            'webSearch': '检索资料'}.get(title, '处理任务')
