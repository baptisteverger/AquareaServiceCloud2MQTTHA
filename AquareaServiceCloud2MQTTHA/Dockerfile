ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python dependencies
RUN apk add --no-cache python3 py3-pip

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

# Copy Python source
COPY *.py .
COPY translation.json .

# Copy startup script
COPY run.sh /
RUN chmod +x /run.sh

CMD ["/run.sh"]
