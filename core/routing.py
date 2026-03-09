from django.urls import path
from ide.consumers import TerminalConsumer, VoiceConsumer, LangChainAgentConsumer

websocket_urlpatterns = [
    path("ws/terminal/", TerminalConsumer.as_asgi()),
    path("ws/voice/", VoiceConsumer.as_asgi()),
    path("ws/agent/", LangChainAgentConsumer.as_asgi()),
]
