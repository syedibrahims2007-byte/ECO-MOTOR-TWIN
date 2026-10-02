# Assumptions

1. **No real hardware** – Modbus/MQTT sources are stubs; the simulator is the default data source.
2. **Training data** – 7 days at 1 sample/minute (10,080 samples per motor) is sufficient for baseline learning.
3. **Fault windows** – Injected at fixed fractions of the simulation duration for reproducibility.
4. **Process coupling** – Linear coupling factors in config; real systems would need system identification.
5. **Health index weights** – Equal weighting of anomaly score, residuals, and trend; tunable in config.
6. **SEC baseline** – Learned from normal-operation data using rolling median.
7. **No authentication** – API is open on localhost; production deployment would need auth.
8. **SQLite** – Sufficient for single-node deployment; TimescaleDB/InfluxDB for scale.
9. **Git not available** – Git was not installed on the system; version control can be initialized later.
10. **Python 3.12 / Node 24** – Installed via winget; versions pinned in requirements.txt / package.json.
