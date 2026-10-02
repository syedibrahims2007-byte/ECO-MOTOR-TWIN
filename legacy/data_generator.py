import pandas as pd
import random
from datetime import datetime

motors = {
    "M1_Conveyor": {
        "voltage": 415,
        "current": 10,
        "temp": 40,
        "rpm": 1450,
        "vibration": 0.10,
        "production": 100
    },

    "M2_Pump": {
        "voltage": 415,
        "current": 8,
        "temp": 38,
        "rpm": 1450,
        "vibration": 0.08,
        "production": 90
    },

    "M3_Compressor": {
        "voltage": 415,
        "current": 12,
        "temp": 45,
        "rpm": 1450,
        "vibration": 0.12,
        "production": 120
    },

    "M4_ProcessMachine": {
        "voltage": 415,
        "current": 15,
        "temp": 42,
        "rpm": 1450,
        "vibration": 0.11,
        "production": 140
    }
}

data = []

for _ in range(1000):

    timestamp = datetime.now()

    for motor, base in motors.items():

        voltage = round(random.uniform(
            base["voltage"] - 10,
            base["voltage"] + 10
        ), 2)

        current = round(random.uniform(
            base["current"] - 1,
            base["current"] + 1
        ), 2)

        temp = round(random.uniform(
            base["temp"] - 2,
            base["temp"] + 2
        ), 2)

        # Simulated overheating fault
        if motor == "M2_Pump":
            temp += 20
        rpm = round(random.uniform(
            base["rpm"] - 20,
            base["rpm"] + 20
        ), 0)

        vibration = round(random.uniform(
            base["vibration"] - 0.02,
            base["vibration"] + 0.02
        ), 3)

        # Simulated bearing fault
        if motor == "M2_Pump":
            vibration += 0.10

        # Three-phase power approximation
        power = round(
            (1.732 * voltage * current * 0.85) / 1000,
            2
        )

        # Energy consumed in one hour equivalent
        energy = round(power * random.uniform(0.8, 1.2), 2)

        production = round(random.uniform(
            base["production"] - 10,
            base["production"] + 10
        ), 0)

        data.append([
            timestamp,
            motor,
            voltage,
            current,
            power,
            temp,
            rpm,
            vibration,
            energy,
            production
        ])

df = pd.DataFrame(
    data,
    columns=[
        "Timestamp",
        "Motor",
        "Voltage_V",
        "Current_A",
        "Power_kW",
        "Temperature_C",
        "RPM",
        "Vibration_g",
        "Energy_kWh",
        "Production_Output"
    ]
)

df.to_csv("data/motor_data.csv", index=False)

print("Dataset generated successfully!")
print("Rows:", len(df))