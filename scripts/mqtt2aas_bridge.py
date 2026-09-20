# SPDX-License-Identifier: MIT
import json
import paho.mqtt.client as mqtt
import requests

# --- MQTT CONFIG -----------------------------------------------------

# Jeśli mosquitto działa na tym samym Macu:
MQTT_BROKER = "localhost"
MQTT_PORT = 1883

# Z Twojej konfiguracji symulatora:
MQTT_TOPIC = "spx/examples/env/telemetry/temperature_c"


# --- AAS CONFIG ------------------------------------------------------

AAS_BASE_URL = "http://192.168.0.172:8081"

# Base64( "urn:spx:envsensor:001:telemetry" )
SUBMODEL_ID_B64 = "dXJuOnNweDplbnZzZW5zb3I6MDAxOnRlbGVtZXRyeQ=="
PROPERTY_IDSHORT = "temperature_c"

UPDATE_URL = (
    f"{AAS_BASE_URL}/submodels/{SUBMODEL_ID_B64}"
    f"/submodel-elements/{PROPERTY_IDSHORT}"
)


def update_aas_temperature(value: float) -> None:
    """Wysyła PUT na SubmodelElement tak jak testowałeś curl-em."""
    body = {
        "modelType": "Property",
        "value": str(value),
        "valueType": "xs:double",
        "idShort": PROPERTY_IDSHORT,
    }

    try:
        resp = requests.put(
            UPDATE_URL,
            headers={"Content-Type": "application/json"},
            data=json.dumps(body),
            timeout=5,
        )
        if resp.status_code // 100 != 2:
            print("AAS update ERROR:", resp.status_code, resp.text)
        else:
            print(f"AAS updated OK -> temperature_c = {value}")
    except Exception as e:
        print("Error updating AAS:", e)


# --- MQTT CALLBACKS --------------------------------------------------


def on_connect(client, userdata, flags, reason_code, properties=None):
    print("MQTT connected with code:", reason_code)
    print("Subscribing to:", MQTT_TOPIC)
    client.subscribe(MQTT_TOPIC, qos=1)


def on_message(client, userdata, msg):
    raw = msg.payload.decode("utf-8", errors="ignore")
    print(f"MQTT {msg.topic}: {raw}")

    # Zakładamy, że payload to liczba, np. "23.5"
    try:
        value = float(raw)
    except ValueError:
        # fallback: gdyby kiedyś przyszedł JSON
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and "temperature_c" in data:
                value = float(data["temperature_c"])
            else:
                print("Nie umiem zinterpretować payloadu jako temperatury:", data)
                return
        except Exception as e:
            print("Nie udało się sparsować payloadu:", e)
            return

    update_aas_temperature(value)


# --- MAIN ------------------------------------------------------------


def main():
    client = mqtt.Client(
        client_id="mqtt2aas-bridge",
        protocol=mqtt.MQTTv5,  # jakby mosquitto marudził, zmień na mqtt.MQTTv311
    )
    client.on_connect = on_connect
    client.on_message = on_message

    print("Connecting to MQTT broker:", MQTT_BROKER, MQTT_PORT)
    client.connect(MQTT_BROKER, MQTT_PORT)
    client.loop_forever()


if __name__ == "__main__":
    main()
