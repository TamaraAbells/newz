import random
import string

from orator.migrations import Migration
from passlib.handlers.bcrypt import bcrypt


class PopulateDb(Migration):

    def up(self):
        """
        Run the migrations.
        """
        self.db.table('users').insert(
            {'username': 'autoposter',
             'password': bcrypt.hash(''.join(random.choices(string.ascii_uppercase + string.digits, k=32))), 'id': 12345,
             'email': 'autoposter'}
        )
        self.db.table('users').insert(
            {'username': 'admin',
             'password': bcrypt.hash(''.join(random.choices(string.ascii_uppercase + string.digits, k=32))),
             'email': 'admin@esourcenews.com'}
        )

    def down(self):
        """
        Revert the migrations.
        """
        self.db.table('users').where('id', '=', 12345).delete()
        self.db.table('users').where('username', '=', 'admin').delete()
