from manager import Manager
from ogn.collect.database import update_device_infos
from ogn.commands.dbutils import engine, session
from ogn.model import Base, DeviceInfoOrigin, AircraftBeacon, ReceiverBeacon, Device, Receiver
from ogn.utils import get_airports
from sqlalchemy import insert, distinct
from sqlalchemy.sql import null, and_, or_, func, not_


manager = Manager()

ALEMBIC_CONFIG_FILE = "alembic.ini"


@manager.command
def init():
    """Initialize the database."""

    from alembic.config import Config
    from alembic import command

    session.execute('CREATE EXTENSION IF NOT EXISTS postgis;')
    session.commit()
    Base.metadata.create_all(engine)
    alembic_cfg = Config(ALEMBIC_CONFIG_FILE)
    command.stamp(alembic_cfg, "head")
    print("Done.")


@manager.command
def upgrade():
    """Upgrade database to the latest version."""

    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config(ALEMBIC_CONFIG_FILE)
    command.upgrade(alembic_cfg, 'head')


@manager.command
def drop(sure='n'):
    """Drop all tables."""
    if sure == 'y':
        Base.metadata.drop_all(engine)
        print('Dropped all tables.')
    else:
        print("Add argument '--sure y' to drop all tables.")


@manager.command
def import_ddb():
    """Import registered devices from the DDB."""

    print("Import registered devices fom the DDB...")
    address_origin = DeviceInfoOrigin.ogn_ddb
    counter = update_device_infos(session,
                                  address_origin)
    print("Imported %i devices." % counter)


@manager.command
def import_file(path='tests/custom_ddb.txt'):
    """Import registered devices from a local file."""
    # (flushes previously manually imported entries)

    print("Import registered devices from '{}'...".format(path))
    address_origin = DeviceInfoOrigin.user_defined
    counter = update_device_infos(session,
                                  address_origin,
                                  csvfile=path)
    print("Imported %i devices." % counter)


@manager.command
def import_airports(path='tests/SeeYou.cup'):
    """Import airports from a ".cup" file"""

    print("Import airports from '{}'...".format(path))
    airports = get_airports(path)
    session.bulk_save_objects(airports)
    session.commit()
    print("Imported {} airports.".format(len(airports)))


@manager.command
def update_devices():
    """Add/update entries in devices table and update foreign keys in aircraft beacons."""

    # Create missing Device from AircraftBeacon
    available_devices = session.query(Device.address) \
        .subquery()

    missing_devices_query = session.query(distinct(AircraftBeacon.address)) \
        .filter(AircraftBeacon.device_id == null()) \
        .filter(~AircraftBeacon.address.in_(available_devices))

    ins = insert(Device).from_select([Device.address], missing_devices_query)
    res = session.execute(ins)
    insert_count = res.rowcount

    # Update relations to aircraft beacons
    upd = session.query(AircraftBeacon) \
        .filter(AircraftBeacon.device_id == null()) \
        .filter(AircraftBeacon.address == Device.address) \
        .update({AircraftBeacon.device_id: Device.id},
                synchronize_session='fetch')

    session.commit()
    print("Inserted {} Devices".format(insert_count))
    print("Updated {} AircraftBeacons".format(upd))


@manager.command
def update_receivers():
    """Add/update entries in receiver table and update foreign keys in aircraft beacons and receiver beacons."""
    # Create missing Receiver from ReceiverBeacon
    available_receivers = session.query(Receiver.name) \
        .subquery()

    missing_receiver_query = session.query(distinct(ReceiverBeacon.name)) \
        .filter(ReceiverBeacon.receiver_id == null()) \
        .filter(~ReceiverBeacon.name.in_(available_receivers))

    ins = insert(Receiver).from_select([Receiver.name], missing_receiver_query)
    res = session.execute(ins)
    insert_count = res.rowcount

    # Update missing or changed location, update it and set country code to None
    last_beacon_update = session.query(ReceiverBeacon.name, func.max(ReceiverBeacon.timestamp).label("timestamp")) \
        .filter(ReceiverBeacon.receiver_id == null()) \
        .group_by(ReceiverBeacon.name) \
        .subquery()

    last_position = session.query(ReceiverBeacon) \
        .filter(and_(ReceiverBeacon.name == last_beacon_update.c.name, ReceiverBeacon.timestamp == last_beacon_update.c.timestamp,
                     ReceiverBeacon.location_wkt != null(), ReceiverBeacon.altitude != null())) \
        .subquery()

    location_changed = session.query(last_position) \
        .filter(and_(last_position.c.name == Receiver.name)) \
        .filter(or_(Receiver.location_wkt == null(), not_(func.ST_Equals(Receiver.location_wkt, last_position.columns.location)), last_position.c.altitude != Receiver.altitude)) \
        .subquery()

    upd = session.query(Receiver) \
        .filter(Receiver.name == location_changed.c.name) \
        .update({Receiver.location_wkt: location_changed.c.location,
                 Receiver.altitude: location_changed.c.altitude,
                 Receiver.country_code: None},
                synchronize_session='fetch')

    # Update missing or changed status
    last_status = session.query(ReceiverBeacon) \
        .filter(and_(ReceiverBeacon.name == last_beacon_update.columns.name, ReceiverBeacon.timestamp == last_beacon_update.c.timestamp,
                     ReceiverBeacon.version != null(), ReceiverBeacon.platform != null())) \
        .subquery()

    status_changed = session.query(last_status) \
        .filter(and_(last_status.columns.name == Receiver.name)) \
        .filter(or_(Receiver.version == null(), Receiver.platform == null(), Receiver.version != last_status.columns.version)) \
        .subquery()

    upd2 = session.query(Receiver) \
        .filter(Receiver.name == status_changed.columns.name) \
        .update({Receiver.version: status_changed.c.version,
                 Receiver.platform: status_changed.c.platform},
                synchronize_session='fetch')

    # Update relations to aircraft beacons
    upd3 = session.query(AircraftBeacon) \
        .filter(and_(AircraftBeacon.receiver_id == null(), AircraftBeacon.receiver_name == Receiver.name)) \
        .update({AircraftBeacon.receiver_id: Receiver.id},
                synchronize_session='fetch')

    # Update relations to receiver beacons
    upd4 = session.query(ReceiverBeacon) \
        .filter(and_(ReceiverBeacon.receiver_id == null(), ReceiverBeacon.name == Receiver.name)) \
        .update({ReceiverBeacon.receiver_id: Receiver.id},
                synchronize_session='fetch')

    session.commit()

    print("Inserted {} Receivers".format(insert_count))
    print("Updated Receivers: {} positions, {} status".format(upd, upd2))
    print("Updated Relations: {} aircraft beacons, {} receiver beacons".format(upd3, upd4))
    return
