from django.http import JsonResponse


# Create your views here.

def get_routes(request):
    routes = [
        {
            'endpoint': '',
            'method': '',
            'body': None,
            "description": ''
        }
    ]

    return JsonResponse(routes, safe=False)
