from django_auth_ldap.config import NestedGroupOfNamesType


class ULNestedGroupOfNamesType(NestedGroupOfNamesType):

    def __init__(self, name_attr='cn'):
        super(ULNestedGroupOfNamesType, self).__init__(name_attr)

    def group_name_from_info(self, group_info):
        """
        Given the (DN, attrs) 2-tuple of an LDAP group, this returns the name of
        the Django group. This may return None to indicate that a particular
        LDAP group has no corresponding Django group.

        The base implementation returns the value of the cn attribute, or
        whichever attribute was given to __init__ in the name_attr
        parameter.
        """
        try:
            dn = group_info[0]
            university = dn.split(',')[-3][3:]
            name = university + '_' + group_info[1][self.name_attr][0]
        except (KeyError, IndexError):
            name = None

        return name
