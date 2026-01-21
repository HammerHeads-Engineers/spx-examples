# DaliGatewayServer Docker Context

Ten katalog służy jako kontekst budowania obrazu `DaliGatewayServer`, aby można go było łatwo uruchamiać w `docker-compose`.

## Struktura

- `Dockerfile` – wieloetapowy build, który klonuje źródła z publicznego repozytorium i publikuje aplikację .NET.
- `data/` – domyślny wolumen na konfigurację i stan (zostanie podmontowany do `/data` w kontenerze).

## Budowanie obrazu

```bash
docker build \
  --build-arg DALIGATEWAY_REF=v1.9.0 \
  -t spx-examples/dali-gateway:latest \
  docker/dali-gateway
```

Argumenty builda:

- `DALIGATEWAY_REPO` – URL repozytorium (domyślnie upstream Henrika Andreasena).
- `DALIGATEWAY_REF` – gałąź, tag lub commit.
- `DALIGATEWAY_PROJECT` – ścieżka do projektu `.csproj`, gdyby struktura upstreamu się zmieniła.

## Uruchamianie

Gotowy obraz można włączyć w `docker-compose` przez sekcję `build` (lokalny build) albo przez wskazanie nazwy obrazu z registry. Kontener wymaga dostępu do interfejsu DALI (najczęściej `/dev/ttyUSB*`) oraz – opcjonalnie – do brokera MQTT.
