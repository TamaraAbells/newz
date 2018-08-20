import pysolr as pysolr
from flask import current_app
from rq.decorators import job

from news.lib.task_queue import redis_conn


class Solr:
    def __init__(self, app=None):
        self._config = None
        self.linksolr = None
        self.usersolr = None
        self.feedsolr = None
        self.logger = None

        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        if 'SOLR' not in app.config:
            raise RuntimeError('Missing "SOLR" configuration')

        self._config = app.config['SOLR']
        self.linksolr = pysolr.Solr(self._config['URL'] + '/links', timeout=10)
        self.usersolr = pysolr.Solr(self._config['URL'] + '/users', timeout=10)
        self.feedsolr = pysolr.Solr(self._config['URL'] + '/feeds', timeout=10)


        self.logger = app.logger

    def search_links(self, q, options=None):
        if options is None:
            options = {
                'hl.fl': '*',
                'hl': 'on',
                'hl.snippets': 1,
                'hl.fragsize': 0,
            }
        return self.linksolr.search('text:{} title:{}'.format(q, q), **options)

    def search_feeds(self, q, options=None):
        if options is None:
            options = {
                'hl.fl': '*',
                'hl': 'on',
                'hl.snippets': 1,
                'hl.fragsize': 0,
            }
        return self.feedsolr.search('name:{} description:{}'.format(q, q), **options)

    def update_link_score(self, link):
        doc = {'id': link.id, 'ups': link.ups, 'downs': link.downs}
        self.linksolr.add([doc], fieldUpdates={'ups': 'set', 'downs': 'set'})


solr = Solr()


@job('medium', connection=redis_conn)
def new_link_queue(link):
    if not current_app.config['SOLR_DISABLED']:
        solr.logger.info('Adding new link to solr: {}'.format(link.title))
        solr.linksolr.add([link.to_solr()])
    return None


@job('medium', connection=redis_conn)
def new_user_queue(user):
    if not current_app.config['SOLR_DISABLED']:
        solr.logger.info('Adding new user to solr: {}'.format(user.username))
        solr.usersolr.add([user.to_solr()])
    return None


def add_feed_to_search(feed):
    if not current_app.config['SOLR_DISABLED']:
        solr.logger.info('Adding new feed to solr: {}'.format(feed.name))
        solr.feedsolr.add([feed.to_solr()])
    return None
