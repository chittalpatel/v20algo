# V20algo

## Setup

```shell
python3 -m venv venv
source venv/bin/activate   # (Linux/macOS)
# OR
venv\Scripts\activate      # (Windows)

# Then install
pip install -r requirements.txt
```

## Run

### Sync market data
```shell
python sync_data.py
```
It will update/download 1D OHCLV stock price data for the stocks in `stocks` file of last 5 years.

### Run webserver locally
```shell
python app.py
```
Starts and runs the webserver locally that will use the downloaded data to run the V20 algorithm. Make sure you've downloaded the market data first.