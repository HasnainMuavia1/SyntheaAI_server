from rest_framework import serializers
from .models import Workspace, ChatSession, ChatMessage

class ChatSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatSession
        fields = ['id', 'project', 'title', 'created_at', 'updated_at']
        read_only_fields = ['id', 'project', 'created_at', 'updated_at']

class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['id', 'project', 'session', 'sender', 'text', 'created_at']
        read_only_fields = ['id', 'project', 'session', 'created_at']
