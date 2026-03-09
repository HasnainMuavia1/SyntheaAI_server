from django.db import models
from django.conf import settings
import os
import uuid

class Workspace(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='workspaces')
    name = models.CharField(max_length=255)
    workspace_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Store path relative to a base directory or absolute.
    # We will compute absolute path dynamically or store the base root.
    directory_path = models.CharField(max_length=1024, blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.user.username})"

    def get_absolute_path(self):
        # Determine the base path for workspaces, e.g., in a 'workspaces' folder at project root
        base_dir = os.path.join(settings.BASE_DIR, '..', 'workspaces')
        if not self.directory_path:
            self.directory_path = os.path.join(base_dir, str(self.user.id), str(self.workspace_id))
        return os.path.abspath(self.directory_path)

    def save(self, *args, **kwargs):
        if not self.directory_path:
            self.directory_path = self.get_absolute_path()
        super().save(*args, **kwargs)
        
        # Ensure directory exists on disk
        if not os.path.exists(self.directory_path):
            os.makedirs(self.directory_path, exist_ok=True)

class ChatSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='chat_sessions')
    title = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Session {self.id} for {self.project.name}"

class ChatMessage(models.Model):
    SENDER_CHOICES = (
        ('user', 'User'),
        ('agent', 'Agent'),
    )
    
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages', null=True)
    project = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='all_messages', null=True, blank=True) # Kept for backward compatibility momentarily
    sender = models.CharField(max_length=10, choices=SENDER_CHOICES)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.session:
            # Touch the session to update its updated_at timestamp
            self.session.save(update_fields=['updated_at'])

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.get_sender_display()}] {self.text[:50]}"

