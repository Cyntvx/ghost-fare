import pandas as pd
from scipy.stats import binom

def distance_km(p1, p2):
    d_lat = (p2['lat'] - p1['lat']) * 111
    d_lon = (p2['lon'] - p1['lon']) * 111
    return (d_lat ** 2 + d_lon ** 2) ** 0.5

def speed_before_cancel(row):
    if pd.isna(row['cancel_time']):
        return None
    start = row['cancel_time'] - pd.Timedelta(minutes=1)
    window = [p for p in row['gps_trace'] if start <= p['time'] <= row['cancel_time']]
    if len(window) < 2:
        return None
    hours = (window[-1]['time'] - window[0]['time']).total_seconds() / 3600
    return distance_km(window[0], window[-1]) / hours

def run_detection(df, speed_limit=5, idle_limit=20):
    df = df.sort_values(['driver_id', 'pickup_time']).reset_index(drop=True)
    df['next_pickup'] = df.groupby('driver_id')['pickup_time'].shift(-1)
    df['idle_after_cancel'] = (df['next_pickup'] - df['cancel_time']).dt.total_seconds() / 60
    same_day = df['next_pickup'].dt.date == df['pickup_time'].dt.date
    df.loc[~same_day, 'idle_after_cancel'] = None
    df['speed_before_cancel'] = df.apply(speed_before_cancel, axis=1)
    df['trip_end'] = df['gps_trace'].apply(lambda trace: trace[-1]['time'])
    df['idle_after_trip'] = (df['next_pickup'] - df['trip_end']).dt.total_seconds() / 60
    df.loc[~same_day, 'idle_after_trip'] = None

    cancelled = df[df['status'] == 'cancelled'].copy()
    cancelled['flag_any'] = ((cancelled['speed_before_cancel'] > speed_limit) |
    (cancelled['idle_after_cancel'] > idle_limit))
    cancelled['is_fraud'] = cancelled['_true_label'].str.startswith('fraud')

    by_driver = cancelled.groupby('driver_id').agg(
        cancels=('trip_id', 'count'),
        flags=('flag_any', 'sum'),
        frauds=('is_fraud', 'sum')
    )
    alpha = 0.05 / len(by_driver)
    p0 = by_driver['flags'].sum() / by_driver['cancels'].sum()
    for _ in range(10):
        p_value = binom.sf(by_driver['flags'] - 1, by_driver['cancels'], p0)
        flagged = p_value < alpha
        rest = by_driver[~flagged]
        new_p0 = max(rest['flags'].sum() / rest['cancels'].sum(), 0.01)
        if abs(new_p0 - p0) < 0.0001:
            break
        p0 = new_p0

    by_driver['p_value'] = binom.sf(by_driver['flags'] - 1, by_driver['cancels'], p0)
    by_driver['flagged_driver'] = by_driver['p_value'] < alpha
    by_driver['is_fraudster'] = by_driver['frauds'] > 0
    done = df[(df['status'] == 'completed') & df['idle_after_trip'].notna()].copy()
    done['long_idle'] = done['idle_after_trip'] > idle_limit
    own = done.groupby('driver_id')['long_idle'].agg(['sum', 'count'])
    own_rate = (own['sum'] + 1) / (own['count'] + 2)
    by_driver['own_rate'] = own_rate.reindex(by_driver.index).fillna(p0)
    by_driver['p_value_within'] = binom.sf(by_driver['flags'] - 1, by_driver['cancels'], by_driver['own_rate'])
    by_driver['flagged_within'] = by_driver['p_value_within'] < alpha
    return by_driver