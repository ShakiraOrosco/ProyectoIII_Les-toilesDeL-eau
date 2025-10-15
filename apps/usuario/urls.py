from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import mi_perfil, lista_usuarios,crear_usuario,actualizar_usuario,eliminar_usuario


urlpatterns = [
    # Autenticación
    path('login/', TokenObtainPairView.as_view(), name='api-login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # este es para ver quien se ha logueado 
    path('mi-perfil/', mi_perfil, name='mi-perfil'),
    #CRUD de usuarios
    path('crear/', crear_usuario, name='crear_usuario'),
    path('', lista_usuarios, name='lista-usuarios'),
    path('<int:id_usuario>/update/', actualizar_usuario, name='actualizar-usuario'),
    path('<int:id_usuario>/delete/', eliminar_usuario, name='eliminar-usuario'),
]
