from .common import Database


def subjectRequirements(tt):
    """
    Add room preferences to each subpart.
    """
    # itype on scheduling_subpart gre na tabelo itype_desc
    # Lab 30
    # Lec 10
    # Rec 20
    type_itype_mapping = {'P': 10, 'LV': 30, 'AV': 20}
    db = Database()
    next_id = db.get_next_id()

    for subject in tt.subjects:
        # Now get all subparts ids connected with this subject
        for activity in subject.activities.filter(activityset=tt.activityset):
            itype = type_itype_mapping[activity.type]
            query = """SELECT ss.uniqueid FROM scheduling_subpart AS ss JOIN 
            instr_offering_config AS ioc ON (ss.config_id=ioc.uniqueid)
            JOIN course_offering AS co ON (co.instr_offr_id=ioc.instr_offr_id)
            WHERE co.external_uid={0} AND ss.itype={1}""".format(subject.id, itype)
            db.execute(query)
            if db.rowcount != 1:
                print("There should be exactly one sheduling subpart for activity {0}".format(activity))
                continue
            # assert db.rowcount == 1, "There should be exactly one sheduling subpart for activity {0}".format(activity)
            subpart_id = db.fetch_next_row()[0]
            if subpart_id is None:
                continue

            # delete_query = "DELETE FROM room_feature_pref WHERE owner_id={0}".format(subpart_id)
            # db.execute(delete_query)
            # Do NOT delete old preferences, just add missing ones
            query = "SELECT room_feature_id FROM room_feature_pref WHERE owner_id={0}".format(subpart_id)
            db.execute(query)
            feature_ids = [fid[0] for fid in db.fetch_all_rows()]

            for requirement in activity.requirements.all():
                name = requirement.name[:20]
                feature_id_query = "SELECT uniqueid FROM room_feature WHERE label='{0}'".format(name)
                db.execute(feature_id_query)
                if db.rowcount == 0:
                    continue
                assert db.rowcount == 1, "There should be exactly one preference for {0}".format(name)
                feature_id = db.fetch_next_row()[0]
                if feature_id not in feature_ids:
                    # print "Inserting feature", activity.name
                    query = """INSERT room_feature_pref (uniqueid,
                            owner_id, pref_level_id, room_feature_id, last_modified_time)
                            VALUES ({0}, {1}, 1, {2}, NULL)
                            """.format(next_id, subpart_id, feature_id, )
                    db.execute(query)
                next_id = db.get_next_id()
    db.commit()
    db.close()
