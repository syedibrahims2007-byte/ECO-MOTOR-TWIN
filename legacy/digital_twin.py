import pandas as pd

# Read dataset
df = pd.read_csv("data/motor_data.csv")

# Get latest reading of each motor
latest = df.groupby("Motor").last()

for motor, row in latest.iterrows():

    health = 100

    # Temperature penalty
    if row["Temperature_C"] > 50:
        health -= 20

    # Vibration penalty
    if row["Vibration_g"] > 0.15:
        health -= 30

    # Current penalty
    if row["Current_A"] > 18:
        health -= 20

    health = max(0, health)

    if health >= 80:
        status = "Healthy"
    elif health >= 60:
        status = "Warning"
    else:
        status = "Critical"

    print("\n------------------------")
    print("Motor:", motor)
    print("Health Index:", health)
    print("Status:", status)