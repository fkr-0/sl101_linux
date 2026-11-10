FROM python:3.12-slim-bookworm
ARG ANSIBLE_CORE_VERSION=2.19.5
ARG MOLECULE_VERSION=26.8.0
RUN apt-get update && apt-get install -y --no-install-recommends openssh-client ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir "ansible-core==${ANSIBLE_CORE_VERSION}" "molecule==${MOLECULE_VERSION}" \
 && useradd --uid 1000 --create-home --shell /bin/sh deploy
COPY entrypoint.sh /usr/local/bin/sl101-ansible-entrypoint
RUN chmod 0755 /usr/local/bin/sl101-ansible-entrypoint
USER deploy
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/sl101-ansible-entrypoint"]
CMD ["check"]
