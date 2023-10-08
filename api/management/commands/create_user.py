from django.core.management.base import BaseCommand

from api.models import CustomUser


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("username", type=str)
        parser.add_argument("password", type=str)

    def handle(self, **options):
        if CustomUser.objects.filter(username=options["username"]).exists():
            print("Skipping creating user because it already exists")
            return
        CustomUser.objects.create_user(
            options["username"], password=options["password"]
        )
