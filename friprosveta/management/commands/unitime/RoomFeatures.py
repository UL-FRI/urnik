from timetable.models import Resource
from .common import Database


def room_features(tt):
    """
    Insert global room features in unitime.
    """
    db = Database()

    next_id = db.get_next_id()
    session_id = db.get_session_id(tt.start)

    for resource in Resource.objects.all():
        name = resource.name[:20]
        id = name.replace(" ", "_")
        feature_id_query = "SELECT uniqueid FROM room_feature WHERE label='{0}'".format(name)
        db.execute(feature_id_query)

        if db.rowcount > 0:
            for feature_id in db.fetch_all_rows():
                feature_id = feature_id[0]
                delete_query = """DELETE FROM room_join_room_feature WHERE feature_id={0}
                        """.format(feature_id)
                db.execute(delete_query)
            delete_query = "DELETE FROM room_feature WHERE label='{0}'".format(name)
            db.execute(delete_query)

        insert_query = """INSERT INTO room_feature (uniqueid, discriminator, label,
                        sis_reference, sis_value, department_id,
                        abbv, session_id) VALUES ({0}, 'global', '{1}', '{2}',
                        NULL, NULL, '{3}', {4})
                        """.format(next_id, name, id, id[:10], session_id)
        db.execute(insert_query)
        db.commit()

        for classroom in resource.classrooms.all():
            room_id_query = "SELECT uniqueid FROM room WHERE external_uid='{0}'".format(classroom.id)
            db.execute(room_id_query)

            if db.rowcount == 0:
                continue
            room_id = db.fetch_next_row()[0]

            insert_query = """INSERT INTO room_join_room_feature 
            (room_id, feature_id)  VALUES
            ({0}, {1})""".format(room_id, next_id)
            db.execute(insert_query)
        next_id = db.get_next_id()

    db.commit()
    db.close()
