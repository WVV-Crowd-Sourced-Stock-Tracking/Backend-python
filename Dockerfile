FROM tiangolo/uvicorn-gunicorn-fastapi:python3.7

RUN pip3 install pipenv
COPY Pipfile* /tmp/
RUN cd /tmp && pipenv lock --requirements > requirements.txt
RUN pip3 install -r /tmp/requirements.txt

COPY ./src/app /app
