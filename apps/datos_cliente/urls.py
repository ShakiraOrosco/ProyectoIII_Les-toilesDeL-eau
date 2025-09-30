from django.urls import path
from .views import home_view

urlpatterns = [
    path('prueba/', home_view, name='home'),
    # aquí otras rutas de clientes si quieres
]