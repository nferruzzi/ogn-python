from datetime import datetime, timedelta, date

from flask import Flask
from flask import Response

from ogn.db import session

from sqlalchemy import func, and_, case, between
from ogn.model import ReceiverBeacon
from ogn.model import AircraftBeacon
from ogn.model import Flarm

from flask import request

app = Flask(__name__)


@app.route("/rec.php")
def index():
    sq = session.query(ReceiverBeacon.name, func.max(ReceiverBeacon.timestamp).label('lastseen')) \
        .group_by(ReceiverBeacon.name) \
        .subquery()

    last_10_minutes = datetime.utcnow() - timedelta(minutes=10)
    receiver_query = session.query(ReceiverBeacon.name, ReceiverBeacon.latitude, ReceiverBeacon.longitude, case([(sq.c.lastseen>last_10_minutes, True)], else_=False).label('is_online')) \
        .filter(and_(ReceiverBeacon.name == sq.c.name, ReceiverBeacon.timestamp == sq.c.lastseen)) \
        .order_by(ReceiverBeacon.name)

    lines = list()
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<markers>')
    lines.append('<m e="0"/>')
    for [name, latitude, longitude, is_online] in receiver_query.all():
        lines.append('<m a="{0}" b="{1:.7f}" c="{2:.7f}" d="{3:1d}"/>'.format(name, latitude, longitude, is_online))

    lines.append('</markers>')
    xml = '\n'.join(lines)
    return Response(xml, mimetype='text/xml')


@app.route('/lxml.php', methods=['GET', 'POST'])
def live():
    show_offline = request.args.get('a', False)
    lat_max = request.args.get('b', 90)
    lat_min = request.args.get('c', -90)
    lon_max = request.args.get('d', 180)
    lon_min = request.args.get('e', -180)

    if show_offline:
        start_observation = date.today()
    else:
        start_observation = datetime.utcnow - timedelta(minutes=5)

    sq = session.query(AircraftBeacon.address, func.max(AircraftBeacon.timestamp).label('lastseen')) \
        .filter(and_(between(AircraftBeacon.latitude, lat_max, lat_min), between(AircraftBeacon.longitude, lon_max, lon_min))) \
        .filter(AircraftBeacon.timestamp > start_observation) \
        .group_by(AircraftBeacon.address) \
        .subquery()

    position_query = session.query(AircraftBeacon, Flarm) \
        .outerjoin(Flarm, AircraftBeacon.address == Flarm.address) \
        .filter(and_(AircraftBeacon.address == sq.c.address, AircraftBeacon.timestamp == sq.c.lastseen))

    lines = list()
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<markers>')

    hashcode = '4711abcd'
    flarm_competition = lambda flarm_object: '_' + hashcode[6:7] if flarm_object is None else flarm_object.competition
    flarm_registration = lambda flarm_object: hashcode if flarm_object is None else flarm_object.registration
    flarm_address = lambda flarm_object: 0 if flarm_object is None else flarm_object.address
    for [ab, flarm] in position_query.all():
        lines.append('<m a="{0:.7f},{1:.7f},{2},{3},{4},{5},{6},{7},{8},{9},{10},{11},{12}"/>'.format(ab.latitude, ab.longitude, flarm_competition(flarm), flarm_registration(flarm), ab.altitude, ab.timestamp, ab.track, ab.ground_speed, ab.climb_rate, ab.aircraft_type, ab.receiver_name, flarm_address(flarm), flarm_registration(flarm)))

    lines.append('</markers>')
    xml = '\n'.join(lines)
    return Response(xml, mimetype='text/xml')


if __name__ == "__main__":
    app.run(debug=True)
