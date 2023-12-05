#!/bin/sh

python manage.py makemigrations
python manage.py migrate
python manage.py create_user user1 pass
python manage.py create_user user2 pass
python manage.py create_user user3 pass

if [ -z "${IS_DEV}" ]; then
    python manage.py collectstatic --no-input
fi

python manage.py runserver 0.0.0.0:8000