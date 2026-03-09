from rest_framework import generics
from django.contrib.auth.models import User
from rest_framework.permissions import AllowAny
from .serializers import RegisterSerializer

from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from .serializers import RegisterSerializer, UserSerializer

@api_view(['GET'])
@permission_classes([AllowAny])
def api_health_check(request):
    return Response({"status": "online", "message": "Synthea API is running"})

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer

class ProfileView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def put(self, request):
        user = request.user
        data = request.data
        
        # Update username if provided
        if 'username' in data and data['username'].strip():
            user.username = data['username'].strip()
            
        # Update password if provided
        if 'password' in data and data['password'].strip():
            password = data['password'].strip()
            if len(password) < 8:
                return Response({'error': 'Password must be at least 8 characters long.'}, status=400)
            user.set_password(password)
            
        user.save()
        serializer = UserSerializer(user)
        return Response(serializer.data)

    def delete(self, request):
        user = request.user
        user.delete()
        return Response({'message': 'Account deleted successfully.'}, status=204)
