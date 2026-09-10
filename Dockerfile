FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus-multiproc

RUN mkdir -p /tmp/prometheus-multiproc

WORKDIR /code

COPY . /code/
RUN pip install .

EXPOSE 8012
