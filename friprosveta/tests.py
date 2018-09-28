from django.test import TestCase
from friprosveta.studis import Studij
from friprosveta.management.commands.import_studis_students import get_parents


class Test(TestCase):
    def test_import_studis_students_get_parents(self):
        studij = Studij(2018)
        studijsko_drevo = {e['id']: e for e in studij.get_studijsko_drevo()}
        entries = [16286, 16266, 16289, 834352532528]
        results = [set(e['id'] for e in get_parents(studijsko_drevo, entry_id).values())
                   for entry_id in entries]
        expected_output = [set([16286, 1228, 2366, 1063, 35]),
                           set([16266, 1281, 2481, 1141, 36]),
                           set([16289, 1321, 2541, 1201]),
                           set()]
        self.assertEqual(results, expected_output, "Parent from studijsko drevo are wrong")
