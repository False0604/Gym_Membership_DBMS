"""
Gym DBMS live demo  <->  MongoDB bridge.

Run:  python database/gym_server.py
Then open http://127.0.0.1:8770/  (or open the HTML file directly; it finds this server).

Creates the gym_db database (14 collections, validators, unique indexes, sample data)
on first start, and saves every COMMIT from the demo into MongoDB. View it in MongoDB
Compass at mongodb://localhost:27017 -> gym_db.
"""
import calendar
import json
import os
import webbrowser
from datetime import date, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from pymongo import ASCENDING, MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError, WriteError

MONGO_URI = os.environ.get('GYM_MONGO_URI', 'mongodb://127.0.0.1:27017')
DB_NAME = 'gym_db'
PORT = 8770
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # the PBL folder
DEMO_PAGE = 'Gym DBMS Live Demo.html'

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=4000)
db = client[DB_NAME]

# demo table key -> (collection, primary key)
TABLES = {
    'member': ('member', 'member_id'),
    'plan': ('plan', 'plan_id'),
    'subscription': ('subscription', 'subscription_id'),
    'payment': ('payment', 'payment_id'),
    'renewal': ('renewal', 'renewal_id'),
    'trainer': ('trainer', 'trainer_id'),
    'assessment': ('assessment', 'assessment_id'),
    'workout': ('workout_programme', 'programme_id'),
    'class': ('class', 'class_id'),
    'schedule': ('schedule', 'schedule_id'),
    'registration': ('registration', 'registration_id'),
    'attendance': ('attendance', 'attendance_id'),
    'equipment': ('equipment', 'equipment_id'),
    'maintenance': ('maintenance', 'maintenance_id'),
}
# foreign keys: column -> parent table
FKS = {
    'subscription': {'member_id': 'member', 'plan_id': 'plan'},
    'payment': {'subscription_id': 'subscription'},
    'renewal': {'subscription_id': 'subscription'},
    'assessment': {'member_id': 'member', 'trainer_id': 'trainer'},
    'workout': {'member_id': 'member'},
    'class': {'trainer_id': 'trainer'},
    'schedule': {'class_id': 'class'},
    'registration': {'member_id': 'member', 'schedule_id': 'schedule'},
    'attendance': {'registration_id': 'registration'},
    'maintenance': {'equipment_id': 'equipment'},
}

