from django.shortcuts import render

# Create your views here.
from rest_framework import viewsets
from .models import ReservaGen
from .serializers import ReservaGenSerializer

class ReservaGenViewSet(viewsets.ModelViewSet):
    queryset = ReservaGen.objects.all()
    serializer_class = ReservaGenSerializer
