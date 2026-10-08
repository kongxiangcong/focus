"""Shared model-visible Source discussion capabilities for both adapters."""
import copy
from ..core_bridge import TOOL


def discussion_tools():
    source = copy.deepcopy(TOOL)
    source['inputSchema']['properties']['action']['enum'] = ['search', 'read_range', 'source_note']
    return [source, {
        'name': 'focus_user_input', 'description': 'Ask the reader a necessary clarification through FOCUS. Does not grant write permissions.',
        'inputSchema': {'type': 'object', 'properties': {'questions': {'type': 'array', 'minItems': 1, 'maxItems': 3,
            'items': {'type': 'object', 'properties': {'id': {'type': 'string'}, 'header': {'type': 'string'},
                'question': {'type': 'string'}, 'options': {'type': 'array', 'items': {'type': 'object',
                    'properties': {'label': {'type': 'string'}, 'description': {'type': 'string'}},
                    'required': ['label', 'description'], 'additionalProperties': False}}},
                'required': ['id', 'header', 'question', 'options'], 'additionalProperties': False}}},
            'required': ['questions'], 'additionalProperties': False}}, {
        'name': 'focus_confirm', 'description': 'Request reader confirmation for a proposed discussion action. Confirmation never authorizes access to other local Sources or bypasses Core guards.',
        'inputSchema': {'type': 'object', 'properties': {'title': {'type': 'string'}, 'detail': {'type': 'string'}},
                        'required': ['title', 'detail'], 'additionalProperties': False}}]


def library_tools():
    tool = copy.deepcopy(TOOL)
    tool['inputSchema']['properties']['action']['enum'] = ['catalog', 'search', 'read_range', 'topic_search', 'topic_range', 'topic_notes']
    return [tool]
