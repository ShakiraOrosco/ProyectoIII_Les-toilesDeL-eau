from django.urls import path
from . import views

urlpatterns = [
    path('auditoria/', views.listar_auditorias, name='listar_auditorias'),
]