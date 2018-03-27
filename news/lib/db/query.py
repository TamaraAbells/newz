from redis_lock import Lock
from rq.decorators import job

from news.lib.cache import cache, conn
from news.lib.db.sorts import sorts
from news.lib.queue import redis_conn
from news.lib.sorts import sort_tuples
from news.lib.utils.time_utils import epoch_seconds

PRECOMPUTE_LIMIT = 1000


def tuple_maker(sort):
    if sort == 'new':
        return lambda x: (x.id, epoch_seconds(x.created_at))
    if sort == 'best':
        return lambda x: (x.id, x.score, epoch_seconds(x.created_at))
    return lambda x: (x.id, x.hot) # default to trending


class LinkQuery():
    def __init__(self, feed_id, sort, time='all'):
        self.feed_id = feed_id
        self.sort = sort
        self.time = time
        self._tupler = tuple_maker(sort)
        self._fetched = False
        self._data = None

    def __iter__(self):
        self.fetch()

        for x in self._data:
            yield x[0]

    def __repr__(self):
        return '<CachedQuery %s %s>' % (self.feed_id, self.sort)

    @property
    def _cache_key(self):
        return "query:{}.{}.{}".format(self.feed_id, self.sort, self.time)

    @property
    def _lock_key(self):
        return "lock:q:{}.{}.{}".format(self.feed_id, self.sort, self.time)

    def _save(self):
        assert self._fetched
        cache.set(self._cache_key, self._data)

    def _rebuild(self):
        from news.models.link import Link
        q = Link.where('feed_id', self.feed_id).order_by_raw(sorts[self.sort]).limit(1000)

        # cache needs array of objects, not a orator collection
        res = [self._tupler(l) for l in q.get()]
        self._data = sort_tuples(res)
        self._fetched = True
        self._save()

    def delete(self, links):
        with Lock(conn, self._lock_key):
            # fetch fresh data from cache
            data = cache.get(self._cache_key) or []
            lids = set(x.id for x in links)

            data = filter(lambda x: x[0] not in lids, data)
            self._data = data
            self._fetched = True
            self._save()
        return True

    def insert(self, links):
        # read - write - modify
        with Lock(conn, self._lock_key):
            data = cache.get(self._cache_key) or []
            item_tuples = [self._tupler(link) for link in links] or []

            existing_fnames = {item[0] for item in data}
            new_fnames = {item[0] for item in item_tuples}

            mutated_length = len(existing_fnames.union(new_fnames))
            would_truncate = mutated_length >= PRECOMPUTE_LIMIT
            if would_truncate and data:
                # only insert items that are already stored or new items
                # that are large enough that they won't be immediately truncated
                # out of storage
                # item structure is (name, sortval1[, sortval2, ...])
                smallest = data[-1]
                item_tuples = [item for item in item_tuples
                               if (item[0] in existing_fnames or
                                   item[1:] >= smallest[1:])]

            if not item_tuples:
                # nothing changes
                return self._data

            # insert the items, remove the duplicates (keeping the
            # one being inserted over the stored value if applicable),
            # and sort the result
            data = [x for x in data if x[0] not in new_fnames]
            data.extend(item_tuples)
            data.sort(reverse=True, key=lambda x: x[1:])
            if len(data) > PRECOMPUTE_LIMIT:
                data = data[:PRECOMPUTE_LIMIT]
            self._data = data
            self._fetched = True
            self._save()
        return True

    def fetch(self):
        self._data = cache.get(self._cache_key)

        if self._data is None:
            self._rebuild()

        self._fetched = True
        return self._data

    def fetch_ids(self):
        self._data = cache.get(self._cache_key)

        if self._data is None:
            self._rebuild()

        self._fetched = True
        return [r[0] for r in self._data]


@job('medium', connection=redis_conn)
def add_to_queries(link):
    for sort in ['trending', 'best', 'new']:  # no need to update 'new' because it doesn't depend on score
        q = LinkQuery(feed_id=link.feed_id, sort=sort)
        q.insert([link])
    return None
