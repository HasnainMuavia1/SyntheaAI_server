from django.contrib import admin
from .models import Workspace, ChatMessage

@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'workspace_id', 'created_at')
    search_fields = ('name', 'user__username', 'workspace_id')
    readonly_fields = ('workspace_id', 'created_at', 'updated_at')

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('project', 'sender', 'text_preview', 'created_at')
    list_filter = ('sender', 'created_at')
    search_fields = ('text', 'project__name')
    readonly_fields = ('created_at',)

    def text_preview(self, obj):
        return obj.text[:50] + '...' if len(obj.text) > 50 else obj.text
    text_preview.short_description = 'Message'

