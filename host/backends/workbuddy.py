"""Domestic WorkBuddy is a separate product, not the CodeBuddy Agent SDK.

Its documented local-assistant integration requires a registered WorkBuddy
Open Platform application and user OAuth consent. Never substitute CodeBuddy.
See research/workbuddy-codex-agent-integration.md.
"""
from .base import Backend, BackendError

UNAVAILABLE_REASON = ('国内 WorkBuddy 尚未接入：需先注册 WorkBuddy 开放平台第三方应用，'
                      '取得本地助理权限并完成用户授权；CodeBuddy CLI 登录不能替代。')


class WorkBuddyBackend(Backend):
    name = 'workbuddy'
    unavailable_reason = UNAVAILABLE_REASON

    def open_session(self, resume_key, *, instructions, skills=()):
        raise BackendError(UNAVAILABLE_REASON)

    def start_turn(self, *, prompt, skills=()):
        raise BackendError(UNAVAILABLE_REASON)

    def send(self, message):
        raise BackendError(UNAVAILABLE_REASON)
