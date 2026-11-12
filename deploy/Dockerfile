# Vehicle workloads (simulator, detector, publisher); Ankaios picks the role via commandArgs.
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY contracts ./contracts
COPY config ./config
RUN pip install --no-cache-dir ".[real]"
ENTRYPOINT ["python", "-m", "fleet.vehicle"]
