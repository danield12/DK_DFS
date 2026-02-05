import openmeteo_requests
import requests_cache
import pandas as pd
import numpy as np
from retry_requests import retry
from datetime import datetime, timedelta
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import r2_score
import scipy.stats

# Setup Open-Meteo API client with cache and retry
cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)

# Constants
LAT = 40.78
LON = -73.97
TIMEZONE = "America/New_York"
TEMP_UNIT = "fahrenheit"

def fetch_historical_data():
    """
    Fetches 5 years of historical observed and model data.
    """
    # Define Date Range
    end_date = datetime.now() - timedelta(days=1)
    start_date = end_date - timedelta(days=365*5)

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    print(f"Fetching Historical Data from {start_str} to {end_str}...")

    # 1. Fetch Observed Data (Reanalysis)
    url_archive = "https://archive-api.open-meteo.com/v1/archive"
    params_archive = {
        "latitude": LAT,
        "longitude": LON,
        "start_date": start_str,
        "end_date": end_str,
        "daily": "temperature_2m_max",
        "timezone": TIMEZONE,
        "temperature_unit": TEMP_UNIT
    }

    responses_archive = openmeteo.weather_api(url_archive, params=params_archive)
    resp_archive = responses_archive[0]

    daily_archive = resp_archive.Daily()

    # Correct Date extraction
    ts_start = daily_archive.Time()
    ts_end = daily_archive.TimeEnd()
    interval = daily_archive.Interval()

    observed_values = daily_archive.Variables(0).ValuesAsNumpy()

    # Create DataFrame
    obs_df = pd.DataFrame({
        "date": pd.to_datetime(range(ts_start, ts_end, interval), unit="s", utc=True).tz_convert(TIMEZONE).floor('D'),
        "observed_temp": observed_values
    })

    # 2. Fetch Historical Model Data (Hindcast/Forecast)
    url_hist = "https://historical-forecast-api.open-meteo.com/v1/forecast"
    params_hist = {
        "latitude": LAT,
        "longitude": LON,
        "start_date": start_str,
        "end_date": end_str,
        "daily": "temperature_2m_max",
        "models": "gfs_seamless",
        "timezone": TIMEZONE,
        "temperature_unit": TEMP_UNIT
    }

    responses_hist = openmeteo.weather_api(url_hist, params=params_hist)
    resp_hist = responses_hist[0]
    daily_hist = resp_hist.Daily()
    model_values = daily_hist.Variables(0).ValuesAsNumpy()

    ts_start_h = daily_hist.Time()
    ts_end_h = daily_hist.TimeEnd()
    interval_h = daily_hist.Interval()

    hist_df = pd.DataFrame({
        "date": pd.to_datetime(range(ts_start_h, ts_end_h, interval_h), unit="s", utc=True).tz_convert(TIMEZONE).floor('D'),
        "model_temp": model_values
    })

    # Merge
    merged_df = pd.merge(obs_df, hist_df, on="date", how="inner")

    # Drop NaNs
    merged_df.dropna(inplace=True)

    return merged_df

def fetch_live_ensemble():
    """
    Fetches live ensemble forecast for Today and Tomorrow.
    """
    print("Fetching Live Ensemble Forecast...")
    url_ensemble = "https://ensemble-api.open-meteo.com/v1/ensemble"

    # forecast_days=2
    params_ensemble = {
        "latitude": LAT,
        "longitude": LON,
        "daily": "temperature_2m_max", # Returns all members
        "timezone": TIMEZONE,
        "temperature_unit": TEMP_UNIT,
        "forecast_days": 2,
        "models": "gfs_seamless"
    }

    responses = openmeteo.weather_api(url_ensemble, params=params_ensemble)
    response = responses[0]

    daily = response.Daily()
    num_vars = daily.VariablesLength()

    # Process members
    members_data = {}

    ts_start = daily.Time()
    ts_end = daily.TimeEnd()
    interval = daily.Interval()

    dates = pd.to_datetime(range(ts_start, ts_end, interval), unit="s", utc=True).tz_convert(TIMEZONE).floor('D')

    for i in range(num_vars):
        vals = daily.Variables(i).ValuesAsNumpy()
        members_data[f"member_{i}"] = vals

    ensemble_df = pd.DataFrame(members_data)
    ensemble_df["date"] = dates

    return ensemble_df

