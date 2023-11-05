FROM python:3.11.5-slim-bullseye

ENV PYTHONUNBUFFERED 1

WORKDIR /llamalang

COPY requirements.txt /llamalang/
RUN pip install -r requirements.txt

COPY . /llamalang/

CMD /bin/sh ./run.sh