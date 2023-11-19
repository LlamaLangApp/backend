FROM python:3.11.5-slim-bullseye

ENV PYTHONUNBUFFERED 1

WORKDIR /llamalang

COPY requirements.txt /llamalang/
RUN pip install -r requirements.txt

COPY . /llamalang/

# if run.sh wont work
#CMD python manage.py migrate && \
#    python manage.py create_user user1 pass && \
#    python manage.py create_user user2 pass && \
#    python manage.py create_user user3 pass && \
#    python manage.py runserver 0.0.0.0:8000

CMD /bin/sh ./run.sh