NUM = {'bsonType': ['int', 'long', 'double', 'decimal']}
STR = {'bsonType': 'string'}
DATE = {'bsonType': 'string', 'pattern': r'^\d{4}-\d{2}-\d{2}$'}
DATETIME = {'bsonType': 'string', 'pattern': r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$'}


def schema(required, props, expr=None):
    v = {'$jsonSchema': {'bsonType': 'object', 'required': required, 'properties': props}}
    if expr:
        v = {'$and': [v, {'$expr': expr}]}
    return v


# NOT NULL, types, ENUMs and CHECK constraints as collection validators
VALIDATORS = {
    'member': schema(['member_id', 'name', 'phone', 'email', 'join_date'], {
        'member_id': NUM, 'name': {**STR, 'maxLength': 80}, 'phone': {**STR, 'maxLength': 10},
        'email': {**STR, 'maxLength': 120}, 'dob': {'bsonType': ['string', 'null']}, 'join_date': DATE}),
    'plan': schema(['plan_id', 'name', 'duration_months', 'price'], {
        'plan_id': NUM, 'name': STR, 'duration_months': {**NUM, 'minimum': 1}, 'price': {**NUM, 'minimum': 0}}),
    'subscription': schema(['subscription_id', 'member_id', 'plan_id', 'start_date', 'end_date', 'status'], {
        'subscription_id': NUM, 'member_id': NUM, 'plan_id': NUM, 'start_date': DATE, 'end_date': DATE,
        'status': {'enum': ['ACTIVE', 'EXPIRED', 'CANCELLED']}},
        {'$gt': ['$end_date', '$start_date']}),                                   # chk_dates
    'payment': schema(['payment_id', 'subscription_id', 'amount', 'method', 'paid_on'], {
        'payment_id': NUM, 'subscription_id': NUM, 'amount': {**NUM, 'minimum': 0},  # chk_amount
        'method': {'enum': ['CASH', 'CARD', 'UPI']}, 'paid_on': DATE}),
    'renewal': schema(['renewal_id', 'subscription_id', 'renewed_on', 'new_end_date'], {
        'renewal_id': NUM, 'subscription_id': NUM, 'renewed_on': DATE, 'new_end_date': DATE}),
    'trainer': schema(['trainer_id', 'name', 'shift', 'phone'], {
        'trainer_id': NUM, 'name': STR, 'shift': {'enum': ['MORNING', 'EVENING']}, 'phone': {**STR, 'maxLength': 10}}),
    'assessment': schema(['assessment_id', 'member_id', 'trainer_id', 'date'], {
        'assessment_id': NUM, 'member_id': NUM, 'trainer_id': NUM, 'date': DATE,
        'weight': {**NUM, 'minimum': 0}, 'bmi': {**NUM, 'minimum': 0}, 'body_fat': {**NUM, 'minimum': 0}}),
    'workout_programme': schema(['programme_id', 'member_id', 'title', 'weeks'], {
        'programme_id': NUM, 'member_id': NUM, 'title': STR, 'weeks': {**NUM, 'minimum': 1}}),
    'class': schema(['class_id', 'trainer_id', 'title', 'capacity'], {
        'class_id': NUM, 'trainer_id': NUM, 'title': STR, 'capacity': {**NUM, 'minimum': 1}}),
    'schedule': schema(['schedule_id', 'class_id', 'day', 'start_time', 'end_time'], {
        'schedule_id': NUM, 'class_id': NUM, 'day': {'enum': ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']},
        'start_time': STR, 'end_time': STR},
        {'$gt': ['$end_time', '$start_time']}),
    'registration': schema(['registration_id', 'member_id', 'schedule_id', 'booking_date', 'status'], {
        'registration_id': NUM, 'member_id': NUM, 'schedule_id': NUM, 'booking_date': DATE,
        'status': {'enum': ['BOOKED', 'ATTENDED', 'CANCELLED']}}),
    'attendance': schema(['attendance_id', 'registration_id', 'check_in'], {
        'attendance_id': NUM, 'registration_id': NUM, 'check_in': DATETIME,
        'check_out': {'bsonType': ['string', 'null']}},
        {'$or': [{'$eq': [{'$ifNull': ['$check_out', None]}, None]}, {'$gt': ['$check_out', '$check_in']}]}),  # chk_checkout
    'equipment': schema(['equipment_id', 'name', 'status'], {
        'equipment_id': NUM, 'name': STR, 'status': {'enum': ['ACTIVE', 'OUT_OF_SERVICE', 'RETIRED']}}),
    'maintenance': schema(['maintenance_id', 'equipment_id', 'date', 'cost'], {
        'maintenance_id': NUM, 'equipment_id': NUM, 'date': DATE, 'cost': {**NUM, 'minimum': 0}}),
}

# UNIQUE constraints as unique indexes (the primary key is also stored as _id)
UNIQUE = {
    'member': [[('email', 1)], [('phone', 1)]],
    'plan': [[('name', 1)]],
    'trainer': [[('phone', 1)]],
    'registration': [[('schedule_id', 1), ('member_id', 1)]],   # uq_sched_member
    'attendance': [[('registration_id', 1)]],                   # 1:1 with Registration
}
INDEXES = {'member': [('name', 1)], 'subscription': [('end_date', 1)], 'payment': [('paid_on', 1)]}


# ---------- sample data: same rows as the demo page ----------
def day(n):
    return (date.today() + timedelta(days=n)).isoformat()


def add_months(s, n):
    y, m, d = map(int, s.split('-'))
    m0 = m - 1 + n
    y, m = y + m0 // 12, m0 % 12 + 1
    return (date(y, m, 1) + timedelta(days=d - 1)).isoformat()   # overflows like JS Date


def seed_rows():
    months = {1: 1, 2: 3, 3: 12, 4: 1}

    def sub(i, m, p, start, status):
        return {'subscription_id': i, 'member_id': m, 'plan_id': p, 'start_date': start,
                'end_date': add_months(start, months[p]), 'status': status}

    def at(n, t):
        return f'{day(n)} {t}:00'

    return {
        'member': [
            {'member_id': 41, 'name': 'Priya Naidu', 'phone': '9845012345', 'email': 'priya.naidu@example.com', 'dob': '1998-07-21', 'join_date': day(-340)},
            {'member_id': 42, 'name': 'Prithvi Rao', 'phone': '9900123456', 'email': 'prithvi.rao@example.com', 'dob': '1995-02-11', 'join_date': day(-264)},
            {'member_id': 43, 'name': 'Pritha Sen', 'phone': '9831045678', 'email': 'pritha.sen@example.com', 'dob': '2000-09-30', 'join_date': day(-577)},
            {'member_id': 44, 'name': 'Prithika M.', 'phone': '9789012345', 'email': 'prithika.m@example.com', 'dob': '2002-12-05', 'join_date': day(-170)},
            {'member_id': 45, 'name': 'Arjun Mehta', 'phone': '9820098765', 'email': 'arjun.mehta@example.com', 'dob': '1993-06-14', 'join_date': day(-127)},
            {'member_id': 46, 'name': 'Kavya Iyer', 'phone': '9741234560', 'email': 'kavya.iyer@example.com', 'dob': '1999-04-02', 'join_date': day(-76)},
            {'member_id': 47, 'name': 'Rohan Kulkarni', 'phone': '9860011223', 'email': 'rohan.k@example.com', 'dob': '1997-10-18', 'join_date': day(-37)},
            {'member_id': 48, 'name': 'Sneha Reddy', 'phone': '9701122334', 'email': 'sneha.reddy@example.com', 'dob': '2001-01-27', 'join_date': day(-24)},
        ],
        'plan': [
            {'plan_id': 1, 'name': 'Monthly', 'duration_months': 1, 'price': 1500, 'features': 'Gym floor'},
            {'plan_id': 2, 'name': 'Quarterly', 'duration_months': 3, 'price': 4000, 'features': 'Gym floor + 4 classes a month'},
            {'plan_id': 3, 'name': 'Annual', 'duration_months': 12, 'price': 14000, 'features': 'All access'},
            {'plan_id': 4, 'name': 'Trial', 'duration_months': 1, 'price': 0, 'features': 'Weekday gym floor'},
        ],
        'subscription': [
            sub(46, 47, 4, day(-37), 'EXPIRED'), sub(47, 43, 1, day(-577), 'EXPIRED'), sub(48, 41, 3, day(-340), 'ACTIVE'),
            sub(49, 42, 2, day(-52), 'ACTIVE'), sub(50, 44, 1, day(-17), 'ACTIVE'), sub(51, 45, 2, day(-35), 'ACTIVE'),
            sub(52, 46, 1, day(-26), 'ACTIVE'),
        ],
        'payment': [
            {'payment_id': 50, 'subscription_id': 48, 'amount': 14000, 'method': 'CARD', 'paid_on': day(-340)},
            {'payment_id': 51, 'subscription_id': 49, 'amount': 4000, 'method': 'UPI', 'paid_on': day(-52)},
            {'payment_id': 52, 'subscription_id': 50, 'amount': 1500, 'method': 'CASH', 'paid_on': day(-17)},
            {'payment_id': 53, 'subscription_id': 51, 'amount': 4000, 'method': 'UPI', 'paid_on': day(-35)},
            {'payment_id': 54, 'subscription_id': 52, 'amount': 1500, 'method': 'UPI', 'paid_on': day(-26)},
        ],
        'renewal': [
            {'renewal_id': 7, 'subscription_id': 47, 'renewed_on': day(-142), 'new_end_date': day(-51)},
            {'renewal_id': 8, 'subscription_id': 48, 'renewed_on': day(-96), 'new_end_date': day(-5)},
            {'renewal_id': 9, 'subscription_id': 50, 'renewed_on': day(-61), 'new_end_date': day(30)},
        ],
        'trainer': [
            {'trainer_id': 1, 'name': 'Meera Joshi', 'specialization': 'Strength', 'shift': 'MORNING', 'phone': '9812345670'},
            {'trainer_id': 2, 'name': 'Karan Bhatia', 'specialization': 'Spin & cardio', 'shift': 'EVENING', 'phone': '9812345671'},
            {'trainer_id': 3, 'name': 'Anjali Desai', 'specialization': 'Yoga & Pilates', 'shift': 'MORNING', 'phone': '9812345672'},
            {'trainer_id': 4, 'name': 'Vikram Singh', 'specialization': 'HIIT', 'shift': 'EVENING', 'phone': '9812345673'},
            {'trainer_id': 5, 'name': 'Neha Kapoor', 'specialization': 'Dance fitness', 'shift': 'EVENING', 'phone': '9812345674'},
            {'trainer_id': 6, 'name': 'Rahul Verma', 'specialization': 'Mobility', 'shift': 'MORNING', 'phone': '9812345675'},
        ],
        'assessment': [
            {'assessment_id': 24, 'member_id': 41, 'trainer_id': 1, 'date': day(-62), 'weight': 61.5, 'bmi': 22.6, 'body_fat': 24.1},
            {'assessment_id': 25, 'member_id': 42, 'trainer_id': 1, 'date': day(-48), 'weight': 78.2, 'bmi': 25.1, 'body_fat': 21.4},
            {'assessment_id': 26, 'member_id': 44, 'trainer_id': 3, 'date': day(-15), 'weight': 55.0, 'bmi': 20.9, 'body_fat': 26.0},
            {'assessment_id': 27, 'member_id': 45, 'trainer_id': 1, 'date': day(-30), 'weight': 84.6, 'bmi': 27.3, 'body_fat': 23.8},
            {'assessment_id': 28, 'member_id': 41, 'trainer_id': 1, 'date': day(-5), 'weight': 60.2, 'bmi': 22.1, 'body_fat': 23.0},
        ],
        'workout': [
            {'programme_id': 11, 'member_id': 41, 'title': 'Strength base', 'goal': 'Muscle gain', 'weeks': 8},
            {'programme_id': 12, 'member_id': 42, 'title': 'Cut phase', 'goal': 'Fat loss', 'weeks': 6},
            {'programme_id': 13, 'member_id': 45, 'title': 'Back to running', 'goal': 'Endurance', 'weeks': 10},
            {'programme_id': 14, 'member_id': 46, 'title': 'Mobility reset', 'goal': 'Flexibility', 'weeks': 4},
        ],
        'class': [
            {'class_id': 1, 'trainer_id': 2, 'title': 'Spin', 'capacity': 15, 'room': 'Studio A'},
            {'class_id': 2, 'trainer_id': 4, 'title': 'HIIT', 'capacity': 15, 'room': 'Studio B'},
            {'class_id': 4, 'trainer_id': 3, 'title': 'Yoga', 'capacity': 20, 'room': 'Studio C'},
            {'class_id': 6, 'trainer_id': 1, 'title': 'Strength', 'capacity': 12, 'room': 'Gym floor'},
            {'class_id': 7, 'trainer_id': 5, 'title': 'Zumba', 'capacity': 25, 'room': 'Studio A'},
            {'class_id': 9, 'trainer_id': 3, 'title': 'Pilates', 'capacity': 12, 'room': 'Studio C'},
        ],
        'schedule': [
            {'schedule_id': 3, 'class_id': 1, 'day': 'MON', 'start_time': '07:00:00', 'end_time': '07:45:00'},
            {'schedule_id': 7, 'class_id': 2, 'day': 'MON', 'start_time': '18:00:00', 'end_time': '18:45:00'},
            {'schedule_id': 11, 'class_id': 4, 'day': 'TUE', 'start_time': '07:00:00', 'end_time': '08:00:00'},
            {'schedule_id': 18, 'class_id': 6, 'day': 'WED', 'start_time': '19:00:00', 'end_time': '20:00:00'},
            {'schedule_id': 21, 'class_id': 7, 'day': 'THU', 'start_time': '18:30:00', 'end_time': '19:30:00'},
            {'schedule_id': 24, 'class_id': 9, 'day': 'SAT', 'start_time': '09:00:00', 'end_time': '10:00:00'},
        ],
        'registration': [
            {'registration_id': 61, 'member_id': 45, 'schedule_id': 3, 'booking_date': day(-6), 'status': 'BOOKED'},
            {'registration_id': 62, 'member_id': 44, 'schedule_id': 11, 'booking_date': day(-5), 'status': 'BOOKED'},
            {'registration_id': 63, 'member_id': 41, 'schedule_id': 7, 'booking_date': day(-4), 'status': 'BOOKED'},
            {'registration_id': 64, 'member_id': 46, 'schedule_id': 3, 'booking_date': day(-3), 'status': 'BOOKED'},
            {'registration_id': 65, 'member_id': 42, 'schedule_id': 3, 'booking_date': day(-2), 'status': 'BOOKED'},
            {'registration_id': 66, 'member_id': 41, 'schedule_id': 11, 'booking_date': day(-2), 'status': 'BOOKED'},
            {'registration_id': 67, 'member_id': 45, 'schedule_id': 7, 'booking_date': day(-1), 'status': 'BOOKED'},
            {'registration_id': 68, 'member_id': 42, 'schedule_id': 11, 'booking_date': day(-1), 'status': 'BOOKED'},
        ],
        'attendance': [
            {'attendance_id': 48, 'registration_id': 61, 'check_in': at(-6, '07:02'), 'check_out': at(-6, '07:48')},
            {'attendance_id': 49, 'registration_id': 62, 'check_in': at(-5, '06:58'), 'check_out': at(-5, '08:01')},
            {'attendance_id': 50, 'registration_id': 63, 'check_in': at(-4, '17:55'), 'check_out': at(-4, '18:47')},
            {'attendance_id': 51, 'registration_id': 64, 'check_in': at(-3, '07:05'), 'check_out': None},
        ],
        'equipment': [
            {'equipment_id': 8, 'name': 'Treadmill T-200', 'category': 'Cardio', 'purchase_date': '2023-04-12', 'status': 'ACTIVE'},
            {'equipment_id': 9, 'name': 'Spin bike #6', 'category': 'Cardio', 'purchase_date': '2022-11-03', 'status': 'OUT_OF_SERVICE'},
            {'equipment_id': 10, 'name': 'Cable crossover', 'category': 'Strength', 'purchase_date': '2024-01-20', 'status': 'ACTIVE'},
            {'equipment_id': 11, 'name': 'Rowing machine', 'category': 'Cardio', 'purchase_date': '2021-08-15', 'status': 'OUT_OF_SERVICE'},
            {'equipment_id': 12, 'name': 'Smith machine', 'category': 'Strength', 'purchase_date': '2024-06-02', 'status': 'ACTIVE'},
        ],
        'maintenance': [
            {'maintenance_id': 15, 'equipment_id': 9, 'date': day(-20), 'cost': 2400},
            {'maintenance_id': 16, 'equipment_id': 11, 'date': day(-14), 'cost': 3800},
            {'maintenance_id': 17, 'equipment_id': 8, 'date': day(-9), 'cost': 1200},
            {'maintenance_id': 18, 'equipment_id': 9, 'date': day(-3), 'cost': 950},
        ],
    }


def setup(reset=False):
    existing = set(db.list_collection_names())
    for key, (coll, pk) in TABLES.items():
        if reset and coll in existing:
            db.drop_collection(coll)
            existing.discard(coll)
        if coll in existing:
            db.command('collMod', coll, validator=VALIDATORS[coll], validationLevel='strict', validationAction='error')
        else:
            db.create_collection(coll, validator=VALIDATORS[coll], validationLevel='strict', validationAction='error')
        c = db[coll]
        c.create_index([(pk, ASCENDING)], unique=True, name=f'pk_{pk}')
        for fields in UNIQUE.get(key, []):
            c.create_index(fields, unique=True, name='uq_' + '_'.join(f for f, _ in fields))
        for f, d in INDEXES.get(key, []):
            c.create_index([(f, d)], name=f'idx_{coll}_{f}')
    if db.member.estimated_document_count() == 0:
        for key, rows in seed_rows().items():
            coll, pk = TABLES[key]
            db[coll].insert_many([{'_id': r[pk], **r} for r in rows])


# ---------- business rules that a single-document validator cannot express ----------
def parent_exists(table, value):
    coll, pk = TABLES[table]
    return db[coll].count_documents({pk: value}, limit=1) > 0


def check_rules(table, row):
    if table == 'subscription':                                         # trg_no_overlap
        if db.subscription.count_documents({'member_id': row['member_id'], 'status': 'ACTIVE',
                                            'start_date': {'$lt': row['end_date']},
                                            'end_date': {'$gt': row['start_date']}}, limit=1):
            return 'Member already has an ACTIVE subscription for these dates'
    if table == 'registration':
        on = row['booking_date']                                         # trg_active_subscription
        if not db.subscription.count_documents({'member_id': row['member_id'], 'status': 'ACTIVE',
                                                'start_date': {'$lte': on}, 'end_date': {'$gte': on}}, limit=1):
            return 'No active subscription for this member'
        sched = db.schedule.find_one({'schedule_id': row['schedule_id']})   # trg_class_capacity
        cls = sched and db['class'].find_one({'class_id': sched['class_id']})
        if cls and db.registration.count_documents({'schedule_id': row['schedule_id'], 'status': {'$ne': 'CANCELLED'}}) >= cls['capacity']:
            return 'Class is full'
    return None


def commit(writes):
    """Insert the rows of one demo COMMIT; undo earlier inserts if a later one fails."""
    done, saved = [], []
    try:
        for w in writes:
            table, row = w['table'], dict(w['row'])
            if table not in TABLES:
                raise ValueError(f'unknown table {table}')
            coll, pk = TABLES[table]
            for col, parent in FKS.get(table, {}).items():
                if row.get(col) is not None and not parent_exists(parent, row[col]):
                    raise ValueError(f'foreign key {col} -> {parent}: no {parent} with {col} = {row[col]}')
            err = check_rules(table, row)
            if err:
                raise ValueError(err)
            db[coll].insert_one({'_id': row[pk], **row})
            done.append((coll, row[pk]))
            saved.append(f'{coll}.{pk} = {row[pk]}')
        return {'ok': True, 'saved': saved}
    except DuplicateKeyError as e:
        msg = 'duplicate key ' + json.dumps((e.details or {}).get('keyValue', {}))
    except WriteError as e:
        msg = 'document failed validation' if e.code == 121 else str(e)
    except (ValueError, PyMongoError) as e:
        msg = str(e)
    for coll, _id in reversed(done):                                     # manual rollback
        db[coll].delete_one({'_id': _id})
    return {'ok': False, 'error': msg}


CHILDREN = {}
for _child, _cols in FKS.items():
    for _col, _parent in _cols.items():
        CHILDREN.setdefault(_parent, []).append((_child, _col))
CASCADE = {'subscription': {'payment', 'renewal'}}   # ON DELETE CASCADE


def update(table, _id, changes):
    """UPDATE ... SET changes WHERE pk = _id (validators and unique indexes still apply)."""
    if table not in TABLES:
        return {'ok': False, 'error': f'unknown table {table}'}
    coll, pk = TABLES[table]
    changes = {k: v for k, v in (changes or {}).items() if k not in (pk, '_id')}
    if not changes:
        return {'ok': False, 'error': 'nothing to update'}
    try:
        current = db[coll].find_one({'_id': _id})
        if not current:
            raise ValueError(f'no {coll} row with {pk} = {_id}')
        for col, parent in FKS.get(table, {}).items():
            if changes.get(col) is not None and not parent_exists(parent, changes[col]):
                raise ValueError(f'foreign key {col} -> {parent}: no {parent} with {col} = {changes[col]}')
        merged = {**current, **changes}
        if table == 'subscription' and merged.get('status') == 'ACTIVE' and db.subscription.count_documents({
                '_id': {'$ne': _id}, 'member_id': merged['member_id'], 'status': 'ACTIVE',
                'start_date': {'$lt': merged['end_date']}, 'end_date': {'$gt': merged['start_date']}}, limit=1):
            raise ValueError('Member already has an ACTIVE subscription for these dates')
        db[coll].update_one({'_id': _id}, {'$set': changes})
        return {'ok': True, 'saved': [f'{coll}.{pk} = {_id} updated ({", ".join(changes)})']}
    except DuplicateKeyError as e:
        return {'ok': False, 'error': 'duplicate key ' + json.dumps((e.details or {}).get('keyValue', {}))}
    except WriteError as e:
        return {'ok': False, 'error': 'document failed validation' if e.code == 121 else str(e)}
    except (ValueError, PyMongoError) as e:
        return {'ok': False, 'error': str(e)}


def delete(table, _id):
    """DELETE ... WHERE pk = _id, with RESTRICT / CASCADE on the foreign keys pointing at it."""
    if table not in TABLES:
        return {'ok': False, 'error': f'unknown table {table}'}
    coll, pk = TABLES[table]
    if not db[coll].count_documents({'_id': _id}, limit=1):
        return {'ok': False, 'error': f'no {coll} row with {pk} = {_id}'}
    for child, col in CHILDREN.get(table, []):
        n = db[TABLES[child][0]].count_documents({col: _id})
        if n and child not in CASCADE.get(table, set()):
            return {'ok': False, 'error': f'cannot delete: {n} {TABLES[child][0]} row(s) still reference it through {col}'}
    removed = []
    for child, col in CHILDREN.get(table, []):
        if child in CASCADE.get(table, set()):
            r = db[TABLES[child][0]].delete_many({col: _id})
            if r.deleted_count:
                removed.append(f'{r.deleted_count} {TABLES[child][0]}')
    db[coll].delete_one({'_id': _id})
    return {'ok': True, 'saved': [f'{coll}.{pk} = {_id} deleted' + (f' (cascade: {", ".join(removed)})' if removed else '')]}


def state():
    return {key: list(db[coll].find({}, {'_id': 0}).sort(pk, 1)) for key, (coll, pk) in TABLES.items()}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        if self.path == '/':
            self.send_response(302)
            self.send_header('Location', '/' + DEMO_PAGE.replace(' ', '%20'))
            self.end_headers()
        elif self.path == '/api/health':
            self.send_json({'ok': True, 'server': client.server_info()['version'], 'db': DB_NAME})
        elif self.path == '/api/state':
            self.send_json(state())
        else:
            super().do_GET()

    def do_POST(self):
        length = int(self.headers.get('Content-Length') or 0)
        payload = json.loads(self.rfile.read(length) or b'{}')
        if self.path == '/api/commit':
            self.send_json(commit(payload.get('writes', [])))
        elif self.path == '/api/update':
            self.send_json(update(payload.get('table'), payload.get('id'), payload.get('set')))
        elif self.path == '/api/delete':
            self.send_json(delete(payload.get('table'), payload.get('id')))
        elif self.path == '/api/reset':
            setup(reset=True)
            self.send_json({'ok': True})
        else:
            self.send_json({'ok': False, 'error': 'not found'}, 404)

    def log_message(self, fmt, *args):
        if '/api/' in (args[0] if args else ''):
            print(self.address_string(), fmt % args)


if __name__ == '__main__':
    setup()
    counts = ', '.join(f'{c}={db[c].estimated_document_count()}' for c, _ in TABLES.values())
    print(f'MongoDB {client.server_info()["version"]} · database {DB_NAME} ready ({counts})')
    url = f'http://127.0.0.1:{PORT}/'
    print(f'Demo: {url}   (Ctrl+C to stop)')
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    if os.environ.get('GYM_NO_BROWSER') != '1':
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
