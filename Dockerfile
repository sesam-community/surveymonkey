FROM python:3-alpine
LABEL maintainer="Egemen Yavuz <melih.egemen.yavuz@sysco.no>"
COPY ./service/*.py /service/
COPY ./service/requirements.txt /service/requirements.txt

RUN pip install --upgrade pip

RUN pip install -r /service/requirements.txt

EXPOSE 5000/tcp

CMD ["python3", "-u", "./service/proxy-service.py"]
