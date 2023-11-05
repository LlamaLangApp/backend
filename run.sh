#!/bin/sh

python manage.py migrate
python manage.py create_user user1 pass
python manage.py create_user user2 pass
python manage.py create_user user3 pass
python manage.py runserver 0.0.0.0:8000