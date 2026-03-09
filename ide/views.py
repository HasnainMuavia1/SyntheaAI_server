import os
import shutil
from pathlib import Path
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework import status
from .models import Workspace, ChatSession, ChatMessage
from .serializers import ChatSessionSerializer, ChatMessageSerializer
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

class BaseWorkspaceView(APIView):
    permission_classes = [IsAuthenticated]

    def get_workspace(self, request):
        project_id = request.query_params.get('projectId') or request.data.get('projectId')
        if project_id:
            try:
                return Workspace.objects.get(user=request.user, workspace_id=project_id)
            except Workspace.DoesNotExist:
                return None
        # Fallback for now if no ID provided
        workspace, created = Workspace.objects.get_or_create(
            user=request.user, 
            defaults={'name': 'My Project'}
        )
        return workspace
        
    def get_safe_path(self, workspace, requested_path):
        base_path = Path(workspace.get_absolute_path())
        # Clean the requested path to prevent directory traversal
        if requested_path.startswith('/'):
            requested_path = requested_path[1:]
        target_path = base_path / requested_path
        # Resolve to handle '.' and '..'
        target_path = target_path.resolve()
        
        # Security check
        if not str(target_path).startswith(str(base_path.resolve())):
            return None
        return target_path

class ProjectListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        workspaces = Workspace.objects.filter(user=request.user).order_by('-updated_at')
        projects = []
        for w in workspaces:
            projects.append({
                'id': str(w.workspace_id),
                'name': w.name,
                'description': getattr(w, 'description', ''), # If description was added to model
                'updated': w.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            })
        return Response({'projects': projects})

    def post(self, request):
        name = request.data.get('name')
        description = request.data.get('description', '')
        if not name:
            return Response({'error': 'Project name is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if name exists for this user
        if Workspace.objects.filter(user=request.user, name__iexact=name).exists():
            return Response({'error': f'Project with name "{name}" already exists'}, status=status.HTTP_400_BAD_REQUEST)

        workspace = Workspace.objects.create(user=request.user, name=name)
        return Response({
            'success': True,
            'project': {
                'id': str(workspace.workspace_id),
                'name': workspace.name,
                'description': description, # Currently description is not in model, just returning it
                'updated': workspace.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            }
        }, status=status.HTTP_201_CREATED)

class ProjectDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, project_id):
        try:
            workspace = Workspace.objects.get(user=request.user, workspace_id=project_id)
            # Delete directory if we want
            target_path = Path(workspace.get_absolute_path())
            if target_path.exists() and target_path.is_dir():
                shutil.rmtree(target_path)
            workspace.delete()
            return Response({'success': True})
        except Workspace.DoesNotExist:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class FileListView(BaseWorkspaceView):
    def get(self, request):
        path = request.query_params.get('path', '')
        workspace = self.get_workspace(request)
        if not workspace:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
            
        target_path = self.get_safe_path(workspace, path)
        
        if not target_path or not target_path.exists() or not target_path.is_dir():
            return Response({'error': 'Invalid directory', 'files': []}, status=status.HTTP_400_BAD_REQUEST)
            
        def build_tree(current_dir):
            tree = []
            for entry in current_dir.iterdir():
                rel_path = str(entry.relative_to(workspace.get_absolute_path())).replace('\\', '/')
                node = {
                    'id': rel_path,
                    'name': entry.name,
                    'type': 'folder' if entry.is_dir() else 'file',
                }
                if entry.is_dir():
                    node['children'] = build_tree(entry)
                tree.append(node)
            return sorted(tree, key=lambda x: (x['type'] != 'folder', x['name'].lower()))
            
        files = build_tree(target_path)
        return Response({'files': files, 'projectName': workspace.name})

class FileDetailView(BaseWorkspaceView):
    def get(self, request):
        path = request.query_params.get('path', '')
        workspace = self.get_workspace(request)
        if not workspace:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
            
        target_path = self.get_safe_path(workspace, path)
        
        if not target_path or not target_path.exists() or target_path.is_dir():
            return Response({'error': 'File not found'}, status=status.HTTP_404_NOT_FOUND)
            
        try:
            with open(target_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return Response({'content': content})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
    def post(self, request):
        # Create or update file
        path = request.data.get('path', '')
        content = request.data.get('content', '')
        is_dir = request.data.get('is_dir', False)
        
        workspace = self.get_workspace(request)
        if not workspace:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
            
        target_path = self.get_safe_path(workspace, path)
        
        if not target_path:
            return Response({'error': 'Invalid path'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            # Ensure parent exists
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if is_dir:
                target_path.mkdir(parents=True, exist_ok=True)
            else:
                with open(target_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            return Response({'success': True})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request):
        path = request.query_params.get('path', '')
        workspace = self.get_workspace(request)
        if not workspace:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)

        target_path = self.get_safe_path(workspace, path)
        
        if not target_path or not target_path.exists():
            return Response({'error': 'File not found'}, status=status.HTTP_404_NOT_FOUND)
            
        try:
            if target_path.is_dir():
                shutil.rmtree(target_path)
            else:
                target_path.unlink()
            return Response({'success': True})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class FileRenameView(BaseWorkspaceView):
    def post(self, request):
        old_path = request.data.get('old_path', '')
        new_path = request.data.get('new_path', '')
        
        workspace = self.get_workspace(request)
        if not workspace:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)

        old_target = self.get_safe_path(workspace, old_path)
        new_target = self.get_safe_path(workspace, new_path)
        
        if not old_target or not old_target.exists():
            return Response({'error': 'Source not found'}, status=status.HTTP_404_NOT_FOUND)
        if not new_target:
            return Response({'error': 'Invalid destination'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            # Ensure parent exists
            new_target.parent.mkdir(parents=True, exist_ok=True)
            old_target.rename(new_target)
            return Response({'success': True})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ChatSessionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        try:
            workspace = Workspace.objects.get(user=request.user, workspace_id=project_id)
            sessions = ChatSession.objects.filter(project=workspace).order_by('-updated_at')
            serializer = ChatSessionSerializer(sessions, many=True)
            return Response(serializer.data)
        except Workspace.DoesNotExist:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, project_id):
        try:
            workspace = Workspace.objects.get(user=request.user, workspace_id=project_id)
            # Create a new session
            session = ChatSession.objects.create(project=workspace, title=request.data.get('title', 'New Chat'))
            serializer = ChatSessionSerializer(session)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Workspace.DoesNotExist:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)

class ChatSessionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, project_id, session_id):
        try:
            workspace = Workspace.objects.get(user=request.user, workspace_id=project_id)
            session = ChatSession.objects.get(id=session_id, project=workspace)
            session.delete()
            return Response({'status': 'deleted'}, status=status.HTTP_204_NO_CONTENT)
        except (Workspace.DoesNotExist, ChatSession.DoesNotExist):
            return Response({'error': 'Session or Project not found'}, status=status.HTTP_404_NOT_FOUND)

    def patch(self, request, project_id, session_id):
        try:
            workspace = Workspace.objects.get(user=request.user, workspace_id=project_id)
            session = ChatSession.objects.get(id=session_id, project=workspace)
            title = request.data.get('title')
            if title:
                session.title = title[:80]  # cap at 80 chars
                session.save(update_fields=['title'])
            serializer = ChatSessionSerializer(session)
            return Response(serializer.data)
        except (Workspace.DoesNotExist, ChatSession.DoesNotExist):
            return Response({'error': 'Session or Project not found'}, status=status.HTTP_404_NOT_FOUND)



class ChatMessageViewSet(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id, session_id):
        try:
            workspace = Workspace.objects.get(user=request.user, workspace_id=project_id)
            session = ChatSession.objects.get(id=session_id, project=workspace)
            messages = ChatMessage.objects.filter(session=session)
            serializer = ChatMessageSerializer(messages, many=True)
            return Response(serializer.data)
        except (Workspace.DoesNotExist, ChatSession.DoesNotExist) as e:
            return Response({'error': str(e)}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, project_id, session_id):
        try:
            workspace = Workspace.objects.get(user=request.user, workspace_id=project_id)
            session = ChatSession.objects.get(id=session_id, project=workspace)
            serializer = ChatMessageSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(session=session)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except (Workspace.DoesNotExist, ChatSession.DoesNotExist) as e:
            return Response({'error': str(e)}, status=status.HTTP_404_NOT_FOUND)

class ChatbotWidgetView(APIView):
    permission_classes = [] # Allow public access for the widget

    def post(self, request):
        user_message = request.data.get('message')
        if not user_message:
            return Response({'error': 'Message is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            llm = ChatGroq(
                model="qwen/qwen3-32b",
                temperature=0,
                max_tokens=None,
                reasoning_format="parsed",
                timeout=None,
                max_retries=2,
            )

            messages = [
                SystemMessage(content="You are the official support chatbot for Synthea, a collaborative AI-powered IDE. Provide helpful, concise information limited strictly to the Synthea product, its features (like AI coding agents, voice commands, file exploration), and website context. If asked about unrelated topics, politely redirect back to Synthea."),
                HumanMessage(content=user_message),
            ]

            ai_msg = llm.invoke(messages)
            response_text = ai_msg.content if hasattr(ai_msg, 'content') else str(ai_msg)
            return Response({'reply': response_text})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
