from django.core.management.base import BaseCommand

from api.models import Translation, WordSet

class Command(BaseCommand):
    def handle(self, **options):
        Translation.objects.all().delete()
        WordSet.objects.all().delete()

        Translation(polish="mleko", english="milk").save()
        Translation(polish="chleb", english="bread").save()
        Translation(polish="mięso", english="meat").save()
        Translation(polish="ryż", english="rice").save()
        Translation(polish="jabłko", english="apple").save()
        Translation(polish="banan", english="banana").save()

        translations = Translation.objects.all()
        
        food_set = WordSet(polish="żywność", english="food")
        food_set.save()
        food_set.words.set(translations)
        food_set.save()
        
        wordsets = WordSet.objects.all()

        print(translations)
        print(wordsets)


