from django.core.management.base import BaseCommand

from api.models import CustomUser


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("username", type=str)
        parser.add_argument("password", type=str)

    def handle(self, **options):
        CustomUser.objects.create_user(options['username'], password=options['password'])
