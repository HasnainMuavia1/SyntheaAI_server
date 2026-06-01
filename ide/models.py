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
        # Always derive the path from the current project root so workspaces stay
        # portable across environments (host dev vs. Docker, Windows vs. Linux).
        # A stored directory_path from another machine (e.g. an old "C:\..." value)
        # must never leak through, so we recompute rather than trust the column.
        base_dir = os.path.join(settings.BASE_DIR, '..', 'workspaces')
        return os.path.abspath(os.path.join(base_dir, str(self.user.id), str(self.workspace_id)))

    def save(self, *args, **kwargs):
        # Normalize the stored path to the current environment on every save.
        self.directory_path = self.get_absolute_path()
        super().save(*args, **kwargs)

        # Ensure directory exists on disk
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
    reasoning = models.TextField(blank=True, null=True)   # Agent thought-stream logs
    files_created = models.TextField(blank=True, null=True)  # JSON list of modified/created paths
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

