FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive TZ=UTC
RUN apt-get update \
 && apt-get install -y --no-install-recommends openjdk-17-jdk-headless maven mysql-server-8.0 mysql-client-8.0 \
      python3 python3-pip curl ca-certificates procps \
 && rm -rf /var/lib/apt/lists/* \
 && pip3 install --no-cache-dir pymysql==1.1.1 pytest==8.3.3 \
 && mkdir -p /var/log/oms /logs/verifier && chmod 777 /var/log/oms
COPY devdb /opt/oms/dev
COPY app /app
WORKDIR /app
# Download every dependency and plugin once so the project builds offline (mvn -o).
RUN mvn -B -q package -DskipTests && rm -rf /app/*/target
CMD ["/bin/bash"]
