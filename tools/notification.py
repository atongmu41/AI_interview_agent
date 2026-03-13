"""通知工具：邮件/短信通知（占位实现）。"""
from tools.base import ToolSpec

def run(channel: str, to: str, content: str, **kwargs: str) -> str:
    return f"[通知] 占位：channel={channel}, to={to}, content={content[:50]}..."

SPEC = ToolSpec(
    name="notification",
    description="发送通知：channel 为 email/sms，to 为地址或号码，content 为内容",
    parameters={"type": "object", "properties": {"channel": {"type": "string", "enum": ["email", "sms"]}, "to": {"type": "string"}, "content": {"type": "string"}}, "required": ["channel", "to", "content"]},
)
