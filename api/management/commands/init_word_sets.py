from django.core.management.base import BaseCommand

from api.models import Translation, WordSet


class Command(BaseCommand):
    def handle(self, **options):
        Translation.objects.all().delete()
        WordSet.objects.all().delete()

        food_set = WordSet(polish="żywność", english="food")
        food_set.save()
        food_set.words.create(polish="mleko", english="milk")
        food_set.words.create(polish="chleb", english="bread")
        food_set.words.create(polish="mięso", english="meat")
        food_set.words.create(polish="ryż", english="rice")
        food_set.words.create(polish="jabłko", english="apple")
        food_set.words.create(polish="banan", english="banana")
        food_set.words.create(polish="marchew", english="carrot")
        food_set.words.create(polish="pomidor", english="tomato")
        food_set.words.create(polish="ziemniak", english="potato")
        food_set.words.create(polish="papryka", english="pepper")
        food_set.words.create(polish="pomarańcza", english="orange")
        food_set.words.create(polish="winogrona", english="grapes")
        food_set.save()

        animal_set = WordSet(polish="zwierzęta", english="animals")
        animal_set.save()
        animal_set.words.create(polish="pies", english="dog")
        animal_set.words.create(polish="kot", english="cat")
        animal_set.words.create(polish="słoń", english="elephant")
        animal_set.words.create(polish="żyrafa", english="giraffe")
        animal_set.words.create(polish="tygrys", english="tiger")
        animal_set.words.create(polish="krokodyl", english="crocodile")
        animal_set.words.create(polish="wąż", english="snake")
        animal_set.words.create(polish="wieloryb", english="whale")
        animal_set.words.create(polish="pingwin", english="penguin")
        animal_set.words.create(polish="papuga", english="parrot")
        animal_set.words.create(polish="lis", english="fox")
        animal_set.words.create(polish="kaczka", english="duck")
        animal_set.save()

        family_set = WordSet(polish="rodzina", english="family")
        family_set.save()
        family_set.words.create(polish="ojciec", english="father")
        family_set.words.create(polish="matka", english="mother")
        family_set.words.create(polish="syn", english="son")
        family_set.words.create(polish="córka", english="daughter")
        family_set.words.create(polish="brat", english="brother")
        family_set.words.create(polish="siostra", english="sister")
        family_set.words.create(polish="dziadek", english="grandfather")
        family_set.words.create(polish="babcia", english="grandmother")
        family_set.words.create(polish="wujek", english="uncle")
        family_set.words.create(polish="ciocia", english="aunt")
        family_set.words.create(polish="kuzyn", english="cousin")
        family_set.words.create(polish="wnuk", english="grandson")
        family_set.save()

        vacation_set = WordSet(polish="wakacje", english="vacations")
        vacation_set.save()
        vacation_set.words.create(polish="plaża", english="beach")
        vacation_set.words.create(polish="morze", english="sea")
        vacation_set.words.create(polish="słońce", english="sun")
        vacation_set.words.create(polish="piasek", english="sand")
        vacation_set.words.create(polish="basen", english="swimming pool")
        vacation_set.words.create(polish="hotel", english="hotel")
        vacation_set.words.create(polish="wycieczka", english="excursion")
        vacation_set.words.create(polish="odpoczynek", english="rest")
        vacation_set.words.create(polish="spacer", english="walk")
        vacation_set.words.create(polish="podróż", english="journey")
        vacation_set.words.create(polish="zwiedzanie", english="sightseeing")
        vacation_set.words.create(polish="krajobraz", english="landscape")
        vacation_set.save()

        wordsets = WordSet.objects.all()
        translations = Translation.objects.all()

        print(translations)
        print(wordsets)
