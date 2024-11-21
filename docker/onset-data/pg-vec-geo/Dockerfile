FROM postgres:17-bullseye
RUN echo "Acquire::http::Pipeline-Depth 0;" > /etc/apt/apt.conf.d/99custom && \
    echo "Acquire::http::No-Cache true;" >> /etc/apt/apt.conf.d/99custom && \
    echo "Acquire::BrokenProxy    true;" >> /etc/apt/apt.conf.d/99custom
# Docker on mac breaks apt installs sometimes, rlly annoying - some hotfixes
RUN apt-get update \
      && apt-get -o Acquire::ForceIPv4=true install -y --no-install-recommends \
           postgresql-17-pgvector \
           postgresql-17-postgis \
      && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /docker-entrypoint-initdb.d
COPY ./initdb-postgis.sh /docker-entrypoint-initdb.d/10_postgis.sh