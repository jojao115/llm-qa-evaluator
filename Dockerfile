FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# Só as dependências do pyproject, numa camada própria: mudar o código não reinstala tudo.
# O código roda direto de /srv (sem instalar o pacote), para a pasta de rubricas montada
# pelo docker compose ser a mesma que a API lê.
COPY pyproject.toml ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" > /tmp/requisitos.txt \
 && pip install -r /tmp/requisitos.txt \
 && useradd --create-home --uid 10001 api

COPY app app
COPY evals evals
USER api

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/saude')"

CMD ["uvicorn", "app.main:criar_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
