from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import mi_perfil, lista_usuarios,crear_usuario,actualizar_usuario,eliminar_usuario


urlpatterns = [
    # Autenticación
    path('login/', TokenObtainPairView.as_view(), name='api-login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # Endpoints personalizados
    path('mi-perfil/', mi_perfil, name='mi-perfil'),
    path('usuarios/crear/', crear_usuario, name='crear_usuario'),
    path('usuarios/', lista_usuarios, name='lista-usuarios'),
    path('usuarios/actualizar/<int:id_usuario>/', actualizar_usuario, name='actualizar_usuario'),
    path('usuarios/<int:id_usuario>/delete/', eliminar_usuario, name='eliminar-usuario'),
]
