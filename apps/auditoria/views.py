from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import Auditoria
from .serializers import AuditoriaSerializer



@api_view(['GET'])
@permission_classes([AllowAny])
def listar_auditorias(request):
    """
    Endpoint para listar auditorías.
    Retorna todas las auditorías ordenadas por fecha descendente,
    incluyendo el nombre del usuario si existe.
    """
    auditorias = Auditoria.objects.select_related('usuario').all()
    serializer = AuditoriaSerializer(auditorias, many=True)
    return Response(serializer.data)