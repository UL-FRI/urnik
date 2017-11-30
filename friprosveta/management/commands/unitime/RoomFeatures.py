from timetable.models import Resource
from common import Database, PreferenceLevel, toStartIndex, level_to_type


def roomFeatures(tt):
    """
    Insert global room features in unitime.
    """
    db = Database()

    next_id = db.getNextID()
    session_id = db.getSessionID(tt.start)

    for resource in Resource.objects.all():
        name = resource.name[:20]
        id = name.replace(" ", "_")
        feature_id_query = u"SELECT uniqueid FROM room_feature WHERE label='{0}'".format(name)
        db.execute(feature_id_query)

        if db.rowcount > 0:
            for feature_id in db.fetchallrows():
                feature_id = feature_id[0]
                delete_query = u"""DELETE FROM room_join_room_feature WHERE feature_id={0}
                        """.format(feature_id)
                db.execute(delete_query)
            delete_query = u"DELETE FROM room_feature WHERE label='{0}'".format(name)
            db.execute(delete_query)

        insert_query = u"""INSERT INTO room_feature (uniqueid, discriminator, label,
                        sis_reference, sis_value, department_id,
                        abbv, session_id) VALUES ({0}, 'global', '{1}', '{2}',
                        NULL, NULL, '{3}', {4})
                        """.format(next_id, name, id, id[:10], session_id)
        db.execute(insert_query)
        db.commit()

        for classroom in resource.classrooms.all():
            room_id_query = u"SELECT uniqueid FROM room WHERE external_uid='{0}'".format(classroom.id)
            db.execute(room_id_query)

            if db.rowcount == 0:
                continue
            room_id = db.fetchnextrow()[0]

            insert_query = u"""INSERT INTO room_join_room_feature 
            (room_id, feature_id)  VALUES
            ({0}, {1})""".format(room_id, next_id)
            db.execute(insert_query)
        next_id = db.getNextID()

    db.commit()
    db.close()