def train_and_select_model(df):
    """
    Trains LinearRegression, RandomForest, and GradientBoosting models.
    Returns the best model based on R2 score.
    """
    print("Training models...")

    # Feature Engineering
    df = df.copy()
    df["doy"] = df["date"].dt.dayofyear

    X = df[["model_temp", "doy"]]
    y = df["observed_temp"]

    # Train Models
    models = {
        "LinearRegression": LinearRegression(),
        "RandomForest": RandomForestRegressor(n_estimators=100, random_state=42),
        "GradientBoosting": GradientBoostingRegressor(n_estimators=100, random_state=42)
    }

    best_score = -np.inf
    best_model = None
    best_name = ""

    print(f"{'Model':<20} | {'R2 Score':<10}")
    print("-" * 35)

    for name, model in models.items():
        # Split
        split_idx = int(len(df) * 0.8)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

        model.fit(X_train, y_train)
        score = r2_score(y_test, model.predict(X_test))

        print(f"{name:<20} | {score:.4f}")

        if score > best_score:
            best_score = score
            best_model = model
            best_name = name

    print("-" * 35)
    print(f"Best Model: {best_name} (R2: {best_score:.4f})")

    # Retrain best model on full dataset
    best_model.fit(X, y)

    return best_model

def generate_forecast_output(best_model, df_live):
    """
    Applies correction to live ensemble and prints probability distribution.
    """
    print("\nGenerating Forecast Probabilities...")

    # Process each row (Day)
    for idx, row in df_live.iterrows():
        date_str = row["date"].strftime("%Y-%m-%d")
        doy = row["date"].dayofyear

        # Extract member values
        member_cols = [c for c in df_live.columns if c.startswith("member_")]
        raw_values = row[member_cols].values.astype(float)

        # Prepare Features for Prediction
        # We need a DataFrame with columns "model_temp" and "doy" matching training
        X_pred = pd.DataFrame({
            "model_temp": raw_values,
            "doy": [doy] * len(raw_values)
        })

        # Predict (Correct)
        corrected_values = best_model.predict(X_pred)

        # Round to integer
        corrected_ints = np.round(corrected_values).astype(int)

        # Calculate Distribution
        unique, counts = np.unique(corrected_ints, return_counts=True)
        total = len(corrected_ints)

        probs = []
        for val, count in zip(unique, counts):
            pct = (count / total) * 100
            if pct >= 1.0: # Exclude < 1%
                probs.append((val, pct))

        # Sort by temperature
        probs.sort(key=lambda x: x[0])

        # Determine label (Today vs Tomorrow)
        # We need current time in NY to determine "Today"
        now_ny = pd.Timestamp.now(tz=TIMEZONE)
        today_str = now_ny.strftime("%Y-%m-%d")
        tomorrow_str = (now_ny + timedelta(days=1)).strftime("%Y-%m-%d")

        if date_str == today_str:
            label = "Today"
        elif date_str == tomorrow_str:
            label = "Tomorrow"
        else:
            label = date_str

        print(f"\nForecast for {label} ({date_str}):")
        print(f"{'Temp (°F)':<10} | {'Probability':<15}")
        print("-" * 25)
        for temp, pct in probs:
            print(f"{temp:<10} | {pct:.1f}%")

if __name__ == "__main__":
    df_hist = fetch_historical_data()
    df_live = fetch_live_ensemble()
    best_model = train_and_select_model(df_hist)
    generate_forecast_output(best_model, df_live)
