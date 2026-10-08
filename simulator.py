import random
import math
from datetime import datetime, timedelta

def random_location():
    lat = random.uniform(6.4, 6.6)
    lon = random.uniform(3.3, 3.5)
    return lat, lon

def interpolate_point(start, end, fraction):
    lat = start[0] + fraction * (end[0] - start[0])
    lon = start[1] + fraction * (end[1] - start[1])
    return lat, lon

def generate_gps_trace(pickup_time, trip_duration, cancel_delay, true_label):
    start_location = random_location()
    interval_seconds = 30
    gps_trace = []

    if true_label == 'genuine_cancel':
        parked_steps = (cancel_delay * 60) // interval_seconds
        for step in range(parked_steps + 1):
            lat = start_location[0] + random.uniform(-0.0002, 0.0002)
            lon = start_location[1] + random.uniform(-0.0002, 0.0002)
            timestamp = pickup_time + timedelta(seconds=step * interval_seconds)
            gps_trace.append({'time': timestamp, 'lat': lat, 'lon': lon})

        away_minutes = random.randint(3, 10)
        away_steps = (away_minutes * 60) // interval_seconds
        speed_kmh = random.uniform(15, 35)
        angle = random.uniform(0, 2 * math.pi)
        step_deg = (speed_kmh / 111) * (interval_seconds / 3600)
        for k in range(1, away_steps + 1):
            lat = start_location[0] + k * step_deg * math.sin(angle)
            lon = start_location[1] + k * step_deg * math.cos(angle)
            timestamp = pickup_time + timedelta(seconds=(parked_steps + k) * interval_seconds)
            gps_trace.append({'time': timestamp, 'lat': lat, 'lon': lon})
        return gps_trace

    is_fraud = true_label in ('fraud_cancel_naive', 'fraud_cancel_silent')
    parked_first = is_fraud and random.random() < 0.5

    drive_start = pickup_time
    drive_minutes = trip_duration
    if parked_first:
        parked_steps = (cancel_delay * 60) // interval_seconds
        for step in range(parked_steps):
            lat = start_location[0] + random.uniform(-0.0002, 0.0002)
            lon = start_location[1] + random.uniform(-0.0002, 0.0002)
            timestamp = pickup_time + timedelta(seconds=step * interval_seconds)
            gps_trace.append({'time': timestamp, 'lat': lat, 'lon': lon})
        drive_start = pickup_time + timedelta(minutes=cancel_delay)
        drive_minutes = trip_duration - cancel_delay

    speed_kmh = random.uniform(20, 40)
    distance_deg = (speed_kmh * (drive_minutes / 60)) / 111
    angle = random.uniform(0, 2 * math.pi)
    end_location = (
        start_location[0] + distance_deg * math.sin(angle),
        start_location[1] + distance_deg * math.cos(angle)
    )

    num_steps = (drive_minutes * 60) // interval_seconds
    for step in range(num_steps + 1):
        fraction = step / num_steps
        point = interpolate_point(start_location, end_location, fraction)
        timestamp = drive_start + timedelta(seconds=step * interval_seconds)
        gps_trace.append({'time': timestamp, 'lat': point[0], 'lon': point[1]})

    if true_label == 'fraud_cancel_silent':
        cancel_time = pickup_time + timedelta(minutes=cancel_delay)
        end_time = pickup_time + timedelta(minutes=trip_duration)
        back_on = end_time - timedelta(minutes=2)
        gps_trace = [p for p in gps_trace
                     if p['time'] <= cancel_time or p['time'] >= back_on]
    return gps_trace

def make_drivers(n_drivers=50, fraud_share=0.1, fraud_rate=0.25, varied_breaks=False):
    drivers = {}
    for driver_id in range(1, n_drivers + 1):
        break_rate = min(random.expovariate(1 / 0.08), 0.5) if varied_breaks else 0.08
        drivers[driver_id] = {'fraudster': False, 'style': None,
                              'fraud_rate': 0, 'break_rate': break_rate}

    n_fraud = max(2, round(n_drivers * fraud_share))
    fraud_ids = random.sample(range(1, n_drivers + 1), n_fraud)
    for i, driver_id in enumerate(fraud_ids):
        drivers[driver_id]['fraudster'] = True
        drivers[driver_id]['style'] = ['naive', 'silent'][i % 2]
        drivers[driver_id]['fraud_rate'] = fraud_rate
    return drivers

def generate_trip(trip_id, driver_id, profile, pickup_time):
    if profile['fraudster']:
        fr = profile['fraud_rate'] * 100
        labels = ['completed', 'genuine_cancel', 'fraud_cancel_' + profile['style']]
        weights = [90 - fr, 10, fr]
    else:
        labels = ['completed', 'genuine_cancel']
        weights = [90, 10]
    true_label = random.choices(labels, weights=weights, k=1)[0]

    trip_duration = random.randint(5, 40)

    if true_label == 'completed':
        status = 'completed'
        cancel_delay = None
        cancel_time = None
    else:
        status = 'cancelled'
        cancel_delay = random.randint(1, 15)
        cancel_time = pickup_time + timedelta(minutes=cancel_delay)
    if true_label in ('fraud_cancel_naive', 'fraud_cancel_silent'):
        trip_duration = random.randint(cancel_delay + 5, 40)

    if true_label == 'genuine_cancel':
        busy_until = cancel_time
    else:
        busy_until = pickup_time + timedelta(minutes=trip_duration)

    gps_trace = generate_gps_trace(pickup_time, trip_duration, cancel_delay, true_label)

    return {
        'trip_id': trip_id,
        'driver_id': driver_id,
        'status': status,
        '_true_label': true_label,
        'pickup_time': pickup_time,
        'cancel_time': cancel_time,
        'gps_trace': gps_trace,
        '_busy_until': busy_until
    }

def generate_dataset(n_drivers=50, n_days=2, fraud_rate=0.25, varied_breaks=False):
    drivers = make_drivers(n_drivers, fraud_rate=fraud_rate, varied_breaks=varied_breaks)
    trips = []
    trip_id = 1
    for driver_id in range(1, n_drivers + 1):
        profile = drivers[driver_id]
        for day in range(n_days):
            clock = datetime(2026, 1, 1 + day, 6, 0, 0) + timedelta(minutes=random.randint(0, 120))
            end_of_day = datetime(2026, 1, 1 + day, 22, 0, 0)
            while True:
                pickup_time = clock + timedelta(minutes=random.randint(2, 20))
                if pickup_time >= end_of_day:
                    break
                trip = generate_trip(trip_id, driver_id, profile, pickup_time)
                trips.append(trip)
                trip_id += 1
                clock = trip['_busy_until']
                if random.random() < profile['break_rate']:
                    clock = clock + timedelta(minutes=random.randint(20, 90))
    return trips