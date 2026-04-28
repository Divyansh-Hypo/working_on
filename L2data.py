import os
import requests
import zipfile
import polars as pl
import calendar

# 1. Setup
year = 2024
symbol = "BTCUSDT"
save_path = "H:\\peakVault\\bookticker\\"
temp_path = "H:\\peakVault\\temp\\"  # Safe temp folder for extraction

os.makedirs(save_path, exist_ok=True)
os.makedirs(temp_path, exist_ok=True)

# Disguise our Python script as a normal Google Chrome browser to bypass Binance blocks
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def download_and_convert(url, file_name):
    """Downloads a ZIP, extracts it, converts to Parquet, and cleans up."""
    parquet_output = os.path.join(save_path, f"{file_name}.parquet")
    
    if os.path.exists(parquet_output):
        print(f"    [SKIP] Already exists: {file_name}.parquet")
        return True

    try:
        response = requests.get(url, headers=HEADERS, stream=True)
        if response.status_code == 200:
            zip_filepath = os.path.join(temp_path, f"{file_name}.zip")
            
            # Save ZIP safely to disk
            with open(zip_filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Extract CSV
            with zipfile.ZipFile(zip_filepath, 'r') as z:
                csv_filename = z.namelist()[0]
                z.extract(csv_filename, temp_path)
            
            extracted_csv_path = os.path.join(temp_path, csv_filename)
            
            # Convert to Parquet using Polars
            df = pl.read_csv(extracted_csv_path, has_header=False)
            df.columns = ["update_id", "event_time", "transaction_time", "symbol", "bid_p", "bid_q", "ask_p", "ask_q"]
            df.write_parquet(parquet_output)
            
            # Cleanup temp files
            os.remove(zip_filepath)
            os.remove(extracted_csv_path)
            
            print(f"    [SUCCESS] Saved {file_name}.parquet")
            return True
        else:
            return False
            
    except Exception as e:
        print(f"    [ERROR] Failed on {file_name}: {e}")
        return False

# 2. The Bulletproof Loop
print(f"[*] Starting Bulletproof BookTicker Download for {year}...")

# You left off at month 4 (April)
for month in range(4, 13):
    month_str = f"{month:02d}"
    monthly_file = f"{symbol}-bookTicker-{year}-{month_str}"
    monthly_url = f"https://data.binance.vision/data/futures/um/monthly/bookTicker/{symbol}/{monthly_file}.zip"
    
    print(f"\n[+] Trying MONTHLY data for {year}-{month_str}...")
    success = download_and_convert(monthly_url, monthly_file)
    
    # If Monthly fails, fallback to Daily for that specific month
    if not success:
        print(f"    [404] Monthly file not found. Falling back to DAILY data for {year}-{month_str}...")
        
        # Get number of days in this month
        _, num_days = calendar.monthrange(year, month)
        
        for day in range(1, num_days + 1):
            day_str = f"{day:02d}"
            daily_file = f"{symbol}-bookTicker-{year}-{month_str}-{day_str}"
            daily_url = f"https://data.binance.vision/data/futures/um/daily/bookTicker/{symbol}/{daily_file}.zip"
            
            print(f"    [>] Fetching {daily_file}...")
            daily_success = download_and_convert(daily_url, daily_file)
            
            if not daily_success:
                print(f"        [404] Daily data for {year}-{month_str}-{day_str} is also missing on Binance.")

print("\nMISSION COMPLETE. NO MORE TIME WASTING. HAVE A GREAT WORKOUT, BROTHER! 💪")
