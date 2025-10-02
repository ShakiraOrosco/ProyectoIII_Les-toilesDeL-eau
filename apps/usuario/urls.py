from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
<<<<<<< HEAD
from .views import mi_perfil, lista_usuarios,crear_usuario,actualizar_usuario,eliminar_usuario


urlpatterns = [
    # Autenticación
    path('login/', TokenObtainPairView.as_view(), name='api-login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Endpoints personalizados
    path('mi-perfil/', mi_perfil, name='mi-perfil'),
    path('usuarios/crear/', crear_usuario, name='crear_usuario'),
    path('usuarios/', lista_usuarios, name='lista-usuarios'),
     path('usuarios/<int:id_usuario>/update/', actualizar_usuario, name='actualizar-usuario'),
    path('usuarios/<int:id_usuario>/delete/', eliminar_usuario, name='eliminar-usuario'),
 
]
=======
from . import views

urlpatterns = [
    path('login/', TokenObtainPairView.as_view(), name='api-login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
>>>>>>> origin/main
