from django.urls import re_path, path
from .views import FileListView, FileDetailView, FileRenameView, ProjectListView, ProjectDetailView, ChatSessionListView, ChatSessionDetailView, ChatMessageViewSet, ChatbotWidgetView

urlpatterns = [
    re_path(r'^files/list$', FileListView.as_view(), name='file_list'),
    re_path(r'^files/detail$', FileDetailView.as_view(), name='file_detail'),
    re_path(r'^files/rename$', FileRenameView.as_view(), name='file_rename'),
    re_path(r'^projects$', ProjectListView.as_view(), name='project_list'),
    re_path(r'^projects/(?P<project_id>[\w-]+)/sessions$', ChatSessionListView.as_view(), name='project_sessions'),
    re_path(r'^projects/(?P<project_id>[\w-]+)/sessions/(?P<session_id>[\w-]+)$', ChatSessionDetailView.as_view(), name='project_session_detail'),
    re_path(r'^projects/(?P<project_id>[\w-]+)/sessions/(?P<session_id>[\w-]+)/messages$', ChatMessageViewSet.as_view(), name='session_messages'),
    re_path(r'^projects/(?P<project_id>[\w-]+)$', ProjectDetailView.as_view(), name='project_detail'),
    path('chatbot', ChatbotWidgetView.as_view(), name='chatbot_widget'),
    path('chatbot/', ChatbotWidgetView.as_view(), name='chatbot_widget_slash'),
]
