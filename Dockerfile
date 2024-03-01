FROM python:3.13.0a4-slim

LABEL maintainer David Mc Ken ()

WORKDIR /app

COPY ./requirements.txt requirements.txt

RUN pip install -r requirements.txt

COPY ./__main__.py __main__.py

CMD [ "python", "__main__.py" ]
