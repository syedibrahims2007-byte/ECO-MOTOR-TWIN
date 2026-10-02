import pandas as pd
from sklearn.ensemble import IsolationForest

# Load dataset
df = pd.read_csv("data/motor_data.csv")

# Features for AI
features = [
    "Voltage_V",
    "Current_A",
    "Power_kW",
    "Temperature_C",
    "RPM",
    "Vibration_g",
    "Energy_kWh",
    "Production_Output"
]

X = df[features]

# Train anomaly detector
model = IsolationForest(
    contamination=0.05,
    random_state=42
)

df["Anomaly"] = model.fit_predict(X)

# Convert output
df["Anomaly"] = df["Anomaly"].map({
    1: "Normal",
    -1: "Abnormal"
})

print(df[["Motor", "Anomaly"]].tail(20))