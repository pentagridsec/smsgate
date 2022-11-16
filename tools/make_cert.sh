#!/bin/sh
HOSTNAME=localhost
openssl req -x509 -newkey rsa:4096 -sha256 -days 3650 -nodes \
  -keyout conf/key.pem -out conf/cert.pem -subj "/CN=${HOSTNAME}" \
  -addext "subjectAltName=DNS:${HOSTNAME}"

