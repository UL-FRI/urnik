from django.test import TestCase
from friprosveta.studis import Studij
from friprosveta.management.commands.import_studis_students import get_parents

from friprosveta.models import GroupSizeHint

from model_mommy import mommy


# class Test(TestCase):
#     def test_import_studis_students_get_parents(self):
#         studij = Studij(2018)
#         studijsko_drevo = {e['id']: e for e in studij.get_studijsko_drevo()}
#         entries = [16286, 16266, 16289, 834352532528]
#         results = [set(e['id'] for e in get_parents(studijsko_drevo, entry_id).values())
#                    for entry_id in entries]
#         expected_output = [set([16286, 1228, 2366, 1063, 35]),
#                            set([16266, 1281, 2481, 1141, 36]),
#                            set([16289, 1321, 2541, 1201]),
#                            set()]
#         self.assertEqual(results, expected_output, "Parent from studijsko drevo are wrong")


class GroupSizeHintTest(TestCase):

    def setUp(self):
        TestCase.setUp(self)
        # Create group and some hints for it
        self.g1, self.g2 = mommy.make('timetable.Group', size=20), mommy.make('timetable.Group', size=5)
        methods1 = [('1', 0), ('2', 10), ('3', 12)]
        methods2 = [('1', 0), ('2', 0), ('3', 0)]
        for method_name, size in methods1:
            mommy.make('friprosveta.GroupSizeHint', group=self.g1, size=size, method=method_name)
        for method_name, size in methods2:
            mommy.make('friprosveta.GroupSizeHint', group=self.g2, size=size, method=method_name)

    def test_group_size_hint_incorrect_strategy(self):
        with self.assertRaises(KeyError):
            GroupSizeHint.strategy(self.g1, ["unknown"], 'Weird strategy name')

    def test_group_size_hint_first(self):
        strategy = 'first'

        methods = ['1', '2']
        expected = 0
        val = GroupSizeHint.strategy(self.g1, methods, strategy)
        self.assertEqual(val, expected,
                         "Strategy '{}' for {} and methods {} should return {}".format(strategy, self.g1,
                                                                                       methods, expected))

        methods = ['2', '3']
        expected = 10
        val = GroupSizeHint.strategy(self.g1, methods, strategy)
        self.assertEqual(val, expected,
                         "Strategy '{}' for {} and methods {} should return {}".format(strategy, self.g1,
                                                                                       methods, expected))

        val = GroupSizeHint.strategy(self.g1, ['non', 'existing'], strategy)
        self.assertIsNone(val, "If no hints are available None should be returned")

    def test_group_size_hint_first_not_zero(self):
        strategy = 'first-non-zero'

        methods = ['1', '2', '3']
        expected = 10
        val = GroupSizeHint.strategy(self.g1, methods, strategy)
        self.assertEqual(val, expected,
                         "Strategy '{}' for {} and methods {} should return {}".format(strategy, self.g1, methods,
                                                                                       expected))

        methods = ['1', '2', '3']
        val = GroupSizeHint.strategy(self.g2, methods, strategy)
        self.assertIsNone(val, "If no hints are available None should be returned")

    def test_group_size_hint_max(self):
        strategy = 'max'

        methods = ['1', '2', '3']
        expected = 12
        val = GroupSizeHint.strategy(self.g1, methods, strategy)
        self.assertEqual(val, expected,
                         "Strategy '{}' for {} and methods {} should return {}".format(strategy, self.g1, methods,
                                                                                       expected))

        val = GroupSizeHint.strategy(self.g1, ['non', 'existing'], strategy)
        self.assertIsNone(val, "If no hints are available None should be returned")

        methods = ['1', '2', '3']
        expected = 0
        val = GroupSizeHint.strategy(self.g2, methods, strategy)
        self.assertEqual(val, expected,
                         "Strategy '{}' for {} and methods {} should return {}".format(strategy, self.g2,
                                                                                       methods, expected,))

    def test_group_size_hint_max_not_zero(self):
        strategy = 'max-non-zero'

        methods = ['1', '2', '3']
        expected = 12
        val = GroupSizeHint.strategy(self.g1, methods, strategy)
        self.assertEqual(val, expected,
                         "Strategy '{}' for {} and methods {} should return {}".format(strategy, self.g1, methods,
                                                                                       expected))

        methods = ['1', '2', '3']
        val = GroupSizeHint.strategy(self.g2, methods, strategy)
        self.assertIsNone(val, "If no hints are available None should be returned")

    def test_group_size_hint_max_group(self):
        strategy = 'max-group'

        methods = ['1', '2', '3']
        expected = 20
        val = GroupSizeHint.strategy(self.g1, methods, strategy)
        self.assertEqual(val, expected,
                         "Strategy '{}' for {} and methods {} should return {}".format(strategy, self.g1, methods,
                                                                                       expected))

        val = GroupSizeHint.strategy(self.g1, ['non', 'existing'], strategy)
        self.assertIsNone(val, "If no hints are available None should be returned")

        methods = ['1', '2', '3']
        expected = max(0, self.g2.size)
        val = GroupSizeHint.strategy(self.g2, methods, strategy)
        self.assertEqual(val, expected,
                         "Strategy '{}' for {} and methods {} should return {}".format(strategy, self.g2, methods,
                                                                                       expected))
